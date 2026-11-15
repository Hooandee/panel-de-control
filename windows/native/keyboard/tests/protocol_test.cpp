#include "../protocol.h"
#undef NDEBUG
#include <cassert>
#include <cstring>
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
    report.version = 9;
    assert(!keyboard::Valid(report));
}
