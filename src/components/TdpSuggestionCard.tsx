import { FC, useState } from "react";
import { Focusable } from "@decky/ui";
import { LuSparkles } from "react-icons/lu";

import { useI18n } from "../i18n";
import { TdpLearned } from "../api";
import { dialToWatts } from "../tdp/logic";
import { ContainedSlider } from "./ContainedSlider";
import { theme } from "../theme";

interface Props {
  learned: TdpLearned;
  /** Apply a fixed PL1 (watts) as a manual setpoint — turns auto-TDP off. */
  onApply: (watts: number) => void;
}

/**
 * Learned-band TDP suggestion — mirrors the fan "Sugerido" card. Shown only when
 * auto-TDP is OFF and we have an enough band: "I learned this game works between
 * X–Y W" + a battery↔performance dial (local state) + an Apply button. Applying
 * sets a FIXED PL1 = lerp(floor, ceil, dial) and turns auto off (fixed vs dynamic
 * are distinct modes). Honest: no band → render nothing (no fabricated suggestion).
 */
export const TdpSuggestionCard: FC<Props> = ({ learned, onApply }) => {
  const { t } = useI18n();
  const [dial, setDial] = useState(50); // 0..100 → battery..performance
  if (!learned.enough || learned.floor == null || learned.ceil == null) return null;

  const floor = learned.floor;
  const ceil = learned.ceil;
  const watts = dialToWatts(floor, ceil, dial / 100);

  return (
    <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden",
                  display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm, color: theme.color.textPrimary }}>
        <LuSparkles size={16} color={theme.color.accent} />
        <span style={{ flex: 1, fontSize: theme.font.body }}>
          {t("tdp.suggest.title", { lo: floor, hi: ceil })}
        </span>
        <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {t("tdp.suggest.value", { w: watts })}
        </span>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.caption, color: theme.color.textMuted }}>
        <span>{t("tdp.dial.battery")}</span>
        <span>{t("tdp.dial.performance")}</span>
      </div>
      <ContainedSlider value={dial} min={0} max={100} step={5} onChange={setDial} />

      <Focusable
        style={{ textAlign: "center", padding: theme.space.sm, borderRadius: theme.radius.sm,
                 background: theme.color.accent, color: theme.color.onAccent, fontSize: theme.font.body, cursor: "pointer" }}
        onActivate={() => onApply(watts)}
        onClick={() => onApply(watts)}
      >
        {t("tdp.suggest.apply", { w: watts })}
      </Focusable>
    </div>
  );
};
