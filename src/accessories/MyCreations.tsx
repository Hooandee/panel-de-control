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
import { forgetPreviews, setSceneDraft, usePreviewEpoch } from "./useAccessories";
import { getQamDocument } from "../qamDocument";
import { createThemeNavigationAccess } from "../themes/runtime/navigationAccess";
import { useLive } from "./EditorShell";
import { OnPanelDot, TileRows, tileStyle } from "./tiles";

const TILE_PITCH = 1.75;

// The section re-renders on every state poll: decoding the same thumbnail each time made every
// tile repaint, so decoded thumbnails are kept by their content.
const thumbCache = new Map<string, DecodedFrames>();
const THUMB_CACHE = 64;
function cachedThumb(thumb: string): DecodedFrames {
  let frames = thumbCache.get(thumb);
  if (!frames) {
    frames = thumbFrames(thumb);
    if (thumbCache.size >= THUMB_CACHE) thumbCache.delete(thumbCache.keys().next().value as string);
    thumbCache.set(thumb, frames);
  }
  return frames;
}

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
  /** Focus comes back to a tile by this label after a dialog, so it must not change with a rename. */
  focusKey?: string;
  onChoose: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
  children: React.ReactNode;
}> = ({ selected, onPanel, label, focusKey, onChoose, onEdit, onDelete, children }) => {
  const { t } = useI18n();
  const [focused, setFocused] = useState(false);
  const choose = useLive(onChoose);
  const edit = useLive(() => onEdit?.());
  const remove = useLive(() => onDelete?.());
  return (
    <Focusable onActivate={choose} onClick={choose} aria-label={focusKey}
      onSecondaryButton={onEdit ? edit : undefined} onSecondaryActionDescription={onEdit ? t("accessories.draw.edit") : undefined}
      onOptionsButton={onDelete ? remove : undefined} onOptionsActionDescription={onDelete ? t("accessories.draw.delete") : undefined}
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

// The file picker closes the menu, so an import ends in whichever panel is mounted by then.
let importFailedNow = false;
const importWatchers = new Set<(failed: boolean) => void>();
function setImportFailed(failed: boolean): void {
  importFailedNow = failed;
  importWatchers.forEach((watch) => watch(failed));
}
function useImportFailed(): boolean {
  const [failed, setFailed] = useState(importFailedNow);
  useEffect(() => {
    importWatchers.add(setFailed);
    return () => {
      importWatchers.delete(setFailed);
      // Seen once: not shown again on a later visit.
      if (importWatchers.size === 0) importFailedNow = false;
    };
  }, []);
  return failed;
}

const drawingKey = (id: string) => `drawing:${id}`;
const focusNav = createThemeNavigationAccess({ allowInactiveContext: true });

// The deleted tile was the dialog's opener, so Steam would drop focus on the QAM tabs: put it on
// its neighbour once the reopened menu has drawn it.
function focusSoon(label: string): void {
  const deadline = Date.now() + 2000;
  const attempt = () => {
    const doc = getQamDocument();
    const target = Array.from(doc?.querySelectorAll<HTMLElement>(".pdc-root .Focusable") ?? [])
      .find((element) => (element.getAttribute("aria-label") || element.textContent || "").trim() === label);
    if (target) {
      focusNav.focus(target);
      if (target.classList.contains("gpfocus")) return;
    }
    if (Date.now() < deadline) window.setTimeout(attempt, 50);
  };
  window.setTimeout(attempt, 0);
}

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
  // Imports and deletes finish after Steam remounted this panel; the epoch they bump re-lists.
  const epoch = usePreviewEpoch();
  useEffect(refresh, [refresh, epoch]);

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
      onConfirm: () => {
        const at = drawings.findIndex((drawing) => drawing.id === summary.id);
        const neighbour = drawings[at + 1] ?? drawings[at - 1];
        focusSoon(neighbour ? drawingKey(neighbour.id) : t("accessories.draw.new"));
        void deleteAccessoryDrawing(summary.id).catch(() => undefined).then(() => {
        forgetPreviews();
        refresh();
        if (summary.id === selectedDrawing) setSceneDraft(null);
        });
      },
    });
  };
  const importFailed = useImportFailed();
  const importFile = async () => {
    setImportFailed(false);
    let picked: { path: string; realpath?: string };
    try {
      picked = await openFilePicker(0, "/home/deck", true, true, undefined, ["png", "gif", "jpg", "jpeg", "webp"]);
    } catch {
      return; // picker cancelled
    }
    try {
      const file = await readAccessoryImage(picked.realpath ?? picked.path);
      if (!file?.ok || !file.data || !file.mime) throw new Error("unreadable");
      const decoded = await importImage(file.mime, file.data);
      const name = (picked.path.split("/").pop() ?? "").replace(/\.[^.]+$/, "").slice(0, 40);
      const saved = await saveAccessoryDrawing({ name, frames: decoded.frames, fps: decoded.fps });
      if (!saved?.ok || !saved.id) throw new Error("not saved");
      setImportFailed(false);
      forgetPreviews();
      refresh();
      onPick(saved.id);
    } catch {
      setImportFailed(true);
    }
  };

  return (
    <>
    <TileRows>
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
          label={drawing.name || t("accessories.draw.untitled")} focusKey={drawingKey(drawing.id)}
          onChoose={() => onPick(drawing.id)} onEdit={() => void edit(drawing)} onDelete={() => remove(drawing)}>
          <PixelPreview decoded={cachedThumb(drawing.thumb)} pitch={TILE_PITCH} animate={false} />
        </Tile>
      ))}
    </TileRows>
    {importFailed && <span style={{ fontSize: theme.font.caption, color: theme.color.warn }}>{t("accessories.draw.importFailed")}</span>}
    </>
  );
};
