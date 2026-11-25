import { createContext, useContext, useEffect } from "react";

export interface SectionBackOverride {
  label: string;
  onBack: () => void;
}

interface SectionBackValue {
  /** Whether the shell header is on screen to carry the override. */
  shown: boolean;
  set: (override: SectionBackOverride | null) => void;
}

export const SectionBackContext = createContext<SectionBackValue | null>(null);

/** Lets a section's sub-view borrow the shell's back action; returns false when it must draw its own. */
export function useSectionBack(override: SectionBackOverride | null): boolean {
  const ctx = useContext(SectionBackContext);
  const label = override?.label;
  const onBack = override?.onBack;
  useEffect(() => {
    if (!ctx) return;
    ctx.set(label && onBack ? { label, onBack } : null);
    return () => ctx.set(null);
  }, [ctx?.set, label, onBack]);
  return Boolean(ctx?.shown);
}
