#pragma once
#include "visual_rules.h"
#include <winrt/Windows.UI.h>
#include <array>

namespace keyboard {
struct ThemeStyle {
    ThemeId id;
    winrt::Windows::UI::Color ink, soft, accent, pressed, enamel, focusedSoft;
    std::array<unsigned, 15> images;
    unsigned imageCount, fontResource, fallbackFontResource;
    const wchar_t* fontFamily;
    const wchar_t* fallbackFontFamily;
    float slice, border, outset, pressedOffset;
    unsigned frames, duration, enterDuration;
    float effectWidth, effectHeight, enterWidth, enterHeight, fadeStart;
};
inline constexpr ThemeStyle VelvetStyle{
    ThemeId::Terciopelo,
    {255,240,220,178}, {153,240,220,178}, {255,217,193,151}, {255,255,243,218}, {255,240,220,178}, {153,240,220,178},
    {101,102,103,104,105,106,108}, 7, 107, 0, L"Josefin Sans", L"",
    54,18,6,3, 18,720,720,126,98,126,98,.8f
};
inline constexpr ThemeStyle LoboStyle{
    ThemeId::LoboBlanco,
    {255,58,9,6}, {140,58,9,6}, {255,214,58,44}, {255,255,248,243}, {255,251,241,234}, {179,255,244,238},
    {201,201,202,203,204,205,206,207,208,209,210,211,212,213,214}, 15, 215, 216, L"Lobo Blanco Letras", L"Cinzel",
    54,18,6,2, 16,380,620,72,58,160,130,.75f
};
inline constexpr ThemeStyle const& StyleFor(ThemeId id) {
    return id == ThemeId::LoboBlanco ? LoboStyle : VelvetStyle;
}
}
