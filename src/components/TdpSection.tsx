import { PanelSectionRow, SliderField } from "@decky/ui";
import { FC } from "react";

import { TdpState, TdpScope, PowerDraw } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { Loading } from "./Loading";
import { ProfileSelector } from "./ProfileSelector";
import { PowerArc } from "./PowerArc";
import { Presets } from "./Presets";
import { AdvancedBoost } from "./AdvancedBoost";
import { TdpSuggestionCard } from "./TdpSuggestionCard";

// Learned-band reasons worth surfacing as "still learning" (others — no_game,
// disabled, error — show no line).
const LEARNING_REASONS = new Set(["no_data", "too_few", "one_level"]);

export interface TdpSectionProps {
  tdp: TdpState | null;
  scope: TdpScope;
  game: { appid: string; name: string } | null;
  power: PowerDraw | null;
  onScope: (scope: TdpScope) => void;
  onWatts: (watts: number) => void;
  onSetLevels: (off2: number, off3: number) => void;
  onResetAuto: () => void;
  // Apply the learned-band suggestion as a FIXED PL1 (also turns auto-TDP off).
  onApplySuggestion: (watts: number) => void;
}

export const TdpSection: FC<TdpSectionProps> = ({ tdp, scope, game, power, onScope, onWatts, onSetLevels, onResetAuto, onApplySuggestion }) => {
  const { t } = useI18n();

  if (!tdp) return <Loading />;

  if (!tdp.supported) {
    return (
      <PanelSectionRow>
        <div style={{ fontSize: 11, color: "rgba(255,255,255,0.45)" }}>{t("tdp.unsupported")}</div>
      </PanelSectionRow>
    );
  }

  const view =
    scope === "global"
      ? { watts: tdp.global_watts, levels: tdp.global_levels, auto: tdp.global_auto }
      : { watts: tdp.watts, levels: tdp.levels, auto: tdp.auto };
  // Active ceiling: on battery the device-aware cap (max), on charger max_ac.
  // Never offer more than the current power source can deliver.
  const activeMax = tdp.on_ac ? tdp.limits.max_ac : tdp.limits.max;
  const isAutoOn = power?.auto_tdp ?? false;
  const atCeiling = Math.min(view.watts, activeMax) >= activeMax;

  return (
    <>
      <PanelSectionRow>
        <ProfileSelector
          scope={scope}
          gameName={game?.name ?? null}
          hasGameProfile={tdp.has_game_profile}
          globalLabel={t("tdp.scope.global")}
          inheritHint={t("tdp.inherit")}
          onScope={onScope}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <PowerArc
          watts={view.watts}
          limits={tdp.limits}
          onAc={tdp.on_ac}
          actualWatts={power?.watts ?? null}
          gpuBusy={power?.gpu_busy ?? null}
          auto={isAutoOn}
          setpoint={power?.setpoint ?? null}
          appliedWatts={power?.applied ?? null}
        />
      </PanelSectionRow>
      {tdp.external_change && (
        // An external tool moved the TDP and we adopted it — say so, so the value
        // doesn't read as a bug.
        <PanelSectionRow>
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {t("tdp.external_change")}
          </div>
        </PanelSectionRow>
      )}
      {/* Auto status, sitting directly under the arc so it fills what would
          otherwise be dead space above the toggle. */}
      {isAutoOn && power?.ui_floor_engaged && (
        // Honest: opening the QAM raised PL1 so the CPU-bound menu render stays
        // fluid — the arc shows a menu-temporary value, NOT the settled in-game one.
        <PanelSectionRow>
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {t("tdp.auto.ui_floor")}
          </div>
        </PanelSectionRow>
      )}
      {isAutoOn && (
        // The learned band when ready, a plain "learning…" note while collecting,
        // nothing otherwise. Auto-TDP itself is decoupled from the band (runs the
        // full range + explores); this is a read-only status line.
        tdp.learned.enough ? (
          <PanelSectionRow>
            <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
              {t("tdp.learned.band", { lo: tdp.learned.floor!, hi: tdp.learned.ceil! })}
            </div>
          </PanelSectionRow>
        ) : LEARNING_REASONS.has(tdp.learned.reason) ? (
          <PanelSectionRow>
            <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
              {t("tdp.learned.learning.title")}
            </div>
          </PanelSectionRow>
        ) : null
      )}
      {!isAutoOn && (
        <>
          <PanelSectionRow>
            <SliderField
              value={Math.min(view.watts, activeMax)}
              min={tdp.limits.min}
              max={activeMax}
              step={1}
              showValue
              onChange={onWatts}
            />
          </PanelSectionRow>
          {atCeiling && (
            <PanelSectionRow>
              <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
                {tdp.on_ac
                  ? t("tdp.ceiling.charger", { max: activeMax })
                  : t("tdp.ceiling.battery", { max: activeMax })}
              </div>
            </PanelSectionRow>
          )}
          <PanelSectionRow>
            <Presets
              presets={tdp.presets}
              onAc={tdp.on_ac}
              activeWatts={view.watts}
              labels={{
                save: t("tdp.preset.save"),
                balanced: t("tdp.preset.balanced"),
                turbo: t("tdp.preset.turbo"),
              }}
              onPick={onWatts}
            />
          </PanelSectionRow>
          {tdp.supports_advanced && (
            <PanelSectionRow>
              <AdvancedBoost
                levels={view.levels}
                auto={view.auto}
                bounds={{ pl2: tdp.level_limits.pl2, pl3: tdp.level_limits.pl3 }}
                onSetLevels={onSetLevels}
                onResetAuto={onResetAuto}
              />
            </PanelSectionRow>
          )}
          {/* Learned-band suggestion: apply a FIXED watt value the loop has learned
              this game lives in. Auto OFF only (it's a third, distinct way to set TDP:
              manual slider · auto-TDP dynamic · learned fixed). Renders nothing without
              an enough band (never a fabricated suggestion). */}
          {tdp.learned.enough && (
            <PanelSectionRow>
              <TdpSuggestionCard learned={tdp.learned} onApply={onApplySuggestion} />
            </PanelSectionRow>
          )}
        </>
      )}
    </>
  );
};
