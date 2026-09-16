import { staticClasses } from "@decky/ui";

import {
  cleanupOwnedQuickAccessTabs,
  configureQuickAccessTabComposition,
  occupiedQuickAccessTabIds,
  registerOwnedQuickAccessTab,
} from "../deckyInternal";
import { PinnedQamView } from "../components/PinnedQamView";
import { getDisabled, subscribeModules } from "../customize/modules";
import { getPresent, subscribePresent } from "../customize/present";
import {
  getLayout as getPanelLayout,
  subscribeLayout as subscribePanelLayout,
} from "../customize/store";
import { getViews, subscribeViews } from "../customize/viewStore";
import { getCurrentLanguage, subscribeLanguage, translate } from "../i18n";
import { getQamDocument } from "../qamDocument";
import { getQamLayout, saveQamLayout, subscribeQamLayout } from "./store";
import { startQamComposerRuntime } from "./runtime";
import { readRenderedQamKeys } from "./renderedKeys";
import { buildPanelQamCatalog } from "./panelCatalog";
import {
  ensureDevice,
  getDeviceSnapshot,
  subscribeDevice,
} from "../system/useDevice";
import {
  ensureDesktopState,
  getDesktopSnapshot,
  subscribeDesktopState,
} from "../desktop/useDesktop";

function getCatalog() {
  const device = getDeviceSnapshot();
  return buildPanelQamCatalog(getViews(), {
    device,
    disabled: new Set(getDisabled()),
    layout: getPanelLayout(),
    desktopMode: getDesktopSnapshot()?.enabled === true,
    present: getPresent,
    presentationKeySuffix: getCurrentLanguage(),
  });
}

function subscribeCatalog(listener: () => void): () => void {
  const unsubscribers = [
    subscribeViews(listener),
    subscribeModules(listener),
    subscribePresent(listener),
    subscribePanelLayout(listener),
    subscribeDevice(listener),
    subscribeDesktopState(listener),
    subscribeLanguage(listener),
  ];
  return () => unsubscribers.forEach((unsubscribe) => unsubscribe());
}

function readRenderedKeys(): string[] | null {
  return readRenderedQamKeys(getQamDocument());
}

function scheduleReadback(readback: () => void): () => void {
  const timer = window.setTimeout(readback, 0);
  return () => window.clearTimeout(timer);
}

export function startPluginQamRuntime(host: unknown = window) {
  ensureDevice();
  ensureDesktopState();
  return startQamComposerRuntime({
    getLayout: getQamLayout,
    saveLayout: saveQamLayout,
    subscribeLayout: subscribeQamLayout,
    getCatalog,
    subscribeCatalog,
    occupiedIds: () => occupiedQuickAccessTabIds(host),
    cleanupOwned: () => cleanupOwnedQuickAccessTabs(host),
    registerOwned: (id, descriptor, lifecycle, onRuntimeFailure) => (
      registerOwnedQuickAccessTab(
        id,
        {
          title: (
            <div className={staticClasses.Title}>
              {descriptor.label || translate(descriptor.labelKey)}
            </div>
          ),
          content: (
            <PinnedQamView
              token={descriptor.token}
              target={descriptor.target}
              lifecycle={lifecycle}
            />
          ),
          icon: descriptor.icon(20),
        },
        host,
        onRuntimeFailure,
      )
    ),
    configure: (config) => configureQuickAccessTabComposition(config, host),
    readRenderedKeys,
    scheduleReadback,
  });
}
