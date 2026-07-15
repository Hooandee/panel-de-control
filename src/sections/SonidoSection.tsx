import { CSSProperties, FC } from "react";
import { Focusable, PanelSectionRow, ToggleField } from "@decky/ui";
import { LuHeadphones, LuSparkles, LuVolume2 } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { useEq } from "../audio/useEq";
import { ProfileSelector } from "../components/ProfileSelector";
import { ContainedSlider } from "../components/ContainedSlider";
import { EqCurveGraph } from "../components/EqCurveGraph";
import { segmentGroupStyle, segmentItemStyle } from "../components/segmented";

/** Sonido: system audio EQ. Curated per-machine presets up front, a full 10-band
 *  graphic EQ folded below. Independent curve per output route (speaker/headphone),
 *  per-game or global. Honest when the host has no PipeWire EQ support. */
export const SonidoSection: FC = () => {
  const { t } = useI18n();
  const { state, scope, game, onScope, onEnable, onPreset, onBands, onNudge, onBass, onReset, onTest } =
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
    borderRadius: 20,
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

          {/* Quick, non-expert tweaks — tap to nudge the curve toward an intent. */}
          <div>
            <div style={{ fontSize: 10, letterSpacing: ".08em", textTransform: "uppercase", color: theme.color.textMuted, margin: "2px 2px 6px" }}>
              {t("audio.quick")}
            </div>
            {(["bass", "voice", "treble"] as const).map((dim) => (
              <div key={dim} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <span style={{ flex: 1, fontSize: theme.font.body, color: theme.color.textPrimary }}>
                  {t(`audio.nudge.${dim}`)}
                </span>
                <Focusable
                  style={{ ...chip(false), minWidth: 40, textAlign: "center", padding: "6px 0" }}
                  onActivate={() => onNudge(dim, -1)}
                  onClick={() => onNudge(dim, -1)}
                >
                  −
                </Focusable>
                <Focusable
                  style={{ ...chip(false), minWidth: 40, textAlign: "center", padding: "6px 0" }}
                  onActivate={() => onNudge(dim, 1)}
                  onClick={() => onNudge(dim, 1)}
                >
                  +
                </Focusable>
              </div>
            ))}
          </div>

          {/* One curve — editable, always visible. A preset sets it; drag any band to
              fine-tune (commits on release). */}
          <div style={{ ...theme.card, padding: "8px 6px 4px" }}>
            <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, margin: "0 4px 4px" }}>
              {t("audio.curve")}
            </div>
            <EqCurveGraph gains={state.gains} editable onChange={onBands} />
            <div style={{ marginTop: 6 }}>
              <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, margin: "0 4px 2px" }}>
                {t("audio.bass")}
              </div>
              <ContainedSlider
                value={state.bass}
                min={0}
                max={100}
                step={5}
                showValue
                onChange={onBass}
              />
            </div>
            <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
              <Focusable
                style={{ ...chip(false), flex: 1, textAlign: "center" }}
                onActivate={onTest}
                onClick={onTest}
              >
                {t("audio.test")}
              </Focusable>
              <Focusable
                style={{ ...chip(false), flex: 1, textAlign: "center" }}
                onActivate={onReset}
                onClick={onReset}
              >
                {t("audio.reset")}
              </Focusable>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
