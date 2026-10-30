import { openFilePicker } from "@decky/api";
import { Focusable } from "@decky/ui";
import { useEffect, useRef, useState, type FC, type ReactNode } from "react";
import { LuCheck, LuFolder, LuFolderPlus, LuImage, LuListPlus, LuMusic, LuPlay, LuTrash2, LuVideo } from "react-icons/lu";

import { useI18n } from "../../i18n";
import { theme } from "../../theme";
import type { AmbientRuntime, AmbientSnapshot } from "../steam/runtime";
import { RoundButton } from "./NowPlaying";
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
  const sources = available.filter((s) => s.kind !== "favorite" && (purpose === "background" || s.kind !== "suggested") &&
    (s.kind !== "known" || !snapshot.scan || (snapshot.scan.library?.[s.id] ?? snapshot.scan.collections[s.id] ?? (s.id === "known.music" ? snapshot.scan.music : []) ?? []).some((m) => acceptsMedia(m.kind, purpose))));
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
    <Focusable flow-children="row" style={{ display: "grid", gridTemplateColumns: "minmax(0, .8fr) minmax(0, 1fr) minmax(0, 1.1fr)", gap: theme.space.md, flex: 1, minHeight: 0 }}>
      <Focusable data-library-column="0" flow-children="column" style={{ overflowY: "auto", minHeight: 0, gridRow: purpose === "background" ? "1 / -1" : undefined }}>
        <Caption>{t("ambient.lib.sources")}</Caption>
        {sources.map((s) => <Row key={s.id} title={SOURCE_LABELS[s.id] ? t(SOURCE_LABELS[s.id]) : s.name ?? s.id} swatch={<LuFolder size={18} />} selected={s.id === current?.id} onActivate={() => setSourceId(s.id)} trailing={s.kind === "folder" || s.kind === "suggested" ? <RoundButton label={t("ambient.lib.remove")} size={30} onActivate={() => void runtime.removeItem(s.kind === "suggested" ? "background" : "library", s.id).then((ok) => { if (!ok) setError(t("ambient.lib.actionFailed")); })}><LuTrash2 size={14} /></RoundButton> : undefined} />)}
        <Button disabled={adding} label={<><LuFolderPlus size={14} />{t(adding ? "ambient.lib.working" : "ambient.lib.addFolder")}</>} onActivate={() => void addFolder()} />
        {purpose === "background" && state.settings.collections?.removedSuggested.filter((id) => SOURCE_LABELS[id]).map((id) => <Row key={id} title={t(SOURCE_LABELS[id])} subtitle={t("ambient.lib.restore")} onActivate={() => void runtime.restoreSuggested("background", id)} />)}
      </Focusable>
      <Focusable data-library-column="1" flow-children="column" style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
        <Caption>{t(purpose === "background" ? "ambient.lib.visualFiles" : "ambient.lib.playableFiles")}</Caption>
        <Focusable flow-children="row" style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
          <Button disabled={applying} style={{ flex: 1, minWidth: 0 }} label={t(multiple ? "ambient.lib.cancelSelection" : "ambient.lib.chooseSeveral")} onActivate={multiple ? cancelMultiple : playback ? () => { setPicks(new Map()); setMultiple(true); } : startMultiple} />
          {playback && multiple && picks.size > 0 && <RoundButton label={t("ambient.queue.addEnd")} size={34} onActivate={() => { void queueItems([...picks.values()], "end"); cancelMultiple(); }}><LuListPlus size={15} /></RoundButton>}
          {playback && !multiple && !!visible?.length && <RoundButton label={t("ambient.lib.playFolder")} size={34} onActivate={() => void playFolder("now")}><LuPlay size={15} /></RoundButton>}
          {playback && !multiple && !!visible?.length && <RoundButton label={t("ambient.lib.queueFolder")} size={34} onActivate={() => void playFolder("end")}><LuListPlus size={15} /></RoundButton>}
        </Focusable>
        <div ref={listRef} style={{ flex: 1, minHeight: 0 }}>
          {visible == null ? <Empty text={t("ambient.lib.loading")} /> : visible.length === 0 ? <Empty text={error || t("ambient.lib.filesEmpty")} /> : listHeight > 0 && <VirtualList key={`${current?.id}:${multiple}`} controllerNavigation items={visible} height={listHeight} rowHeight={ROW_HEIGHT} keyOf={(m) => m.ref} renderRow={(m) => <Focusable {...menuHandlers(rowMenu(m))} onSecondaryActionDescription={m.kind === "image" ? undefined : t("ambient.lib.preview")} onSecondaryButton={m.kind === "image" ? undefined : (event) => {
            event.preventDefault();
            event.stopPropagation();
            if (!event.detail.is_repeat) void quickAction(m);
          }}><Row title={m.name} selected={multiple ? chosen.has(m.ref) : m.ref === selected?.ref} swatch={m.kind === "image" ? <LuImage size={18} /> : m.kind === "video" ? <LuVideo size={18} /> : <LuMusic size={18} />} trailing={multiple ? <span role="checkbox" aria-checked={chosen.has(m.ref)} aria-label={m.name} style={{ width: 18, height: 18, flexShrink: 0, border: `1px solid ${theme.color.accent}`, borderRadius: 4, display: "grid", placeItems: "center", color: theme.color.accent }}>{chosen.has(m.ref) && <LuCheck size={14} />}</span> : undefined} onActivate={() => choose(m)} /></Focusable>} />}
        </div>
        {(error || notice) && <div role="status" style={{ color: error ? theme.color.warn : theme.color.textMuted, fontSize: theme.font.caption }}>{error || notice}</div>}
      </Focusable>
      <Focusable data-library-column="2" flow-children="column" style={{ display: "flex", flexDirection: "column", minHeight: 0, minWidth: 0 }}>
      <aside aria-label={viewed?.name} style={{ minWidth: 0, paddingTop: 22, minHeight: 0, display: "flex", flexDirection: "column", gap: 10, flex: 1 }}>
        {viewed?.kind === "image"
          ? <MediaPreview key={viewed.ref} item={viewed} runtime={runtime} />
          : snapshot.player?.track
            ? <LibraryPlayback runtime={runtime} player={snapshot.player} />
            : viewed && <MediaPreview key={viewed.ref} item={viewed} runtime={runtime} />}
      </aside>
      <Button primary style={{ flexShrink: 0 }} disabled={applying || (multiple ? chosen.size < (playback ? 1 : 2) : !selected)} label={applying ? t("ambient.lib.working") : multiple && playback ? t("ambient.lib.playSelected", { n: String(picks.size) }) : t("ambient.lib.save")} onActivate={() => void save()} />
      </Focusable>
    </Focusable>
  </Focusable>;
};
