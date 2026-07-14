import { CSSProperties, FC } from "react";
import { Focusable, PanelSectionRow, ToggleField } from "@decky/ui";
import { LuAudioLines, LuHeadphones, LuSparkles, LuVolume2 } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { useEq } from "../audio/useEq";
import { ProfileSelector } from "../components/ProfileSelector";
import { Collapsible } from "../components/Collapsible";
import { EqCurveGraph } from "../components/EqCurveGraph";
import { segmentGroupStyle, segmentItemStyle } from "../components/segmented";

/** Sonido: system audio EQ. Curated per-machine presets up front, a full 10-band
 *  graphic EQ folded below. Independent curve per output route (speaker/headphone),
 *  per-game or global. Honest when the host has no PipeWire EQ support. */
export const SonidoSection: FC = () => {
  const { t } = useI18n();
  const { state, scope, game, onScope, onEnable, onPreset, onBands, onReset } = useEq();

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
            {state.presets.map((p) => (
              <Focusable
                key={p.id}
                style={chip(state.preset === p.id)}
                onActivate={() => onPreset(p.id)}
                onClick={() => onPreset(p.id)}
              >
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  {p.id === "device_tuned" && <LuSparkles size={12} color={theme.color.accent} />}
                  {presetLabel(p.id)}
                </span>
              </Focusable>
            ))}
          </Focusable>

          {/* Current response curve (read-only preview). */}
          <div style={{ ...theme.card, padding: "8px 6px 2px" }}>
            <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, margin: "0 4px 2px" }}>
              {t("audio.curve")}
            </div>
            <EqCurveGraph gains={state.gains} editable={false} onChange={() => {}} />
          </div>

          {/* Full 10-band editor, folded. Dragging a band commits on release. */}
          <Collapsible
            id="audioAdvanced"
            icon={<LuAudioLines size={15} />}
            title={t("audio.advanced")}
            summary={presetLabel(state.preset)}
          >
            <EqCurveGraph gains={state.gains} editable onChange={onBands} />
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
