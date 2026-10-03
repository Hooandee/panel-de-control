import { FC, useSyncExternalStore } from "react";

import { useI18n } from "../../src/i18n";
import { PotenciaProviderMount } from "../../src/sections/providerMounts";
import { ModalHost } from "./shims/deckyUi";
import { currentToasts, subscribeToasts, toaster } from "./shims/deckyApi";
import { Deck, useScreenOff } from "./deck/Deck";
import { PageBoundary } from "./PageBoundary";

const Toasts: FC = () => {
  const toasts = useSyncExternalStore(subscribeToasts, currentToasts);
  return (
    <div className="k-toasts">
      {toasts.map((toast) => (
        <div key={toast.id} className="k-toast">
          {toast.title && <b>{toast.title}</b>}
          {toast.body && <span>{toast.body}</span>}
        </div>
      ))}
    </div>
  );
};

export const KioskApp: FC = () => {
  const { t } = useI18n();
  const screen = useScreenOff(() => toaster.toast({ title: t("kiosk.failed") }));
  return (
    <div className="k-shell">
      <PageBoundary
        where="kiosk:deck"
        fallback={(retry) => (
          <div className="k-error">
            <span>{t("kiosk.error")}</span>
            <button type="button" className="g-cta" onClick={retry}>{t("kiosk.retry")}</button>
          </div>
        )}
      >
        {/* With the panel off nothing is shown, so nothing is polled either. */}
        {!screen.off && (
          <PotenciaProviderMount>
            <Deck onScreenOff={screen.sleep} />
          </PotenciaProviderMount>
        )}
      </PageBoundary>
      <Toasts />
      <ModalHost />
      {screen.off && <div className="k-asleep" onPointerDown={screen.wake} />}
    </div>
  );
};
