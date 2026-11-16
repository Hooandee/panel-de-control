#pragma once
#include <cstddef>
#include <cstdint>
#include <cmath>
#include <initializer_list>
#include <string_view>
#include "theme_id.h"

namespace keyboard {
constexpr std::uint32_t ProtocolVersion = 6;
struct Initialization {
    std::wstring_view session;
    ThemeId theme = ThemeId::None;
};
inline bool ParseInitialization(std::wstring_view data, bool styling, Initialization& result) noexcept {
    result = {};
    if (data.size() < 40 || data.substr(0, 2) != L"6|" || data[2] != L'.' || data[39] != L'|') return false;
    const auto session = data.substr(2, 37);
    for (std::size_t i = 1; i < session.size(); ++i) {
        const bool separator = i == 9 || i == 14 || i == 19 || i == 24;
        const auto c = session[i];
        const bool hex = (c >= L'0' && c <= L'9') || (c >= L'a' && c <= L'f') || (c >= L'A' && c <= L'F');
        if (separator ? c != L'-' : !hex) return false;
    }
    const auto name = data.substr(40);
    const auto theme = name == L"terciopelo" ? ThemeId::Terciopelo :
                       name == L"lobo-blanco" ? ThemeId::LoboBlanco : ThemeId::None;
    if (styling ? !KnownTheme(theme) : !name.empty()) return false;
    result = {session, theme};
    return true;
}
constexpr std::uint32_t MaxNodes = 512;
constexpr std::size_t TypeLength = 128;
struct Node {
    std::uint64_t id = 0;
    std::uint64_t parent = 0;
    char type[TypeLength]{};
};
enum ProbeFlag : std::uint32_t {
    ProbeStarted = 1, ProbeImageLoaded = 2, ProbeInserted = 4, ProbeRestored = 8,
    ProbeFailed = 16, ProbeGeometryChanged = 32
};
enum class StylePhase : std::uint32_t { Idle, Applying, Applied, Waiting, Restoring, Failed };
constexpr std::uint32_t MaxStates = 64;
constexpr std::uint32_t MaxChromeNodes = 24;
struct ChromeGeometry {
    std::uint32_t kind = 0, background = 0;
    float x = 0, y = 0, width = 0, height = 0, radius = 0;
};
constexpr std::uint32_t MaxFontSamples = 16;
struct FontSample {
    char family[TypeLength]{};
    std::uint32_t role = 0, kind = 0;
    float size = 0, opacity = 0;
    std::uint32_t visible = 0;
};
struct Report {
    std::uint32_t version = ProtocolVersion;
    std::uint32_t count = 0;
    std::int32_t subscribeResult = 0;
    std::int32_t unsubscribeResult = 0;
    std::uint32_t truncated = 0;
    std::uint32_t probeFlags = 0;
    std::int32_t probeResult = 0;
    StylePhase phase = StylePhase::Idle;
    ThemeId appliedTheme = ThemeId::None;
    std::uint32_t keyCount = 0, styledKeys = 0, restoredKeys = 0, pendingKeys = 0;
    std::int32_t styleResult = 0;
    std::uint32_t stateCount = 0;
    char states[MaxStates][TypeLength]{};
    Node nodes[MaxNodes]{};
    std::uint32_t chromeCount = 0;
    ChromeGeometry chrome[MaxChromeNodes]{};
    std::uint32_t fontCount = 0;
    FontSample fonts[MaxFontSamples]{};
};
inline bool TypeCharacter(char c) {
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
           (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '`';
}
inline bool Valid(const Report& report) {
    if (report.version != ProtocolVersion || report.fontCount > MaxFontSamples || report.chromeCount > MaxChromeNodes || report.count > MaxNodes || report.truncated > 1 || report.probeFlags > 63 || report.stateCount > MaxStates ||
        report.keyCount > 256 || report.styledKeys > report.keyCount ||
        report.pendingKeys > 256 || static_cast<unsigned>(report.phase) > 5) return false;
    if (report.phase == StylePhase::Applied ? !KnownTheme(report.appliedTheme) : report.appliedTheme != ThemeId::None) return false;
    if (report.phase == StylePhase::Applied &&
        (!report.keyCount || report.keyCount != report.styledKeys || report.pendingKeys || report.styleResult < 0)) return false;
    if (report.phase == StylePhase::Idle && (report.keyCount || report.styledKeys || report.pendingKeys)) return false;
    for (std::uint32_t i = 0; i < report.chromeCount; ++i) {
        const auto& node = report.chrome[i];
        if (node.kind > 2 || node.background > 1) return false;
        for (float value : {node.x, node.y, node.width, node.height, node.radius})
            if (!std::isfinite(value) || std::abs(value) > 32768) return false;
        if (node.width < 0 || node.height < 0 || node.radius < 0) return false;
    }
    for (std::uint32_t i = 0; i < report.fontCount; ++i) {
        const auto& sample = report.fonts[i];
        if (sample.role > 1 || sample.kind > 1 || sample.visible > 1 ||
            !std::isfinite(sample.size) || sample.size < 0 || sample.size > 1024 ||
            !std::isfinite(sample.opacity) || sample.opacity < 0 || sample.opacity > 1) return false;
        std::size_t j = 0;
        for (; j < TypeLength && sample.family[j]; ++j)
            if (!TypeCharacter(sample.family[j]) && sample.family[j] != ' ' &&
                sample.family[j] != '-' && sample.family[j] != ',') return false;
        if (j == 0 || j == TypeLength) return false;
    }
    for (std::uint32_t i = 0; i < report.count; ++i) {
        std::size_t j = 0;
        for (; j < TypeLength && report.nodes[i].type[j]; ++j)
            if (!TypeCharacter(report.nodes[i].type[j])) return false;
        if (j == 0 || j == TypeLength) return false;
    }
    for (std::uint32_t i = 0; i < report.stateCount; ++i) {
        std::size_t j = 0;
        for (; j < TypeLength && report.states[i][j]; ++j)
            if (!TypeCharacter(report.states[i][j])) return false;
        if (j == 0 || j == TypeLength) return false;
    }
    return true;
}
inline bool RestorationConfirmed(const Report& report) {
    return Valid(report) && report.phase == StylePhase::Idle && report.styleResult >= 0 &&
           report.subscribeResult >= 0 && report.unsubscribeResult >= 0;
}

}
