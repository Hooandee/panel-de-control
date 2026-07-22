import { createContext, useContext } from "react";
import { ColorControl } from "./useColor";
import { HdrControl } from "./useHdr";
import { NightControl } from "./useNight";

// Pantalla's blocks (OLED look, color, HDR, night) share ONE useColor/useHdr/
// useNight instance with the section chrome (scope tab, confirm bar, perf note):
// the color scope and the confirm/preview countdown are cross-block state, so a
// single owner is the correct model. The section provides it; blocks consume it
// instead of each mounting its own (which would diverge the optimistic state and
// double the polls).
export interface PantallaCtx {
  color: ColorControl;
  hdr: HdrControl;
  night: NightControl;
}

const Ctx = createContext<PantallaCtx | null>(null);
export const PantallaProvider = Ctx.Provider;

/** The shared Pantalla controls. Only valid inside <PantallaProvider> (the
 *  Pantalla section / a custom view that hosts these blocks). */
export function usePantalla(): PantallaCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("usePantalla outside PantallaProvider");
  return c;
}
