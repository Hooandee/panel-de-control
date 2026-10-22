import { DialogButton, DropdownItem, PanelSectionRow, ToggleField } from "@decky/ui";
import { FC, useEffect, useState } from "react";
import { LuCheck, LuPlug, LuSend, LuSun } from "react-icons/lu";

import { PixelPreview } from "../accessories/PixelPreview";
import { DecodedFrames } from "../accessories/pixelFrames";
import { SceneGallery } from "../accessories/SceneGallery";
import { SceneOptions } from "../accessories/SceneOptions";
import type { Block } from "../accessories/ComposerEditor";
import { loadPreview, setSceneDraft, useAccessories, usePreviewEpoch, useSceneDraft } from "../accessories/useAccessories";
import { pauseJsauxApp } from "../api";
import { Loading } from "../components/Loading";
import { ValueBar } from "../components/ValueBar";
import { useI18n } from "../i18n";
import { theme } from "../theme";

const HERO_PITCH = 4;
const HALF_HOURS = Array.from({ length: 48 }, (_, i) => {
  const value = `${String(Math.floor(i / 2)).padStart(2, "0")}:${i % 2 ? "30" : "00"}`;
  return { data: value, label: value };
});

type Status = "connected" | "busy" | "searching";

const StatusPill: FC<{ status: Status }> = ({ status }) => {
  const { t } = useI18n();
  const colour = status === "connected" ? theme.color.ok : status === "busy" ? theme.color.warn : theme.color.textMuted;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 9px", borderRadius: 999,
      background: "rgba(255,255,255,0.06)", fontSize: theme.font.caption, fontWeight: 650, color: theme.color.textPrimary }}>
      <span style={{ width: 7, height: 7, borderRadius: 4, background: colour, boxShadow: status === "connected" ? `0 0 8px ${colour}` : "none" }} />
      {t(`accessories.status.${status}`)}
    </span>
  );
};

const Hero: FC<{
  status: Status;
  sceneId: string | null;
  options: Record<string, unknown>;
  labelKey: string | undefined;
  power: boolean;
  onPanel: boolean;
  canShow: boolean;
  onShow: () => void;
}> = ({ status, sceneId, options, labelKey, power, onPanel, canShow, onShow }) => {
  const { t } = useI18n();
  const [decoded, setDecoded] = useState<DecodedFrames | null>(null);
  const [sending, setSending] = useState(false);
  const epoch = usePreviewEpoch();
  useEffect(() => {
    let live = true;
    if (!sceneId) {
      setDecoded(null);
      return undefined;
    }
    void loadPreview(sceneId, options).then((value) => { if (live) setDecoded(value); });
    return () => { live = false; };
  }, [sceneId, JSON.stringify(options), epoch]);
  const title = labelKey ? t(labelKey) : t("accessories.pick");
  const badge = !sceneId ? null : onPanel ? t("accessories.badge.onPanel") : t("accessories.badge.preview");
  const show = () => {
    if (onPanel || !canShow || sending) return;
    setSending(true);
    Promise.resolve(onShow()).finally(() => setSending(false));
  };
  return (
    <div style={{ ...theme.card, padding: theme.space.md, display: "flex", flexDirection: "column", alignItems: "center",
      gap: theme.space.sm, background: `radial-gradient(120% 80% at 50% 0%, rgba(${theme.color.accentRgb},0.14), ${theme.color.surfaceRaised} 60%)` }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
          <span style={{ fontSize: theme.font.body, fontWeight: 750, color: theme.color.textPrimary, letterSpacing: 0.2 }}>JSAUX PIXEL</span>
          <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("accessories.device.subtitle")}</span>
        </div>
        <StatusPill status={status} />
      </div>
      <div style={{ position: "relative", marginTop: theme.space.xs }}>
        <PixelPreview decoded={decoded} pitch={HERO_PITCH} animate label={title}
          style={{ opacity: power || !onPanel ? 1 : 0.45, transition: "opacity 240ms ease" }} />
        {badge && (
          <span style={{ position: "absolute", top: 8, left: 8, padding: "2px 8px", borderRadius: 999, fontSize: 10, fontWeight: 750,
            letterSpacing: 0.4, textTransform: "uppercase", background: onPanel ? "rgba(126,224,160,0.92)" : `rgba(${theme.color.accentRgb},0.92)`,
            color: "#08110c" }}>
            {badge}
          </span>
        )}
      </div>
      <span style={{ fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
        {onPanel && !power ? t("accessories.power.off") : title}
      </span>
      {sceneId && canShow && (
        <DialogButton onClick={show} onOKButton={show}
          style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, fontWeight: 750,
            background: onPanel ? "rgba(255,255,255,0.06)" : theme.color.accent, color: onPanel ? theme.color.textMuted : theme.color.onAccent }}>
          {onPanel ? <LuCheck /> : <LuSend />}
          {onPanel ? t("accessories.show.done") : sending ? t("accessories.show.sending") : t("accessories.show")}
        </DialogButton>
      )}
    </div>
  );
};

