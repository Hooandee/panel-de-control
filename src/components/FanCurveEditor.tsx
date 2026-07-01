import { FC } from "react";
import { Focusable, Spinner } from "@decky/ui";
import { LuSparkles } from "react-icons/lu";

import { useI18n } from "../i18n";
import { FanCurveControl, shownPoints } from "../fans/useFanCurve";
import { FanPreset, FanSuggestion } from "../api";
import { FanCurveGraph } from "./FanCurveGraph";
import { AdaptiveCard } from "./SuggestionCard";
import { ProfileSelector } from "./ProfileSelector";
import { segmentGroupStyle, segmentItemStyle } from "./segmented";
import { theme } from "./../theme";

// The selectable curve modes. "adaptive" = the learned curve (adapts itself);
// "custom" = the hand-drawn editing mode; the rest are fixed presets.
const MODES: FanPreset[] = ["auto", "adaptive", "silent", "balanced", "performance", "custom"];

interface Props {
  control: FanCurveControl;
  liveTemp: number | null;
  // The live learning suggestion (per-game). Fuels the Adaptive card; may be null
  // until the first fetch lands.
  suggestion: FanSuggestion | null;
}

/**
 * Presentational fan-curve editor: scope selector + mode chips + (per mode) either
 * the Adaptive learning card or the draggable curve graph + hint/saved line. Used
 * both inline in the Ventiladores card and (larger) inside the full-screen modal.
 * All state/handlers come from a FanCurveControl instance supplied by the caller.
 */
export const FanCurveEditor: FC<Props> = ({ control, liveTemp, suggestion }) => {
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
  const adaptive = curveState.preset === "adaptive";
  const points = shownPoints(curveState) ?? [];

  // Footer hint for the active (non-adaptive) mode; adaptive shows its own card.
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
          const select = () =>
            mode === "custom" ? control.onCustomMode() : control.onPreset(mode);
          return (
            <Focusable
              key={mode}
              style={{ ...segmentItemStyle(active), flex: "1 1 60px", padding: "6px 8px",
                       display: "flex", alignItems: "center", justifyContent: "center", gap: 4 }}
              onActivate={select}
              onClick={select}
            >
              {mode === "adaptive" && <LuSparkles size={12} />}
              {t(`fans.preset.${mode}`)}
            </Focusable>
          );
        })}
      </Focusable>

      {adaptive ? (
        <AdaptiveCard
          suggestion={suggestion}
          liveTemp={liveTemp}
          bias={curveState.bias}
          onBias={control.onAdaptiveBias}
        />
      ) : (
        <>
          <FanCurveGraph points={points} liveTemp={liveTemp} editable={editable} onChange={control.onCurve} />
          <div style={{ fontSize: theme.font.caption, color: control.saved ? theme.color.ok : theme.color.textMuted }}>
            {hint}
          </div>
        </>
      )}
    </div>
  );
};
