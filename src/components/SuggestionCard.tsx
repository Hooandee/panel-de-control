import { FC } from "react";
import { Spinner } from "@decky/ui";
import { LuSparkles, LuVolumeX, LuThermometerSnowflake } from "react-icons/lu";

import { useI18n } from "../i18n";
import { FanSuggestion } from "../api";
import { Point } from "../fans/curve";
import { dialTone, interpolateCurves, learningProgress, minutesLeft, suggestState } from "../fans/suggestLogic";
import { FanCurveGraph } from "./FanCurveGraph";
import { ContainedSlider } from "./ContainedSlider";
import { ProgressBar } from "./ProgressBar";
import { ThermalScale } from "./ThermalScale";
import { theme } from "../theme";

interface Props {
  // The live suggestion for the current game; null until the first fetch lands.
  suggestion: FanSuggestion | null;
  liveTemp: number | null;
  // Persisted silence↔cool bias (-100..100) of the adaptive mode.
  bias: number;
  onBias: (bias: number) => void;
}

/**
 * Body of the ADAPTIVE curve mode (green). Choosing the mode IS the opt-in and IS
 * the apply — there is NO Apply button. It shows what the learner is doing for THIS
 * game and lets the user bias it quieter↔cooler:
 * - ready    → the learned curve (biased by the dial) + silence↔cool dial (drives HW)
 * - learning → green dashed candidate + green observed points + progress + "keep playing"
 * - spread   → progress full + honest "need more temperature variation"
 * - empty    → "start playing" (no fabricated curve — never-fake)
 * - disabled → "turn on learning in Settings"
 * - no_game  → "launch a game"
 * `unsupported` never reaches here (the chip only shows when the device can write).
 */
export const AdaptiveCard: FC<Props> = ({ suggestion, liveTemp, bias, onBias }) => {
  const { t } = useI18n();

  // No suggestion fetched yet → a neutral spinner (never a fabricated curve).
  if (!suggestion) return <Spinner width={24} />;

  const state = suggestState(suggestion);
  const ready = state === "ready";
  const green = theme.color.ok;
  const { minutes, target_minutes: target, seconds, target_seconds, available, band, curves } = suggestion;
  const left = minutesLeft(seconds, target_seconds);

  // ready → the learned curve biased by the persisted dial; learning/spread → the
  // balanced candidate (green preview). Never a curve without real data.
  const points: Point[] | null = !curves
    ? null
    : ready
      ? interpolateCurves(curves.quiet as Point[], curves.balanced as Point[], curves.cool as Point[], bias / 100)
      : (curves.balanced as Point[]);

  return (
    <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden",
                  boxShadow: `inset 0 0 0 1px ${green}`,
                  display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm, color: theme.color.textPrimary }}>
        <LuSparkles size={16} color={green} />
        <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
          <span style={{ fontSize: theme.font.body }}>
            {t(ready ? "fans.adaptive.title" : "fans.suggest.learning.title")}
          </span>
          <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {t("fans.suggest.continuous")}
          </span>
        </div>
        <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {ready && band
            ? t("fans.suggest.band", { lo: band.floor, hi: band.peak, min: minutes })
            : t("fans.suggest.progress", { min: minutes, target })}
        </span>
      </div>

      {!ready && <ProgressBar value={learningProgress(seconds, target_seconds, available)} />}

      {/* Peak temperature + colored scale. Only when a real band exists (never
          fabricate a peak). Shows during learning too so the number is live. */}
      {band && <ThermalScale peak={band.peak} />}

      {points && (
        <FanCurveGraph
          points={points}
          liveTemp={liveTemp}
          editable={false}
          onChange={() => {}}
          stroke={green}
          dashed={!ready}
        />
      )}

      {ready ? (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.caption, color: theme.color.textMuted }}>
            <span>{t("fans.suggest.dial.quiet")}</span>
            <span>{t("fans.suggest.dial.cool")}</span>
          </div>
          <ContainedSlider value={bias} min={-100} max={100} step={1} onChange={onBias} />
          {/* Translate the dial into plain language for a non-expert. */}
          {(() => {
            const tone = dialTone(bias);
            const ToneIcon = tone === "quiet" ? LuVolumeX : tone === "cool" ? LuThermometerSnowflake : LuSparkles;
            return (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.xs,
                            fontSize: theme.font.caption, color: theme.color.textMuted }}>
                <ToneIcon size={13} />
                <span>{t(`fans.suggest.tone.${tone}`)}</span>
              </div>
            );
          })()}
        </>
      ) : (
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.5 }}>
          {state === "spread" ? t("fans.suggest.hint.flat")
            : state === "disabled" ? t("fans.suggest.hint.disabled")
            : state === "no_game" ? t("fans.suggest.msg.nogame")
            : state === "empty" ? t("fans.suggest.msg.empty")
            : t("fans.suggest.msg.learning", { left })}
        </div>
      )}
    </div>
  );
};
