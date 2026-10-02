import { FC, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { BlocksView } from "../../src/sections/CustomView";
import { useViews } from "../../src/customize/viewStore";
import { currentAccentHex, currentAccentRgb, subscribeAccent } from "../../src/system/accentColor";
import { useI18n } from "../../src/i18n";
import { ModalHost } from "./shims/deckyUi";
import { currentToasts, subscribeToasts } from "./shims/deckyApi";
import { kioskPages, KioskPage } from "./pages";

const useAccentVars = () => {
  const hex = useSyncExternalStore(subscribeAccent, currentAccentHex);
  return { "--k-accent": hex, "--k-accent-rgb": currentAccentRgb() } as Record<string, string>;
};

const Clock: FC = () => {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 15_000);
    return () => window.clearInterval(id);
  }, []);
  return <span className="k-clock">{now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>;
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

export const KioskApp: FC = () => {
  const { t } = useI18n();
  const pages: KioskPage[] = kioskPages(useViews(), t("kiosk.page.default"));
  const pager = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const onScroll = () => {
    const el = pager.current;
    if (el) setActive(Math.round(el.scrollLeft / Math.max(1, el.clientWidth)));
  };
  const current = pages[Math.min(active, pages.length - 1)];

  return (
    <div className="k-shell" style={useAccentVars()}>
      <header className="k-header">
        <div>
          <div className="k-eyebrow">{t("app.title")}</div>
          <div className="k-title">{current?.name}</div>
        </div>
        <Clock />
      </header>
      <div className="k-pager" ref={pager} onScroll={onScroll}>
        {pages.map((page) => (
          <section key={page.id} className="k-page">
            <div className="k-columns">
              <BlocksView blockIds={page.blocks} />
            </div>
          </section>
        ))}
      </div>
      {pages.length > 1 && (
        <nav className="k-dots" aria-hidden>
          {pages.map((page, index) => (
            <i key={page.id} className={index === active ? "is-on" : undefined} />
          ))}
        </nav>
      )}
      <Toasts />
      <ModalHost />
    </div>
  );
};
