import { GamepadButton, getFocusNavController, type GamepadEvent } from "@decky/ui";
import { useRef, type MouseEvent } from "react";

interface NavNode {
  m_element?: HTMLElement;
  m_Root?: NavNode;
  m_rgChildren?: NavNode[];
  m_rgChildNavTrees?: NavNode[];
  BTakeFocus?: (source: number) => boolean;
}

export function focusLibraryElement(element: HTMLElement): boolean {
  try {
    const controller = getFocusNavController();
    if (typeof controller?.FocusElement === "function") {
      controller.FocusElement(element);
      return true;
    }
    // Current Steam builds require the owning navigation node, rather than DOM focus().
    const pending: NavNode[] = [controller?.GetActiveNavTree?.()];
    const seen = new Set<NavNode>();
    while (pending.length && seen.size < 20000) {
      const node = pending.pop();
      if (!node || seen.has(node)) continue;
      seen.add(node);
      if (node.m_element === element && node.BTakeFocus) return node.BTakeFocus(3);
      if (node.m_Root) pending.push(node.m_Root);
      pending.push(...node.m_rgChildren ?? [], ...node.m_rgChildNavTrees ?? []);
    }
  } catch {
    // A disappearing Steam navigation tree must not break modal dismissal.
  }
  element.focus({ preventScroll: true });
  return element.ownerDocument.activeElement === element;
}

function consume(event: GamepadEvent) {
  event.preventDefault();
  event.stopPropagation();
}

export function useLibraryNavigation(onClose?: () => void) {
  const root = useRef<HTMLDivElement>(null);
  const active = useRef<number | null>(null);
  const remembered = useRef(new Map<number, HTMLElement>());
  const columnOf = (target: EventTarget | null) => {
    const element = target as HTMLElement | null;
    const column = element?.closest?.<HTMLElement>("[data-library-column]");
    return column ? Number(column.dataset.libraryColumn) : null;
  };
  const focusColumn = (index: number) => {
    const column = root.current?.querySelector<HTMLElement>(`[data-library-column="${index}"]`);
    if (!column) return false;
    const previous = remembered.current.get(index);
    const target = previous?.isConnected && column.contains(previous) ? previous : column;
    if (!focusLibraryElement(target)) return false;
    active.current = index;
    return true;
  };
  const onGamepadFocus = (event: GamepadEvent) => {
    const index = columnOf(event.target);
    active.current = index;
    if (index !== null) remembered.current.set(index, event.target as HTMLElement);
  };
  const onClickCapture = (event: MouseEvent<HTMLDivElement>) => {
    const index = columnOf(event.target);
    active.current = index;
    if (index === null) return;
    const target = (event.target as HTMLElement).closest<HTMLElement>('.Focusable,button,input,[tabindex="0"]');
    if (target && root.current?.contains(target)) focusLibraryElement(target);
  };
  const onCancelButton = (event: GamepadEvent) => {
    consume(event);
    if (active.current === null || active.current === 0) onClose?.();
    else focusColumn(active.current - 1);
  };
  const onGamepadDirection = (event: GamepadEvent) => {
    const index = active.current;
    if (index === null) return;
    if ((event.target as HTMLElement)?.closest?.('input,textarea,[role="slider"]')) return;
    const delta = event.detail.button === GamepadButton.DIR_RIGHT ? 1 : event.detail.button === GamepadButton.DIR_LEFT ? -1 : 0;
    const tile = (event.target as HTMLElement)?.closest?.("[data-library-tile]");
    const neighbour = tile && (delta > 0 ? tile.nextElementSibling : tile.previousElementSibling);
    if (neighbour?.matches("[data-library-tile]")) return;
    if (delta && index + delta >= 0 && focusColumn(index + delta)) consume(event);
  };
  return { ref: root, onGamepadFocus, onClickCapture, onCancelButton, onGamepadDirection };
}
