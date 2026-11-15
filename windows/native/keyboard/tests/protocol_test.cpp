#include "../protocol.h"
#undef NDEBUG
#include <cassert>
#include <cstring>
#include <limits>
int main() {
    keyboard::Report report{};
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
    assert(keyboard::Valid(report));
    report.phase = keyboard::StylePhase::Idle;
    assert(!keyboard::Valid(report));
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
    report.version = 9;
    assert(!keyboard::Valid(report));
}
