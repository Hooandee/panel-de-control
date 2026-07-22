import { ColorControl } from "./useColor";
import { HdrControl } from "./useHdr";
import { NightControl } from "./useNight";
import { createSectionContext } from "../sectionContext";

// Pantalla's blocks (OLED look, color, HDR, night) share ONE useColor/useHdr/
// useNight instance with the section chrome (scope tab, confirm bar, perf note):
// the color scope and the confirm/preview countdown are cross-block state, so a
// single owner is correct. The section provides it; blocks consume it.
export interface PantallaCtx {
  color: ColorControl;
  hdr: HdrControl;
  night: NightControl;
}

export const [PantallaProvider, usePantalla] = createSectionContext<PantallaCtx>("usePantalla");
