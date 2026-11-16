const MISSING_BACKEND_METHOD = /Plugin object has no attribute/i;

export type StaleBackendSink = (detail: string) => void;

let sink: StaleBackendSink | null = null;
let reported = false;

export function setStaleBackendSink(next: StaleBackendSink | null): void {
  sink = next;
  reported = false;
}

export function isMissingBackendMethod(error: unknown): boolean {
  const message = error instanceof Error ? error.message : typeof error === "string" ? error : "";
  return MISSING_BACKEND_METHOD.test(message);
}

export function reportStaleBackend(error: unknown): boolean {
  if (!isMissingBackendMethod(error)) return false;
  if (sink && !reported) {
    reported = true;
    const detail = error instanceof Error ? error.message : String(error);
    try { sink(detail); } catch {}
  }
  return true;
}