const EmptyState: FC<{ busyBy: string | null; onTakeOver: () => void }> = ({ busyBy, onTakeOver }) => {
  const { t } = useI18n();
  const busy = !!busyBy;
  const official = !!busyBy && busyBy.startsWith("jsaux");
  const [failed, setFailed] = useState(false);
  return (
    <div style={{ ...theme.card, padding: theme.space.lg, display: "flex", flexDirection: "column", alignItems: "center", gap: theme.space.sm, textAlign: "center" }}>
      <LuPlug size={28} color={busy ? theme.color.warn : theme.color.accent} />
      <span style={{ fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
        {t(!busy ? "accessories.empty.title" : official ? "accessories.busy.title" : "accessories.busy.other.title")}
      </span>
      <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.45 }}>
        {!busy ? t("accessories.empty.body") : official ? t("accessories.busy.body") : t("accessories.busy.other.body", { name: busyBy ?? "" })}
      </span>
      {official && (
        <DialogButton style={{ marginTop: theme.space.xs }}
          onClick={() => void pauseJsauxApp().then((r) => { setFailed(!r?.ok); if (r?.ok) onTakeOver(); }).catch(() => setFailed(true))}>
          {t("accessories.busy.takeOver")}
        </DialogButton>
      )}
      {failed && <span style={{ fontSize: theme.font.caption, color: theme.color.warn }}>{t("accessories.busy.failed")}</span>}
    </div>
  );
};

interface Draft {
  id: string;
  options: Record<string, unknown>;
}

const sameOptions = (a: Record<string, unknown>, b: Record<string, unknown>) => JSON.stringify(a) === JSON.stringify(b);

