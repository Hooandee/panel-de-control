import { FC, ReactNode } from "react";
import type { LearningTag } from "../learning/logic";

export type SectionIcon = (size: number) => ReactNode;

export interface SectionDef {
  id: string;
  icon: SectionIcon;
  labelKey: string;
  descriptionKey: string;
  accent: string;
  label?: string;
  learningTags?: readonly LearningTag[];
  Component: FC;
}
