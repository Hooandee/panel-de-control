import type { CustomView } from "../customize/views";
import { TABS } from "../customize/manifest";
import { viewIconNode } from "../customize/viewIcons";
import { viewTabId } from "../customize/views";
import { sectionAvailable, type SectionAvailability } from "../sections/availability";
import { buildQamViewCatalog, type QamViewSource } from "./viewCatalog";

export function buildPanelQamCatalog(
  views: readonly CustomView[],
  availability?: SectionAvailability & { presentationKeySuffix?: string },
) {
  const customSources: QamViewSource[] = views.map((view) => ({
    id: viewTabId(view.id),
    label: view.name,
    labelKey: "customize.views.namePlaceholder",
    descriptionKey: "customize.views.cardDesc",
    accent: "#586b78",
    icon: (size) => viewIconNode(view.icon, size),
    presentationKey: `${view.name}\u0000${view.icon}`,
  }));
  const tabs = availability
    ? TABS.filter((tab) => sectionAvailable(tab.id, availability))
    : TABS;
  const catalog = buildQamViewCatalog([...tabs, ...customSources]);
  if (!availability?.presentationKeySuffix) return catalog;
  return catalog.map((entry) => ({
    ...entry,
    presentationKey: `${entry.presentationKey ?? ""}\u0000${availability.presentationKeySuffix}`,
  }));
}
