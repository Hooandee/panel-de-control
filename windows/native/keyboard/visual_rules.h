#pragma once
#include "theme_id.h"

namespace keyboard {
enum class KeyRole { Normal, Enter, Backspace, Shift, CapsLock, Tab, AltGr };
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
