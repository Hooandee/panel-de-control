import { openFilePicker } from "@decky/api";
import { Focusable } from "@decky/ui";
import { FC, useCallback, useEffect, useState } from "react";
import { LuBlocks, LuImagePlus, LuPencil } from "react-icons/lu";

import { deleteAccessoryDrawing, DrawingSummary, listAccessoryDrawings, loadAccessoryDrawing, readAccessoryImage, saveAccessoryDrawing } from "../api";
import { confirmDestructive } from "./SafeConfirm";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { decodeFrame } from "./drawing";
import { Block, openComposerModal } from "./ComposerModal";
import { openDrawModal } from "./DrawModal";
import { importImage } from "./imageImport";
import { decodeFrames, DecodedFrames } from "./pixelFrames";
import { PixelPreview } from "./PixelPreview";
import { forgetPreviews } from "./useAccessories";

const TILE_PITCH = 1.75;

function thumbFrames(thumb: string): DecodedFrames {
  const rgb = decodeFrame(thumb);
  const palette: number[][] = [];
  const lookup = new Map<string, number>();
  const indices = new Uint8Array(64 * 54);
  for (let i = 0; i < indices.length; i += 1) {
    const key = `${rgb[i * 3]},${rgb[i * 3 + 1]},${rgb[i * 3 + 2]}`;
    let at = lookup.get(key);
    if (at === undefined && palette.length < 255) {
      at = palette.length;
      lookup.set(key, at);
      palette.push([rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2]]);
    }
    indices[i] = at ?? 0;
  }
  let raw = "";
  for (let i = 0; i < indices.length; i += 1) raw += String.fromCharCode(indices[i]);
  return decodeFrames({ palette, frames: [btoa(raw)], delays: [100], firmwareAnimation: null });
}

const Tile: FC<{ active: boolean; label: string; onChoose: () => void; onEdit?: () => void; onDelete?: () => void; children: React.ReactNode }> =
  ({ active, label, onChoose, onEdit, onDelete, children }) => {
    const { t } = useI18n();
    const [focused, setFocused] = useState(false);
    return (
      <Focusable onActivate={onChoose} onClick={onChoose}
        onSecondaryButton={onEdit} onSecondaryActionDescription={onEdit ? t("accessories.draw.edit") : undefined}
        onOptionsButton={onDelete} onOptionsActionDescription={onDelete ? t("accessories.draw.delete") : undefined}
        onGamepadFocus={() => setFocused(true)} onGamepadBlur={() => setFocused(false)}
        style={{ borderRadius: theme.radius.md, padding: theme.space.sm, display: "flex", flexDirection: "column", alignItems: "center",
          gap: 6, minWidth: 0, background: active ? `rgba(${theme.color.accentRgb},0.10)` : theme.color.surfaceRaised,
          boxShadow: focused ? `inset 0 0 0 1px ${theme.color.accent}, 0 0 0 2px ${theme.color.accent}` : active ? `inset 0 0 0 1px ${theme.color.accent}88` : `inset 0 0 0 1px ${theme.color.outline}`,
          transform: focused ? "scale(1.03)" : "scale(1)", transition: "box-shadow 120ms ease, transform 120ms ease" }}>
        {children}
        <span style={{ fontSize: theme.font.caption, fontWeight: 650, color: active ? theme.color.textPrimary : theme.color.textMuted,
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "100%" }}>{label}</span>
      </Focusable>
    );
  };

const ActionArt: FC<{ icon: React.ReactNode }> = ({ icon }) => (
  <div style={{ width: Math.round(64 * TILE_PITCH), height: Math.round(54 * TILE_PITCH), borderRadius: 6, display: "flex", alignItems: "center",
    justifyContent: "center", background: `radial-gradient(circle at 50% 40%, rgba(${theme.color.accentRgb},0.25), #0a090b 70%)`, color: theme.color.accent }}>
    {icon}
  </div>
);

export const MyCreations: FC<{
  activeDrawing: string | null;
  composing: boolean;
  layout: Block[];
  onShow: (id: string) => void;
  onCompose: (blocks: Block[]) => void;
}> = ({ activeDrawing, composing, layout, onShow, onCompose }) => {
  const { t } = useI18n();
  const [drawings, setDrawings] = useState<DrawingSummary[]>([]);
  const refresh = useCallback(() => {
    void listAccessoryDrawings().then((result) => setDrawings(result?.drawings ?? [])).catch(() => setDrawings([]));
  }, []);
  useEffect(refresh, [refresh]);

  const sent = (id: string) => {
    forgetPreviews();
    refresh();
    onShow(id);
  };
  const edit = async (summary: DrawingSummary) => {
    const full = await loadAccessoryDrawing(summary.id);
    if (!full?.ok || !full.frames) return;
    openDrawModal({ id: full.id, name: full.name ?? "", frames: full.frames.map(decodeFrame), fps: full.fps ?? 8 }, sent);
  };
  const remove = (summary: DrawingSummary) => {
    confirmDestructive({
      title: t("accessories.draw.deleteTitle"), desc: summary.name || t("accessories.draw.untitled"),
      confirmLabel: t("accessories.draw.delete"), cancelLabel: t("accessories.draw.cancel"),
      onConfirm: () => void deleteAccessoryDrawing(summary.id).then(refresh),
    });
  };
  const importFile = async () => {
    try {
      const picked = await openFilePicker(0, "/home/deck/Pictures", true, true, undefined, ["png", "gif", "jpg", "jpeg", "webp"]);
      const file = await readAccessoryImage(picked.realpath ?? picked.path);
      if (!file?.ok || !file.data || !file.mime) return;
      const decoded = await importImage(file.mime, file.data);
      const name = (picked.path.split("/").pop() ?? "").replace(/\.[^.]+$/, "").slice(0, 40);
      const saved = await saveAccessoryDrawing({ name, frames: decoded.frames, fps: decoded.fps });
      if (saved?.ok && saved.id) sent(saved.id);
    } catch {
      /* picker cancelled */
    }
  };

  return (
    <Focusable flow-children="grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: theme.space.sm }}>
      <Tile active={false} label={t("accessories.draw.new")} onChoose={() => openDrawModal({ name: "", frames: [], fps: 8 }, sent)}>
        <ActionArt icon={<LuPencil size={30} />} />
      </Tile>
      <Tile active={false} label={t("accessories.draw.import")} onChoose={() => void importFile()}>
        <ActionArt icon={<LuImagePlus size={30} />} />
      </Tile>
      <Tile active={composing} label={t("accessories.compose.title")} onChoose={() => openComposerModal(layout, onCompose)}>
        <ActionArt icon={<LuBlocks size={30} />} />
      </Tile>
      {drawings.map((drawing) => (
        <Tile key={drawing.id} active={drawing.id === activeDrawing} label={drawing.name || t("accessories.draw.untitled")}
          onChoose={() => onShow(drawing.id)} onEdit={() => void edit(drawing)} onDelete={() => remove(drawing)}>
          <PixelPreview decoded={thumbFrames(drawing.thumb)} pitch={TILE_PITCH} animate={false} />
        </Tile>
      ))}
    </Focusable>
  );
};
