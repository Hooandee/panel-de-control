import { recordUiDiagnostic as recordUiDiagnosticRpc } from "../api";

export type UiDiagnosticArea = "cleaner" | "proton" | "media";

let lastRecorded = "";

export function recordUiDiagnostic(area: UiDiagnosticArea, code: string, detail = ""): void {
  const key = `${area}\u0000${code}\u0000${detail}`;
  if (key === lastRecorded) return;
  lastRecorded = key;
  try {
    void Promise.resolve(recordUiDiagnosticRpc(area, code, detail)).catch(() => undefined);
  } catch {}
}
