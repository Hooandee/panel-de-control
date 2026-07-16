import { FC } from "react";

import { SectionDef } from "./types";
import { TABS } from "../customize/manifest";
import { PotenciaSection } from "./PotenciaSection";
import { SistemaSection } from "./SistemaSection";
import { PantallaSection } from "./PantallaSection";
import { VentiladoresSection } from "./VentiladoresSection";
import { MandosSection } from "./MandosSection";
import { ParametrosSection } from "./ParametrosSection";
import { AjustesSection } from "./AjustesSection";

// Section body per tab id. The tab metadata (order, label, icon) lives in the
// customization manifest (TABS) so the editor can read it without importing the
// section components (which would cycle back through here).
const COMPONENTS: Record<string, FC> = {
  power: PotenciaSection,
  system: SistemaSection,
  display: PantallaSection,
  fans: VentiladoresSection,
  mandos: MandosSection,
  params: ParametrosSection,
  settings: AjustesSection,
};

/**
 * The control-center sections, in default tab order. Single source of truth: the
 * TabBar and the body both read from here. Built from the manifest's TABS +
 * COMPONENTS above — add a section by adding a TABS entry and a component here.
 */
export const SECTIONS: SectionDef[] = TABS.map((tab) => ({
  ...tab,
  Component: COMPONENTS[tab.id],
}));
