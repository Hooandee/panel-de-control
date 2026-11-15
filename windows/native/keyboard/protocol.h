#pragma once
#include <cstddef>
#include <cstdint>

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
struct Report {
    std::uint32_t version = 2;
    std::uint32_t count = 0;
    std::int32_t subscribeResult = 0;
    std::int32_t unsubscribeResult = 0;
    std::uint32_t truncated = 0;
    std::uint32_t probeFlags = 0;
    std::int32_t probeResult = 0;
    Node nodes[MaxNodes]{};
};
inline bool TypeCharacter(char c) {
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
           (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '`';
}
inline bool Valid(const Report& report) {
    if (report.version != 2 || report.count > MaxNodes || report.truncated > 1 || report.probeFlags > 63) return false;
    for (std::uint32_t i = 0; i < report.count; ++i) {
        std::size_t j = 0;
        for (; j < TypeLength && report.nodes[i].type[j]; ++j)
            if (!TypeCharacter(report.nodes[i].type[j])) return false;
        if (j == 0 || j == TypeLength) return false;
    }
    return true;
}
}
