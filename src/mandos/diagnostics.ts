export type ControllerAvailability = "supported" | "experimental" | "unavailable";
export type ControllerApply = "hot" | "recreate" | "next_launch" | "read_only";
export type ControllerReadback = "exact" | "accepted" | "observed" | "none";
export type ControllerEvidence = "upstream" | "physical" | "upstream_and_physical" | "unknown";
export type ControllerCapabilityScope = "global" | "game";

export interface ControllerCapabilitySurface {
  owner: string;
  availability: ControllerAvailability;
  fields: Record<string, unknown>;
  scope: ControllerCapabilityScope[];
  apply: ControllerApply;
  readback: ControllerReadback;
  evidence: ControllerEvidence;
  reason?: string;
}

export interface ControllerDiagnosticSource {
  manager: "hhd" | "inputplumber";
  version?: string;
  name?: string;
  source_count?: number;
}

export interface ControllerDiagnosticBattery {
  label: string;
  percent: number;
}

export interface ControllerDiagnosticButton {
  source: string;
  label: string;
}

export interface ControllerDiagnosticOperation {
  operation?: string;
  owner?: string;
  mode?: string;
  ok?: boolean;
  reason?: string;
  enabled?: boolean;
  strength?: number;
  profile_bytes?: number;
  rollback_confirmed?: boolean;
  readback?: boolean;
  echoed_value?: number;
}

export interface ControllerDiagnostics {
  device_key: string | null;
  sources: ControllerDiagnosticSource[];
  batteries: ControllerDiagnosticBattery[];
  inputs: { buttons?: ControllerDiagnosticButton[] };
  motion: ControllerCapabilitySurface | null;
  virtual_controller: ControllerCapabilitySurface | null;
  vibration: ControllerCapabilitySurface | null;
  last_operations: Record<string, ControllerDiagnosticOperation>;
}

export type DiagnosticOperationLabel =
  | "confirmed"
  | "accepted"
  | "observed"
  | "requested"
  | "failed"
  | "unavailable";

export function operationLabel(value: {
  desired?: unknown;
  applied?: boolean;
  readback?: unknown;
}): DiagnosticOperationLabel {
  if (value.applied === true && value.readback === "exact") return "confirmed";
  if (value.applied === true && value.readback === "observed") return "observed";
  if (value.applied === true && value.readback === "accepted") return "accepted";
  if (value.applied === false && value.desired !== undefined) return "requested";
  if (value.applied === false) return "failed";
  if (value.applied === true) return "accepted";
  return "unavailable";
}

export function diagnosticOperationLabel(
  value: ControllerDiagnosticOperation,
): DiagnosticOperationLabel {
  if (value.ok === false) return "failed";
  if (value.ok === true && value.readback === true) return "confirmed";
  if (value.ok === true) return "accepted";
  return "unavailable";
}

export type DiagnosticGroup = "sources" | "batteries" | "inputs" | "motion" | "virtual_controller" | "vibration" | "operations";

export function visibleDiagnosticGroups(value: ControllerDiagnostics): DiagnosticGroup[] {
  const groups: DiagnosticGroup[] = [];
  if (value.sources.length > 0) groups.push("sources");
  if (value.batteries.length > 0) groups.push("batteries");
  if ((value.inputs.buttons?.length ?? 0) > 0) groups.push("inputs");
  if (value.motion) groups.push("motion");
  if (value.virtual_controller) groups.push("virtual_controller");
  if (value.vibration) groups.push("vibration");
  if (Object.keys(value.last_operations).length > 0) groups.push("operations");
  return groups;
}

const AVAILABILITY = new Set<ControllerAvailability>(["supported", "experimental", "unavailable"]);
const APPLY = new Set<ControllerApply>(["hot", "recreate", "next_launch", "read_only"]);
const READBACK = new Set<ControllerReadback>(["exact", "accepted", "observed", "none"]);
const EVIDENCE = new Set<ControllerEvidence>(["upstream", "physical", "upstream_and_physical", "unknown"]);
const SCOPES = new Set<ControllerCapabilityScope>(["global", "game"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isMember<T extends string>(value: unknown, allowed: Set<T>): value is T {
  return typeof value === "string" && allowed.has(value as T);
}

function cleanSurface(value: unknown): ControllerCapabilitySurface | null {
  if (!isRecord(value)) return null;
  const { owner, availability, fields, scope, apply, readback, evidence, reason } = value;
  if (
    typeof owner !== "string" || owner.length === 0
    || !isMember(availability, AVAILABILITY)
    || !isRecord(fields)
    || !Array.isArray(scope) || !scope.every((item) => isMember(item, SCOPES))
    || !isMember(apply, APPLY)
    || !isMember(readback, READBACK)
    || !isMember(evidence, EVIDENCE)
    || (reason !== undefined && (typeof reason !== "string" || reason.length === 0))
  ) return null;
  return {
    owner,
    availability,
    fields,
    scope,
    apply,
    readback,
    evidence,
    ...(typeof reason === "string" ? { reason } : {}),
  };
}

function cleanSources(value: unknown): ControllerDiagnosticSource[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item): ControllerDiagnosticSource[] => {
    if (!isRecord(item) || (item.manager !== "hhd" && item.manager !== "inputplumber")) return [];
    if (item.version !== undefined && typeof item.version !== "string") return [];
    if (item.name !== undefined && typeof item.name !== "string") return [];
    if (
      item.source_count !== undefined
      && (!Number.isInteger(item.source_count) || (item.source_count as number) < 0 || (item.source_count as number) > 64)
    ) return [];
    return [{
      manager: item.manager,
      ...(typeof item.version === "string" ? { version: item.version } : {}),
      ...(typeof item.name === "string" ? { name: item.name } : {}),
      ...(typeof item.source_count === "number" ? { source_count: item.source_count } : {}),
    }];
  });
}

