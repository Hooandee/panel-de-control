// Decky raises a backend AttributeError as name "Python Exception" with an empty message; the text
// ('Plugin' object has no attribute 'x', quoted) only lives in pythonTraceback.
const MISSING_BACKEND_METHOD = /'?Plugin'? object has no attribute[^\n]*/i;

export type StaleBackendSink = (detail: string) => void;

let sink: StaleBackendSink | null = null;
let reported = false;

export function setStaleBackendSink(next: StaleBackendSink | null): void {
  sink = next;
  reported = false;
}

function errorText(error: unknown): string {
  if (typeof error === "string") return error;
  if (!(error instanceof Error)) return "";
  const traceback = (error as Error & { pythonTraceback?: unknown }).pythonTraceback;
  return typeof traceback === "string" && traceback ? `${error.message} ${traceback}`.trim() : error.message;
}

export function isMissingBackendMethod(error: unknown): boolean {
  return MISSING_BACKEND_METHOD.test(errorText(error));
}

export function reportStaleBackend(error: unknown): boolean {
  if (!isMissingBackendMethod(error)) return false;
  if (sink && !reported) {
    reported = true;
    const detail = errorText(error).match(MISSING_BACKEND_METHOD)?.[0].trim() ?? "";
    try { sink(detail); } catch {}
  }
  return true;
}
