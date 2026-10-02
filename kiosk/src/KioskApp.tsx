import { CSSProperties, FC, useRef, useState, useSyncExternalStore } from "react";

import { BlocksView } from "../../src/sections/CustomView";
import { useViews } from "../../src/customize/viewStore";
import { useKioskViewIds } from "../../src/customize/kioskViewStore";
import { currentAccentHex, currentAccentRgb, subscribeAccent } from "../../src/system/accentColor";
import { useRunningGame } from "../../src/tdp/useRunningGame";
import { useI18n } from "../../src/i18n";
import { ModalHost } from "./shims/deckyUi";
import { currentToasts, subscribeToasts } from "./shims/deckyApi";
import { kioskPages } from "./pages";
import { DeckPage } from "./deck/DeckPage";
import { artUrl, useLive } from "./now/live";
import { batteryReading } from "./now/metrics";
import { PageBoundary } from "./PageBoundary";

const DECK_PAGE_ID = "deck";

const useAccentVars = (): CSSProperties => {
  const hex = useSyncExternalStore(subscribeAccent, currentAccentHex);
  return { "--k-accent": hex, "--k-accent-rgb": currentAccentRgb() } as CSSProperties;
};

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

const StatusBattery: FC<{ percent: number | null; charging: boolean }> = ({ percent, charging }) => (
  <span className={`k-status-battery${charging ? " is-charging" : ""}`}>
    {percent != null && <span>{percent}%</span>}
    <span className="k-status-shell">
      <span style={{ width: `${percent ?? 0}%` }} />
    </span>
  </span>
);

export const KioskApp: FC = () => {
  const { t, lang } = useI18n();
  const live = useLive();
  const game = useRunningGame();
  const pages = [
    { id: DECK_PAGE_ID, name: game?.name ?? t("app.title"), blocks: [] as readonly string[] },
    ...kioskPages(useViews(), useKioskViewIds(), t("kiosk.page.default")),
  ];
  const pager = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const onScroll = () => {
    const el = pager.current;
    if (el) setActive(Math.round(el.scrollLeft / Math.max(1, el.clientWidth)));
  };
  const goTo = (index: number) => pager.current?.scrollTo({ left: index * pager.current.clientWidth, behavior: "smooth" });
  const current = pages[Math.min(active, pages.length - 1)];
  const battery = batteryReading(live.battery);
  const art = game && /^\d+$/.test(game.appid) ? artUrl(game.appid, "hero") : null;

  return (
    <div className="k-shell" style={useAccentVars()}>
      <div className={`k-backdrop${art ? " is-on" : ""}`} style={{ backgroundImage: art ? `url(${art})` : undefined }} />

      <header className="k-header">
        <div key={current?.id} className="k-title">{current?.name}</div>
        <div className="k-status">
          <span className="k-clock">{new Date().toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" })}</span>
          <StatusBattery percent={battery.percent} charging={battery.mood === "charging"} />
        </div>
      </header>

      <div className="k-pager" ref={pager} onScroll={onScroll}>
        {pages.map((page) => (
          <section key={page.id} className="k-page">
            <PageBoundary
              where={`kiosk:${page.id === DECK_PAGE_ID ? "deck" : "view"}`}
              fallback={(retry) => (
                <div className="k-card k-page-error">
                  <span>{t("kiosk.page.error")}</span>
                  <button type="button" className="k-button" onClick={retry}>{t("kiosk.page.retry")}</button>
                </div>
              )}
            >
              {page.id === DECK_PAGE_ID ? (
                <DeckPage live={live} />
              ) : (
                <BlocksView blockIds={page.blocks} className="k-blocks" />
              )}
            </PageBoundary>
          </section>
        ))}
      </div>

      {pages.length > 1 && (
        <nav className="k-dots">
          {pages.map((page, index) => (
            <button
              key={page.id}
              type="button"
              aria-label={page.name}
              className={index === active ? "is-on" : undefined}
              onClick={() => goTo(index)}
            />
          ))}
        </nav>
      )}
      <Toasts />
      <ModalHost />
    </div>
  );
};
