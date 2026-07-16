import { CSSProperties, FC } from "react";
import { Focusable, PanelSectionRow } from "@decky/ui";
import { LuGlobe, LuPalette, LuSlidersHorizontal, LuSparkles } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { useColor } from "../display/useColor";
import { useNight } from "../display/useNight";
import { useHdr } from "../display/useHdr";
import { isNativeColor, isCalibrated } from "../display/color";
import { ProfileSelector } from "../components/ProfileSelector";
import { ContainedSlider } from "../components/ContainedSlider";
import { Collapsible } from "../components/Collapsible";
import { OledLookCard } from "../components/OledLookCard";
import { AdvancedColor } from "../components/AdvancedColor";
import { NightModeCard } from "../components/NightModeCard";
import { HdrPanel } from "../components/HdrPanel";
import { segmentGroupStyle, segmentItemStyle } from "../components/segmented";
import { useOledLookCardHidden } from "../system/oledLookVisibility";

/** Pantalla: panel color. One-tap OLED look (per model) → saturation (per-game) →
 *  global calibration (temperature / contrast). Honest when the host
 *  has no gamescope color control. */
export const PantallaSection: FC = () => {
  const { t } = useI18n();
  const {
    state, scope, game, revertIn, onScope,
    onSaturation, onCalibration, confirmCalibration, onOledLook, onPreset, onReset,
  } = useColor();
  const night = useNight();
  const hdr = useHdr(scope, game?.appid ?? null);
  const oledLookCardHidden = useOledLookCardHidden();

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
  const chip = (on: boolean): CSSProperties => ({
    ...segmentItemStyle(on),
    flex: 1,
    padding: "6px 4px",
  });

  const sdrBody = (
    <>
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

      {/* Scope tab — governs the per-game color controls below (OLED look, Ambiente,
          saturation, calibration, HDR). */}
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

      {/* One-tap per-model OLED look — per-game via the scope tab above; hidden on real
          OLED panels (oled_look null). */}
      {state.oled_look && !oledLookCardHidden && (
        <div style={{ marginTop: theme.space.sm }}>
          <OledLookCard active={active} onApply={onOledLook} onReset={onReset} />
        </div>
      )}

      {/* Ambiente — one-tap balanced looks, per-game via the scope tab above. */}
      <PanelSectionRow>
        <div style={{ ...theme.card, padding: theme.space.md, marginTop: theme.space.sm, overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
            <LuSparkles size={16} color={theme.color.accent} />
            <span style={{ fontSize: theme.font.body, fontWeight: 600, color: theme.color.textPrimary }}>
              {t("display.look")}
            </span>
          </div>
          <Focusable style={segmentGroupStyle}>
            {state.presets.map((key) => (
              <Focusable key={key} style={chip(state.active_preset === key)}
                onActivate={() => onPreset(key)} onClick={() => onPreset(key)}>
                {t(`display.look.${key}`)}
              </Focusable>
            ))}
          </Focusable>
        </div>
      </PanelSectionRow>
      <PanelSectionRow>
        <div style={{ ...theme.card, padding: theme.space.md, margin: `${theme.space.sm}px 0`, overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 2 }}>
            <LuPalette size={16} color={theme.color.accent} />
            <span style={{ fontSize: theme.font.body, fontWeight: 600, color: theme.color.textPrimary }}>
              {t("display.saturation")}
            </span>
            <span style={{ marginLeft: "auto", fontSize: theme.font.value, fontWeight: 700, color: theme.color.textPrimary }}>
              {state.saturation}%
            </span>
          </div>
          <ContainedSlider value={state.saturation} min={0} max={200} step={5}
            scale={0.75} onChange={onSaturation} />
        </div>
      </PanelSectionRow>

      {/* Advanced color lab (global panel calibration). */}
      <Collapsible
        id="color-advanced"
        icon={<LuSlidersHorizontal size={16} />}
        title={t("display.advanced")}
        summary={isCalibrated(state) ? t("display.custom") : t("display.native")}
      >
        <AdvancedColor state={state} onChange={onCalibration} />
        {active && (
          <Focusable
            style={{
              display: "flex", justifyContent: "center", marginTop: 10, padding: "6px 12px",
              borderRadius: theme.radius.sm, background: theme.color.surfaceRaised,
              boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
              color: theme.color.textPrimary, fontSize: theme.font.body, cursor: "pointer",
            }}
            onActivate={onReset} onClick={onReset}
          >
            {t("display.reset")}
          </Focusable>
        )}
      </Collapsible>

      {/* HDR on/off — per-game, governed by the same scope tab as the color above. */}
      {hdr.state?.supported && (
        <PanelSectionRow>
          <HdrPanel state={hdr.state} onChange={hdr.update} />
        </PanelSectionRow>
      )}

      {/* General — applies to every game, NOT governed by the scope tab above. */}
      {night.state?.supported && (
        <>
          <PanelSectionRow>
            <div style={{ display: "flex", alignItems: "center", gap: 8, margin: `${theme.space.md}px 0 ${theme.space.xs}px`, color: theme.color.textMuted }}>
              <LuGlobe size={13} />
              <span style={{ fontSize: theme.font.caption }}>{t("display.general")}</span>
              <div style={{ flex: 1, height: 1, background: theme.color.hairline }} />
            </div>
          </PanelSectionRow>
          <PanelSectionRow>
            <NightModeCard state={night.state} onChange={night.update} />
          </PanelSectionRow>
        </>
      )}
    </>
  );

  return sdrBody;
};
