import { FC, useEffect, useRef, useState } from "react";
import { DialogButton, PanelSectionRow } from "@decky/ui";
import { LuFan } from "react-icons/lu";

import { FanTargetState, setFanTargetTemp } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { ContainedSlider } from "./ContainedSlider";
import { SegmentedTabs } from "./SegmentedTabs";

type PresetId = NonNullable<FanTargetState["presets"]>[number]["id"] | "custom";

const SLIDER_SETTLE_MS = 400;

export function activePreset(state: FanTargetState, celsius: number | null): PresetId {
  return state.presets?.find((preset) => preset.celsius === celsius)?.id ?? "custom";
}

export const FanTargetCard: FC<{ state: FanTargetState; onChange: () => void }> = ({ state, onChange }) => {
  const { t } = useI18n();
  const [celsius, setCelsius] = useState<number | null>(state.celsius ?? null);
  const [failed, setFailed] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pending = useRef<number | null>(null);
  const sequence = useRef(0);

  useEffect(() => setCelsius(state.celsius ?? null), [state.celsius]);

  const commit = (value: number | null) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    pending.current = null;
    const request = ++sequence.current;
    setFanTargetTemp(value)
      .then((result) => {
        if (request !== sequence.current) return;
        setFailed(!result.ok);
        setCelsius(result.celsius ?? null);
      })
      .catch(() => { if (request === sequence.current) setFailed(true); })
      .finally(onChange);
  };

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
    if (pending.current !== null) void setFanTargetTemp(pending.current).catch(() => null);
  }, []);

  const onSlide = (value: number) => {
    setCelsius(value);
    pending.current = value;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => commit(value), SLIDER_SETTLE_MS);
  };

  const min = state.min ?? 50;
  const max = state.max ?? 90;
  const preset = activePreset(state, celsius);
  const tabs = (state.presets ?? []).map((item) => ({
    value: item.id as PresetId,
    label: t(`fans.target.preset.${item.id}`),
  }));

  return (
    <PanelSectionRow>
      <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden", display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
            <LuFan size={16} color={theme.color.accent} /> {t("fans.target.title")}
          </span>
          <span data-testid="fan-target-value" style={{ fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
            {celsius === null ? "—" : `${celsius} °C`}
          </span>
        </div>
        {tabs.length > 0 && (
          <SegmentedTabs
            label={t("fans.target.title")}
            tabs={tabs}
            value={preset}
            onChange={(id) => {
              const value = state.presets?.find((item) => item.id === id)?.celsius;
              if (value === undefined) return;
              setCelsius(value);
              commit(value);
            }}
          />
        )}
        <ContainedSlider value={celsius ?? state.default ?? max} min={min} max={max} step={1} onChange={onSlide} />
        <span style={{ fontSize: theme.font.caption, color: failed ? theme.color.warn : theme.color.textMuted, lineHeight: 1.4 }}>
          {t(failed ? "fans.target.failed" : "fans.target.note")}
        </span>
        {state.target != null && (
          <DialogButton style={{ minWidth: 0, padding: "6px 10px", fontSize: theme.font.caption }} onClick={() => commit(null)}>
            {t("fans.target.reset", { c: state.default ?? 80 })}
          </DialogButton>
        )}
      </div>
    </PanelSectionRow>
  );
};
