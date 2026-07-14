import { FC, ReactNode } from "react";
import { Focusable } from "@decky/ui";
import { LuSparkles, LuRefreshCw, LuVolumeX, LuScale, LuZap, LuPencil } from "react-icons/lu";

import { useI18n } from "../i18n";
import { FanCurveControl, shownPoints } from "../fans/useFanCurve";
import { presetConverges } from "../fans/logic";
import { fanCurveNotice } from "../fans/notice";
import { FanPreset, FanSuggestion } from "../api";
import { FanCurveGraph } from "./FanCurveGraph";
import { Loading } from "./Loading";
import { AdaptiveCard } from "./SuggestionCard";
import { ProfileSelector } from "./ProfileSelector";
import { segmentGroupStyle, segmentItemStyle } from "./segmented";
import { theme } from "./../theme";

// The selectable curve modes. "adaptive" = the learned curve (adapts itself);
// "custom" = the hand-drawn editing mode; the rest are fixed presets.
const MODES: FanPreset[] = ["auto", "adaptive", "silent", "balanced", "performance", "custom"];

// One icon per mode. Inactive chips show ONLY the icon (like the top tab bar), so
// six modes fit one tidy row; the selected chip expands to icon + label.
const MODE_ICON: Record<FanPreset, ReactNode> = {
  auto: <LuRefreshCw size={13} />,
  adaptive: <LuSparkles size={13} />,
  silent: <LuVolumeX size={13} />,
  balanced: <LuScale size={13} />,
  performance: <LuZap size={13} />,
  custom: <LuPencil size={13} />,
};

interface Props {
  control: FanCurveControl;
  liveTemp: number | null;
  // The live learning suggestion (per-game). Fuels the Adaptive card; may be null
  // until the first fetch lands.
  suggestion: FanSuggestion | null;
  // Full-screen modal? Only then do the mode chips show their labels; inline (the
  // narrow QAM card) they stay icon-only so the six modes fit one clean row.
  expanded?: boolean;
}

/**
 * Presentational fan-curve editor: scope selector + mode chips + (per mode) either
 * the Adaptive learning card or the draggable curve graph + hint/saved line. Used
 * both inline in the Ventiladores card and (larger) inside the full-screen modal.
 * All state/handlers come from a FanCurveControl instance supplied by the caller.
 */
export const FanCurveEditor: FC<Props> = ({ control, liveTemp, suggestion, expanded = false }) => {
  const { t } = useI18n();
  const curveState = control.state;

  if (!curveState) return <Loading />;
  if (!curveState.supported) {
    return (
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
        {fanCurveNotice(curveState, t)}
      </div>
    );
  }

  const editable = curveState.preset === "custom";
  const adaptive = curveState.preset === "adaptive";
  const points = shownPoints(curveState) ?? [];

  // Footer hint for the active (non-adaptive) mode; adaptive shows its own card.
  // For a fixed preset while the device is still cool, explain that presets look
  // the same until it heats up (the fan sits at its floor) — so idle-convergence
  // isn't mistaken for "the preset didn't apply".
  const hint = control.saved
    ? t("fans.curve.saved")
    : curveState.preset === "auto"
    ? t("fans.curve.auto.hint")
    : curveState.preset === "custom"
    ? t("fans.curve.custom.hint")
    : presetConverges(curveState.preset, liveTemp)
    ? t("fans.preset.cool.hint")
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

      <Focusable style={{ ...segmentGroupStyle, ...(expanded ? { flexWrap: "wrap" } : null) }}>
        {MODES.map((mode) => {
          const active = curveState.preset === mode;
          const label = t(`fans.preset.${mode}`);
          const select = () =>
            mode === "custom" ? control.onCustomMode() : control.onPreset(mode);
          return (
            <Focusable
              key={mode}
              style={{ ...segmentItemStyle(active), flex: expanded ? "1 1 90px" : 1, padding: "6px 8px" }}
              aria-label={label}
              title={label}
              onActivate={select}
              onClick={select}
            >
              {MODE_ICON[mode]}
              {/* Labels only in the full-screen modal; the inline QAM card is
                  icon-only (tooltip/aria-label still name each mode). */}
              {expanded && <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{label}</span>}
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
