import { findModuleChild } from "@decky/ui";
import type { FC } from "react";

/** Steam's own composition levels; `Notification` keeps Steam's window drawn over a running game. */
export enum UIComposition {
  Hidden = 0,
  Notification = 1,
  Overlay = 2,
  Opaque = 3,
  OverlayKeyboard = 4,
}

type CompositionHook = (composition: UIComposition) => { releaseComposition: () => void };

let cached: CompositionHook | null | undefined;

// Steam's toast layer requests gamescope composition through this hook; matched by the three
// SteamClient calls it makes, the same way decky-steam-pip (BSD-3-Clause) finds it.
function compositionHook(): CompositionHook | null {
  if (cached !== undefined) return cached;
  try {
    cached = findModuleChild((module: Record<string, unknown>) => {
      if (typeof module !== "object" || !module) return undefined;
      for (const key in module) {
        const candidate = module[key];
        if (typeof candidate !== "function") continue;
        const source = candidate.toString();
        if (
          source.includes("AddMinimumCompositionStateRequest")
          && source.includes("ChangeMinimumCompositionStateRequest")
          && source.includes("RemoveMinimumCompositionStateRequest")
          && !source.includes("m_mapCompositionStateRequests")
        ) return candidate;
      }
      return undefined;
    }) ?? null;
  } catch {
    cached = null;
  }
  return cached ?? null;
}

export function canDrawOverGames(): boolean {
  return compositionHook() !== null;
}

const Request: FC<{ hook: CompositionHook; level: UIComposition }> = ({ hook, level }) => {
  hook(level);
  return null;
};

/**
 * Mount while something must stay visible over a game; unmounting releases the request.
 * `Notification` only draws: touch and controller keep going to the game. `Overlay` also takes
 * the controller from the game, as Steam's own menus do.
 */
export const OverGameComposition: FC<{ level?: UIComposition }> = ({ level = UIComposition.Notification }) => {
  const hook = compositionHook();
  return hook ? <Request hook={hook} level={level} /> : null;
};
