import type { FC } from "react";

import type { SectionDef, SectionIcon } from "./types";
import type { LearningTag } from "../learning/logic";

export interface SectionMetadata {
  id: string;
  labelKey: string;
  descriptionKey: string;
  accent: string;
  icon: SectionIcon;
  learningTags?: readonly LearningTag[];
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
