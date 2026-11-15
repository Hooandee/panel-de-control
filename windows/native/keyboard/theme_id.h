#pragma once
#include <cstdint>
#include <string_view>

namespace keyboard {
enum class ThemeId : std::uint32_t { None = 0, Terciopelo = 1, LoboBlanco = 2 };
inline constexpr const char* ThemeName(ThemeId theme) noexcept {
    switch (theme) {
    case ThemeId::Terciopelo: return "terciopelo";
    case ThemeId::LoboBlanco: return "lobo-blanco";
    default: return "";
    }
}
inline constexpr ThemeId ParseTheme(std::string_view theme) noexcept {
    return theme == "terciopelo" ? ThemeId::Terciopelo :
           theme == "lobo-blanco" ? ThemeId::LoboBlanco : ThemeId::None;
}
inline constexpr bool KnownTheme(ThemeId theme) noexcept {
    return theme == ThemeId::Terciopelo || theme == ThemeId::LoboBlanco;
}
}
