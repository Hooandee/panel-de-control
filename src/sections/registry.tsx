import { FC } from "react";

import { SectionDef } from "./types";
import { TABS } from "../customize/manifest";
import { PotenciaSection } from "./PotenciaSection";
import { SistemaSection } from "./SistemaSection";
import { PantallaSection } from "./PantallaSection";
import { VentiladoresSection } from "./VentiladoresSection";
import { SonidoSection } from "./SonidoSection";
import { MandosSection } from "./MandosSection";
import { HudSection } from "./HudSection";
import { ParametrosSection } from "./ParametrosSection";
import { LimpiezaSection } from "./LimpiezaSection";
import { AmbienteSection } from "./AmbienteSection";
import { TemasSection } from "./TemasSection";
import { AjustesSection } from "./AjustesSection";
import { buildSections } from "./registryModel";
import { registerSystemBlocks } from "./systemBlocks";
import { registerFanBlocks } from "./fanBlocks";
import { registerDisplayBlocks } from "./displayBlocks";
import { registerMandosBlocks } from "./mandosBlocks";
import { registerPowerBlocks } from "./powerBlocks";

// Called functions, not bare side-effect imports (which get tree-shaken away).
registerSystemBlocks();
registerFanBlocks();
registerDisplayBlocks();
registerMandosBlocks();
registerPowerBlocks();

const COMPONENTS: Record<string, FC> = {
  power: PotenciaSection,
  system: SistemaSection,
  display: PantallaSection,
  fans: VentiladoresSection,
  audio: SonidoSection,
  mandos: MandosSection,
  hud: HudSection,
  params: ParametrosSection,
  cleaner: LimpiezaSection,
  ambient: AmbienteSection,
  themes: TemasSection,
  settings: AjustesSection,
};

export const SECTIONS: SectionDef[] = buildSections(TABS, COMPONENTS);
