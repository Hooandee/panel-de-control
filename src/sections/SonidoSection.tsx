import { CSSProperties, FC, ReactNode } from "react";
import { Focusable, PanelSectionRow, ToggleField } from "@decky/ui";
import {
  LuAudioLines, LuBell, LuHeadphones, LuMaximize2, LuMic, LuPause, LuPlay, LuSparkles,
  LuVolume2, LuWaves,
} from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { useEq } from "../audio/useEq";
import { toneLevel, ToneRegion } from "../audio/logic";
import { ProfileSelector } from "../components/ProfileSelector";
import { ContainedSlider } from "../components/ContainedSlider";
import { Collapsible } from "../components/Collapsible";
import { EqCurveGraph } from "../components/EqCurveGraph";
import { openEqCurveModal } from "../components/EqCurveModal";
import { segmentGroupStyle, segmentItemStyle } from "../components/segmented";

const TONE_ICON: Record<ToneRegion, ReactNode> = {
  graves: <LuWaves size={14} />,
  voces: <LuMic size={14} />,
  agudos: <LuBell size={14} />,
};
const ZONE_BAND: Record<ToneRegion, number> = { graves: 2, voces: 6, agudos: 8 };

/** Sonido: system audio EQ. Curated per-machine presets up front, a full 10-band
 *  graphic EQ folded below. Independent curve per output route (speaker/headphone),
 *  per-game or global. Honest when the host has no PipeWire EQ support. */
export const SonidoSection: FC = () => {
  const { t } = useI18n();
  const { state, scope, game, onScope, onEnable, onPreset, onBands, onTone, onReset, onTest, refresh } =
    useEq();

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
            <Focusable
              style={{ ...chip(state.test_playing), marginLeft: "auto", display: "flex", alignItems: "center", gap: 5, padding: "4px 10px" }}
              onActivate={onTest}
              onClick={onTest}
              title={state.test_playing ? t("audio.stop") : t("audio.test")}
            >
              {state.test_playing ? <LuPause size={12} /> : <LuPlay size={12} />}
              {state.test_playing ? t("audio.stop") : t("audio.test")}
            </Focusable>
          </div>

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

          {/* Simple tone: three sliders anyone understands (icon + label in the slider's
              own row = compact). Graves also engages the bass enhancer on its positive side. */}
          <div>
            <div style={{ fontSize: 10, letterSpacing: ".08em", textTransform: "uppercase", color: theme.color.textMuted, margin: "2px 2px 6px" }}>
              {t("audio.tone")}
            </div>
            {(["graves", "voces", "agudos"] as ToneRegion[]).map((region) => (
              <ContainedSlider
                key={region}
                label={
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    {TONE_ICON[region]}
                    {t(`audio.tone.${region}`)}
                  </span>
                }
                value={toneLevel(state.gains, region)}
                min={-12}
                max={12}
                step={1}
                showValue
                onChange={(v) => onTone(region, v)}
              />
            ))}
          </div>

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
