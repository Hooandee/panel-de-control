import { DialogButton, DropdownItem, PanelSectionRow, ToggleField } from "@decky/ui";
import { FC, useEffect, useState } from "react";
import { LuPlug, LuSun } from "react-icons/lu";

import { PixelPreview } from "../accessories/PixelPreview";
import { DecodedFrames } from "../accessories/pixelFrames";
import { SceneGallery } from "../accessories/SceneGallery";
import { SceneOptions } from "../accessories/SceneOptions";
import type { Block } from "../accessories/ComposerModal";
import { loadPreview, useAccessories } from "../accessories/useAccessories";
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

const Hero: FC<{ status: Status; sceneId: string | null; options: Record<string, unknown>; labelKey: string | undefined; power: boolean }> = ({ status, sceneId, options, labelKey, power }) => {
  const { t } = useI18n();
  const [decoded, setDecoded] = useState<DecodedFrames | null>(null);
  useEffect(() => {
    let live = true;
    if (!sceneId) {
      setDecoded(null);
      return undefined;
    }
    void loadPreview(sceneId, options).then((value) => { if (live) setDecoded(value); });
    return () => { live = false; };
  }, [sceneId, JSON.stringify(options)]);
  const caption = !power ? t("accessories.power.off") : labelKey ? t(labelKey) : t("accessories.pick");
  return (
    <div style={{ ...theme.card, padding: theme.space.md, display: "flex", flexDirection: "column", alignItems: "center",
      gap: theme.space.md, background: `radial-gradient(120% 80% at 50% 0%, rgba(${theme.color.accentRgb},0.14), ${theme.color.surfaceRaised} 60%)` }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span style={{ fontSize: theme.font.body, fontWeight: 750, color: theme.color.textPrimary, letterSpacing: 0.2 }}>JSAUX PIXEL</span>
          <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("accessories.device.subtitle")}</span>
        </div>
        <StatusPill status={status} />
      </div>
      <PixelPreview decoded={power ? decoded : null} pitch={HERO_PITCH} animate label={labelKey ? t(labelKey) : undefined}
        style={{ opacity: status === "connected" && power ? 1 : 0.55, transition: "opacity 240ms ease" }} />
      <span style={{ fontSize: theme.font.body, fontWeight: 650, color: theme.color.textPrimary }}>
        {caption}
      </span>
    </div>
  );
};

const EmptyState: FC<{ busy: boolean; onTakeOver: () => void }> = ({ busy, onTakeOver }) => {
  const { t } = useI18n();
  const [failed, setFailed] = useState(false);
  return (
    <div style={{ ...theme.card, padding: theme.space.lg, display: "flex", flexDirection: "column", alignItems: "center", gap: theme.space.sm, textAlign: "center" }}>
      <LuPlug size={28} color={busy ? theme.color.warn : theme.color.accent} />
      <span style={{ fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
        {t(busy ? "accessories.busy.title" : "accessories.empty.title")}
      </span>
      <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.45 }}>
        {t(busy ? "accessories.busy.body" : "accessories.empty.body")}
      </span>
      {busy && (
        <DialogButton style={{ marginTop: theme.space.xs }}
          onClick={() => void pauseJsauxApp().then((r) => { setFailed(!r?.ok); if (r?.ok) onTakeOver(); }).catch(() => setFailed(true))}>
          {t("accessories.busy.takeOver")}
        </DialogButton>
      )}
      {failed && <span style={{ fontSize: theme.font.caption, color: theme.color.warn }}>{t("accessories.busy.failed")}</span>}
    </div>
  );
};

export const AccesoriosSection: FC = () => {
  const { t } = useI18n();
  const { state, chooseScene, setBrightness, setPower, setNight, setGameScene, refresh } = useAccessories();
  if (!state) return <PanelSectionRow><Loading /></PanelSectionRow>;
  const status: Status = state.present ? "connected" : state.busy_by ? "busy" : "searching";
  const active = state.catalog.find((scene) => scene.id === state.scene);
  const showingId = state.showing ?? state.scene;
  const showing = state.catalog.find((scene) => scene.id === showingId);
  const gameScenes = state.catalog.filter((scene) => scene.category === "game" || scene.id === "pet");
  const gameOptions = [{ data: "", label: t("accessories.gameScene.none") },
    ...gameScenes.map((scene) => ({ data: scene.id, label: t(scene.labelKey) }))];
  return (
    <>
      <PanelSectionRow>
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.section, marginTop: theme.space.sm }}>
          <Hero status={status} sceneId={showingId} options={showingId === state.scene ? state.options : {}}
            labelKey={showing?.labelKey} power={state.power && !state.night_active} />
          {state.present && active && (
            <SceneOptions options={active.options} values={state.options}
              onChange={(values) => void chooseScene(active.id, values)} />
          )}
          {!state.present && <EmptyState busy={!!state.busy_by} onTakeOver={() => void refresh()} />}
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
        </>
      )}
      <PanelSectionRow>
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, marginTop: theme.space.sm }}>
          <span style={{ fontSize: theme.font.caption, fontWeight: 700, color: theme.color.textMuted, textTransform: "uppercase", letterSpacing: 0.8 }}>
            {t("accessories.gallery")}
          </span>
          <SceneGallery catalog={state.catalog} activeScene={state.scene ?? ""}
            activeDrawing={typeof state.options.drawing === "string" ? state.options.drawing : null}
            layout={state.scene === "composed" ? ((state.options.layout as { blocks?: Block[] } | undefined)?.blocks ?? []) : []}
            onChoose={(id, options) => void chooseScene(id, options ?? {})} />
        </div>
      </PanelSectionRow>
      {state.present && (
        <>
          <PanelSectionRow>
            <DropdownItem label={t("accessories.gameScene")} description={t("accessories.gameScene.desc")} rgOptions={gameOptions}
              selectedOption={state.game_scene ?? ""} onChange={(option) => void setGameScene(option.data ? String(option.data) : null)} />
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
