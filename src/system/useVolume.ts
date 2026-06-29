import { SystemControl } from "./types";
import { useScalar } from "./useScalar";
import { systemVolume } from "./audio";

/** Current system volume as an integer percent, with a setter. */
export function useVolume(): SystemControl {
  return useScalar(systemVolume);
}
