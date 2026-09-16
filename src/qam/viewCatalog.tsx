import { LuSlidersVertical } from "react-icons/lu";

import type { SectionIcon } from "../sections/types";
import { isViewTabId } from "../customize/views";
import { QAM_HOME_TOKEN, type QamEntryToken } from "./layout";

export type QamViewTarget =
  | { kind: "home" }
  | { kind: "section"; id: string };

export interface QamViewDescriptor {
  token: QamEntryToken;
  labelKey: string;
  label?: string;
  descriptionKey: string;
  accent: string;
  icon: SectionIcon;
  target: QamViewTarget;
  presentationKey?: string;
}

export interface QamViewSource {
  id: string;
  labelKey: string;
  label?: string;
  descriptionKey: string;
  accent: string;
  icon: SectionIcon;
  presentationKey?: string;
}

const homeIcon: SectionIcon = (size) => <LuSlidersVertical size={size} />;

export function tokenForSectionId(id: string): QamEntryToken {
  return isViewTabId(id)
    ? `pdc:view:${id.slice("view:".length)}`
    : `pdc:section:${id}`;
}

export function targetForQamToken(token: QamEntryToken): QamViewTarget | null {
  if (token === QAM_HOME_TOKEN) return { kind: "home" };
  if (token.startsWith("pdc:section:") && token.length > "pdc:section:".length) {
    return { kind: "section", id: token.slice("pdc:section:".length) };
  }
  if (token.startsWith("pdc:view:") && token.length > "pdc:view:".length) {
    return { kind: "section", id: `view:${token.slice("pdc:view:".length)}` };
  }
  return null;
}

export function buildQamViewCatalog(sections: readonly QamViewSource[]): QamViewDescriptor[] {
  return [
    {
      token: QAM_HOME_TOKEN,
      labelKey: "app.title",
      descriptionKey: "home.subtitle",
      accent: "#586b78",
      icon: homeIcon,
      target: { kind: "home" },
    },
    ...sections.map((section): QamViewDescriptor => ({
      token: tokenForSectionId(section.id),
      labelKey: section.labelKey,
      label: section.label,
      descriptionKey: section.descriptionKey,
      accent: section.accent,
      icon: section.icon,
      target: { kind: "section", id: section.id },
      presentationKey: section.presentationKey,
    })),
  ];
}
