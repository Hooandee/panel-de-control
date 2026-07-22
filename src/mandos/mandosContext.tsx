import { createContext, useContext } from "react";
import { ControllerControl } from "./useController";

// Mandos' blocks (manager status, remap editor, HHD settings) share ONE controller
// config + scope with the section: the scope tab and the per-game remap are
// cross-block state, so a single owner is correct. The section provides it; blocks
// consume it instead of each mounting its own (which would diverge / double-fetch).
const Ctx = createContext<ControllerControl | null>(null);
export const MandosProvider = Ctx.Provider;

/** The shared controller controls. Only valid inside <MandosProvider>. */
export function useMandos(): ControllerControl {
  const c = useContext(Ctx);
  if (!c) throw new Error("useMandos outside MandosProvider");
  return c;
}
