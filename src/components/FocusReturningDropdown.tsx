import { useRef, type ComponentProps, type FC } from "react";
import { DropdownItem, Menu, MenuItem, showContextMenu, type SingleDropdownOption } from "@decky/ui";
import { getQamDocument } from "../qamDocument";
import { createThemeNavigationAccess } from "../themes/runtime/navigationAccess";

const navigation = createThemeNavigationAccess({ allowInactiveContext: true });
const ATTRIBUTE = "data-pdc-performance-dropdown";

type Props = Omit<ComponentProps<typeof DropdownItem>, "rgOptions" | "onMenuWillOpen" | "onMenuOpened"> & {
  controlId: string;
  rgOptions: SingleDropdownOption[];
};

function restoreDropdownFocus(original: HTMLElement, controlId: string, opener: HTMLElement | null): void {
  const view = original.ownerDocument.defaultView;
  if (!view) return;
  const deadline = Date.now() + 2000;
  const attempt = () => {
    const doc = getQamDocument() ?? original.ownerDocument;
    const root = original.isConnected ? original : Array.from(doc.querySelectorAll<HTMLElement>(`[${ATTRIBUTE}]`))
      .find((candidate) => candidate.getAttribute(ATTRIBUTE) === controlId);
    const target = opener?.isConnected ? opener : root?.querySelector<HTMLElement>("button, [role=button]");
    const moved = doc.querySelector<HTMLElement>(".pdc-root .gpfocus");
    if (moved && moved !== target && !root?.contains(moved)) return;
    if (target) {
      navigation.focus(target);
      if (target.classList.contains("gpfocus")) return;
    }
    if (Date.now() < deadline) view.setTimeout(attempt, 50);
  };
  view.setTimeout(attempt, 0);
}

export const FocusReturningDropdown: FC<Props> = ({ controlId, rgOptions, ...props }) => {
  const root = useRef<HTMLDivElement>(null);
  const open = () => {
    const element = root.current;
    if (!element || props.disabled) return false;
    const opener = element.querySelector<HTMLElement>(".gpfocus")
      ?? element.querySelector<HTMLElement>("button, [role=button]");
    let closed = false;
    let menu: ReturnType<typeof showContextMenu> | undefined;
    const close = () => {
      if (closed) return;
      closed = true;
      menu?.Hide();
      restoreDropdownFocus(element, controlId, opener);
    };
    menu = showContextMenu(
      <Menu label={props.menuLabel ?? (typeof props.label === "string" ? props.label : "")} onCancel={close}>
        {rgOptions.map((option, index) => <MenuItem key={index} selected={option.data === props.selectedOption} onSelected={() => {
          if (closed) return;
          close();
          props.onChange?.(option);
        }}>{option.label}</MenuItem>)}
      </Menu>,
      opener ?? element,
      props.contextMenuPositionOptions,
    );
    return false;
  };
  return <div ref={root} data-pdc-performance-dropdown={controlId}>
    <DropdownItem {...props} rgOptions={rgOptions} onMenuWillOpen={open} />
  </div>;
};
