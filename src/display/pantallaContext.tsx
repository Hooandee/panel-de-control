import { ColorControl } from "./useColor";
import { HdrControl } from "./useHdr";
import { NightControl } from "./useNight";
import { createSectionContext } from "../sectionContext";

export interface PantallaCtx {
  color: ColorControl;
  hdr: HdrControl;
  night: NightControl;
}

export const [PantallaProvider, usePantalla] = createSectionContext<PantallaCtx>("usePantalla");
