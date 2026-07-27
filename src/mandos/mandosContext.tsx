import { ControllerControl } from "./useController";
import { createSectionContext } from "../sectionContext";

export const [MandosProvider, useMandos] = createSectionContext<ControllerControl>("useMandos");
