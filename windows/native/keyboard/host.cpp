#include "common.h"
#include <tlhelp32.h>
#include <sddl.h>
#include <winternl.h>
#include <filesystem>
#include <iostream>
#include <vector>
#include <algorithm>
#include <cwctype>
#include <atomic>
#include <thread>

namespace {
DWORD build = 0;
DWORD targetPid = 0;
DWORD previousPid = 0;
ULONGLONG previousCreation = 0;
unsigned attempts = 0;
unsigned frameworkChecks = 0;
std::atomic<bool> stopRequested{false};
std::string lastStatus = "waiting_for_keyboard", lastError = "keyboard_not_running";
const char* architecture = "unknown";
void Result(const char* status, const char* error, HRESULT hr = S_OK,
            const keyboard::Report* report = nullptr) {
    lastStatus = status; lastError = error;
    const bool connected = report && SUCCEEDED(report->subscribeResult);
    std::cout << "{\"status\":\"" << status << "\",\"errorCode\":\"" << error
              << "\",\"windowsBuild\":" << build << ",\"architecture\":\"" << architecture << "\",\"processId\":"
              << targetPid << ",\"connected\":" << (connected ? "true" : "false")
              << ",\"hresult\":" << static_cast<long>(hr)
              << ",\"observedElements\":" << (report ? report->count : 0)
              << ",\"truncated\":" << (report && report->truncated ? "true" : "false")
              << ",\"probeFlags\":" << (report ? report->probeFlags : 0)
              << ",\"probeHresult\":" << (report ? report->probeResult : 0)
              << ",\"keyCount\":" << (report ? report->keyCount : 0)
              << ",\"styledKeys\":" << (report ? report->styledKeys : 0)
              << ",\"restoredKeys\":" << (report ? report->restoredKeys : 0)
              << ",\"pendingKeys\":" << (report ? report->pendingKeys : 0)
              << ",\"stateCatalog\":[";
    if (report) for (unsigned i = 0; i < report->stateCount; ++i) {
        if (i) std::cout << ',';
        std::cout << '\"' << report->states[i] << '\"';
    }
    std::cout << "],\"chromeGeometry\":[";
    if (report) for (unsigned i = 0; i < report->chromeCount; ++i) {
        if (i) std::cout << ',';
        const auto& n = report->chrome[i];
        std::cout << "{\"kind\":" << n.kind << ",\"background\":" << n.background
                  << ",\"x\":" << n.x << ",\"y\":" << n.y << ",\"width\":" << n.width
                  << ",\"height\":" << n.height << ",\"radius\":" << n.radius << '}';
    }
    std::cout << "],\"fontSamples\":[";
    if (report) for (unsigned i = 0; i < report->fontCount; ++i) {
        if (i) std::cout << ',';
        const auto& sample = report->fonts[i];
        std::cout << "{\"family\":\"" << sample.family << "\",\"role\":" << sample.role
                  << ",\"kind\":" << sample.kind << ",\"size\":" << sample.size
                  << ",\"opacity\":" << sample.opacity << ",\"visible\":" << sample.visible << '}';
    }
    std::cout << "],\"nodes\":[";
    if (report) for (std::uint32_t i = 0; i < report->count; ++i) {
        if (i) std::cout << ',';
        const auto& node = report->nodes[i];
        std::cout << "{\"id\":" << node.id << ",\"parent\":" << node.parent
                  << ",\"type\":\"" << node.type << "\"}";
    }
    std::cout << "]}" << std::endl;
}
std::vector<BYTE> UserToken(HANDLE process) {
    HANDLE raw = nullptr;
    if (!OpenProcessToken(process, TOKEN_QUERY, &raw)) return {};
    Handle token(raw);
    DWORD size = 0;
    GetTokenInformation(token.value, TokenUser, nullptr, 0, &size);
    std::vector<BYTE> data(size);
    if (!size || !GetTokenInformation(token.value, TokenUser, data.data(), size, &size)) return {};
    return data;
}
bool SameUser(HANDLE process) {
    auto ours = UserToken(GetCurrentProcess());
    auto theirs = UserToken(process);
    return !ours.empty() && !theirs.empty() &&
        EqualSid(reinterpret_cast<TOKEN_USER*>(ours.data())->User.Sid,
                 reinterpret_cast<TOKEN_USER*>(theirs.data())->User.Sid);
}
std::wstring Lower(std::wstring value) {
    std::transform(value.begin(), value.end(), value.begin(), towlower); return value;
}
bool IsSystemKeyboard(HANDLE process) {
    wchar_t filename[32768]{};
    DWORD size = 32768;
    wchar_t windows[MAX_PATH]{};
    if (!QueryFullProcessImageNameW(process, 0, filename, &size) ||
        !GetWindowsDirectoryW(windows, MAX_PATH)) return false;
    auto path = Lower(filename);
    auto root = Lower(std::wstring(windows) + L"\\SystemApps\\");
    return path.compare(0, root.size(), root) == 0 &&
        Lower(std::filesystem::path(path).filename().wstring()) == L"textinputhost.exe";
}
bool UsesWindowsXaml(DWORD pid) {
    Handle snapshot(CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid));
    if (!snapshot) return false;
    MODULEENTRY32W entry{}; entry.dwSize = sizeof(entry);
    if (!Module32FirstW(snapshot.value, &entry)) return false;
    do { if (_wcsicmp(entry.szModule, L"Windows.UI.Xaml.dll") == 0) return true; }
    while (Module32NextW(snapshot.value, &entry));
    return false;
}
bool TargetContainerSid(HANDLE process, std::wstring& sid) {
    HANDLE raw = nullptr;
    if (!OpenProcessToken(process, TOKEN_QUERY, &raw)) return false;
    Handle token(raw);
    DWORD container = 0, size = 0;
    if (!GetTokenInformation(token.value, TokenIsAppContainer, &container, sizeof(container), &size)) return false;
    if (!container) return true;
    GetTokenInformation(token.value, TokenAppContainerSid, nullptr, 0, &size);
    std::vector<BYTE> data(size);
    if (!size || !GetTokenInformation(token.value, TokenAppContainerSid, data.data(), size, &size)) return false;
    LPWSTR text = nullptr;
    if (!ConvertSidToStringSidW(reinterpret_cast<TOKEN_APPCONTAINER_INFORMATION*>(data.data())->TokenAppContainer, &text)) return false;
    sid = text; LocalFree(text); return true;
}
struct Security {
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    SECURITY_ATTRIBUTES attributes{sizeof(SECURITY_ATTRIBUTES), nullptr, FALSE};
    ~Security() { if (descriptor) LocalFree(descriptor); }
    bool Initialize(const std::wstring& containerSid) {
        auto token = UserToken(GetCurrentProcess());
        if (token.empty()) return false;
        LPWSTR sid = nullptr;
        if (!ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(token.data())->User.Sid, &sid)) return false;
        const std::wstring sddl = L"D:P(A;;GA;;;" + std::wstring(sid) + L")" +
            (containerSid.empty() ? L"" : L"(A;;GRGW;;;" + containerSid + L")") +
            L"S:(ML;;NW;;;LW)";
        LocalFree(sid);
        if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl.c_str(), SDDL_REVISION_1,
                                                                  &descriptor, nullptr)) return false;
        attributes.lpSecurityDescriptor = descriptor; return true;
    }
};
bool FinishIo(HANDLE pipe, OVERLAPPED& operation, DWORD& transferred, DWORD timeout) {
    if (WaitForSingleObject(operation.hEvent, timeout) == WAIT_OBJECT_0)
        return GetOverlappedResult(pipe, &operation, &transferred, FALSE) != FALSE;
    CancelIoEx(pipe, &operation);
    GetOverlappedResult(pipe, &operation, &transferred, TRUE);
    return false;
}
bool ReadReport(HANDLE pipe, HANDLE event, keyboard::Report& report) {
    DWORD received = 0;
    const auto deadline = GetTickCount64() + 4500;
    while (received < sizeof(report)) {
        ResetEvent(event); OVERLAPPED operation{}; operation.hEvent = event;
        DWORD transferred = 0;
        const bool read = ReadFile(pipe, reinterpret_cast<BYTE*>(&report) + received,
            static_cast<DWORD>(sizeof(report) - received), &transferred, &operation) != FALSE;
        if (!read) {
            const auto now = GetTickCount64();
            if (GetLastError() != ERROR_IO_PENDING || now >= deadline ||
                !FinishIo(pipe, operation, transferred, static_cast<DWORD>(deadline - now))) return false;
        }
        if (!transferred) return false;
        received += transferred;
    }
    return keyboard::Valid(report);
}
bool WriteCommand(HANDLE pipe, HANDLE event, BYTE value) {
    ResetEvent(event); OVERLAPPED operation{}; operation.hEvent = event;
    DWORD written = 0;
    if (WriteFile(pipe, &value, 1, &written, &operation)) return written == 1;
    return GetLastError() == ERROR_IO_PENDING && FinishIo(pipe, operation, written, 1000) && written == 1;
}
void StyleResult(const keyboard::Report& report) {
    if (FAILED(report.subscribeResult)) Result("connection_failed", "xaml_subscribe_failed", report.subscribeResult, &report);
    else if (FAILED(report.unsubscribeResult)) Result("connection_failed", "xaml_unsubscribe_failed", report.unsubscribeResult, &report);
    else if (FAILED(report.styleResult)) Result("connection_failed", "style_failed", report.styleResult, &report);
    else switch (report.phase) {
    case keyboard::StylePhase::Applied: Result("applied", "styles_active", S_OK, &report); break;
    case keyboard::StylePhase::Applying: Result("applying", "styles_pending", S_OK, &report); break;
    case keyboard::StylePhase::Waiting: Result("waiting_for_keyboard", "keyboard_not_visible", S_OK, &report); break;
    case keyboard::StylePhase::Restoring: Result("restoring", "styles_restoring", S_OK, &report); break;
    case keyboard::StylePhase::Idle: Result("disabled", "styles_restored", S_OK, &report); break;
    default: Result("connection_failed", "style_failed", E_FAIL, &report); break;
    }
}
}
int Run(bool faceProbe, bool styling, bool effectProbe = false) {
    targetPid = 0;
    RTL_OSVERSIONINFOW version{}; version.dwOSVersionInfoSize = sizeof(version);
    using GetVersion = LONG(WINAPI*)(PRTL_OSVERSIONINFOW);
    auto getVersion = reinterpret_cast<GetVersion>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"), "RtlGetVersion"));
    SYSTEM_INFO system{}; GetNativeSystemInfo(&system);
    const bool versionKnown = getVersion && getVersion(&version) == 0;
    if (versionKnown) build = version.dwBuildNumber;
    architecture = system.wProcessorArchitecture == PROCESSOR_ARCHITECTURE_AMD64 ? "x64" :
        system.wProcessorArchitecture == PROCESSOR_ARCHITECTURE_ARM64 ? "arm64" :
        system.wProcessorArchitecture == PROCESSOR_ARCHITECTURE_INTEL ? "x86" : "unknown";
    if (!versionKnown || version.dwMajorVersion != 10 ||
        version.dwBuildNumber < 22000 || system.wProcessorArchitecture != PROCESSOR_ARCHITECTURE_AMD64) {
        Result("unsupported", "unsupported_windows_or_architecture"); return 0;
    }
    build = version.dwBuildNumber;
    if ((faceProbe || styling) && build != 26300) { Result("unsupported", "probe_build_unverified"); return 0; }
    DWORD session = 0; ProcessIdToSessionId(GetCurrentProcessId(), &session);
    Handle snapshot(CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0));
    PROCESSENTRY32W entry{}; entry.dwSize = sizeof(entry);
    if (snapshot && Process32FirstW(snapshot.value, &entry)) do {
        DWORD candidateSession = 0;
        if (_wcsicmp(entry.szExeFile, L"TextInputHost.exe") == 0 &&
            ProcessIdToSessionId(entry.th32ProcessID, &candidateSession) && candidateSession == session) {
            if (targetPid) { Result("connection_failed", "ambiguous_target"); return 0; }
            targetPid = entry.th32ProcessID;
        }
    } while (Process32NextW(snapshot.value, &entry));
    if (!targetPid) { previousPid = 0; Result(styling ? "waiting_for_keyboard" : "connection_failed", "keyboard_not_running"); return 0; }

    Handle process(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, targetPid));
    USHORT machine = 0, nativeMachine = 0;
    if (!process || !SameUser(process.value) || !IsSystemKeyboard(process.value) ||
        !IsWow64Process2(process.value, &machine, &nativeMachine) || machine != IMAGE_FILE_MACHINE_UNKNOWN ||
        nativeMachine != IMAGE_FILE_MACHINE_AMD64) {
        Result("connection_failed", "target_not_authorized"); return 0;
    }
    FILETIME creation{}, exited{}, kernelTime{}, userTime{};
    if (!GetProcessTimes(process.value, &creation, &exited, &kernelTime, &userTime)) {
        Result("connection_failed", "target_not_authorized"); return 0;
    }
    const ULONGLONG created = (static_cast<ULONGLONG>(creation.dwHighDateTime) << 32) | creation.dwLowDateTime;
    if (styling) {
        if (previousPid != targetPid || previousCreation != created) {
            attempts = 0; frameworkChecks = 0; previousPid = targetPid; previousCreation = created;
        }
        if (attempts >= 3 || (attempts && lastError != "xaml_attach_failed" && lastError != "xaml_framework_not_observed")) { Result(lastStatus.c_str(), lastError.c_str()); return 0; }
        if (frameworkChecks >= 15) { Result("connection_failed", "xaml_framework_not_observed"); return 0; }
    }
    if (!UsesWindowsXaml(targetPid)) {
        if (styling) ++frameworkChecks;
        Result(styling && frameworkChecks < 15 ? "waiting_for_keyboard" : "connection_failed", "xaml_framework_not_observed");
        return 0;
    }
    if (styling) { frameworkChecks = 0; ++attempts; }
    const auto mutexName = L"Local\\PanelDeControl.KeyboardDiscovery." + std::to_wstring(targetPid);
    Handle mutex(CreateMutexW(nullptr, TRUE, mutexName.c_str()));
    if (!mutex || GetLastError() == ERROR_ALREADY_EXISTS) {
        Result("connection_failed", "discovery_busy"); return 0;
    }
    wchar_t executable[32768]{};
    const auto pathLength = GetModuleFileNameW(nullptr, executable, 32768);
    if (!pathLength || pathLength >= 32768) { Result("runtime_missing", "runtime_path_invalid"); return 0; }
    auto tap = std::filesystem::path(executable).parent_path() / L"PanelDeControl.KeyboardTap.dll";
    if (!std::filesystem::is_regular_file(tap)) { Result("runtime_missing", "tap_missing"); return 0; }
    std::wstring containerSid;
    if (!TargetContainerSid(process.value, containerSid)) {
        Result("connection_failed", "target_token_unavailable"); return 0;
    }
    GUID nonce{}; wchar_t nonceText[40]{};
    if (FAILED(CoCreateGuid(&nonce)) || !StringFromGUID2(nonce, nonceText, 40)) {
        Result("connection_failed", "ipc_create_failed"); return 0;
    }
    const std::wstring sessionToken = L"." + std::wstring(nonceText + 1, 36);
    const auto serverPipe = containerSid.empty() ? PipeName(targetPid, sessionToken) :
        L"\\\\.\\pipe\\Sessions\\" + std::to_wstring(session) + L"\\AppContainerNamedObjects\\" +
        containerSid + L"\\PanelDeControl.KeyboardDiscovery." + std::to_wstring(targetPid) + sessionToken;
    Security security;
    if (!security.Initialize(containerSid)) { Result("connection_failed", "ipc_security_failed"); return 0; }
    Handle pipe(CreateNamedPipeW(serverPipe.c_str(), (styling ? PIPE_ACCESS_DUPLEX : PIPE_ACCESS_INBOUND) | FILE_FLAG_OVERLAPPED |
                                FILE_FLAG_FIRST_PIPE_INSTANCE, PIPE_TYPE_BYTE | PIPE_READMODE_BYTE |
                                PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS, 1, 0, sizeof(keyboard::Report),
                                0, &security.attributes));
    Handle event(CreateEventW(nullptr, TRUE, FALSE, nullptr));
    if (!pipe || !event) { Result("connection_failed", "ipc_create_failed"); return 0; }
    OVERLAPPED operation{}; operation.hEvent = event.value;
    const bool immediate = ConnectNamedPipe(pipe.value, &operation) != FALSE;
    const DWORD connectError = immediate ? ERROR_SUCCESS : GetLastError();
    if (!immediate && connectError != ERROR_IO_PENDING && connectError != ERROR_PIPE_CONNECTED) {
        Result("connection_failed", "ipc_connect_failed"); return 0;
    }
    auto xaml = LoadLibraryExW(L"Windows.UI.Xaml.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    const auto initialize = xaml ? reinterpret_cast<decltype(&InitializeXamlDiagnosticsEx)>(
        GetProcAddress(xaml, "InitializeXamlDiagnosticsEx")) : nullptr;
    if (!initialize) { CancelIoEx(pipe.value, nullptr); Result("unsupported", "xaml_diagnostics_missing"); return 0; }
    HRESULT hr = HRESULT_FROM_WIN32(ERROR_NOT_FOUND);
    // Connection names are an implementation detail, not a documented keyboard contract.
    for (int i = 1; i <= 4 && hr == HRESULT_FROM_WIN32(ERROR_NOT_FOUND); ++i) {
        const auto name = L"VisualDiagConnection" + std::to_wstring(i);
        hr = initialize(name.c_str(), targetPid, L"", tap.c_str(), effectProbe ? KeyboardEffectsProbeId : styling ? KeyboardStyleId : faceProbe ? KeyboardFaceProbeId : KeyboardTapId, sessionToken.c_str());
    }
    DWORD transferred = 0;
    if (FAILED(hr)) {
        CancelIoEx(pipe.value, nullptr); Result("connection_failed", "xaml_attach_failed", hr); return 0;
    }
    if (!immediate && connectError == ERROR_IO_PENDING && !FinishIo(pipe.value, operation, transferred, faceProbe ? 14000 : 8000)) {
        Result("connection_failed", "tap_receipt_timeout"); return 0;
    }
    ULONG clientPid = 0;
    if (!GetNamedPipeClientProcessId(pipe.value, &clientPid) || clientPid != targetPid ||
        WaitForSingleObject(process.value, 0) != WAIT_TIMEOUT) {
        Result("connection_failed", "receipt_sender_invalid"); return 0;
    }
    keyboard::Report report;
    if (styling) {
        while (true) {
            const bool stopping = stopRequested.load();
            if (!WriteCommand(pipe.value, event.value, stopping ? 2 : 1) || !ReadReport(pipe.value, event.value, report)) {
                if (WaitForSingleObject(process.value, 100) == WAIT_OBJECT_0)
                    Result(stopping ? "disabled" : "waiting_for_keyboard", stopping ? "styles_restored" : "keyboard_not_running");
                else Result("connection_failed", stopping ? "restore_unconfirmed" : "receipt_invalid");
                return 0;
            }
            if (WaitForSingleObject(process.value, 0) == WAIT_OBJECT_0) {
                Result(stopping ? "disabled" : "waiting_for_keyboard", stopping ? "styles_restored" : "keyboard_not_running"); return 0;
            }
            StyleResult(report);
            if (stopping || report.phase == keyboard::StylePhase::Idle || FAILED(report.styleResult)) return 0;
            for (int i = 0; i < 10 && !stopRequested; ++i) Sleep(100);
        }
    }
    if (!ReadReport(pipe.value, event.value, report)) { Result("connection_failed", "receipt_invalid"); return 0; }
    if (FAILED(report.subscribeResult)) Result("connection_failed", "xaml_subscribe_failed", report.subscribeResult, &report);
    else if (FAILED(report.unsubscribeResult)) Result("connection_failed", "xaml_unsubscribe_failed", report.unsubscribeResult, &report);
    else if (faceProbe) Result("experimental_probe",
        (report.probeFlags & keyboard::ProbeFailed) ? "probe_failed" :
        (report.probeFlags & keyboard::ProbeRestored) && (report.probeFlags & keyboard::ProbeInserted) ? "probe_restored" :
        (report.probeFlags & keyboard::ProbeStarted) ? "probe_incomplete" : "probe_target_not_observed",
        report.probeResult, &report);
    else Result("discovery_required", "selectors_unverified", S_OK, &report);
    return 0;
}

