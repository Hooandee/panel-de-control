import { FC, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Focusable, PanelSectionRow } from "@decky/ui";
import { LuMaximize2, LuPencil, LuRefreshCw, LuScale, LuVolumeX, LuZap } from "react-icons/lu";

import { DesktopFanChannel, FanCurveState, getFanCurveState, setDesktopFanCurve } from "../api";
import { Point } from "../fans/curve";
import { desktopFanVisible } from "../fans/presentation";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { openDesktopFanCurveModal } from "./DesktopFanCurveModal";
import { FanCurveGraph } from "./FanCurveGraph";
import { segmentGroupStyle, segmentItemStyle } from "./segmented";

type Mode = DesktopFanChannel["preset"];
const MODES: Mode[] = ["auto", "silent", "balanced", "performance", "custom"];
const ICONS: Record<Mode, ReactNode> = {
  auto: <LuRefreshCw size={13} />, silent: <LuVolumeX size={13} />,
  balanced: <LuScale size={13} />, performance: <LuZap size={13} />, custom: <LuPencil size={13} />,
};

const ChannelCard: FC<{ channel: DesktopFanChannel; state: FanCurveState; refresh: () => void }> = ({ channel, state, refresh }) => {
  const { t } = useI18n();
  const balanced = useMemo(() => state.presets.find((item) => item.id === "balanced")?.points ?? [], [state.presets]);
  const [points, setPoints] = useState<Point[]>(channel.points ?? balanced);
  const timer = useRef<number | null>(null);
  const opening = useRef(false);
  useEffect(() => setPoints(channel.points ?? balanced), [channel.points, balanced]);
  useEffect(() => () => { if (timer.current != null) window.clearTimeout(timer.current); }, []);
  const select = (mode: Mode) => {
    const seed = mode === "custom" ? (points.length ? points : balanced) : null;
    setDesktopFanCurve(channel.key, mode, seed, "global", null).then(refresh).catch(() => {});
  };
  const change = (next: Point[]) => {
    setPoints(next);
    if (timer.current != null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      timer.current = null;
      setDesktopFanCurve(channel.key, "custom", next, "global", null).then(refresh).catch(() => {});
    }, 200);
  };
  const liveTemp = null;
  const openEditor = () => {
    if (opening.current) return;
    opening.current = true;
    const launch = (draft: Point[]) => {
      openDesktopFanCurveModal(
        channel.key,
        t(`desktop.fan.${channel.key}`),
        draft,
        refresh,
      );
      window.setTimeout(() => { opening.current = false; }, 0);
    };
    if (timer.current == null) {
      launch(points);
      return;
    }
    window.clearTimeout(timer.current);
    timer.current = null;
    setDesktopFanCurve(channel.key, "custom", points, "global", null)
      .then((next) => {
        const confirmed = next.apply_ok === true
          ? next.channels?.find((candidate) => candidate.key === channel.key)
          : undefined;
        if (confirmed?.controllable && confirmed.preset === "custom" && confirmed.points?.length) {
          launch(confirmed.points as Point[]);
        } else {
          opening.current = false;
          refresh();
        }
      })
      .catch(() => {
        opening.current = false;
        refresh();
      });
  };
  const summary = t("desktop.fan.summary", {
    rpm: channel.rpm == null ? t("desktop.metric.unavailable") : `${channel.rpm} RPM`,
    sensor: channel.sensor ?? t("desktop.metric.noSensor"),
  });
  return (
    <PanelSectionRow>
      <div style={{ ...theme.card, padding: theme.space.md, display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <div
          data-testid={`desktop-fan-header-${channel.key}`}
          style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}
        >
          <span style={{ color: theme.color.textPrimary, fontWeight: 650 }}>{t(`desktop.fan.${channel.key}`)}</span>
          <span style={{ color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.35 }}>
            {summary}
          </span>
        </div>
        {channel.controllable ? <Focusable style={segmentGroupStyle}>
          {MODES.map((mode) => (
            <Focusable key={mode} style={{ ...segmentItemStyle(channel.preset === mode), flex: 1, padding: "6px" }}
              title={t(`fans.preset.${mode}`)} aria-label={t(`fans.preset.${mode}`)}
              onActivate={() => select(mode)} onClick={() => select(mode)}>
              {ICONS[mode]}
            </Focusable>
          ))}
        </Focusable> : (
          <span style={{ color: theme.color.textMuted, fontSize: theme.font.caption }}>{t("desktop.fan.firmwareOnly")}</span>
        )}
        {channel.controllable && channel.preset !== "auto" && <FanCurveGraph points={points} liveTemp={liveTemp}
          editable={channel.preset === "custom"} onChange={change} />}
        {channel.controllable && channel.preset === "custom" && (
          <Focusable
            role="button"
            aria-label={t("fans.curve.expand")}
            title={t("fans.curve.expand")}
            onActivate={openEditor}
            onClick={openEditor}
            style={{ ...segmentItemStyle(false), padding: "7px 10px" }}
          >
            <LuMaximize2 size={15} />
            <span>{t("fans.curve.expand")}</span>
          </Focusable>
        )}
        <Focusable
          data-testid={`desktop-fan-note-${channel.key}`}
          role="note"
          onActivate={() => {}}
          noFocusRing
          style={{ minWidth: 0, color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.4 }}
        >
          {t("desktop.fan.auto.note")}
        </Focusable>
      </div>
    </PanelSectionRow>
  );
};

export const DesktopFanCurves: FC<{ initial: FanCurveState }> = ({ initial }) => {
  const [state, setState] = useState(initial);
  const refresh = () => { getFanCurveState().then(setState).catch(() => {}); };
  useEffect(() => {
    const timer = window.setInterval(refresh, 1500);
    return () => window.clearInterval(timer);
  }, []);
  return <>{(state.channels ?? [])
    .filter((channel) => desktopFanVisible(state.device_key, channel.key))
    .map((channel) => <ChannelCard key={channel.key} channel={channel} state={state} refresh={refresh} />)}</>;
};
