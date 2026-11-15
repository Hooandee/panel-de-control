#pragma once
#include <cstddef>
#include <cstdint>
#include <cmath>
#include <initializer_list>

namespace keyboard {
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
struct Report {
    std::uint32_t version = 4;
    std::uint32_t count = 0;
    std::int32_t subscribeResult = 0;
    std::int32_t unsubscribeResult = 0;
    std::uint32_t truncated = 0;
    std::uint32_t probeFlags = 0;
    std::int32_t probeResult = 0;
    StylePhase phase = StylePhase::Idle;
    std::uint32_t keyCount = 0, styledKeys = 0, restoredKeys = 0, pendingKeys = 0;
    std::int32_t styleResult = 0;
    std::uint32_t stateCount = 0;
    char states[MaxStates][TypeLength]{};
    Node nodes[MaxNodes]{};
    std::uint32_t chromeCount = 0;
    ChromeGeometry chrome[MaxChromeNodes]{};
};
inline bool TypeCharacter(char c) {
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
           (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '`';
}
inline bool Valid(const Report& report) {
    if (report.version != 4 || report.chromeCount > MaxChromeNodes || report.count > MaxNodes || report.truncated > 1 || report.probeFlags > 63 || report.stateCount > MaxStates ||
        report.keyCount > 256 || report.styledKeys > report.keyCount ||
        report.pendingKeys > 256 || static_cast<unsigned>(report.phase) > 5) return false;
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
}
