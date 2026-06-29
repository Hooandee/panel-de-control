import { LuGauge, LuSlidersHorizontal, LuSettings } from "react-icons/lu";

import { SectionDef } from "./types";
import { PotenciaSection } from "./PotenciaSection";
import { SistemaSection } from "./SistemaSection";
import { AjustesSection } from "./AjustesSection";

/**
 * The control-center sections, in tab order. Single source of truth: the TabBar
 * and the body both read from here. Add a future section (Ventiladores,
 * Perfiles) by appending one entry.
 */
export const SECTIONS: SectionDef[] = [
  { id: "power", icon: <LuGauge size={15} />, labelKey: "nav.power", Component: PotenciaSection },
  { id: "system", icon: <LuSlidersHorizontal size={15} />, labelKey: "nav.system", Component: SistemaSection },
  { id: "settings", icon: <LuSettings size={15} />, labelKey: "nav.settings", Component: AjustesSection },
];
