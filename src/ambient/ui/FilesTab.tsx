import { openFilePicker } from "@decky/api";
import { Focusable } from "@decky/ui";
import { useEffect, useRef, useState, type FC, type ReactNode } from "react";
import { LuCamera, LuCheck, LuFolder, LuFolderPlus, LuImage, LuImages, LuListPlus, LuMusic, LuPlay, LuSparkles, LuVideo } from "react-icons/lu";

import { useI18n } from "../../i18n";
import { theme } from "../../theme";
import type { CollectionEntry } from "../steam/rpc";
import type { AmbientRuntime, AmbientSnapshot } from "../steam/runtime";
import { thumbnail } from "../steam/thumbnails";
import { LibraryPlayback } from "./LibraryPlayback";
import { Button, Caption, Row, menuHandlers, type ItemMenu } from "./primitives";
import { Empty, ROW_HEIGHT, useMeasuredHeight } from "./stationsParts";
import { VirtualList } from "./VirtualList";
import { useLibraryNavigation } from "./libraryNavigation";
import { acceptsMedia, photoSelection, preferredSource, type LibraryItem, type LibraryPhoto, type LibraryPurpose } from "./libraryModel";

export const SOURCE_LABELS: Record<string, string> = {
  "known.images": "ambient.tile.known", "known.music": "ambient.music.mine", screenshots: "ambient.tile.screenshots",
  "suggested.library": "ambient.tile.library", "suggested.nasa": "ambient.tile.nasa", "suggested.bing": "ambient.tile.bing",
};

export const MediaPreview: FC<{ item: LibraryItem; runtime: AmbientRuntime }> = ({ item, runtime }) => {
  const { t } = useI18n();
  const [url, setUrl] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  useEffect(() => {
    let active = true;
    setUrl(null);
    setPending(item.kind === "image");
    if (item.kind === "image") void runtime.previewMedia(item.ref)
      .then((url) => { if (active) setUrl(url); })
      .catch(() => undefined)
      .finally(() => { if (active) setPending(false); });
    return () => { active = false; };
  }, [runtime, item.ref]);
  return <><div style={{ width: "100%", aspectRatio: "16 / 9", borderRadius: 8, overflow: "hidden", background: "#101216", display: "grid", placeItems: "center" }}>
    {item.kind === "audio" ? <LuMusic size={32} /> : item.kind === "video" ? <LuVideo size={32} /> : url
      ? <img src={url} alt={item.name} style={{ width: "100%", height: "100%", objectFit: "contain" }} />
      : <div style={{ padding: 8, fontSize: theme.font.caption }}>{t(pending ? "ambient.lib.loading" : "ambient.lib.loadFailed")}</div>}
  </div>{item.credit && <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, paddingTop: 4 }}>{item.credit}</div>}</>;
};

export const MediaSelection: FC<{ item: LibraryItem; purpose: LibraryPurpose; runtime: AmbientRuntime }> = ({ item, purpose, runtime }) => {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const apply = async () => {
    if (busy) return;
    setBusy(true);
    setStatus("");
    try {
      if (purpose === "background" && item.kind !== "audio") {
        await runtime.useBackground({ ...item, kind: item.kind });
        setStatus(t("ambient.lib.backgroundApplied"));
      } else await runtime.playMedia(item.ref);
    } catch { setStatus(t("ambient.lib.actionFailed")); }
    finally { setBusy(false); }
  };
  return <div style={{ paddingTop: 6 }}>
    <Button primary disabled={busy} label={t(busy ? "ambient.lib.working" : purpose === "background" ? "ambient.lib.useBackground" : "ambient.player.play")} onActivate={() => void apply()} />
    {status && <div role="status" style={{ fontSize: theme.font.caption, marginTop: 4 }}>{status}</div>}
  </div>;
};

