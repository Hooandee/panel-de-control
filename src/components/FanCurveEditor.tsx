import { FC } from "react";
import { Focusable, Spinner } from "@decky/ui";

import { useI18n } from "../i18n";
import { FanCurveControl, shownPoints } from "../fans/useFanCurve";
import { FanPreset } from "../api";
import { FanCurveGraph } from "./FanCurveGraph";
import { ProfileSelector } from "./ProfileSelector";
import { segmentGroupStyle, segmentItemStyle } from "./segmented";
import { theme } from "./../theme";

// "custom" is its own editing mode; presets are apply-only (read-only curve).
const MODES: FanPreset[] = ["auto", "silent", "balanced", "performance", "custom"];

interface Props {
  control: FanCurveControl;
  liveTemp: number | null;
}

/**
 * Presentational fan-curve editor: scope selector + preset chips + the draggable
 * curve graph + hint/saved line. Used both inline in the Ventiladores card and
 * (larger) inside the full-screen modal. All state/handlers come from a
 * FanCurveControl instance supplied by the caller.
 */
export const FanCurveEditor: FC<Props> = ({ control, liveTemp }) => {
  const { t } = useI18n();
  const curveState = control.state;

  if (!curveState) return <Spinner />;
  if (!curveState.supported) {
    return (
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
        {t("fans.curve.unsupported")}
      </div>
    );
  }

  const editable = curveState.preset === "custom";
  const points = shownPoints(curveState) ?? [];

  // What the footer line says: a transient "Guardado" after a save, else a hint
  // for the active mode.
  const hint = control.saved
    ? t("fans.curve.saved")
    : curveState.preset === "auto"
    ? t("fans.curve.auto.hint")
    : curveState.preset === "custom"
    ? t("fans.curve.custom.hint")
    : t(`fans.preset.${curveState.preset}`);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      {control.game && (
        <ProfileSelector
          scope={control.scope}
          gameName={control.game.name}
          hasGameProfile={curveState.has_game_profile}
          globalLabel={t("tdp.scope.global")}
          inheritHint={t("tdp.inherit")}
          onScope={control.setScope}
        />
      )}

      <Focusable style={{ ...segmentGroupStyle, flexWrap: "wrap" }}>
        {MODES.map((mode) => {
          const active = curveState.preset === mode;
          const select = () => (mode === "custom" ? control.onCustomMode() : control.onPreset(mode));
          return (
            <Focusable
              key={mode}
              style={{ ...segmentItemStyle(active), flex: "1 1 60px", padding: "6px 8px" }}
              onActivate={select}
              onClick={select}
            >
              {t(`fans.preset.${mode}`)}
            </Focusable>
          );
        })}
      </Focusable>

      <FanCurveGraph points={points} liveTemp={liveTemp} editable={editable} onChange={control.onCurve} />

      <div style={{ fontSize: theme.font.caption, color: control.saved ? theme.color.ok : theme.color.textMuted }}>
        {hint}
      </div>
    </div>
  );
};
