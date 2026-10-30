interface NavigationTree {
  RegisterGlobalButtonHandler?(button: number, handler: (event?: unknown) => boolean): unknown;
}

interface NavigationController {
  GetActiveNavTree?(): NavigationTree | null;
  SetCatchAllGamepadInput?(callback: (button: number, down: boolean, repeat: boolean) => boolean): { Unregister?(): void } | undefined;
}

const STEAM_GUIDE = 27;
const QUICK_ACCESS = 28;

function steamNavigationController(): NavigationController | null | undefined {
  const scope = globalThis as typeof globalThis & {
    FocusNavController?: NavigationController;
    GamepadNavTree?: { m_context?: { m_controller?: NavigationController } };
  };
  return scope.GamepadNavTree?.m_context?.m_controller ?? scope.FocusNavController;
}

function consume(event: unknown): void {
  if (!event || typeof event !== "object") return;
  for (const method of ["preventDefault", "stopPropagation", "stopImmediatePropagation"] as const) {
    const callback = Reflect.get(event, method);
    if (typeof callback === "function") callback.call(event);
  }
}

function registerOn(tree: NavigationTree, buttons: readonly number[], handler: (button: number) => void): (() => void) | null {
  const register = tree.RegisterGlobalButtonHandler;
  if (typeof register !== "function") return null;
  const releases: (() => void)[] = [];
  try {
    for (const button of buttons) {
      const release = register.call(tree, button, (event?: unknown) => {
        consume(event);
        handler(button);
        return true;
      });
      if (typeof release === "function") releases.push(release as () => void);
    }
  } catch {
    for (const release of releases.splice(0).reverse()) release();
    return null;
  }
  return () => {
    for (const release of releases.splice(0).reverse()) release();
  };
}

const FOLLOW_MS = 150;

/**
 * Steam asks catch-all callbacks before it hands a button to the focused element, so a focused
 * game tile behind the card never sees A. Steam and QAM still reach Steam; every other button is
 * held back while the capture lasts.
 */
function catchAllButtons(
  controller: NavigationController | null | undefined,
  buttons: readonly number[],
  handler: (button: number) => void,
): (() => void) | null {
  if (typeof controller?.SetCatchAllGamepadInput !== "function") return null;
  let registration: { Unregister?(): void } | undefined;
  try {
    registration = controller.SetCatchAllGamepadInput((button, down, repeat) => {
      if (button === STEAM_GUIDE || button === QUICK_ACCESS) return false;
      if (down && !repeat && buttons.includes(button)) handler(button);
      return true;
    });
  } catch {
    return null;
  }
  const unregister = registration?.Unregister;
  if (typeof unregister !== "function") return null;
  return () => unregister.call(registration);
}

/**
 * Takes the given controller buttons from Steam's active navigation tree until released, whatever
 * brand the controller is: Steam hands every pad to the UI with the same button codes. Steam and
 * QAM stay with Steam because they are never registered here.
 *
 * Steam switches its active tree a moment after the QAM closes (and whenever another of its
 * windows takes over), so the capture moves to whichever tree is active while it lasts.
 */
export function captureButtons(
  buttons: readonly number[],
  handler: (button: number) => void,
  getController: () => NavigationController | null | undefined = steamNavigationController,
  schedule: (tick: () => void, ms: number) => () => void = (tick, ms) => {
    const timer = setInterval(tick, ms);
    return () => clearInterval(timer);
  },
): () => void {
  let controller: NavigationController | null | undefined;
  try {
    controller = getController();
  } catch {
    controller = null;
  }
  const catchAll = catchAllButtons(controller, buttons, handler);
  if (catchAll) return catchAll;
  let tree: NavigationTree | null = null;
  let release: (() => void) | null = null;
  const follow = () => {
    let active: NavigationTree | null | undefined;
    try {
      active = getController()?.GetActiveNavTree?.();
    } catch {
      return;
    }
    if (!active || active === tree) return;
    release?.();
    tree = active;
    release = registerOn(active, buttons, handler);
  };
  follow();
  const stopFollowing = schedule(follow, FOLLOW_MS);
  return () => {
    stopFollowing();
    release?.();
    release = null;
    tree = null;
  };
}
