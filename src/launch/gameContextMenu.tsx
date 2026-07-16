import { afterPatch, findInReactTree, findModuleChild, MenuItem, Patch } from "@decky/ui";

import { openLaunchEditorModal } from "../components/LaunchEditorModal";
import { GameEntry } from "./steamApi";
import { stableGameKey, isNonSteam } from "../tdp/gameIdentity";
import { translate } from "../i18n";

// Add a "Launch parameters" entry to a game's library context menu (the menu that
// opens on the game's options button), like CSS Loader's cover-art entry. This
// patches Steam internals, so EVERYTHING is guarded: if the menu component or its
// item list can't be found, we add nothing and leave Steam completely untouched
// (never throw — a bad patch here could destabilize the shared UI).

/* eslint-disable @typescript-eslint/no-explicit-any */

// Steam's library context-menu class, located by a long-stable prototype marker.
const LibraryContextMenu: any = findModuleChild((m: any) => {
  if (typeof m !== "object") return undefined;
  for (const prop in m) {
    try {
      if (m[prop]?.prototype?.AddSocialButtons) return m[prop];
    } catch {
      /* some props throw on access */
    }
  }
  return undefined;
});

function entryFor(appid: number): GameEntry | null {
  try {
    const ov = (window as any).appStore?.GetAppOverviewByAppID?.(appid);
    const id = { appid, display_name: ov?.display_name, app_type: ov?.app_type };
    return {
      liveAppid: appid,
      stableKey: stableGameKey(id),
      name: ov?.display_name || String(appid),
      isNonSteam: isNonSteam(id),
    };
  } catch {
    return null;
  }
}

/** Install the context-menu patch. Returns an unpatch fn (no-op if it didn't hook). */
export function installGameContextMenu(): () => void {
  let patch: Patch | undefined;
  try {
    if (!LibraryContextMenu?.prototype?.render) return () => {};
    patch = afterPatch(LibraryContextMenu.prototype, "render", (args: any, ret: any) => {
      try {
        const appid: number | undefined = args?.[0]?.overview?.appid ?? args?.[0]?.appid;
        if (typeof appid !== "number") return ret;
        // The vertical list of menu items — find the children array and append ours once.
        const list = findInReactTree(
          ret,
          (x: any) =>
            Array.isArray(x?.props?.children) &&
            x.props.children.some?.((c: any) => typeof c?.props?.onSelected === "function"),
        );
        const arr = list?.props?.children;
        if (Array.isArray(arr) && !arr.some((c: any) => c?.key === "pdc-launch-params")) {
          arr.push(
            <MenuItem
              key="pdc-launch-params"
              onSelected={() => {
                const g = entryFor(appid);
                if (g) openLaunchEditorModal(g, () => {});
              }}
            >
              {translate("params.contextMenu")}
            </MenuItem>,
          );
        }
      } catch {
        /* any mismatch → leave the menu exactly as Steam built it */
      }
      return ret;
    });
  } catch {
    /* couldn't hook → no entry, Steam untouched */
  }
  return () => {
    try {
      patch?.unpatch();
    } catch {
      /* ignore */
    }
  };
}
