export const REPORT_CATEGORIES = [
  "tdp",
  "cpu_gpu",
  "hud",
  "fans",
  "display",
  "controllers",
  "battery",
  "system",
  "audio",
  "launch",
  "themes",
  "other",
] as const;

export type ReportCategory = (typeof REPORT_CATEGORIES)[number];

export function toggleCategory(
  selected: ReportCategory[],
  id: ReportCategory,
): ReportCategory[] {
  return selected.includes(id)
    ? selected.filter((x) => x !== id)
    : [...selected, id];
}

export function canSubmit(_selected: ReportCategory[], text: string): boolean {
  return text.trim().length > 0;
}

interface DisplayApi {
  RegisterForBrightnessChanges?: unknown;
  SetBrightness?: unknown;
}

export function displayReportContext(
  selected: ReportCategory[],
  display: unknown,
): Record<string, unknown> {
  if (!selected.includes("display") && !selected.includes("system")) return {};
  const api = (display ?? {}) as DisplayApi;
  return {
    display: {
      brightness: {
        subscribe_available:
          typeof api.RegisterForBrightnessChanges === "function",
        set_available: typeof api.SetBrightness === "function",
      },
    },
  };
}

export function buildReportContext(
  selected: ReportCategory[],
  display: unknown,
  launch: Record<string, unknown>,
  qam: object,
): Record<string, unknown> {
  return {
    ...launch,
    ...displayReportContext(selected, display),
    qam,
  };
}
