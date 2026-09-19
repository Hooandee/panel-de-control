type DiagnosticScalar = string | number | boolean | null;
type DiagnosticValue = DiagnosticScalar | DiagnosticValue[] | { [key: string]: DiagnosticValue };

export type SteamPerformanceDiagnosticData = Record<string, DiagnosticValue>;

export interface SteamPerformanceDiagnosticEvent {
  sequence: number;
  area: string;
  data: SteamPerformanceDiagnosticData;
}

export interface SteamPerformanceDiagnosticSnapshot {
  schema: 1;
  current: Record<string, SteamPerformanceDiagnosticData>;
  events: SteamPerformanceDiagnosticEvent[];
}

let current: Record<string, SteamPerformanceDiagnosticData> = {};
let events: SteamPerformanceDiagnosticEvent[] = [];
let sequence = 0;
const signatures = new Map<string, string>();
const MAX_EVENTS = 24;

const cleanText = (value: string, limit = 240): string => (
  value.replace(/\s+/g, " ").trim().slice(0, limit)
);
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(
  value,
  (_key, item) => typeof item === "string" ? cleanText(item) : item,
)) as T;

export function steamPerformanceError(error: unknown): SteamPerformanceDiagnosticData {
  try {
    if (error instanceof Error) {
      return {
        name: cleanText(String(error.name || "Error"), 80),
        message: cleanText(String(error.message)),
      };
    }
    return {
      name: "UnknownError",
      message: cleanText(String(error)),
    };
  } catch {
    return {
      name: "UnknownError",
      message: "unreadable thrown value",
    };
  }
}

export function recordSteamPerformanceDiagnostic(
  area: string,
  data: SteamPerformanceDiagnosticData,
): void {
  try {
    const normalized = clone(data);
    const signature = JSON.stringify(normalized);
    if (signatures.get(area) === signature) return;
    signatures.set(area, signature);
    current = {
      ...current,
      [area]: normalized,
    };
    sequence += 1;
    events = [...events, { sequence, area, data: normalized }].slice(-MAX_EVENTS);
  } catch {}
}

export function steamPerformanceDiagnostics(): SteamPerformanceDiagnosticSnapshot | null {
  if (Object.keys(current).length === 0) return null;
  return {
    schema: 1,
    current: clone(current),
    events: clone(events),
  };
}

export function resetSteamPerformanceDiagnostics(): void {
  current = {};
  events = [];
  sequence = 0;
  signatures.clear();
}
