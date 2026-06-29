import {
  PanelSection,
  PanelSectionRow,
  SliderField,
  Spinner,
  ErrorBoundary,
  staticClasses,
} from "@decky/ui";
import { definePlugin } from "@decky/api";
import { LuGauge } from "react-icons/lu";
import { FC, ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { getDevice, getTdpState, setTdpWatts, DeviceInfo, TdpState, TdpScope } from "./api";
import { I18nProvider, useI18n } from "./i18n";
import { DeviceHeader } from "./components/DeviceHeader";
import { LanguageToggle } from "./components/LanguageToggle";
import { PowerArc } from "./components/PowerArc";
import { ProfileSelector } from "./components/ProfileSelector";
import { Presets } from "./components/Presets";
import { fraction, zoneFor } from "./tdp/logic";
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

  if (failed) {
    return (
      <PanelSection>
        <PanelSectionRow>{t("load.error")}</PanelSectionRow>
      </PanelSection>
    );
  }
  if (!device) return <Spinner />;

  let tdpSection: ReactNode = <Spinner />;
  if (tdp && !tdp.supported) {
    tdpSection = (
      <PanelSectionRow>
        <div style={{ fontSize: 11, color: "rgba(255,255,255,0.45)" }}>{t("tdp.unsupported")}</div>
      </PanelSectionRow>
    );
  } else if (tdp) {
    const displayWatts = scope === "global" ? tdp.global_watts : tdp.watts;
    const zone = zoneFor(fraction(displayWatts, tdp.limits.min, tdp.limits.max_ac));
    const onWatts = (w: number) => {
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
    };
    tdpSection = (
      <>
        <PanelSectionRow>
          <ProfileSelector
            scope={scope}
            gameName={game?.name ?? null}
            hasGameProfile={tdp.has_game_profile}
            globalLabel={t("tdp.scope.global")}
            inheritHint={t("tdp.inherit")}
            onScope={setScope}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <PowerArc
            watts={displayWatts}
            limits={tdp.limits}
            onAc={tdp.on_ac}
            zoneLabel={t(`tdp.zone.${zone.key}`)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <SliderField
            value={displayWatts}
            min={tdp.limits.min}
            max={tdp.limits.max_ac}
            step={1}
            showValue
            onChange={onWatts}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <Presets
            limits={tdp.limits}
            onAc={tdp.on_ac}
            labels={{
              save: t("tdp.preset.save"),
              balanced: t("tdp.preset.balanced"),
              turbo: t("tdp.preset.turbo"),
            }}
            onPick={onWatts}
          />
        </PanelSectionRow>
      </>
    );
  }

  return (
    <PanelSection>
      <PanelSectionRow>
        <DeviceHeader device={device} />
      </PanelSectionRow>
      <LanguageToggle />
      {tdpSection}
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
