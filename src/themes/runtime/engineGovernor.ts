import type { MotionIntensity } from "./obsidianConfig";

export type EngineBudget = "suspended" | "efficient" | "balanced" | "cinematic";

interface MotionMedia {
  matches: boolean;
  addEventListener(name: "change", listener: () => void): void;
  removeEventListener(name: "change", listener: () => void): void;
}

interface EngineGovernorOptions {
  doc: Document;
  performance: boolean;
  motionIntensity: MotionIntensity;
  onBudget(budget: EngineBudget): void;
  media?: MotionMedia;
}

export function startEngineGovernor({
  doc,
  performance,
  motionIntensity,
  onBudget,
  media = doc.defaultView?.matchMedia?.("(prefers-reduced-motion: reduce)"),
}: EngineGovernorOptions): () => void {
  let current: EngineBudget | null = null;
  let stopped = false;
  const refresh = () => {
    if (stopped) return;
    const next: EngineBudget = doc.hidden
      ? "suspended"
      : performance || media?.matches
        ? "efficient"
        : motionIntensity === "reduced"
          ? "balanced"
          : "cinematic";
    if (next === current) return;
    current = next;
    onBudget(next);
  };

  doc.addEventListener("visibilitychange", refresh);
  media?.addEventListener("change", refresh);
  refresh();
  return () => {
    if (stopped) return;
    stopped = true;
    doc.removeEventListener("visibilitychange", refresh);
    media?.removeEventListener("change", refresh);
  };
}
