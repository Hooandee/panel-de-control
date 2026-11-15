#include "common.h"
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

    static DWORD WINAPI Collect(void* context) noexcept {
        auto self = static_cast<Tap*>(context);
        const auto com = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        self->report.subscribeResult = self->tree->AdviseVisualTreeChange(self);
        if (SUCCEEDED(self->report.subscribeResult)) {
            Sleep(3000);
            self->report.unsubscribeResult = self->tree->UnadviseVisualTreeChange(self);
        }
        // Never wait for the owner on a XAML callback thread.
        Handle pipe(CreateFileW(PipeName(GetCurrentProcessId()).c_str(), GENERIC_WRITE, 0,
                                nullptr, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, nullptr));
        if (pipe) {
            Handle done(CreateEventW(nullptr, TRUE, FALSE, nullptr));
            OVERLAPPED operation{};
            operation.hEvent = done.value;
            DWORD written = 0;
            keyboard::Report snapshot;
            { std::lock_guard lock(self->gate); snapshot = self->report; }
            if (!WriteFile(pipe.value, &snapshot, sizeof(snapshot), &written, &operation) &&
                GetLastError() == ERROR_IO_PENDING) {
                if (WaitForSingleObject(done.value, 1000) != WAIT_OBJECT_0) {
                    CancelIoEx(pipe.value, &operation);
                }
                GetOverlappedResult(pipe.value, &operation, &written, TRUE);
            }
        }
        const bool detached = SUCCEEDED(self->report.unsubscribeResult);
        HMODULE pin = self->pin;
        if (detached) {
            self->tree.Reset();
            self->site.Reset();
            discovering = false;
            self->Release();
        }
        // A failed unsubscribe retains callback + module; releasing either could crash Windows.
        if (SUCCEEDED(com)) CoUninitialize();
        if (detached) FreeLibraryAndExitThread(pin, 0);
        return 0;
    }
public:
    Tap() { ++objects; }
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
        { std::lock_guard lock(gate); report = {}; }
        auto hr = value->QueryInterface(IID_PPV_ARGS(&tree));
        if (FAILED(hr)) { discovering = false; return hr; }
        site = value;
        if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,
                               reinterpret_cast<LPCWSTR>(&KeyboardTapId), &pin)) {
            discovering = false; return HRESULT_FROM_WIN32(GetLastError());
        }
        AddRef();
        Handle worker(CreateThread(nullptr, 0, Collect, this, 0, nullptr));
        if (!worker) {
            hr = HRESULT_FROM_WIN32(GetLastError());
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
public:
    Factory() { ++objects; }
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
        auto tap = new(std::nothrow) Tap;
        if (!tap) return E_OUTOFMEMORY;
        auto hr = tap->QueryInterface(iid, out); tap->Release(); return hr;
    }
    HRESULT STDMETHODCALLTYPE LockServer(BOOL lock) override { if (lock) ++objects; else --objects; return S_OK; }
};
}
STDAPI DllGetClassObject(REFCLSID clsid, REFIID iid, void** out) {
    if (!out) return E_POINTER;
    *out = nullptr;
    if (clsid != KeyboardTapId) return CLASS_E_CLASSNOTAVAILABLE;
    auto factory = new(std::nothrow) Factory;
    if (!factory) return E_OUTOFMEMORY;
    auto hr = factory->QueryInterface(iid, out); factory->Release(); return hr;
}
STDAPI DllCanUnloadNow() { return objects == 0 ? S_OK : S_FALSE; }
