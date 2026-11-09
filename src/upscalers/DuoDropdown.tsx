import { Dropdown } from "@decky/ui";
import { useEffect, useRef, type ReactNode } from "react";
import { createThemeNavigationAccess } from "../themes/runtime/navigationAccess";
import { holdPage } from "./pageMemory";
import { hasDuoOpener, openDuoDropdown, selectDuoDropdown, subscribeDuoDropdown, takeDuoOpener, takeDuoSelection } from "./duoDropdownMemory";

const MENU_SPACING = `
.BasicUIContextMenu:has([data-pdc-up-option]) .contextMenuItem:first-child { margin-top: 0 !important; }
.BasicUIContextMenu:has([data-pdc-up-option]) .contextMenuItem:last-child { margin-bottom: 0 !important; }
`;

const navigation = createThemeNavigationAccess({ allowInactiveContext: true });

export function DuoDropdown<T extends string>({ controlId, label, value, options, onChange, disabled, ready = true, badge }: {
  controlId: string;
  label: string;
  value: T;
  options: { value: T; label: ReactNode }[];
  onChange: (value: T) => void;
  disabled?: boolean;
  ready?: boolean;
  badge?: ReactNode;
}) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = root.current;
    if (!element) return;
    const showIcons = () => {
      element.querySelectorAll<SVGElement>(".pdc-up-mako-icon, .pdc-up-optiscaler-icon, .pdc-up-lossless-icon, .pdc-up-dll-icon")
        .forEach((icon) => icon.style.setProperty("display", "inline-block", "important"));
    };
    showIcons();
    const observer = new MutationObserver(showIcons);
    observer.observe(element, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [value]);
  const current = useRef({ onChange, ready, disabled, options });
  current.current = { onChange, ready, disabled, options };
  useEffect(() => {
    let dispatchTimer: ReturnType<typeof setTimeout>;
    let focusTimer: ReturnType<typeof setTimeout>;
    let alive = true;
    const restoreFocus = () => {
      if (!hasDuoOpener(controlId)) return;
      const deadline = Date.now() + 2000;
      const focus = () => {
        if (!alive) return;
        const target = root.current?.querySelector<HTMLElement>("button, [role=button], .Focusable");
        if (target?.isConnected && navigation.focus(target)) {
          takeDuoOpener(controlId);
          return;
        }
        if (Date.now() < deadline) focusTimer = setTimeout(focus, 50);
      };
      focusTimer = setTimeout(focus, 0);
    };
    const dispatch = () => {
      clearTimeout(dispatchTimer);
      dispatchTimer = setTimeout(() => {
        if (!alive || !current.current.ready || current.current.disabled) return;
        const selected = takeDuoSelection(controlId);
        if (selected !== undefined && current.current.options.some((option) => option.value === selected)) {
          current.current.onChange(selected as T);
        }
        if (selected !== undefined) restoreFocus();
      }, 0);
    };
    const unsubscribe = subscribeDuoDropdown(controlId, dispatch);
    restoreFocus();
    dispatch();
    return () => {
      alive = false;
      unsubscribe();
      clearTimeout(dispatchTimer);
      clearTimeout(focusTimer);
    };
  }, [controlId, ready, disabled]);
  return <div ref={root} data-pdc-duo-dropdown={controlId} aria-label={label} style={{ width: "100%", maxWidth: "100%", minWidth: 0 }}>
    <Dropdown menuLabel={label} selectedOption={value} disabled={disabled || !ready}
      renderButtonValue={(element) => <span style={{ display: "flex", alignItems: "center", justifyContent: badge ? "space-between" : "center", gap: 6, width: "100%", textAlign: "center" }}>{element}{badge && <span style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", flexShrink: 0 }}>{badge}</span>}</span>}
      rgOptions={options.map((option, index) => ({ data: option.value, label: <>{index === 0 && <style>{MENU_SPACING}</style>}<span data-pdc-up-option>{option.label}</span></> }))}
      onMenuWillOpen={(show) => { holdPage(); openDuoDropdown(controlId); show(); }}
      onChange={(option) => selectDuoDropdown(controlId, option.data)} />
  </div>;
}
