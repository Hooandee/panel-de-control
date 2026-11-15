#pragma once
#include "common.h"

namespace keyboard {
bool BeginFaceProbe() noexcept;
void ObserveFace(IXamlDiagnostics* diagnostics, InstanceHandle handle) noexcept;
void ReadFaceProbe(Report& report) noexcept;
}
