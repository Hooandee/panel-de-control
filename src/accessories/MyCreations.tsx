import { openFilePicker } from "@decky/api";
import { Focusable } from "@decky/ui";
import { FC, useCallback, useEffect, useState } from "react";
import { LuBlocks, LuImagePlus, LuPencil } from "react-icons/lu";

import { deleteAccessoryDrawing, DrawingSummary, listAccessoryDrawings, loadAccessoryDrawing, readAccessoryImage, saveAccessoryDrawing } from "../api";
import { confirmDestructive } from "./SafeConfirm";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { decodeFrame } from "./drawing";
import type { Block } from "./ComposerEditor";
import { openEditor } from "./editorRoute";
import { importImage } from "./imageImport";
import { decodeFrames, DecodedFrames } from "./pixelFrames";
import { PixelPreview } from "./PixelPreview";
import { forgetPreviews } from "./useAccessories";
import { OnPanelDot, tileStyle } from "./tiles";

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

const Tile: FC<{
  selected: boolean;
  onPanel?: boolean;
  label: string;
  onChoose: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
  children: React.ReactNode;
}> = ({ selected, onPanel, label, onChoose, onEdit, onDelete, children }) => {
  const { t } = useI18n();
  const [focused, setFocused] = useState(false);
  return (
    <Focusable onActivate={onChoose} onClick={onChoose}
      onSecondaryButton={onEdit} onSecondaryActionDescription={onEdit ? t("accessories.draw.edit") : undefined}
      onOptionsButton={onDelete} onOptionsActionDescription={onDelete ? t("accessories.draw.delete") : undefined}
      onGamepadFocus={() => setFocused(true)} onGamepadBlur={() => setFocused(false)} style={tileStyle(focused, selected)}>
      {children}
      <div style={{ display: "flex", alignItems: "center", gap: 5, maxWidth: "100%", justifyContent: "center", minWidth: 0 }}>
        {onPanel && <OnPanelDot />}
        <span style={{ fontSize: theme.font.caption, fontWeight: 650, color: selected || focused ? theme.color.textPrimary : theme.color.textMuted,
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{label}</span>
      </div>
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
  selectedDrawing: string | null;
  panelDrawing: string | null;
  composing: boolean;
  composedOnPanel: boolean;
  layout: Block[];
  onPick: (id: string) => void;
  onSend: (sceneId: string, options: Record<string, unknown>) => void;
}> = ({ selectedDrawing, panelDrawing, composing, composedOnPanel, layout, onPick, onSend }) => {
  const { t } = useI18n();
  const [drawings, setDrawings] = useState<DrawingSummary[]>([]);
  const refresh = useCallback(() => {
    void listAccessoryDrawings().then((result) => setDrawings(result?.drawings ?? [])).catch(() => setDrawings([]));
  }, []);
  useEffect(refresh, [refresh]);

  const sent = (id: string) => {
    forgetPreviews();
    refresh();
    onSend("custom", { drawing: id });
  };
  const edit = async (summary: DrawingSummary) => {
    const full = await loadAccessoryDrawing(summary.id);
    if (!full?.ok || !full.frames) return;
    openEditor({ kind: "draw", draft: { id: full.id, name: full.name ?? "", frames: full.frames.map(decodeFrame), fps: full.fps ?? 8 }, onSent: sent });
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
      if (saved?.ok && saved.id) {
        forgetPreviews();
        refresh();
        onPick(saved.id);
      }
    } catch {
      /* picker cancelled */
    }
  };

  return (
    <Focusable flow-children="grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: theme.space.sm }}>
      <Tile selected={false} label={t("accessories.draw.new")} onChoose={() => openEditor({ kind: "draw", draft: { name: "", frames: [], fps: 8 }, onSent: sent })}>
        <ActionArt icon={<LuPencil size={30} />} />
      </Tile>
      <Tile selected={false} label={t("accessories.draw.import")} onChoose={() => void importFile()}>
        <ActionArt icon={<LuImagePlus size={30} />} />
      </Tile>
      <Tile selected={composing} onPanel={composedOnPanel} label={t("accessories.compose.title")}
        onChoose={() => openEditor({ kind: "compose", blocks: layout, onShow: (blocks) => onSend("composed", { layout: { blocks } }) })}>
        <ActionArt icon={<LuBlocks size={30} />} />
      </Tile>
      {drawings.map((drawing) => (
        <Tile key={drawing.id} selected={drawing.id === selectedDrawing} onPanel={drawing.id === panelDrawing}
          label={drawing.name || t("accessories.draw.untitled")}
          onChoose={() => onPick(drawing.id)} onEdit={() => void edit(drawing)} onDelete={() => remove(drawing)}>
          <PixelPreview decoded={thumbFrames(drawing.thumb)} pitch={TILE_PITCH} animate={false} />
        </Tile>
      ))}
    </Focusable>
  );
};
