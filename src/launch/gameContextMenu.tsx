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

// Insert our item just before "Properties…".
const spliceLaunchItem = (children: any[], appid: number) => {
  const propertiesIdx = children.findIndex((item) =>
    findInReactTree(item, (x) => x?.onSelected && x.onSelected.toString().includes("AppProperties")),
  );
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
  if (propertiesIdx >= 0) children.splice(propertiesIdx, 0, item);
  else children.push(item);
};

// Only the game's own context menu (has an item whose onSelected mentions launchSource).
const isOpeningAppContextMenu = (items: any[]) =>
  !!items?.length &&
  !!findInReactTree(items, (x) => x?.props?.onSelected && x.props.onSelected.toString().includes("launchSource"));

const handleItemDupes = (items: any[]) => {
  const idx = items.findIndex((x: any) => x?.key === "pdc-launch-params");
  if (idx !== -1) items.splice(idx, 1);
};

const patchMenuItems = (menuItems: any[], appid: number) => {
  let updated = appid;
  const parent = menuItems.find(
    (x: any) => x?._owner?.pendingProps?.overview?.appid && x._owner.pendingProps.overview.appid !== appid,
  );
  if (parent) updated = parent._owner.pendingProps.overview.appid;
  if (updated === appid) {
    const foundApp = findInTree(menuItems, (x: any) => x?.app?.appid, { walkable: ["props", "children"] });
    if (foundApp) updated = foundApp.app.appid;
  }
  spliceLaunchItem(menuItems, updated);
};

function patchContextMenu(LibraryContextMenu: any): { unpatch: () => void } {
  const patches: { outer?: Patch; inner?: Patch; unpatch: () => void } = { unpatch: () => {} };
  patches.outer = afterPatch(LibraryContextMenu.prototype, "render", (_: any, component: any) => {
    let appid = 0;
    if (component?._owner?.pendingProps?.overview?.appid) {
      appid = component._owner.pendingProps.overview.appid;
    } else {
      const foundApp = findInTree(component?.props?.children, (x: any) => x?.app?.appid, { walkable: ["props", "children"] });
      if (foundApp) appid = foundApp.app.appid;
    }
    if (!patches.inner) {
      patches.inner = afterPatch(component, "type", (_: any, ret: any) => {
        afterPatch(ret.type.prototype, "render", (_: any, ret2: any) => {
          const menuItems = ret2?.props?.children?.[0];
          if (!isOpeningAppContextMenu(menuItems)) return ret2;
          try {
            handleItemDupes(menuItems);
          } catch {
            return ret2;
          }
          patchMenuItems(menuItems, appid);
          return ret2;
        });
        afterPatch(ret.type.prototype, "shouldComponentUpdate", ([nextProps]: any, shouldUpdate: any) => {
          try {
            handleItemDupes(nextProps.children);
          } catch {
            return shouldUpdate;
          }
          if (shouldUpdate === true) patchMenuItems(nextProps.children, appid);
          return shouldUpdate;
        });
        return ret;
      });
    } else {
      spliceLaunchItem(component.props.children, appid);
    }
    return component;
  });
  patches.unpatch = () => {
    patches.outer?.unpatch();
    patches.inner?.unpatch();
  };
  return patches;
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
