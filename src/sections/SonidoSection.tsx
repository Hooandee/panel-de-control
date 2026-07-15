import { CSSProperties, FC, ReactNode } from "react";
import { Focusable, PanelSectionRow, ToggleField } from "@decky/ui";
import {
  LuAudioLines, LuBell, LuHeadphones, LuMaximize2, LuMic, LuMusic, LuPause, LuPlay, LuPlus,
  LuShieldCheck, LuSparkles, LuTriangleAlert, LuVolume2, LuWaves, LuX,
} from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { useEq } from "../audio/useEq";
import { GAIN_MAX, GAIN_MIN, toneCeiling, toneLevel, ToneRegion } from "../audio/logic";
import { ProfileSelector } from "../components/ProfileSelector";
import { ContainedSlider } from "../components/ContainedSlider";
import { Collapsible } from "../components/Collapsible";
import { EqCurveGraph } from "../components/EqCurveGraph";
import { openEqCurveModal } from "../components/EqCurveModal";
import { openSaveProfileModal } from "../components/SaveProfileModal";
import { segmentGroupStyle, segmentItemStyle } from "../components/segmented";

const TONE_ICON: Record<ToneRegion, ReactNode> = {
  graves: <LuWaves size={14} />,
  voces: <LuMic size={14} />,
  agudos: <LuBell size={14} />,
};
const ZONE_BAND: Record<ToneRegion, number> = { graves: 2, voces: 6, agudos: 8 };
const TEST_ICON: Record<string, ReactNode> = {
  bass: <LuWaves size={12} />,
  voice: <LuMic size={12} />,
  treble: <LuBell size={12} />,
  full: <LuMusic size={12} />,
};

/** Sonido: system audio EQ. Curated per-machine presets up front, a full 10-band
 *  graphic EQ folded below. Independent curve per output route (speaker/headphone),
 *  per-game or global. Honest when the host has no PipeWire EQ support. */