export const FilesTab: FC<{ runtime: AmbientRuntime; snapshot: AmbientSnapshot; purpose: LibraryPurpose; header: ReactNode; onClose?: () => void }> = ({ runtime, snapshot, purpose, header, onClose }) => {
  const { t } = useI18n();
  const saving = useRef(false);
  const navigation = useLibraryNavigation(() => { if (!saving.current) onClose?.(); });
  useEffect(() => runtime.beginLibrarySession(), [runtime]);
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [items, setItems] = useState<LibraryItem[] | null>(null);
  const [selected, setSelected] = useState<LibraryItem | null>(null);
  const [viewed, setViewed] = useState<LibraryItem | null>(null);
  const quickPlaying = useRef(false);
  const [multiple, setMultiple] = useState(false);
  const [photos, setPhotos] = useState(new Map<string, LibraryPhoto>());
  const [picks, setPicks] = useState(new Map<string, LibraryItem>());
  const [notice, setNotice] = useState("");
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState("");
  const [adding, setAdding] = useState(false);
  const [listRef, listHeight] = useMeasuredHeight();
  const state = snapshot.state!;
  const available = state.collections.some((s) => s.id === "known.music") || !snapshot.scan?.music.length
    ? state.collections : [...state.collections, { id: "known.music", kind: "known" as const }];
  const sources = available.filter((s) => {
    if (s.kind === "favorite" || (purpose === "playback" && s.kind === "suggested")) return false;
    if (!snapshot.scan || (s.kind !== "known" && s.kind !== "folder" && s.kind !== "screenshots")) return true;
    const media = snapshot.scan.library?.[s.id] ?? snapshot.scan.collections[s.id] ?? (s.id === "known.music" ? snapshot.scan.music : []) ?? [];
    return s.kind === "folder" && media.length === 0 ? true : media.some((m) => acceptsMedia(m.kind, purpose));
  });
  const wantedRef = purpose === "background" ? state.settings.background.pinned || snapshot.current?.ref : snapshot.player?.track?.id;
  const wantedCollection = purpose === "background" && snapshot.current?.ref === wantedRef ? snapshot.current?.collection : undefined;
  const preferred = preferredSource(sources, snapshot.scan, purpose, wantedRef, wantedCollection);
  const current = sources.find((s) => s.id === sourceId) ?? sources.find((s) => s.id === preferred);
  const playback = purpose === "playback";
  const visible = multiple ? items?.filter((item) => (item.kind === "image") !== playback) : items;
  const chosen = playback ? picks : photos;
  useEffect(() => {
    let active = true;
    setSelected(null);
    setViewed(null);
    setError("");
    if (!current) { setItems([]); return; }
    setItems(null);
    if (!snapshot.scan && current.kind !== "suggested") return;
    const media = snapshot.scan?.library?.[current.id] ?? snapshot.scan?.collections[current.id] ?? (current.id === "known.music" ? snapshot.scan?.music : []) ?? [];
    const pending: Promise<LibraryItem[]> = current.kind === "suggested"
      ? runtime.libraryItems(current.id)
      : Promise.resolve(media.map((m) => ({ ref: m.id, name: m.name, kind: m.kind, collection: current.id })));
    void pending.then((items) => { if (active) setItems(items.filter((m) => acceptsMedia(m.kind, purpose))); }).catch(() => {
      if (active) { setItems([]); setError(t("ambient.lib.loadFailed")); }
    });
    return () => { active = false; };
  }, [runtime, current?.id, snapshot.scan, purpose]);
  const startMultiple = () => {
    const inventory: LibraryItem[] = [...snapshot.items ?? [], ...Object.entries(snapshot.scan?.library ?? snapshot.scan?.collections ?? {}).flatMap(([collection, media]) => media.map((item) => ({ ref: item.id, kind: item.kind, name: item.name, collection })))];
    setPhotos(photoSelection(state.settings.background.selectedRefs ?? [], inventory));
    setSourceId(current?.id ?? null);
    setSelected((item) => item?.kind === "image" ? item : null);
    setMultiple(true);
  };
  const cancelMultiple = () => {
    setMultiple(false);
    setPhotos(new Map());
    setPicks(new Map());
  };
  const queueItems = async (selection: LibraryItem[], where: "end" | "next") => {
    setError("");
    setNotice("");
    try {
      const added = await runtime.enqueueItems(selection, where);
      if (!added) setError(t("ambient.lib.actionFailed"));
      else setNotice(t("ambient.queue.added", { n: String(added) }));
    } catch { setError(t("ambient.lib.actionFailed")); }
  };
  const playFolder = async (where: "now" | "end") => {
    if (!current || applying) return;
    setError("");
    setNotice("");
    try {
      if (!await runtime.playCollection(current.id, where)) return setError(t("ambient.lib.actionFailed"));
      if (where === "end") setNotice(t("ambient.queue.added", { n: String(visible?.length ?? 0) }));
      else onClose?.();
    } catch { setError(t("ambient.lib.actionFailed")); }
  };
  const rowMenu = (item: LibraryItem): ItemMenu | undefined => playback && !multiple && item.kind !== "image" ? {
    title: item.name,
    hint: t("ambient.menu.options"),
    actions: [
      { label: t("ambient.queue.addEnd"), onSelect: () => void queueItems([item], "end") },
      { label: t("ambient.queue.playNext"), onSelect: () => void queueItems([item], "next") },
    ],
  } : undefined;
  const choose = (item: LibraryItem) => {
    if (applying) return;
    setSelected(item);
    setViewed(item);
    setSourceId(current?.id ?? null);
    if (multiple && playback && item.kind !== "image") setPicks((previous) => {
      const next = new Map(previous);
      if (next.has(item.ref)) next.delete(item.ref);
      else next.set(item.ref, item);
      return next;
    });
    else if (multiple && item.kind === "image") setPhotos((previous) => {
      const next = new Map(previous);
      if (next.has(item.ref)) next.delete(item.ref);
      else next.set(item.ref, { ...item, kind: "image" });
      return next;
    });
  };
  const quickAction = async (item: LibraryItem) => {
    if (applying || quickPlaying.current || item.kind === "image") return;
    setSelected(item);
    setViewed(item);
    setSourceId(current?.id ?? null);
    setError("");
    quickPlaying.current = true;
    try { await runtime.previewLibraryMedia(item); }
    catch { setError(t("ambient.lib.actionFailed")); }
    finally { quickPlaying.current = false; }
  };
  const save = async () => {
    const selection = multiple ? [...chosen.values()] : selected ? [selected] : [];
    if (saving.current || !selection.length || (multiple && !playback && selection.length < 2)) return;
    saving.current = true;
    setApplying(true);
    setError("");
    try {
      await runtime.saveLibrarySelection(selection, purpose);
      onClose?.();
    } catch { setError(t("ambient.lib.actionFailed")); }
    finally { saving.current = false; setApplying(false); }
  };
  const addFolder = async () => {
    if (adding) return;
    let picked;
    try { picked = await openFilePicker(1 as never, state.knownFolders[purpose === "background" ? "images" : "music"][0] ?? "/home", false, true); }
    catch { return; }
    if (!picked?.realpath) return;
    setAdding(true);
    setError("");
    try {
      if (!await runtime.addFolder(picked.realpath, "library")) setError(t("ambient.lib.actionFailed"));
      else {
        const added = runtime.getSnapshot().state?.collections.find((s) => s.path === picked.realpath);
        if (added) setSourceId(added.id);
      }
    } catch { setError(t("ambient.lib.actionFailed")); }
    finally { setAdding(false); }
  };
  const countOf = (id: string) => (snapshot.scan?.library?.[id] ?? snapshot.scan?.collections[id] ?? (id === "known.music" ? snapshot.scan?.music : []) ?? []).filter((m) => acceptsMedia(m.kind, purpose)).length;
  const selection = multiple ? [...chosen.values()] : selected ? [selected] : [];
  const actionLabel = applying ? t("ambient.lib.working")
    : !selection.length ? t(playback ? "ambient.player.play" : "ambient.lib.useBackground")
      : playback ? (selection.length > 1 ? t("ambient.lib.playSelected", { n: String(selection.length) }) : t("ambient.player.play"))
        : selection.length > 1 ? t("ambient.lib.rotatePhotos", { n: String(selection.length) }) : t("ambient.lib.useBackground");
  const canApply = !applying && (multiple ? chosen.size >= (playback ? 1 : 2) : !!selected);
  const title = current ? SOURCE_LABELS[current.id] ? t(SOURCE_LABELS[current.id]) : current.name ?? current.id : "";
  const docked = !!snapshot.player?.video;
  const gridRows = !playback && visible ? chunk(visible, docked ? GRID_COLUMNS - 1 : GRID_COLUMNS) : [];
  return <Focusable {...navigation}
    onCancelButton={(event) => {
      if (runtime.getSnapshot().videoFullscreen) {
        event.preventDefault(); event.stopPropagation(); runtime.setVideoFullscreen(false);
      } else navigation.onCancelButton(event);
    }}
    onGamepadDirection={(event) => {
      if (runtime.getSnapshot().videoFullscreen) { event.preventDefault(); event.stopPropagation(); }
      else navigation.onGamepadDirection(event);
    }} flow-children="column" style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, gap: theme.space.md }}>
    {header}
    <Focusable flow-children="row" style={{ display: "grid", gridTemplateColumns: docked ? "minmax(0, .72fr) minmax(0, 1.25fr) minmax(0, .95fr)" : "minmax(0, .72fr) minmax(0, 1.6fr)", gap: theme.space.md, flex: 1, minHeight: 0 }}>
      <Focusable data-library-column="0" flow-children="column" style={{ display: "flex", flexDirection: "column", gap: 2, overflowY: "auto", minHeight: 0 }}>
        <Caption>{t("ambient.lib.folders")}</Caption>
        <Row title={t(adding ? "ambient.lib.working" : "ambient.lib.addFolder")} swatch={<LuFolderPlus size={18} style={{ color: theme.color.accent }} />} onActivate={() => void addFolder()} />
        {sources.map((s) => {
          const name = playback && s.id === "known.images" ? t("ambient.coll.known") : SOURCE_LABELS[s.id] ? t(SOURCE_LABELS[s.id]) : s.name ?? s.id;
          const removable = s.kind === "folder" || s.kind === "suggested";
          const remove = () => void runtime.removeItem(s.kind === "suggested" ? "background" : "library", s.id).then((ok) => { if (!ok) setError(t("ambient.lib.actionFailed")); });
          return <Focusable key={s.id} {...menuHandlers(removable ? { title: name, hint: t("ambient.menu.options"), actions: [{ label: t("ambient.lib.remove"), destructive: true, onSelect: remove }] } : undefined)}>
            <Row title={name} subtitle={s.path ? shortPath(s.path) : undefined} swatch={sourceIcon(s)} selected={s.id === current?.id} onActivate={() => setSourceId(s.id)}
              trailing={s.kind !== "suggested" && countOf(s.id) > 0 ? <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, fontVariantNumeric: "tabular-nums" }}>{countOf(s.id)}</span> : undefined} />
          </Focusable>;
        })}
        {purpose === "background" && state.settings.collections?.removedSuggested.filter((id) => SOURCE_LABELS[id]).map((id) => <Row key={id} title={t(SOURCE_LABELS[id])} subtitle={t("ambient.lib.restore")} onActivate={() => void runtime.restoreSuggested("background", id)} />)}
      </Focusable>
      <Focusable data-library-column="1" flow-children="column" style={{ display: "flex", flexDirection: "column", minHeight: 0, minWidth: 0, gap: 6 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, minWidth: 0 }}>
          <span style={{ fontSize: 15, fontWeight: 700, color: theme.color.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{title}</span>
          {!!visible?.length && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{visible.length}</span>}
        </div>
        <Focusable flow-children="row" style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {playback && !multiple && !!visible?.length && <Button label={<><LuPlay size={14} /> {t("ambient.lib.playAll")}</>} onActivate={() => void playFolder("now")} />}
          {playback && !multiple && !!visible?.length && <Button label={<><LuListPlus size={14} /> {t("ambient.queue.addEnd")}</>} onActivate={() => void playFolder("end")} />}
          {playback && multiple && picks.size > 0 && <Button label={<><LuListPlus size={14} /> {t("ambient.queue.addEnd")}</>} onActivate={() => { void queueItems([...picks.values()], "end"); cancelMultiple(); }} />}
          {!!visible?.length && <Button disabled={applying} label={t(multiple ? "ambient.lib.cancelSelection" : "ambient.lib.chooseSeveral")} onActivate={multiple ? cancelMultiple : playback ? () => { setPicks(new Map()); setMultiple(true); } : startMultiple} />}
        </Focusable>
        <div ref={listRef} style={{ flex: 1, minHeight: 0 }}>
          {visible == null ? <Empty text={t("ambient.lib.loading")} /> : visible.length === 0 ? <Empty text={error || t("ambient.lib.filesEmpty")} /> : listHeight > 0 && (playback
            ? <VirtualList key={`${current?.id}:${multiple}`} controllerNavigation items={visible} height={listHeight} rowHeight={ROW_HEIGHT} keyOf={(m) => m.ref} renderRow={(m) => <Focusable {...menuHandlers(rowMenu(m))} onSecondaryActionDescription={m.kind === "image" ? undefined : t("ambient.lib.preview")} onSecondaryButton={m.kind === "image" ? undefined : (event) => {
              event.preventDefault();
              event.stopPropagation();
              if (!event.detail.is_repeat) void quickAction(m);
            }}><Row title={m.name.replace(/\.[^.]+$/, "")} selected={multiple ? chosen.has(m.ref) : m.ref === selected?.ref} swatch={m.kind === "video" ? <LuVideo size={18} /> : <LuMusic size={18} />} trailing={multiple ? <Checkmark on={chosen.has(m.ref)} label={m.name} /> : undefined} onActivate={() => choose(m)} /></Focusable>} />
            : <VirtualList key={`${current?.id}:${multiple}`} controllerNavigation items={gridRows} height={listHeight} rowHeight={TILE_ROW_HEIGHT} keyOf={(row) => row[0].ref} renderRow={(row) => (
              <Focusable flow-children="row" style={{ display: "grid", gridTemplateColumns: `repeat(${docked ? GRID_COLUMNS - 1 : GRID_COLUMNS}, minmax(0, 1fr))`, gap: 8, height: TILE_ROW_HEIGHT - 8 }}>
                {row.map((m) => <MediaTile key={m.ref} item={m} label={tileName(m.name, title)} runtime={runtime} selected={multiple ? chosen.has(m.ref) : m.ref === selected?.ref} checkable={multiple} onActivate={() => choose(m)} onSecondary={m.kind === "image" ? undefined : () => void quickAction(m)} secondaryLabel={t("ambient.lib.preview")} />)}
              </Focusable>
            )} />)}
        </div>
        {(error || notice) && <div role="status" style={{ color: error ? theme.color.warn : theme.color.textMuted, fontSize: theme.font.caption }}>{error || notice}</div>}
        <Focusable flow-children="row" style={{ display: "flex", alignItems: "center", gap: theme.space.sm, minHeight: 40 }}>
          <span aria-label={viewed?.name} style={{ flex: 1, minWidth: 0, fontSize: theme.font.caption, color: theme.color.textMuted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{multiple ? t("ambient.lib.selectedCount", { n: String(chosen.size) }) : viewed?.name.replace(/\.[^.]+$/, "") ?? ""}</span>
          <Button primary style={{ flexShrink: 0, minWidth: 150 }} disabled={!canApply} label={actionLabel} onActivate={() => void save()} />
        </Focusable>
      </Focusable>
      {docked && <Focusable data-library-column="2" flow-children="column" style={{ display: "flex", flexDirection: "column", minHeight: 0, minWidth: 0, paddingTop: 26 }}>
        <aside aria-label={snapshot.player.track?.title} style={{ minWidth: 0 }}><LibraryPlayback runtime={runtime} player={snapshot.player} /></aside>
      </Focusable>}
    </Focusable>
  </Focusable>;
};

const GRID_COLUMNS = 3;
const TILE_ROW_HEIGHT = 118;

function chunk<T>(items: readonly T[], size: number): T[][] {
  const rows: T[][] = [];
  for (let i = 0; i < items.length; i += size) rows.push(items.slice(i, i + size));
  return rows;
}

function sourceIcon(source: CollectionEntry) {
  if (source.id === "screenshots") return <LuCamera size={18} />;
  if (source.id === "known.music") return <LuMusic size={18} />;
  if (source.id === "known.images") return <LuImages size={18} />;
  if (source.kind === "suggested") return <LuSparkles size={18} />;
  return <LuFolder size={18} />;
}

/** Where a folder lives, without the home prefix: "~/Pictures/Ambiente demo". */
export function shortPath(path: string): string {
  const parent = path.replace(/\/[^/]+\/?$/, "");
  const home = parent.match(/^\/home\/[^/]+/)?.[0];
  return home ? "~" + parent.slice(home.length) : parent;
}

const Checkmark: FC<{ on: boolean; label: string }> = ({ on, label }) => (
  <span role="checkbox" aria-checked={on} aria-label={label} style={{ width: 18, height: 18, flexShrink: 0, border: `1px solid ${theme.color.accent}`, borderRadius: 4, display: "grid", placeItems: "center", color: theme.color.accent, background: on ? `rgba(${theme.color.accentRgb},0.15)` : "transparent" }}>{on && <LuCheck size={14} />}</span>
);

/** A picture's name without its extension, nor the folder name it often repeats ("GTA VI - Vice City"). */
export function tileName(name: string, folder: string): string {
  const bare = name.replace(/\.[^.]+$/, "");
  const prefix = folder && bare.toLowerCase().startsWith(folder.toLowerCase()) ? bare.slice(folder.length).replace(/^[\s\-–_:·]+/, "") : "";
  return prefix || bare;
}

const MediaTile: FC<{ item: LibraryItem; label: string; runtime: AmbientRuntime; selected: boolean; checkable: boolean; onActivate: () => void; onSecondary?: () => void; secondaryLabel: string }> = ({ item, label, runtime, selected, checkable, onActivate, onSecondary, secondaryLabel }) => {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setSrc(null);
    if (item.kind !== "image") return;
    void runtime.previewMedia(item.ref).then(async (url) => {
      if (!url || !active) return;
      const small = await thumbnail(url);
      if (active) setSrc(small ?? url);
    }).catch(() => undefined);
    return () => { active = false; };
  }, [runtime, item.ref]);
  return (
    <Focusable data-library-tile="" onActivate={onActivate} onClick={onActivate}
      onSecondaryActionDescription={onSecondary ? secondaryLabel : undefined}
      onSecondaryButton={onSecondary ? (event) => { event.preventDefault(); event.stopPropagation(); if (!event.detail.is_repeat) onSecondary(); } : undefined}
      style={{ position: "relative", display: "flex", flexDirection: "column", gap: 4, minWidth: 0, cursor: "pointer", borderRadius: theme.radius.sm }}>
      <div style={{ position: "relative", width: "100%", height: TILE_ROW_HEIGHT - 32, borderRadius: theme.radius.sm, overflow: "hidden", background: "#101216", display: "grid", placeItems: "center",
        boxShadow: selected ? `0 0 0 2px ${theme.color.accent}` : `inset 0 0 0 1px ${theme.color.hairline}` }}>
        {item.kind === "video" ? <LuVideo size={24} style={{ color: theme.color.textMuted }} /> : src
          ? <img src={src} alt="" decoding="async" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          : <LuImage size={22} style={{ color: theme.color.textMuted, opacity: 0.6 }} />}
        {checkable && <span style={{ position: "absolute", top: 6, right: 6 }}><Checkmark on={selected} label={item.name} /></span>}
      </div>
      <span style={{ fontSize: 11.5, color: selected ? theme.color.textPrimary : theme.color.textMuted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
    </Focusable>
  );
};
