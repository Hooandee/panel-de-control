#include "../visual_rules.h"
#undef NDEBUG
#include <cassert>
int main() {
    using namespace keyboard;
    assert(RoleFromGlyph(L'\uE750').role == KeyRole::Backspace);
    assert(RoleFromGlyph(L'\uE751').role == KeyRole::Enter);
    assert(RoleFromGlyph(L'\uE752').role == KeyRole::Shift);
    assert(RoleFromGlyph(L'\uE84B').role == KeyRole::Shift);
    assert(RoleFromGlyph(L'\uE925').role == KeyRole::Backspace);
    assert(RoleFromGlyph(L'\uE966').role == KeyRole::Enter);
    assert(RoleFromGlyph(L'\uE7FD').role == KeyRole::Tab);
    assert(RoleFromSipGlyph(L'\uE3D7').role == KeyRole::Shift);
    assert(!RoleFromSipGlyph(L'\uE3D7').latched);
    assert(RoleFromSipGlyph(L'\uE3D8').role == KeyRole::Shift);
    assert(RoleFromSipGlyph(L'\uE3D8').latched);
    assert(RoleFromSipGlyph(L'\uE752').role == KeyRole::Shift);
    assert(RoleFromGlyph(L'\uE3D8').role == KeyRole::Normal);
    assert(RoleFromGlyph(L'a').role == KeyRole::Normal);
    assert(RoleFromGlyph(L'\uE753').role == KeyRole::Normal);
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
