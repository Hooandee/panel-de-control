#pragma once
#include <winrt/Windows.UI.h>

namespace keyboard::terciopelo {
inline constexpr winrt::Windows::UI::Color Ink{255, 240, 220, 178};
inline constexpr winrt::Windows::UI::Color Accent{255, 217, 193, 151};
inline constexpr winrt::Windows::UI::Color Pressed{255, 255, 243, 218};
inline constexpr winrt::Windows::UI::Color Latched{255, 246, 214, 140};
inline constexpr winrt::Windows::UI::Color Background{255, 11, 11, 12};
inline constexpr float Slice = 54, Border = 18, Outset = 6;
}
