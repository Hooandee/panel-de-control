import { useEffect, useRef } from "react";

/**
 * A ref that stays true while the component is mounted, re-armed on a StrictMode
 * remount (the cleanup sets it false, the next mount sets it true again). Use it to
 * skip a late async callback — e.g. a setState — after the component unmounts.
 */
export function useMountedRef() {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  return mounted;
}
