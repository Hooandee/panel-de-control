#pragma once
#define NOMINMAX
#include <windows.h>
#include <xamlom.h>
#include <string>
#include "protocol.h"

inline constexpr CLSID KeyboardTapId = {0xf387a3d8, 0xb16c, 0x4aad, {0xa4, 0x52, 0x74, 0x52, 0x12, 0xbb, 0xb3, 0x61}};
inline constexpr CLSID KeyboardFaceProbeId = {0x4fcd44a6, 0x068b, 0x42a6, {0x91, 0xa1, 0x77, 0x82, 0x53, 0x59, 0x88, 0x39}};
inline constexpr CLSID KeyboardStyleId = {0xf4a79e9c, 0xf20b, 0x438a, {0xb6, 0xe6, 0x24, 0x81, 0x80, 0xda, 0xc5, 0x2d}};
inline std::wstring PipeName(DWORD pid, const std::wstring& session = {}) {
    return L"\\\\.\\pipe\\LOCAL\\PanelDeControl.KeyboardDiscovery." + std::to_wstring(pid) + session;
}
struct Handle {
    HANDLE value = INVALID_HANDLE_VALUE;
    explicit Handle(HANDLE h = INVALID_HANDLE_VALUE) : value(h) {}
    ~Handle() { if (value && value != INVALID_HANDLE_VALUE) CloseHandle(value); }
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
    explicit operator bool() const { return value && value != INVALID_HANDLE_VALUE; }
};
