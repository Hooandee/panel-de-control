import { SystemControl } from "./types";
import { useScalar } from "./useScalar";
import { displayBrightness } from "./display";

/** Current screen brightness as an integer percent, with a setter. */
export function useBrightness(): SystemControl {
  return useScalar(displayBrightness);
}
