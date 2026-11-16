#pragma once
#include "theme_id.h"
#include <string_view>

namespace keyboard {
enum class KeyRole { Normal, Enter, Backspace, Shift, CapsLock, Tab, AltGr };
struct KeyGlyph { KeyRole role; bool latched; };
inline constexpr KeyGlyph RoleFromGlyph(wchar_t glyph) {
    switch (glyph) {
    case L'\uE925': case L'\uE926': case L'\uEB96': case L'\uE750': return {KeyRole::Backspace, false};
    case L'\uE966': case L'\uEB97': case L'\uE751': return {KeyRole::Enter, false};
    case L'\uE84A': case L'\uE84B': case L'\uE752': return {KeyRole::Shift, false};
    case L'\uE7FD': return {KeyRole::Tab, false};
    default: return {KeyRole::Normal, false};
    }
}
inline constexpr KeyGlyph RoleFromSipGlyph(wchar_t glyph) {
    if (glyph == L'\uE3D7') return {KeyRole::Shift, false};
    if (glyph == L'\uE3D8') return {KeyRole::Shift, true};
    return RoleFromGlyph(glyph);
}
inline constexpr KeyGlyph RoleFromCaption(std::wstring_view caption) {
    if (caption == L"Tab") return {KeyRole::Tab, false};
    if (caption == L"Entrar") return {KeyRole::Enter, false};
    if (caption == L"May\u00fas") return {KeyRole::Shift, false};
    if (caption == L"Bloq May") return {KeyRole::CapsLock, false};
    if (caption == L"Alt Gr") return {KeyRole::AltGr, false};
    return {KeyRole::Normal, false};
}
inline constexpr bool SignKey(KeyRole role) {
    return role >= KeyRole::Enter && role <= KeyRole::Tab;
}
inline constexpr unsigned FaceIndex(ThemeId theme, KeyRole role, bool focused, bool pressed, bool hover, bool latched) {
    if (theme == ThemeId::Terciopelo) return pressed ? (focused ? 4 : 3) : focused ? 2 : hover ? 1 : 0;
    if (latched) return focused ? 2 : 9;
    if (focused) return pressed ? 4 : 2;
    return SignKey(role) ? (pressed ? 8 : 7) : (pressed ? 3 : 0);
}
}
