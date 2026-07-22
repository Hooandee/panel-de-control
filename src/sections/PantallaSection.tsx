import { FC } from "react";
import { Focusable, PanelSectionRow } from "@decky/ui";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { useColor } from "../display/useColor";
import { useNight } from "../display/useNight";
import { useHdr } from "../display/useHdr";
import { isNativeColor } from "../display/color";
import { PantallaProvider } from "../display/pantallaContext";
import { ProfileSelector } from "../components/ProfileSelector";
import { SectionView } from "../customize/blocks";

/** Pantalla: panel color. The scope tab, confirm/auto-revert bar and perf note are
 *  fixed chrome that governs the color blocks; the OLED look, color cluster, HDR
 *  and night mode are self-contained blocks rendered from the registry. All share
 *  one useColor/useHdr/useNight via PantallaProvider. Honest when the host has no
 *  gamescope color control. */
export const PantallaSection: FC = () => {
  const { t } = useI18n();
  const color = useColor();
  const { state, scope, game, revertIn, confirmCalibration, onScope } = color;
  const hdr = useHdr(scope, game?.appid ?? null);
  const night = useNight();

  if (!state) return null;

  if (!state.supported) {
    return (
      <PanelSectionRow>
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {t("display.unsupported")}
        </div>
      </PanelSectionRow>
    );
  }

  const active = !isNativeColor(state);

  return (
    <PantallaProvider value={{ color, hdr, night }}>
      {/* Confirm-or-auto-revert bar for an unconfirmed calibration change (the
          "changing screen resolution" safety pattern). Prominent + always visible. */}
      {revertIn !== null && (
        <PanelSectionRow>
          <div style={{
            display: "flex", alignItems: "center", gap: theme.space.sm,
            borderRadius: theme.radius.md, padding: theme.space.md, marginBottom: theme.space.card,
            background: "rgba(255,180,84,0.14)", boxShadow: `inset 0 0 0 1px ${theme.color.warn}`,
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
                {t("display.confirm.title")}
              </div>
              <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
                {t("display.confirm.desc", { s: revertIn })}
              </div>
            </div>
            <Focusable
              style={{
                display: "flex", alignItems: "center", justifyContent: "center",
                padding: "8px 14px", borderRadius: theme.radius.sm,
                background: theme.color.accent, color: "#ffffff", fontWeight: 700,
                fontSize: theme.font.body, cursor: "pointer", whiteSpace: "nowrap",
              }}
              onActivate={confirmCalibration} onClick={confirmCalibration}
            >
              {t("display.confirm.save")}
            </Focusable>
          </div>
        </PanelSectionRow>
      )}

      {/* Honest, device-named note where a look costs extra power (Intel forces
          composition). Padded so it doesn't crowd the cards. */}
      {state.perf_cost && active && (
        <PanelSectionRow>
          <div style={{
            fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.4,
            padding: "8px 10px", margin: "2px 0 8px",
            borderRadius: theme.radius.sm, background: "rgba(255,255,255,0.04)",
          }}>
            {t("display.perf_note", { device: state.device_name })}
          </div>
        </PanelSectionRow>
      )}

      {/* Scope tab — governs the per-game color controls below. */}
      <PanelSectionRow>
        <ProfileSelector
          scope={scope}
          gameName={game?.name ?? null}
          hasGameProfile={state.has_game_profile}
          globalLabel={t("tdp.scope.global")}
          inheritHint={t("display.inherit")}
          onScope={onScope}
        />
      </PanelSectionRow>

      <SectionView sectionId="display" />
    </PantallaProvider>
  );
};