export const SonidoSection: FC = () => {
  const { t } = useI18n();
  const {
    state, scope, game, onScope, onEnable, onPreset, onBands, onTone, onLoudness, onGuard, onReset,
    onTest, onSaveProfile, onApplyProfile, onDeleteProfile, refresh,
  } = useEq();

  if (!state) return null;

  if (!state.supported) {
    return (
      <PanelSectionRow>
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {t("audio.unsupported")}
        </div>
      </PanelSectionRow>
    );
  }

  const chip = (on: boolean): CSSProperties => ({
    ...segmentItemStyle(on),
    padding: "6px 12px",
    whiteSpace: "nowrap",
  });

  const presetLabel = (id: string) =>
    id === "device_tuned"
      ? t("audio.preset.device_tuned", { device: state.device_name })
      : t(`audio.preset.${id}`);

  const isHeadphone = state.route === "headphone";
  const guarded = !isHeadphone && state.guard;
  const ceilings = isHeadphone ? undefined : state.safe_limits.bands;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.section }}>
      <ProfileSelector
        scope={scope}
        gameName={game?.name ?? null}
        hasGameProfile={state.has_game_profile}
        globalLabel={t("tdp.scope.global")}
        inheritHint={t("audio.inherit")}
        onScope={onScope}
      />

      <PanelSectionRow>
        <ToggleField
          label={t("audio.enable")}
          description={t("audio.enable.desc")}
          checked={state.enabled}
          onChange={onEnable}
        />
      </PanelSectionRow>

      {state.enabled && (
        <>
          {/* Active output route (auto-detected) — the curve you edit follows it. */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: theme.font.caption,
              color: theme.color.textMuted,
            }}
          >
            {isHeadphone ? <LuHeadphones size={14} /> : <LuVolume2 size={14} />}
            <span style={{ color: theme.color.textPrimary }}>
              {isHeadphone ? t("audio.route.headphone") : t("audio.route.speaker")}
            </span>
            <span
              style={{
                fontSize: 9,
                color: theme.color.ok,
                border: `1px solid ${theme.color.ok}`,
                borderRadius: 6,
                padding: "0 5px",
              }}
            >
              {t("audio.route.auto")}
            </span>
          </div>

          <Collapsible
            id="audioTest"
            icon={<LuPlay size={15} />}
            title={t("audio.test.title")}
            summary={
              state.test_playing && state.test_sample
                ? t(`audio.test.${state.test_sample}`)
                : undefined
            }
          >
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {state.test_samples.map((s) => {
                const on = state.test_playing && state.test_sample === s;
                return (
                  <Focusable
                    key={s}
                    style={{ ...chip(on), display: "flex", alignItems: "center", gap: 5, padding: "6px 12px" }}
                    onActivate={() => onTest(s)}
                    onClick={() => onTest(s)}
                  >
                    {on ? <LuPause size={12} /> : TEST_ICON[s]}
                    {t(`audio.test.${s}`)}
                  </Focusable>
                );
              })}
            </div>
          </Collapsible>

          {/* Curated presets — the device-tuned one is the hero (first). */}
          <Focusable style={{ ...segmentGroupStyle, flexWrap: "wrap", gap: 6, background: "none", padding: 0 }}>
            {state.presets.map((p) => {
              const on = state.preset === p.id;
              return (
                <Focusable
                  key={p.id}
                  style={chip(on)}
                  onActivate={() => onPreset(p.id)}
                  onClick={() => onPreset(p.id)}
                >
                  <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    {p.id === "device_tuned" && (
                      <LuSparkles
                        size={12}
                        color={on ? theme.color.textPrimary : theme.color.accent}
                      />
                    )}
                    {presetLabel(p.id)}
                  </span>
                </Focusable>
              );
            })}
          </Focusable>

          {state.preset === "device_tuned" &&
            state.presets.find((p) => p.id === "device_tuned")?.tuned === false && (
              <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginTop: -4 }}>
                {t("audio.preset.device_tuned.base")}
              </div>
            )}

          {/* My profiles — named curves the user saves and reuses across games. */}
          <div>
            <div style={{ fontSize: 10, letterSpacing: ".08em", textTransform: "uppercase", color: theme.color.textMuted, margin: "2px 2px 6px" }}>
              {t("audio.profile.mine")}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {state.profiles.map((pr) => {
                const active =
                  pr.bass === state.bass &&
                  pr.gains.length === state.gains.length &&
                  pr.gains.every((g, i) => g === state.gains[i]);
                return (
                <span key={pr.name} style={{ ...chip(active), display: "inline-flex", alignItems: "center", gap: 6, paddingRight: 6 }}>
                  <Focusable
                    style={{ cursor: "pointer" }}
                    onActivate={() => onApplyProfile(pr.name)}
                    onClick={() => onApplyProfile(pr.name)}
                  >
                    {pr.name}
                  </Focusable>
                  <Focusable
                    style={{ display: "flex", cursor: "pointer", color: theme.color.textMuted }}
                    onActivate={() => onDeleteProfile(pr.name)}
                    onClick={() => onDeleteProfile(pr.name)}
                    title={t("audio.profile.delete")}
                  >
                    <LuX size={12} />
                  </Focusable>
                </span>
                );
              })}
              <Focusable
                style={{ ...chip(false), display: "inline-flex", alignItems: "center", gap: 4 }}
                onActivate={() => openSaveProfileModal(game?.name ?? "", onSaveProfile)}
                onClick={() => openSaveProfileModal(game?.name ?? "", onSaveProfile)}
              >
                <LuPlus size={12} />
                {t("audio.profile.saveCurrent")}
              </Focusable>
            </div>
          </div>

          {/* Simple tone: three sliders anyone understands (icon + label in the slider's
              own row = compact). Graves also engages the bass enhancer on its positive side. */}
          <div>
            <div style={{ fontSize: 10, letterSpacing: ".08em", textTransform: "uppercase", color: theme.color.textMuted, margin: "2px 2px 6px" }}>
              {t("audio.tone")}
            </div>
            {(["graves", "voces", "agudos"] as ToneRegion[]).map((region) => {
              const level = toneLevel(state.gains, region);
              const cap = ceilings ? toneCeiling(region, ceilings) : GAIN_MAX;
              const over = !isHeadphone && !state.guard && level > cap;
              return (
                <ContainedSlider
                  key={region}
                  label={
                    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      {TONE_ICON[region]}
                      {t(`audio.tone.${region}`)}
                      {over && (
                        <LuTriangleAlert size={12} color={theme.color.danger} title={t("audio.guard.risk")} />
                      )}
                    </span>
                  }
                  value={guarded ? Math.min(level, cap) : level}
                  min={GAIN_MIN}
                  max={guarded ? cap : GAIN_MAX}
                  step={1}
                  showValue
                  onChange={(v) => onTone(region, v)}
                />
              );
            })}
          </div>

          {!isHeadphone && (
            <PanelSectionRow>
              <ToggleField
                label={
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <LuShieldCheck size={14} />
                    {t("audio.guard")}
                  </span>
                }
                description={state.guard ? t("audio.guard.desc") : t("audio.guard.off")}
                checked={state.guard}
                onChange={onGuard}
              />
            </PanelSectionRow>
          )}

          <PanelSectionRow>
            <ToggleField
              label={t("audio.loudness")}
              description={t("audio.loudness.desc")}
              checked={state.loudness}
              onChange={onLoudness}
            />
          </PanelSectionRow>

          {/* Full 10-band editor, folded for experts — with a full-screen button and
              friendly zone labels on the graph. */}
          <Collapsible
            id="audioAdvanced"
            icon={<LuAudioLines size={15} />}
            title={t("audio.advanced")}
            summary={presetLabel(state.preset)}
            action={
              <Focusable
                style={{ display: "flex", alignItems: "center", padding: 4, borderRadius: theme.radius.sm, color: theme.color.textMuted, cursor: "pointer" }}
                onActivate={() => openEqCurveModal(refresh)}
                onClick={() => openEqCurveModal(refresh)}
                title={t("audio.fullscreen")}
              >
                <LuMaximize2 size={16} />
              </Focusable>
            }
          >
            <EqCurveGraph
              gains={state.gains}
              editable
              onChange={onBands}
              ceilings={ceilings}
              guard={guarded}
              zones={(["graves", "voces", "agudos"] as ToneRegion[]).map((r) => ({
                label: t(`audio.tone.${r}`),
                band: ZONE_BAND[r],
              }))}
              yTitle={t("audio.axis.y")}
            />
            <Focusable
              style={{ ...chip(false), textAlign: "center", marginTop: 10 }}
              onActivate={onReset}
              onClick={onReset}
            >
              {t("audio.reset")}
            </Focusable>
          </Collapsible>
        </>
      )}
    </div>
  );
};
