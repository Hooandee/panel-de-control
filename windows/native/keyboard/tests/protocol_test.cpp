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
    report.version = 9;
    assert(!keyboard::Valid(report));
}
