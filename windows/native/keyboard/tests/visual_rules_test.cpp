#include "../visual_rules.h"
#undef NDEBUG
#include <cassert>
int main() {
    using namespace keyboard;
    assert(FaceIndex(ThemeId::LoboBlanco, KeyRole::Normal, false, false, false, false) == 0);
    assert(FaceIndex(ThemeId::LoboBlanco, KeyRole::Enter, false, false, false, false) == 7);
    assert(FaceIndex(ThemeId::LoboBlanco, KeyRole::Backspace, false, true, false, false) == 8);
    assert(FaceIndex(ThemeId::LoboBlanco, KeyRole::Enter, true, true, false, false) == 4);
    assert(FaceIndex(ThemeId::LoboBlanco, KeyRole::Shift, false, true, false, true) == 9);
    assert(FaceIndex(ThemeId::LoboBlanco, KeyRole::Shift, true, true, false, true) == 2);
    assert(FaceIndex(ThemeId::LoboBlanco, KeyRole::AltGr, false, false, false, true) == 9);
    assert(FaceIndex(ThemeId::LoboBlanco, KeyRole::Normal, false, false, true, false) == 0);
    assert(FaceIndex(ThemeId::Terciopelo, KeyRole::Shift, false, false, true, true) == 1);
}
