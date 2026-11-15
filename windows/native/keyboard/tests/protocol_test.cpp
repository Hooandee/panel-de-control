#include "../protocol.h"
#undef NDEBUG
#include <cassert>
#include <cstring>
#include <limits>
int main() {
    using keyboard::ThemeId;
    static_assert(sizeof(ThemeId) == sizeof(std::uint32_t));
    static_assert(static_cast<std::uint32_t>(ThemeId::None) == 0);
    static_assert(static_cast<std::uint32_t>(ThemeId::Terciopelo) == 1);
    static_assert(static_cast<std::uint32_t>(ThemeId::LoboBlanco) == 2);
    static_assert(keyboard::ProtocolVersion == 6);
    assert(std::strcmp(keyboard::ThemeName(ThemeId::None), "") == 0);
    assert(std::strcmp(keyboard::ThemeName(static_cast<ThemeId>(3)), "") == 0);
    for (auto theme : {ThemeId::Terciopelo, ThemeId::LoboBlanco}) {
        assert(keyboard::ParseTheme(keyboard::ThemeName(theme)) == theme);
        assert(keyboard::KnownTheme(theme));
    }
    for (auto name : {"", "none", "Terciopelo", "LoboBlanco", "lobo blanco", "lobo-blanco ", "terciopelo|lobo-blanco"})
        assert(keyboard::ParseTheme(name) == ThemeId::None);
    assert(!keyboard::KnownTheme(ThemeId::None));
    assert(!keyboard::KnownTheme(static_cast<ThemeId>(3)));
    const std::wstring_view nonce = L".01234567-89ab-CDEF-0123-456789abcdef";
    keyboard::Initialization initialization;
    for (const auto data : {L"6|.01234567-89ab-CDEF-0123-456789abcdef|terciopelo",
                            L"6|.01234567-89ab-CDEF-0123-456789abcdef|lobo-blanco"}) {
        assert(keyboard::ParseInitialization(data, true, initialization));
        assert(initialization.session == nonce);
        assert(keyboard::KnownTheme(initialization.theme));
        assert(!keyboard::ParseInitialization(data, false, initialization));
    }
    assert(keyboard::ParseInitialization(L"6|.01234567-89ab-CDEF-0123-456789abcdef|", false, initialization));
    assert(initialization.session == nonce && initialization.theme == ThemeId::None);
    for (const auto data : {L"", L".01234567-89ab-CDEF-0123-456789abcdef",
            L"5|.01234567-89ab-CDEF-0123-456789abcdef|terciopelo",
            L"06|.01234567-89ab-CDEF-0123-456789abcdef|terciopelo",
            L"6|.01234567-89ab-CDEF-0123-456789abcdef|",
            L"6|.01234567-89ab-CDEF-0123-456789abcdef|other",
            L"6|.01234567-89ab-CDEF-0123-456789abcdef|terciopelo|lobo-blanco",
            L"6|.01234567889ab-CDEF-0123-456789abcdef|terciopelo",
            L"6|.01234567-89ab-CDEF-0123-456789abcdeg|terciopelo",
            L"6|/01234567-89ab-CDEF-0123-456789abcdef|terciopelo",
            L"6|.01234567-89ab-CDEF-0123-456789abcdef/terciopelo"}) {
        assert(!keyboard::ParseInitialization(data, true, initialization));
        assert(initialization.session.empty() && initialization.theme == ThemeId::None);
    }
    keyboard::Report report{};
    assert(report.version == 6 && report.appliedTheme == ThemeId::None);
    assert(keyboard::Valid(report));
    report.count = keyboard::MaxNodes + 1;
    assert(!keyboard::Valid(report));
    report.count = 1;
    std::strcpy(report.nodes[0].type, "Windows.UI.Xaml.Controls.Grid");
    assert(keyboard::Valid(report));
    std::strcpy(report.nodes[0].type, "typed text\"secret");
    assert(!keyboard::Valid(report));
    std::memset(report.nodes[0].type, 'a', keyboard::TypeLength);
    assert(!keyboard::Valid(report));
    report = {};
    report.probeFlags = 64;
    assert(!keyboard::Valid(report));
    report = {};
    report.phase = keyboard::StylePhase::Applied;
    assert(!keyboard::Valid(report));
    report.keyCount = 40; report.styledKeys = 39; report.pendingKeys = 1;
    assert(!keyboard::Valid(report));
    report.styledKeys = 40; report.pendingKeys = 0;
    assert(!keyboard::Valid(report));
    for (auto theme : {ThemeId::Terciopelo, ThemeId::LoboBlanco}) {
        report.appliedTheme = theme;
        assert(keyboard::Valid(report));
    }
    report.appliedTheme = static_cast<ThemeId>(3);
    assert(!keyboard::Valid(report));
    report.appliedTheme = ThemeId::Terciopelo;
    report.phase = keyboard::StylePhase::Idle;
    assert(!keyboard::Valid(report));
    for (auto phase : {keyboard::StylePhase::Idle, keyboard::StylePhase::Applying,
                       keyboard::StylePhase::Waiting, keyboard::StylePhase::Restoring, keyboard::StylePhase::Failed}) {
        report = {};
        report.phase = phase;
        assert(keyboard::Valid(report));
        for (auto theme : {ThemeId::Terciopelo, ThemeId::LoboBlanco, static_cast<ThemeId>(3)}) {
            report.appliedTheme = theme;
            assert(!keyboard::Valid(report));
        }
    }
    report = {};
    report.stateCount = 1;
    std::strcpy(report.states[0], "state with input");
    assert(!keyboard::Valid(report));
    report = {};
    report.chromeCount = 1;
    report.chrome[0].width = std::numeric_limits<float>::infinity();
    assert(!keyboard::Valid(report));
    report.chrome[0].width = -1;
    assert(!keyboard::Valid(report));
    report.chrome[0].width = 800;
    assert(keyboard::Valid(report));
    report.chromeCount = keyboard::MaxChromeNodes + 1;
    assert(!keyboard::Valid(report));
    report = {};
    report.fontCount = 1;
    auto& font = report.fonts[0];
    std::strcpy(font.family, "Segoe Fluent Icons, Segoe UI");
    font.role = 1; font.kind = 1; font.size = 16; font.opacity = 1; font.visible = 1;
    assert(keyboard::Valid(report));
    for (const auto* family : {"", "C:\\Users\\private", "ms-appx:///font.ttf", "font\"secret", "font's", "font/secret"}) {
        std::strcpy(font.family, family);
        assert(!keyboard::Valid(report));
    }
    std::memset(font.family, 'a', keyboard::TypeLength);
    assert(!keyboard::Valid(report));
    std::strcpy(font.family, "Original Family-1._`");
    for (float invalid : {-1.f, 1025.f, std::numeric_limits<float>::quiet_NaN(), std::numeric_limits<float>::infinity()}) {
        font.size = invalid;
        assert(!keyboard::Valid(report));
    }
    font.size = 1024;
    for (float invalid : {-0.1f, 1.1f, std::numeric_limits<float>::quiet_NaN(), std::numeric_limits<float>::infinity()}) {
        font.opacity = invalid;
        assert(!keyboard::Valid(report));
    }
    font.opacity = 0;
    font.role = 2;
    assert(!keyboard::Valid(report));
    font.role = 0; font.kind = 2;
    assert(!keyboard::Valid(report));
    font.kind = 0; font.visible = 2;
    assert(!keyboard::Valid(report));
    font.visible = 0;
    assert(keyboard::Valid(report));
    report.fontCount = keyboard::MaxFontSamples + 1;
    assert(!keyboard::Valid(report));
    report = {};
    for (auto version : {0u, 5u, 7u, 9u}) {
        report.version = version;
        assert(!keyboard::Valid(report));
    }
}