export const AccesoriosSection: FC = () => {
  const { t } = useI18n();
  const { state, chooseScene, setBrightness, setPower, setNight, setGameScene, setAlerts, setOnSuspend, refresh } = useAccessories();
  const { draft } = useSceneDraft();
  const setDraft = setSceneDraft;
  if (!state) return <PanelSectionRow><Loading /></PanelSectionRow>;
  const status: Status = state.present ? "connected" : state.busy_by ? "busy" : "searching";
  const current: Draft | null = draft ?? (state.scene ? { id: state.scene, options: state.options } : null);
  const meta = state.catalog.find((scene) => scene.id === current?.id);
  const onPanel = !!current && current.id === state.scene && sameOptions(current.options, state.options);
  const gameScenes = state.catalog.filter((scene) => scene.category === "game" || scene.id === "pet");
  const gameOptions = [{ data: "", label: t("accessories.gameScene.none") },
    ...gameScenes.flatMap((scene) => scene.id === "game_cover"
      ? [{ data: "game_cover|full", label: `${t(scene.labelKey)} · ${t("accessories.layout.full")}` },
        { data: "game_cover|side", label: `${t(scene.labelKey)} · ${t("accessories.layout.side")}` }]
      : [{ data: scene.id, label: t(scene.labelKey) }])];
  const gameSelected = state.game_scene === "game_cover"
    ? `game_cover|${state.game_options?.layout === "side" ? "side" : "full"}` : state.game_scene ?? "";
  const pickGameScene = (value: string) => {
    if (!value) return void setGameScene(null);
    const [id, layout] = value.split("|");
    void setGameScene(id, layout ? { layout } : {});
  };
  const preview = (id: string, options: Record<string, unknown> = {}) => setDraft({ id, options });
  const show = async () => {
    if (!current) return;
    if (await chooseScene(current.id, current.options)) setDraft(null);
  };
  const send = async (id: string, options: Record<string, unknown>) => {
    if (await chooseScene(id, options)) setDraft(null);
  };
  return (
    <>
      <PanelSectionRow>
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.section, marginTop: theme.space.sm }}>
          <Hero status={status} sceneId={current?.id ?? null} options={current?.options ?? {}} labelKey={meta?.labelKey}
            power={state.power && !state.night_active} onPanel={onPanel} canShow={state.present} onShow={show} />
          {!state.present && <EmptyState busyBy={state.busy_by} onTakeOver={() => void refresh()} />}
        </div>
      </PanelSectionRow>
      <PanelSectionRow>
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, marginTop: theme.space.sm }}>
          <span style={{ fontSize: theme.font.caption, fontWeight: 700, color: theme.color.textMuted, textTransform: "uppercase", letterSpacing: 0.8 }}>
            {t("accessories.gallery")}
          </span>
          <SceneGallery catalog={state.catalog} selectedScene={current?.id ?? ""} panelScene={state.scene ?? ""}
            selectedDrawing={current?.id === "custom" && typeof current.options.drawing === "string" ? current.options.drawing : null}
            panelDrawing={state.scene === "custom" && typeof state.options.drawing === "string" ? state.options.drawing : null}
            layout={current?.id === "composed" ? ((current.options.layout as { blocks?: Block[] } | undefined)?.blocks ?? []) : []}
            onPick={(id, options) => preview(id, options ?? {})} onSend={(id, options) => void send(id, options)}>
            {current && meta && meta.options.length > 0 && (
              <SceneOptions options={meta.options} values={current.options} speedrunPaused={state.speedrun_paused}
                onRunChanged={() => void refresh()} onChange={(values) => preview(current.id, values)} />
            )}
          </SceneGallery>
        </div>
      </PanelSectionRow>
      {state.present && (
        <>
          <PanelSectionRow>
            <ValueBar icon={<LuSun size={16} color={theme.color.brightness} />} label={t("accessories.brightness")}
              percent={state.brightness} onChange={(value) => void setBrightness(value)} />
          </PanelSectionRow>
          <PanelSectionRow>
            <ToggleField label={t("accessories.power")} checked={state.power} onChange={(on) => void setPower(on)} />
          </PanelSectionRow>
          <PanelSectionRow>
            <DropdownItem label={t("accessories.gameScene")} description={t("accessories.gameScene.desc")} rgOptions={gameOptions}
              selectedOption={gameSelected} onChange={(option) => pickGameScene(String(option.data ?? ""))} />
          </PanelSectionRow>
          <PanelSectionRow>
            <ToggleField label={t("accessories.alerts.achievements")} description={t("accessories.alerts.achievements.desc")}
              checked={state.alerts.achievements} onChange={(on) => void setAlerts(on)} />
          </PanelSectionRow>
          <PanelSectionRow>
            <DropdownItem label={t("accessories.suspend")} description={t("accessories.suspend.desc")}
              rgOptions={[{ data: "off", label: t("accessories.suspend.off") }, { data: "pet", label: t("accessories.suspend.pet") }]}
              selectedOption={state.on_suspend ?? "off"} onChange={(option) => void setOnSuspend(option.data === "pet" ? "pet" : "off")} />
          </PanelSectionRow>
          <PanelSectionRow>
            <ToggleField label={t("accessories.night")} description={state.night.enabled ? t("accessories.night.range", { from: state.night.from, to: state.night.to }) : undefined}
              checked={state.night.enabled} onChange={(on) => void setNight({ ...state.night, enabled: on })} />
          </PanelSectionRow>
          {state.night.enabled && (
            <>
              <PanelSectionRow>
                <DropdownItem label={t("accessories.night.from")} rgOptions={HALF_HOURS} selectedOption={state.night.from}
                  onChange={(option) => void setNight({ ...state.night, from: String(option.data) })} />
              </PanelSectionRow>
              <PanelSectionRow>
                <DropdownItem label={t("accessories.night.to")} rgOptions={HALF_HOURS} selectedOption={state.night.to}
                  onChange={(option) => void setNight({ ...state.night, to: String(option.data) })} />
              </PanelSectionRow>
            </>
          )}
        </>
      )}
    </>
  );
};
