import { recordUiDiagnostic as recordUiDiagnosticRpc } from "../api";

export type UiDiagnosticArea = "cleaner" | "proton" | "media";

export function recordUiDiagnostic(area: UiDiagnosticArea, code: string, detail = ""): void {
  try {
    void Promise.resolve(recordUiDiagnosticRpc(area, code, detail)).catch(() => undefined);
  } catch {}
}
