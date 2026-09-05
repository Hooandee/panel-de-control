import type { FC, ReactNode } from "react";

import type { SectionDef } from "./types";

export interface SectionMetadata {
  id: string;
  labelKey: string;
  icon: ReactNode;
}

export function buildSections(
  tabs: readonly SectionMetadata[],
  components: Readonly<Record<string, FC | undefined>>,
): SectionDef[] {
  return tabs.map((tab) => {
    const Component = components[tab.id];
    if (!Component) throw new Error(`Missing component for section: ${tab.id}`);
    return { ...tab, Component };
  });
}
