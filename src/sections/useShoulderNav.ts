import { useEffect, useRef } from "react";
import { cycleTab } from "./nav";

// L1 / R1 in Steam's controller-input button enum (ControllerInputGamepadButton
// GAMEPAD_BUTTON_LSHOULDER / RSHOULDER — the enum isn't re-exported by @decky/ui).
const LSHOULDER = 30;
const RSHOULDER = 31;

/**
 * Cycle the tab bar with the shoulder buttons (L1 = previous, R1 = next) while
 * the panel is open. The listener is registered once; the live tab list and
 * active id are read through refs so it never re-registers on a render. Degrades
 * silently when the input API is absent (touch/gamepad focus navigation still
 * works).
 */
export function useShoulderNav(
  ids: string[],
  activeId: string,
  onSelect: (id: string) => void,
): void {
  const idsRef = useRef(ids);
  const activeRef = useRef(activeId);
  const selectRef = useRef(onSelect);
  useEffect(() => {
    idsRef.current = ids;
    activeRef.current = activeId;
    selectRef.current = onSelect;
  });

  useEffect(() => {
    let reg: { unregister?: () => void } | null = null;
    try {
      const input = SteamClient?.Input;
      if (!input || typeof input.RegisterForControllerInputMessages !== "function") return;
      reg = input.RegisterForControllerInputMessages((_idx: number, button: number, pressed: boolean) => {
        if (!pressed || (button !== LSHOULDER && button !== RSHOULDER)) return;
        const next = cycleTab(idsRef.current, activeRef.current, button === RSHOULDER ? 1 : -1);
        if (next !== activeRef.current) selectRef.current(next);
      });
    } catch {
      /* input API unavailable — no shoulder navigation */
    }
    return () => {
      try {
        reg?.unregister?.();
      } catch {
        /* ignore */
      }
    };
  }, []);
}