int wmain(int argc, wchar_t** argv) {
    const bool faceProbe = argc == 2 && wcscmp(argv[1], L"probe-key-face") == 0;
    const bool effectProbe = argc == 2 && wcscmp(argv[1], L"probe-effects") == 0;
    const bool styling = effectProbe || (argc == 2 && wcscmp(argv[1], L"serve") == 0);
    if (argc != 2 || (!faceProbe && !styling && wcscmp(argv[1], L"discover") != 0)) {
        Result("connection_failed", "invalid_command"); return 2;
    }
    if (!styling) return Run(faceProbe, false);
    std::thread([] {
        std::string line;
        while (std::getline(std::cin, line)) if (line == "stop") break;
        stopRequested = true;
    }).detach();
    if (effectProbe) std::thread([] { Sleep(12000); stopRequested = true; }).detach();
    do {
        Run(false, true, effectProbe);
        if (lastStatus == "unsupported" || lastStatus == "runtime_missing") break;
        for (int i = 0; i < 20 && !stopRequested; ++i) Sleep(100);
    } while (!stopRequested);
    if ((lastStatus == "waiting_for_keyboard" && lastError == "keyboard_not_running") ||
        (attempts == 0 && lastError == "xaml_framework_not_observed")) Result("disabled", "styles_restored");
    return 0;
}
