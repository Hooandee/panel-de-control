import {
  PanelSection,
  PanelSectionRow,
  Spinner,
  ErrorBoundary,
  staticClasses,
} from "@decky/ui";
import { definePlugin } from "@decky/api";
import { LuGauge } from "react-icons/lu";
import { FC, useCallback, useEffect, useRef, useState } from "react";

import { getDevice, getTdpState, setTdpWatts, DeviceInfo, TdpState, TdpScope } from "./api";
import { I18nProvider, useI18n } from "./i18n";
import { DeviceHeader } from "./components/DeviceHeader";
import { LanguageToggle } from "./components/LanguageToggle";
import { TdpSection } from "./components/TdpSection";
import { useRunningGame } from "./tdp/useRunningGame";

const Content: FC = () => {
  // ALL hooks above any early return.
  const { t } = useI18n();
  const game = useRunningGame();
  const [device, setDevice] = useState<DeviceInfo | null>(null);
  const [tdp, setTdp] = useState<TdpState | null>(null);
  const [scope, setScope] = useState<TdpScope>("global");
  const [failed, setFailed] = useState(false);
  const commitTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(() => {
    getTdpState().then(setTdp).catch(() => {});
  }, []);

  useEffect(() => {
    getDevice().then(setDevice).catch(() => setFailed(true));
    refresh();
  }, [refresh]);

  const appid = game?.appid;
  useEffect(() => {
    setScope(appid ? "game" : "global");
    refresh();
  }, [appid, refresh]);

  const onWatts = useCallback(
    (w: number) => {
      setTdp((cur) =>
        cur
          ? {
              ...cur,
              watts: scope === "game" ? w : cur.watts,
              global_watts: scope === "global" ? w : cur.global_watts,
            }
          : cur,
      );
      if (commitTimer.current) clearTimeout(commitTimer.current);
      const target = scope === "game" && game ? game.appid : null;
      commitTimer.current = setTimeout(() => {
        setTdpWatts(w, scope, target).then(() => refresh()).catch(() => {});
      }, 200);
    },
    [scope, game, refresh],
  );

  if (failed) {
    return (
      <PanelSection>
        <PanelSectionRow>{t("load.error")}</PanelSectionRow>
      </PanelSection>
    );
  }
  if (!device) return <Spinner />;

  return (
    <PanelSection>
      <PanelSectionRow>
        <DeviceHeader device={device} />
      </PanelSectionRow>
      <LanguageToggle />
      <TdpSection tdp={tdp} scope={scope} game={game} onScope={setScope} onWatts={onWatts} />
    </PanelSection>
  );
};

export default definePlugin(() => ({
  name: "Panel de Control",
  titleView: <div className={staticClasses.Title}>Panel de Control</div>,
  content: (
    <I18nProvider>
      <ErrorBoundary>
        <Content />
      </ErrorBoundary>
    </I18nProvider>
  ),
  icon: <LuGauge />,
  onDismount() {
    // no global listeners; hooks clean up their own
  },
}));
