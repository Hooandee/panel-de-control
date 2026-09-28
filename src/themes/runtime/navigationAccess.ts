export type ThemeExtensionNavigationAction = "up" | "down" | "confirm" | "cancel";

export interface ThemeExtensionNavigationAccess {
  focus(element: HTMLElement): boolean;
  capture(handler: (action: ThemeExtensionNavigationAction) => void): () => void;
}

interface NavigationButtons {
  up: number;
  down: number;
  confirm: number;
  cancel: number;
}

interface NavigationController {
  GetActiveNavTree?(): NavigationTree | null;
  FocusElement?(element: HTMLElement): unknown;
}

interface NavigationNode {
  m_element?: unknown;
  m_rgChildren?: unknown;
  BTakeFocus?(source?: number): unknown;
}

interface NavigationTree {
  m_Root?: NavigationNode | null;
  m_rgChildNavTrees?: unknown;
  RegisterGlobalButtonHandler?(
    button: number,
    handler: (event?: unknown) => boolean,
  ): unknown;
}

interface ThemeNavigationAccessDependencies {
  getController?(): NavigationController | null | undefined;
  buttons?: Readonly<NavigationButtons>;
}

const DEFAULT_BUTTONS: Readonly<NavigationButtons> = Object.freeze({
  up: 9,
  down: 10,
  confirm: 1,
  cancel: 2,
});

function getSteamNavigationController(): NavigationController | null | undefined {
  const scope = globalThis as typeof globalThis & {
    FocusNavController?: NavigationController;
    GamepadNavTree?: { m_context?: { m_controller?: NavigationController } };
  };
  return scope.GamepadNavTree?.m_context?.m_controller ?? scope.FocusNavController;
}

const MAX_SEARCHED_NODES = 20_000;
const GAMEPAD_FOCUS_SOURCE = 3;

// Steam no longer exposes FocusElement and ignores DOM focus(); only the owning node moves focus.
function findNavigationNode(tree: NavigationTree, element: HTMLElement): NavigationNode | null {
  const pending: unknown[] = [tree];
  const seen = new Set<unknown>();
  let searched = 0;
  while (pending.length > 0 && searched < MAX_SEARCHED_NODES) {
    const current = pending.pop();
    if (!current || typeof current !== "object" || seen.has(current)) continue;
    seen.add(current);
    searched += 1;
    const candidate = current as NavigationNode & NavigationTree;
    if (candidate.m_element === element) return candidate;
    if (candidate.m_Root) pending.push(candidate.m_Root);
    for (const list of [candidate.m_rgChildren, candidate.m_rgChildNavTrees]) {
      if (Array.isArray(list)) pending.push(...list);
    }
  }
  return null;
}

function focusThroughNavigationNode(
  controller: NavigationController | null | undefined,
  element: HTMLElement,
): boolean {
  const tree = controller?.GetActiveNavTree?.();
  if (!tree) return false;
  const node = findNavigationNode(tree, element);
  if (typeof node?.BTakeFocus !== "function") return false;
  return Boolean(node.BTakeFocus(GAMEPAD_FOCUS_SOURCE));
}

function consumeInput(event: unknown): void {
  if (!event || typeof event !== "object") return;
  for (const method of ["preventDefault", "stopPropagation", "stopImmediatePropagation"] as const) {
    const callback = Reflect.get(event, method);
    if (typeof callback === "function") callback.call(event);
  }
}

export function createThemeNavigationAccess({
  getController = getSteamNavigationController,
  buttons = DEFAULT_BUTTONS,
}: ThemeNavigationAccessDependencies = {}): Readonly<ThemeExtensionNavigationAccess> {
  return Object.freeze({
    focus(element: HTMLElement): boolean {
      let hostFocused = false;
      try {
        const controller = getController();
        if (typeof controller?.FocusElement === "function") {
          controller.FocusElement(element);
          hostFocused = true;
        } else if (focusThroughNavigationNode(controller, element)) {
          return true;
        }
      } catch {
        hostFocused = false;
      }
      try {
        element.focus({ preventScroll: true });
      } catch {
        return hostFocused;
      }
      return hostFocused || element.ownerDocument.activeElement === element;
    },
    capture(handler: (action: ThemeExtensionNavigationAction) => void): () => void {
      let tree: NavigationTree | null | undefined;
      try {
        tree = getController()?.GetActiveNavTree?.();
      } catch {
        return () => {};
      }
      const register = tree?.RegisterGlobalButtonHandler;
      if (!tree || typeof register !== "function") return () => {};
      const releases: Array<() => void> = [];
      const bindings: readonly [number, ThemeExtensionNavigationAction][] = [
        [buttons.up, "up"],
        [buttons.down, "down"],
        [buttons.confirm, "confirm"],
        [buttons.cancel, "cancel"],
      ];
      try {
        for (const [button, action] of bindings) {
          const release = register.call(tree, button, (event?: unknown) => {
            consumeInput(event);
            handler(action);
            return true;
          });
          if (typeof release === "function") releases.push(release as () => void);
        }
      } catch {
        for (const release of releases.splice(0).reverse()) release();
        return () => {};
      }
      let active = true;
      return () => {
        if (!active) return;
        active = false;
        for (const release of releases.splice(0).reverse()) release();
      };
    },
  });
}
