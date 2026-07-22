import { ControllerControl } from "./useController";
import { createSectionContext } from "../sectionContext";

// Mandos' blocks (manager status, remap editor, HHD settings) share ONE controller
// config + scope with the section: the scope tab and the per-game remap are
// cross-block state, so a single owner is correct.
export const [MandosProvider, useMandos] = createSectionContext<ControllerControl>("useMandos");
