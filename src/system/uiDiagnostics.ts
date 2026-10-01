import { recordUiDiagnostic as recordUiDiagnosticRpc } from "../api";

export type UiDiagnosticArea = "cleaner" | "proton" | "media" | "frontend";

const PANEL_BUNDLE = /Panel(?:%20| )de(?:%20| )Control/;

export function recordUiDiagnostic(area: UiDiagnosticArea, code: string, detail = ""): void {
  try {
    void Promise.resolve(recordUiDiagnosticRpc(area, code, detail)).catch(() => undefined);
  } catch {}
}

export function describeError(where: string, error: unknown): { code: string; detail: string } {
  const name = error instanceof Error ? error.name : typeof error;
  const code = name.replace(/([a-z0-9])([A-Z])/g, "$1_$2").replace(/[^a-zA-Z0-9_]/g, "_").toLowerCase().slice(0, 48) || "unknown";
  const message = error instanceof Error ? error.message : String(error);
  const stack = error instanceof Error && typeof error.stack === "string" ? error.stack : "";
  const frame = stack.split("\n").map((line) => line.trim()).find((line) => PANEL_BUNDLE.test(line)) ?? "";
  const location = frame.replace(/^at\s+/, "").replace(/\(?https?:\/\/[^)\s]*\/([^/)\s]+:\d+:\d+)\)?/, "$1");
  return { code: /^[a-z]/.test(code) ? code : `e_${code}`.slice(0, 48), detail: `${where}: ${message} ${location}`.trim() };
}

/** Steam and other plugins share this window: only errors from Panel's bundle count. */
export function startFrontendErrorReporting(target: Window): () => void {
  const report = (error: unknown, source: string) => {
    const stack = error instanceof Error && typeof error.stack === "string" ? error.stack : "";
    if (!PANEL_BUNDLE.test(stack) && !PANEL_BUNDLE.test(source)) return;
    const { code, detail } = describeError("async", error);
    recordUiDiagnostic("frontend", code, detail);
  };
  const onError = (event: ErrorEvent) => report(event.error ?? event.message, event.filename ?? "");
  const onRejection = (event: PromiseRejectionEvent) => report(event.reason, "");
  target.addEventListener("error", onError);
  target.addEventListener("unhandledrejection", onRejection);
  return () => {
    target.removeEventListener("error", onError);
    target.removeEventListener("unhandledrejection", onRejection);
  };
}
