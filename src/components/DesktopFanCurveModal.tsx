import { FC, useEffect, useMemo, useRef, useState } from "react";
import { Focusable, ModalRoot, SliderField, showModal } from "@decky/ui";

import { DesktopFanChannel, getFanCurveState, setDesktopFanCurve } from "../api";
import { GEOM, Point, clampMonotonic, percentToPwm, pwmToPercent } from "../fans/curve";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { FanCurveGraph } from "./FanCurveGraph";
import { FocusRoot } from "./FocusRoot";
import { segmentGroupStyle, segmentItemStyle } from "./segmented";

interface ModalProps {
  channelKey: DesktopFanChannel["key"];
  title: string;
  initialPoints: Point[];
  closeModal?: () => void;
}

const CurveSlider: FC<{
  label: string;
  value: string;
  raw: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}> = ({ label, value, raw, min, max, onChange }) => (
  <div style={{ ...theme.card, padding: theme.space.sm, minWidth: 0, overflow: "hidden" }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: theme.space.sm, color: theme.color.textPrimary }}>
      <span style={{ color: theme.color.textMuted }}>{label}</span>
      <span style={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{value}</span>
    </div>
    {min < max && (
      <div style={{ overflow: "hidden", marginTop: theme.space.xs }}>
        <SliderField value={raw} min={min} max={max} step={1} showValue={false} onChange={onChange} />
      </div>
    )}
  </div>
);

const DesktopFanCurveModalBody: FC<ModalProps> = ({ channelKey, title, initialPoints, closeModal }) => {
  const { t } = useI18n();
  const [points, setPoints] = useState<Point[]>(() => clampMonotonic(initialPoints));
  const [selected, setSelected] = useState(0);
  const [available, setAvailable] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const savingNow = useRef(false);

  useEffect(() => {
    let alive = true;
    getFanCurveState().then((next) => {
      if (!alive) return;
      const channel = next.independent
        ? next.channels?.find((candidate) => candidate.key === channelKey)
        : undefined;
      if (!channel?.controllable || channel.preset !== "custom" || !channel.points?.length) {
        setAvailable(false);
        return;
      }
    }).catch(() => {});
    return () => { alive = false; };
  }, [channelKey]);

  const point = points[selected];
  const bounds = useMemo(() => {
    const previous = points[selected - 1];
    const next = points[selected + 1];
    return {
      tempMin: previous?.[0] ?? GEOM.tempMin,
      tempMax: next?.[0] ?? GEOM.tempMax,
      pwmMin: previous?.[1] ?? 0,
      pwmMax: next?.[1] ?? GEOM.pwmMax,
    };
  }, [points, selected]);

  const updatePoint = (axis: 0 | 1, value: number) => {
    setPoints((current) => current.map((candidate, index) => {
      if (index !== selected) return candidate;
      const next: Point = [...candidate];
      const min = axis === 0 ? bounds.tempMin : bounds.pwmMin;
      const max = axis === 0 ? bounds.tempMax : bounds.pwmMax;
      next[axis] = Math.max(min, Math.min(max, Math.round(value)));
      return next;
    }));
  };

  const save = () => {
    if (savingNow.current) return;
    savingNow.current = true;
    setSaving(true);
    setSaveError(false);
    setDesktopFanCurve(channelKey, "custom", points, "global", null)
      .then((next) => {
        const confirmed = next?.independent
          ? next.channels?.find((channel) => channel.key === channelKey)
          : undefined;
        if (next.apply_ok !== true || !confirmed?.controllable || confirmed.preset !== "custom" || !confirmed.points?.length) {
          throw new Error("desktop fan curve was not confirmed");
        }
        closeModal?.();
      })
      .catch(() => {
        savingNow.current = false;
        setSaving(false);
        setSaveError(true);
      });
  };

  if (!available || !point) {
    return <div style={{ color: theme.color.textMuted }}>{t("desktop.fan.manual.unavailable")}</div>;
  }

  return (
    <FocusRoot style={{ display: "flex", flexDirection: "column", gap: theme.space.md, padding: theme.space.sm }}>
      <div>
        <div style={{ fontSize: theme.font.value, color: theme.color.textPrimary }}>{title}</div>
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("desktop.fan.manual.subtitle")}</div>
      </div>
      <div style={{ maxWidth: 760, width: "100%", margin: "0 auto", display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <FanCurveGraph points={points} liveTemp={null} editable onChange={setPoints} />
        <Focusable style={{ ...segmentGroupStyle, flexWrap: "wrap" }}>
          {points.map(([temp, pwm], index) => {
            const active = index === selected;
            const choose = () => setSelected(index);
            return (
              <Focusable
                key={index}
                role="button"
                aria-label={t("desktop.fan.manual.point", { point: index + 1 })}
                style={{ ...segmentItemStyle(active), flex: "1 1 76px", padding: "6px 8px" }}
                onActivate={choose}
                onClick={choose}
              >
                {temp}° · {pwmToPercent(pwm)}%
              </Focusable>
            );
          })}
        </Focusable>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: theme.space.sm }}>
          <CurveSlider
            label={t("desktop.fan.manual.temperature")}
            value={`${point[0]} °C`}
            raw={point[0]}
            min={bounds.tempMin}
            max={bounds.tempMax}
            onChange={(value) => updatePoint(0, value)}
          />
          <CurveSlider
            label={t("desktop.fan.manual.speed")}
            value={`${pwmToPercent(point[1])}%`}
            raw={pwmToPercent(point[1])}
            min={pwmToPercent(bounds.pwmMin)}
            max={pwmToPercent(bounds.pwmMax)}
            onChange={(value) => updatePoint(1, percentToPwm(value))}
          />
        </div>
        {saveError && <div style={{ color: theme.color.danger, fontSize: theme.font.caption }}>{t("desktop.fan.manual.saveError")}</div>}
        <Focusable
          role="button"
          aria-label={t("desktop.fan.manual.save")}
          onActivate={save}
          onClick={save}
          style={{ ...segmentItemStyle(false), padding: "9px 12px", opacity: saving ? 0.55 : 1 }}
        >
          {saving ? t("desktop.fan.manual.saving") : t("desktop.fan.manual.save")}
        </Focusable>
      </div>
    </FocusRoot>
  );
};

const DesktopFanCurveModal: FC<ModalProps> = ({ closeModal, ...props }) => (
  <ModalRoot closeModal={closeModal} bAllowFullSize>
    <DesktopFanCurveModalBody {...props} closeModal={closeModal} />
  </ModalRoot>
);

export function openDesktopFanCurveModal(
  channelKey: DesktopFanChannel["key"],
  title: string,
  initialPoints: Point[],
  onClosed: () => void,
): void {
  showModal(
    <DesktopFanCurveModal channelKey={channelKey} title={title} initialPoints={initialPoints} />,
    window,
    { fnOnClose: onClosed },
  );
}
