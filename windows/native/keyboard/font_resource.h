#pragma once
#include "common.h"
#include <cmath>
#include <vector>
#include <winrt/Windows.Storage.h>
#include <winrt/Windows.UI.Xaml.Controls.h>
#include <winrt/Windows.UI.Xaml.Media.h>

namespace keyboard {
class FontResource {
    std::wstring path, name;
public:
    winrt::Windows::UI::Xaml::Media::FontFamily family{nullptr};
    void Load(HMODULE module, unsigned resourceId, const wchar_t* familyName) {
        using namespace winrt;
        auto resource = FindResourceW(module, MAKEINTRESOURCEW(resourceId), RT_RCDATA);
        if (!resource) throw hresult_error(HRESULT_FROM_WIN32(GetLastError()));
        auto bytes = LockResource(LoadResource(module, resource));
        const auto size = SizeofResource(module, resource);
        if (!bytes || !size) throw hresult_error(E_FAIL);
        if (!path.empty()) {
            Handle existing(CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_DELETE,
                nullptr, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr));
            if (existing) {
                BY_HANDLE_FILE_INFORMATION info{};
                if (!GetFileInformationByHandle(existing.value, &info) || info.nFileSizeHigh || info.nFileSizeLow != size ||
                    (info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)) throw hresult_error(E_ACCESSDENIED);
                std::vector<BYTE> contents(size); DWORD read = 0;
                if (!ReadFile(existing.value, contents.data(), size, &read, nullptr) || read != size ||
                    memcmp(contents.data(), bytes, size)) throw hresult_error(E_ACCESSDENIED);
            } else if (GetLastError() == ERROR_FILE_NOT_FOUND) { path.clear(); name.clear(); }
            else throw hresult_error(HRESULT_FROM_WIN32(GetLastError()));
        }
        if (path.empty()) {
            GUID id{}; wchar_t text[40]{};
            check_hresult(CoCreateGuid(&id));
            if (!StringFromGUID2(id, text, 40)) throw hresult_error(E_FAIL);
            name = L"PanelKeyboard-" + std::wstring(text + 1, 36) + L".ttf";
            auto folder = Windows::Storage::ApplicationData::Current().TemporaryFolder();
            path = std::wstring(folder.Path()) + L"\\" + name;
            Handle file(CreateFileW(path.c_str(), GENERIC_WRITE, FILE_SHARE_READ, nullptr, CREATE_NEW, FILE_ATTRIBUTE_TEMPORARY, nullptr));
            if (!file) { path.clear(); throw hresult_error(HRESULT_FROM_WIN32(GetLastError())); }
            DWORD written = 0;
            if (!WriteFile(file.value, bytes, size, &written, nullptr) || written != size) throw hresult_error(E_FAIL);
        }
        family = Windows::UI::Xaml::Media::FontFamily(L"ms-appdata:///temp/" + name + L"#" + familyName + L", Segoe UI");
    }
    bool Resolved() const {
        using namespace winrt::Windows;
        UI::Xaml::Controls::TextBlock custom, fallback;
        custom.Text(L"Hamburgefontsiv 0123456789"); fallback.Text(L"Hamburgefontsiv 0123456789");
        custom.FontSize(40); fallback.FontSize(40);
        custom.FontFamily(family); fallback.FontFamily(UI::Xaml::Media::FontFamily(L"Segoe UI"));
        custom.Measure({10000, 10000}); fallback.Measure({10000, 10000});
        return std::abs(custom.DesiredSize().Width - fallback.DesiredSize().Width) > 0.5f;
    }
    void Clear() noexcept {
        family = nullptr;
        if (!path.empty() && DeleteFileW(path.c_str())) { path.clear(); name.clear(); }
    }
};
}
