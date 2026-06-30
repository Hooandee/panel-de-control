import { FC, useState } from "react";
import { Focusable, SliderField } from "@decky/ui";
import { LuSparkles } from "react-icons/lu";

import { useI18n } from "../i18n";
import { FanSuggestion } from "../api";
import { Point } from "../fans/curve";
import { interpolateCurves } from "../fans/suggestLogic";
import { FanCurveGraph } from "./FanCurveGraph";
import { theme } from "../theme";

interface Props {
  suggestion: FanSuggestion; // caller guarantees available && curves != null
  liveTemp: number | null;
  onApply: (points: Point[]) => void;
}

/**
 * "Sugerido" preview: a read-only curve graph fit to the game's observed thermal
 * band, plus a silence↔cool dial that blends the three anchor curves locally (no
 * RPC per drag). Applying hands the resulting points to the curve control, which
 * persists them as a Custom profile. Honest: the dial is a preference, not a
 * promise of degrees — the caption states the real band it was fit to.
 */
export const SuggestionCard: FC<Props> = ({ suggestion, liveTemp, onApply }) => {
  const { t } = useI18n();
  const [dial, setDial] = useState(0); // -100..100 → quiet..cool
  const [open, setOpen] = useState(false);

  const c = suggestion.curves!;
  const points = interpolateCurves(
    c.quiet as Point[],
    c.balanced as Point[],
    c.cool as Point[],
    dial / 100,
  );

  return (
    <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden",
                  display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      <Focusable
        style={{ display: "flex", alignItems: "center", gap: theme.space.sm, cursor: "pointer", color: theme.color.textPrimary }}
        onActivate={() => setOpen((o) => !o)}
        onClick={() => setOpen((o) => !o)}
      >
        <LuSparkles size={16} color={theme.color.accent} />
        <span style={{ flex: 1, fontSize: theme.font.body }}>{t("fans.suggest.title")}</span>
        <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {suggestion.band
            ? t("fans.suggest.band", { lo: suggestion.band.floor, hi: suggestion.band.peak, min: suggestion.minutes })
            : ""}
        </span>
      </Focusable>

      {open && (
        <>
          <FanCurveGraph points={points} liveTemp={liveTemp} editable={false} onChange={() => {}} />

          <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.caption, color: theme.color.textMuted }}>
            <span>{t("fans.suggest.dial.quiet")}</span>
            <span>{t("fans.suggest.dial.cool")}</span>
          </div>
          {/* scale(0.86)+overflow per the SliderField bleed gotcha (see AdvancedBoost). */}
          <div style={{ overflow: "hidden" }}>
            <div style={{ transform: "scale(0.86)" }}>
              <SliderField value={dial} min={-100} max={100} step={1} onChange={setDial} />
            </div>
          </div>

          <Focusable
            style={{ textAlign: "center", padding: theme.space.sm, borderRadius: theme.radius.sm,
                     background: theme.color.accent, color: "#06121f", fontSize: theme.font.body, cursor: "pointer" }}
            onActivate={() => onApply(points)}
            onClick={() => onApply(points)}
          >
            {t("fans.suggest.apply")}
          </Focusable>
        </>
      )}
    </div>
  );
};
