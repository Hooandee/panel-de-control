import { describe, expect, it } from "vitest";

import {
  normalizeControllerDiagnostics,
  diagnosticOperationLabel,
  operationLabel,
  visibleDiagnosticGroups,
  type ControllerDiagnostics,
} from "./diagnostics";

const emptyDiagnostics: ControllerDiagnostics = {
  device_key: "generic",
  sources: [],
  batteries: [],
  inputs: {},
  motion: null,
  virtual_controller: null,
  vibration: null,
  last_operations: {},
};

describe("controller diagnostics presentation", () => {
  it("does not label requested vibration as confirmed", () => {
    expect(operationLabel({ desired: 70, applied: false, readback: null }))
      .toEqual("requested");
  });

  it("omits empty diagnostic groups", () => {
    expect(visibleDiagnosticGroups(emptyDiagnostics)).toEqual([]);
  });

  it("does not turn accepted writes into physical confirmation", () => {
    expect(operationLabel({ desired: 70, applied: true, readback: "accepted" }))
      .toEqual("accepted");
  });

  it("only marks an operation confirmed when it has real readback", () => {
    expect(diagnosticOperationLabel({ ok: true })).toEqual("accepted");
    expect(diagnosticOperationLabel({ ok: true, readback: true })).toEqual("confirmed");
    expect(diagnosticOperationLabel({ ok: false })).toEqual("failed");
  });

  it("rejects unknown capability unions at runtime", () => {
    const normalized = normalizeControllerDiagnostics({
      ...emptyDiagnostics,
      vibration: {
        owner: "native",
        availability: "future-value",
        fields: { mode: "dual" },
        scope: ["global"],
        apply: "hot",
        readback: "exact",
        evidence: "physical",
      },
    });

    expect(normalized.vibration).toBeNull();
    expect(visibleDiagnosticGroups(normalized)).toEqual([]);
  });

  it("keeps exact valid fields and omits empty groups", () => {
    const normalized = normalizeControllerDiagnostics({
      ...emptyDiagnostics,
      sources: [{ manager: "inputplumber", version: "0.78", source_count: 3 }],
      inputs: { buttons: [{ source: "LeftPaddle1", label: "M2" }] },
      virtual_controller: {
        owner: "inputplumber",
        availability: "supported",
        fields: { actual_mode: "xbox-elite", readiness: "dbus_target_type" },
        scope: ["global", "game"],
        apply: "recreate",
        readback: "exact",
        evidence: "upstream",
      },
      vibration: {
        owner: "native",
        availability: "supported",
        fields: { mode: "dual", left: 35, right: 45 },
        scope: ["global", "game"],
        apply: "hot",
        readback: "exact",
        evidence: "upstream_and_physical",
      },
    });

    expect(normalized.sources).toEqual([
      { manager: "inputplumber", version: "0.78", source_count: 3 },
    ]);
    expect(visibleDiagnosticGroups(normalized)).toEqual([
      "sources", "inputs", "virtual_controller", "vibration",
    ]);
  });

  it("drops operations containing unknown semantic values", () => {
    const normalized = normalizeControllerDiagnostics({
      ...emptyDiagnostics,
      last_operations: {
        vibration: { operation: "invented_operation", ok: true },
      },
    });

    expect(normalized.last_operations).toEqual({});
  });

  it("keeps Lenovo HD vibration operations", () => {
    const normalized = normalizeControllerDiagnostics({
      ...emptyDiagnostics,
      last_operations: {
        vibration: {
          mode: "lenovo_hd",
          ok: false,
          reason: "write_failed",
          rollback_confirmed: false,
          readback: false,
        },
      },
    });

    expect(normalized.last_operations.vibration).toEqual({
      mode: "lenovo_hd",
      ok: false,
      reason: "write_failed",
      rollback_confirmed: false,
      readback: false,
    });
  });

  it("keeps Xbox HD vibration and manager operations", () => {
    const normalized = normalizeControllerDiagnostics({
      ...emptyDiagnostics,
      last_operations: {
        manager: {
          operation: "set_xbox_hd_haptics",
          ok: true,
        },
        vibration: {
          mode: "asus_xbox_hd",
          ok: true,
          readback: true,
        },
      },
    });

    expect(normalized.last_operations).toEqual({
      manager: {
        operation: "set_xbox_hd_haptics",
        ok: true,
      },
      vibration: {
        mode: "asus_xbox_hd",
        ok: true,
        readback: true,
      },
    });
  });
});
