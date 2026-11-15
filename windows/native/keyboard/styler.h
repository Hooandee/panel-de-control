#pragma once
#include "common.h"

namespace keyboard {
bool BeginStyleSession() noexcept;
void ObserveStyle(IXamlDiagnostics* diagnostics, InstanceHandle handle) noexcept;
void RenewStyleLease() noexcept;
void StopStyleSession() noexcept;
void ReadStyleSession(Report& report) noexcept;
}
