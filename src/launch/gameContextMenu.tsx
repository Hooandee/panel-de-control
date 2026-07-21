import {
  afterPatch,
  fakeRenderComponent,
  findInReactTree,
  findInTree,
  findModuleByExport,
  Export,
  MenuItem,
  Patch,
} from "@decky/ui";
import { FC } from "react";

import { openLaunchEditorModal } from "../components/LaunchEditorModal";
import { GameEntry, overviewToEntry } from "./steamApi";
import { replaceMenuItem } from "./menuItems";
import { translate } from "../i18n";

// Add a "Launch parameters" entry to a game's library context menu (the options
// menu on a game). Patching Steam's internal LibraryContextMenu is adapted from
// decky-steamgriddb's contextMenuPatch (GPL-3.0):
//   https://github.com/SteamGridDB/decky-steamgriddb
// That derivation is why this project is licensed GPL-3.0 (see THIRD_PARTY_NOTICES).
// Everything is guarded: if the menu can't be located we install nothing.

/* eslint-disable @typescript-eslint/no-explicit-any */

function entryFor(appid: number): GameEntry | null {
  try {
    const ov = (window as any).appStore?.GetAppOverviewByAppID?.(appid);
    return ov ? overviewToEntry(ov) : null;
  } catch {
    return null;
  }
}

// Insert our item just before "Properties…". No-op when the appid is unknown, so we
// never attach a menu entry that would open the wrong game.
const spliceLaunchItem = (children: unknown, appid: number) => {
  if (!appid) return false;
  const item = (
    <MenuItem
      key="pdc-launch-params"
      onSelected={() => {
        const g = entryFor(appid);
        if (g) openLaunchEditorModal(g, () => {});
      }}
    >
      {translate("params.contextMenu")}
    </MenuItem>
  );
  return replaceMenuItem<any>(children, "pdc-launch-params", item, (candidate) =>
    !!findInReactTree(candidate, (x) => x?.onSelected && x.onSelected.toString().includes("AppProperties")),
  );
};

// Only the game's own context menu (has an item whose onSelected mentions launchSource).
const isOpeningAppContextMenu = (items: unknown) =>
  Array.isArray(items) &&
  items.length > 0 &&
  !!findInReactTree(items, (x) => x?.props?.onSelected && x.props.onSelected.toString().includes("launchSource"));

// Derive the appid from THIS menu's own tree (never a stale value captured when the
// prototype was first patched); insert nothing if it can't be determined.
const patchMenuItems = (menuItems: unknown) => {
  try {
    if (!isOpeningAppContextMenu(menuItems) || !Array.isArray(menuItems)) return;
    let appid = 0;
    const parent = menuItems.find((x: any) => x?._owner?.pendingProps?.overview?.appid);
    if (parent) appid = parent._owner.pendingProps.overview.appid;
    if (!appid) {
      const foundApp = findInTree(menuItems, (x: any) => x?.app?.appid, { walkable: ["props", "children"] });
      if (foundApp) appid = foundApp.app.appid;
    }
    spliceLaunchItem(menuItems, appid);
  } catch {
    /* Steam changed the internal menu shape. */
  }
};

function patchContextMenu(LibraryContextMenu: any): { unpatch: () => void } {
  // Track EVERY patch handle so unpatch() removes them all — the inner prototype
  // patches used to be discarded, leaking callbacks onto Steam's menu prototypes
  // that survived plugin reload/disable and stacked up.
  const all: Patch[] = [];
  const patchedProtos = new Set<unknown>();
  let innerHooked = false;

  const outer = afterPatch(LibraryContextMenu.prototype, "render", (_: any, component: any) => {
    if (!innerHooked) {
      innerHooked = true;
      all.push(
        afterPatch(component, "type", (_: any, ret: any) => {
          const proto = ret?.type?.prototype;
          if (proto && !patchedProtos.has(proto)) {
            patchedProtos.add(proto);
            all.push(
              afterPatch(proto, "render", (_: any, ret2: any) => {
                const menuItems = ret2?.props?.children?.[0];
                patchMenuItems(menuItems);
                return ret2;
              }),
            );
            all.push(
              afterPatch(proto, "shouldComponentUpdate", ([nextProps]: any, shouldUpdate: any) => {
                if (shouldUpdate === true) patchMenuItems(nextProps.children);
                return shouldUpdate;
              }),
            );
          }
          return ret;
        }),
      );
    } else {
      patchMenuItems(component?.props?.children);
    }
    return component;
  });
  all.push(outer);

  return {
    unpatch: () => {
      for (const p of all) {
        try {
          p.unpatch();
        } catch {
          /* ignore */
        }
      }
    },
  };
}

/** Locate Steam's game context-menu component (SteamGridDB's approach). */
function findLibraryContextMenu(): any {
  try {
    return fakeRenderComponent(
      Object.values(
        findModuleByExport((e: Export) => e?.toString && e.toString().includes("().LibraryContextMenu")),
      ).find((sibling: any) => sibling?.toString().includes("navigator:")) as FC,
    ).type;
  } catch {
    return undefined;
  }
}

/** Install the context-menu patch. Returns an unpatch fn (no-op if it didn't hook). */
export function installGameContextMenu(): () => void {
  try {
    const LibraryContextMenu = findLibraryContextMenu();
    if (!LibraryContextMenu?.prototype?.render) return () => {};
    const p = patchContextMenu(LibraryContextMenu);
    return () => {
      try {
        p.unpatch();
      } catch {
        /* ignore */
      }
    };
  } catch {
    return () => {};
  }
}