function cleanBatteries(value: unknown): ControllerDiagnosticBattery[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item): ControllerDiagnosticBattery[] => {
    if (
      !isRecord(item) || typeof item.label !== "string"
      || typeof item.percent !== "number" || !Number.isFinite(item.percent)
      || item.percent < 0 || item.percent > 100
    ) return [];
    return [{ label: item.label, percent: item.percent }];
  });
}

function cleanInputs(value: unknown): ControllerDiagnostics["inputs"] {
  if (!isRecord(value) || !Array.isArray(value.buttons)) return {};
  const buttons = value.buttons.flatMap((item): ControllerDiagnosticButton[] => {
    if (!isRecord(item) || typeof item.source !== "string" || typeof item.label !== "string") return [];
    return [{ source: item.source, label: item.label }];
  });
  return buttons.length > 0 ? { buttons } : {};
}

function cleanOperations(value: unknown): Record<string, ControllerDiagnosticOperation> {
  if (!isRecord(value)) return {};
  const operationNames = new Set([
    "discover_composite", "validate_composite", "read_capabilities",
    "read_source_device_paths", "read_profile", "load_profile", "reset_default",
    "read_force_feedback", "set_force_feedback", "rumble", "stop_rumble", "apply_profile",
    "read_supported_target_device_ids", "read_target_devices", "read_target_device_types", "set_target_devices",
    "read_xbox_hd_haptics_support", "read_xbox_hd_haptics", "set_xbox_hd_haptics",
  ]);
  const owners = new Set(["hhd", "inputplumber", "native", "evdev"]);
  const modes = new Set(["dual", "gain", "lenovo_hd", "asus_xbox_hd"]);
  const reasons = new Set([
    "busctl_exit", "composite_ambiguous", "composite_not_found", "config_echo_mismatch",
    "identity_changed", "identity_unavailable", "initial_readback_unavailable", "invalid_response",
    "invalid_value", "load_failed", "merge_failed", "process_unavailable", "profile_conflict",
    "profile_unavailable", "readback_mismatch", "short_write", "unsupported", "write_failed",
    "target_devices_empty", "target_identity_invalid", "target_identity_unavailable",
  ]);
  const result: Record<string, ControllerDiagnosticOperation> = {};
  for (const [key, item] of Object.entries(value)) {
    if (!isRecord(item)) continue;
    if (item.operation !== undefined && !isMember(item.operation, operationNames)) continue;
    if (item.owner !== undefined && !isMember(item.owner, owners)) continue;
    if (item.mode !== undefined && !isMember(item.mode, modes)) continue;
    if (item.reason !== undefined && !isMember(item.reason, reasons)) continue;
    const clean: ControllerDiagnosticOperation = {};
    for (const field of ["operation", "owner", "mode", "reason"] as const) {
      if (typeof item[field] === "string") clean[field] = item[field];
    }
    for (const field of ["ok", "enabled", "rollback_confirmed", "readback"] as const) {
      if (typeof item[field] === "boolean") clean[field] = item[field];
    }
    for (const field of ["strength", "profile_bytes", "echoed_value"] as const) {
      if (typeof item[field] === "number" && Number.isFinite(item[field])) clean[field] = item[field];
    }
    if (Object.keys(clean).length > 0) result[key] = clean;
  }
  return result;
}

export function normalizeControllerDiagnostics(value: unknown): ControllerDiagnostics {
  if (!isRecord(value)) {
    return {
      device_key: null,
      sources: [],
      batteries: [],
      inputs: {},
      motion: null,
      virtual_controller: null,
      vibration: null,
      last_operations: {},
    };
  }
  return {
    device_key: typeof value.device_key === "string" ? value.device_key : null,
    sources: cleanSources(value.sources),
    batteries: cleanBatteries(value.batteries),
    inputs: cleanInputs(value.inputs),
    motion: cleanSurface(value.motion),
    virtual_controller: cleanSurface(value.virtual_controller),
    vibration: cleanSurface(value.vibration),
    last_operations: cleanOperations(value.last_operations),
  };
}
