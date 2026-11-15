#pragma once
#include "common.h"
#include <cmath>
#include <winrt/Windows.Storage.h>
#include <winrt/Windows.UI.Xaml.Controls.h>
#include <winrt/Windows.UI.Xaml.Media.h>

namespace keyboard {
class FontResource {
    std::wstring path;
public:
    winrt::Windows::UI::Xaml::Media::FontFamily family{nullptr};
    void Load(HMODULE module) {
        using namespace winrt;
        GUID id{}; wchar_t text[40]{};
        check_hresult(CoCreateGuid(&id));
        if (!StringFromGUID2(id, text, 40)) throw hresult_error(E_FAIL);
        const auto name = L"PanelKeyboard-" + std::wstring(text + 1, 36) + L".ttf";
        auto folder = Windows::Storage::ApplicationData::Current().TemporaryFolder();
        path = std::wstring(folder.Path()) + L"\\" + name;
        auto resource = FindResourceW(module, MAKEINTRESOURCEW(107), RT_RCDATA);
        if (!resource) throw hresult_error(HRESULT_FROM_WIN32(GetLastError()));
        auto bytes = LockResource(LoadResource(module, resource));
        const auto size = SizeofResource(module, resource);
        Handle file(CreateFileW(path.c_str(), GENERIC_WRITE, FILE_SHARE_READ, nullptr, CREATE_NEW, FILE_ATTRIBUTE_TEMPORARY, nullptr));
        if (!file) { path.clear(); throw hresult_error(HRESULT_FROM_WIN32(GetLastError())); }
        DWORD written = 0;
        if (!bytes || !size || !WriteFile(file.value, bytes, size, &written, nullptr) || written != size)
            throw hresult_error(E_FAIL);
        family = Windows::UI::Xaml::Media::FontFamily(L"ms-appdata:///temp/" + name + L"#Josefin Sans, Segoe UI");
    }
    bool Resolved() const {
        using namespace winrt::Windows;
        UI::Xaml::Controls::TextBlock custom, fallback;
        custom.Text(L"Hamburgefontsiv 0123456789"); fallback.Text(custom.Text());
        custom.FontSize(40); fallback.FontSize(40);
        custom.FontFamily(family); fallback.FontFamily(UI::Xaml::Media::FontFamily(L"Segoe UI"));
        custom.Measure({10000, 10000}); fallback.Measure({10000, 10000});
        return std::abs(custom.DesiredSize().Width - fallback.DesiredSize().Width) > 0.5f;
    }
    void Clear() noexcept {
        family = nullptr;
        if (!path.empty() && DeleteFileW(path.c_str())) path.clear();
    }
};
}
