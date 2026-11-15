#include "common.h"
#include "face_probe.h"
#include "styler.h"
#include <ocidl.h>
#include <wrl/client.h>
#include <atomic>
#include <mutex>
#include <new>

using Microsoft::WRL::ComPtr;
namespace {
std::atomic<long> objects{0};
std::atomic<bool> discovering{false};

class Tap final : public IObjectWithSite, public IVisualTreeServiceCallback2 {
    std::atomic<ULONG> refs{1};
    ComPtr<IUnknown> site;
    ComPtr<IVisualTreeService> tree;
    std::mutex gate;
    keyboard::Report report;
    HMODULE pin = nullptr;
    bool faceProbe = false;
    bool styling = false;
    std::wstring session;
    ULONGLONG observeUntil = 0;
    ComPtr<IXamlDiagnostics> diagnostics;

    bool Send(HANDLE pipe) noexcept {
        Handle done(CreateEventW(nullptr, TRUE, FALSE, nullptr));
        OVERLAPPED operation{}; operation.hEvent = done.value;
        DWORD written = 0;
        keyboard::Report snapshot;
        { std::lock_guard lock(gate); snapshot = report; }
        if (faceProbe) keyboard::ReadFaceProbe(snapshot);
        if (styling) keyboard::ReadStyleSession(snapshot);
        if (WriteFile(pipe, &snapshot, sizeof(snapshot), &written, &operation)) return written == sizeof(snapshot);
        if (GetLastError() != ERROR_IO_PENDING) return false;
        const bool completed = WaitForSingleObject(done.value, 1000) == WAIT_OBJECT_0;
        if (!completed) CancelIoEx(pipe, &operation);
        return GetOverlappedResult(pipe, &operation, &written, TRUE) && completed && written == sizeof(snapshot);
    }
    bool Command(HANDLE pipe, BYTE& command) noexcept {
        Handle done(CreateEventW(nullptr, TRUE, FALSE, nullptr));
        OVERLAPPED operation{}; operation.hEvent = done.value;
        DWORD received = 0;
        if (ReadFile(pipe, &command, 1, &received, &operation)) return received == 1;
        if (GetLastError() != ERROR_IO_PENDING) return false;
        const bool completed = WaitForSingleObject(done.value, 3000) == WAIT_OBJECT_0;
        if (!completed) CancelIoEx(pipe, &operation);
        return GetOverlappedResult(pipe, &operation, &received, TRUE) && completed && received == 1;
    }
    static DWORD WINAPI Collect(void* context) noexcept {
        auto self = static_cast<Tap*>(context);
        const auto com = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        self->observeUntil = GetTickCount64() + 2000;
        self->report.subscribeResult = self->tree->AdviseVisualTreeChange(self);
        if (self->styling) {
            Handle pipe(CreateFileW(PipeName(GetCurrentProcessId(), self->session).c_str(), GENERIC_READ | GENERIC_WRITE,
                0, nullptr, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, nullptr));
            bool connected = static_cast<bool>(pipe);
            if (SUCCEEDED(self->report.subscribeResult)) {
                while (connected) {
                    BYTE command = 0;
                    if (!self->Command(pipe.value, command) || command != 1) break;
                    keyboard::RenewStyleLease();
                    connected = self->Send(pipe.value);
                    keyboard::Report state;
                    keyboard::ReadStyleSession(state);
                    if (state.phase == keyboard::StylePhase::Failed) break;
                }
            }
            keyboard::StopStyleSession();
            const auto deadline = GetTickCount64() + 4000;
            keyboard::Report state;
            do {
                Sleep(100); keyboard::ReadStyleSession(state);
            } while (state.phase != keyboard::StylePhase::Idle && GetTickCount64() < deadline);
            if (SUCCEEDED(self->report.subscribeResult))
                self->report.unsubscribeResult = self->tree->UnadviseVisualTreeChange(self);
            if (connected) self->Send(pipe.value);
        } else {
            if (SUCCEEDED(self->report.subscribeResult)) {
                Sleep(self->faceProbe ? 11000 : 3000);
                self->report.unsubscribeResult = self->tree->UnadviseVisualTreeChange(self);
            }
            Handle pipe(CreateFileW(PipeName(GetCurrentProcessId(), self->session).c_str(), GENERIC_WRITE, 0,
                nullptr, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, nullptr));
            if (pipe) self->Send(pipe.value);
        }
        const bool detached = SUCCEEDED(self->report.unsubscribeResult);
        HMODULE pin = self->pin;
        if (detached) {
            self->diagnostics.Reset(); self->tree.Reset(); self->site.Reset();
            discovering = false; self->Release();
        }
        if (SUCCEEDED(com)) CoUninitialize();
        if (detached) FreeLibraryAndExitThread(pin, 0);
        return 0;
    }

public:
    explicit Tap(bool probe, bool style) : faceProbe(probe), styling(style) { ++objects; }
    ~Tap() { --objects; }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (iid == IID_IUnknown || iid == IID_IObjectWithSite) *out = static_cast<IObjectWithSite*>(this);
        else if (iid == __uuidof(IVisualTreeServiceCallback) || iid == __uuidof(IVisualTreeServiceCallback2))
            *out = static_cast<IVisualTreeServiceCallback2*>(this);
        else return E_NOINTERFACE;
        AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++refs; }
    ULONG STDMETHODCALLTYPE Release() override {
        auto remaining = --refs; if (!remaining) delete this; return remaining;
    }
    HRESULT STDMETHODCALLTYPE SetSite(IUnknown* value) override {
        if (!value) return S_OK;
        if (discovering.exchange(true)) return HRESULT_FROM_WIN32(ERROR_BUSY);
        if (faceProbe && !keyboard::BeginFaceProbe()) { discovering = false; return HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS); }
        { std::lock_guard lock(gate); report = {}; }
        auto hr = value->QueryInterface(IID_PPV_ARGS(&tree));
        if (FAILED(hr)) { discovering = false; return hr; }
        {
            hr = value->QueryInterface(IID_PPV_ARGS(&diagnostics));
            if (FAILED(hr)) { discovering = false; return hr; }
        }
        BSTR data = nullptr;
        hr = diagnostics->GetInitializationData(&data);
        if (SUCCEEDED(hr) && data) {
            const auto length = SysStringLen(data);
            if (length != 37 || data[0] != L'.') hr = E_INVALIDARG;
            for (UINT i = 1; SUCCEEDED(hr) && i < length; ++i)
                if (!iswxdigit(data[i]) && data[i] != L'-') hr = E_INVALIDARG;
            if (SUCCEEDED(hr)) session.assign(data, length);
        }
        SysFreeString(data);
        if (FAILED(hr) || session.empty()) { discovering = false; return E_INVALIDARG; }
        if (styling && !keyboard::BeginStyleSession()) { discovering = false; return HRESULT_FROM_WIN32(ERROR_BUSY); }
        site = value;
        if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,
                               reinterpret_cast<LPCWSTR>(&KeyboardTapId), &pin)) {
            if (styling) keyboard::StopStyleSession();
            discovering = false; return HRESULT_FROM_WIN32(GetLastError());
        }
        AddRef();
        Handle worker(CreateThread(nullptr, 0, Collect, this, 0, nullptr));
        if (!worker) {
            hr = HRESULT_FROM_WIN32(GetLastError());
            if (styling) keyboard::StopStyleSession();
            Release(); FreeLibrary(pin); discovering = false; return hr;
        }
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetSite(REFIID iid, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        return site ? site->QueryInterface(iid, out) : E_NOINTERFACE;
    }
    HRESULT STDMETHODCALLTYPE OnVisualTreeChange(ParentChildRelation relation, VisualElement element,
                                                  VisualMutationType mutation) override {
        if (mutation != Add || !element.Type) return S_OK;
        if (faceProbe && GetTickCount64() < observeUntil &&
            wcscmp(element.Type, L"Windows.UI.Xaml.Controls.Border") == 0)
            keyboard::ObserveFace(diagnostics.Get(), element.Handle);
        if (styling && wcscmp(element.Type, L"WindowsInternal.ComposableShell.Experiences.TextInputUndocked.Controls.KeyboardKey") == 0)
            keyboard::ObserveStyle(diagnostics.Get(), element.Handle);
        keyboard::Node node{};
        node.id = element.Handle;
        node.parent = relation.Parent;
        std::size_t i = 0;
        for (; i < keyboard::TypeLength - 1 && element.Type[i]; ++i) {
            const wchar_t c = element.Type[i];
            if (c > 127 || !keyboard::TypeCharacter(static_cast<char>(c))) return S_OK;
            node.type[i] = static_cast<char>(c);
        }
        if (!i || element.Type[i]) return S_OK;
        std::lock_guard lock(gate);
        if (report.count < keyboard::MaxNodes) report.nodes[report.count++] = node;
        else report.truncated = 1;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE OnElementStateChanged(InstanceHandle, VisualElementState, LPCWSTR) override {
        return S_OK;
    }
};
class Factory final : public IClassFactory {
    std::atomic<ULONG> refs{1};
    bool faceProbe, styling;
public:
    explicit Factory(bool probe, bool style) : faceProbe(probe), styling(style) { ++objects; }
    ~Factory() { --objects; }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (iid != IID_IUnknown && iid != IID_IClassFactory) return E_NOINTERFACE;
        *out = static_cast<IClassFactory*>(this); AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++refs; }
    ULONG STDMETHODCALLTYPE Release() override { auto n = --refs; if (!n) delete this; return n; }
    HRESULT STDMETHODCALLTYPE CreateInstance(IUnknown* outer, REFIID iid, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (outer) return CLASS_E_NOAGGREGATION;
        auto tap = new(std::nothrow) Tap(faceProbe, styling);
        if (!tap) return E_OUTOFMEMORY;
        auto hr = tap->QueryInterface(iid, out); tap->Release(); return hr;
    }
    HRESULT STDMETHODCALLTYPE LockServer(BOOL lock) override { if (lock) ++objects; else --objects; return S_OK; }
};
}
STDAPI DllGetClassObject(REFCLSID clsid, REFIID iid, void** out) {
    if (!out) return E_POINTER;
    *out = nullptr;
    if (clsid != KeyboardTapId && clsid != KeyboardFaceProbeId && clsid != KeyboardStyleId) return CLASS_E_CLASSNOTAVAILABLE;
    auto factory = new(std::nothrow) Factory(clsid == KeyboardFaceProbeId, clsid == KeyboardStyleId);
    if (!factory) return E_OUTOFMEMORY;
    auto hr = factory->QueryInterface(iid, out); factory->Release(); return hr;
}
STDAPI DllCanUnloadNow() { return objects == 0 ? S_OK : S_FALSE; }
