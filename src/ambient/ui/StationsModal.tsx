import { Dropdown, Focusable, ModalRoot, TextField, showModal } from "@decky/ui";
import { useEffect, useMemo, useRef, useState, type FC } from "react";
import { LuGlobe, LuHeart, LuLibrary, LuSearch } from "react-icons/lu";

import { FocusRoot } from "../../components/FocusRoot";
import { useI18n } from "../../i18n";
import { theme } from "../../theme";
import type { RadioCatalog, RadioFilters, RadioOrder, Station } from "../core/types";
import { CITY_ZOOM, STATION_ZOOM, unproject, viewRadiusKm } from "../core/mapNavigation";
import { homeCountry } from "../steam/homeCountry";
import { trackSource } from "../steam/player";
import { stationSubtitle } from "../steam/runtime";
import { Artwork, RoundButton } from "./NowPlaying";
import { Button, Segmented, menuHandlers, type ItemMenu } from "./primitives";
import { PlaylistsTab } from "./PlaylistsTab";
import { QueueTab } from "./QueueTab";
import { LinksTab } from "./LibraryTabs";
import { FilesTab } from "./FilesTab";
import { LibraryPlayback } from "./LibraryPlayback";
import type { LibraryPurpose } from "./libraryModel";
import { backToPanel, leavePanel } from "./panelModal";
import { useAmbient } from "./useAmbient";
import { VirtualList } from "./VirtualList";
import { WorldMap, type MapView } from "./WorldMap";
import { Chip, DimDialog, Empty, ROW_HEIGHT, Sheet, oneLine, useMeasuredHeight } from "./stationsParts";

export type LibraryTab = "music" | "discover" | "links" | "lists" | "queue";

/** Curated moods mapped to Radio Browser tags; the long tail lives in "More styles". */
const MOODS: readonly { id: string; tag: string }[] = [
  { id: "games", tag: "videogame" },
  { id: "lofi", tag: "lofi" },
  { id: "chill", tag: "chillout" },
  { id: "synthwave", tag: "synthwave" },
  { id: "electronic", tag: "electronic" },
  { id: "jazz", tag: "jazz" },
  { id: "classical", tag: "classical" },
  { id: "rock", tag: "rock" },
  { id: "pop", tag: "pop" },
  { id: "news", tag: "news" },
];
const HIGH_QUALITY_KBPS = 128;
const DEBOUNCE_MS = 300;
/** Wait for the map to settle before asking for a region's stations; panning and zooming stay smooth. */
const GEO_SETTLE_MS = 700;
const GEO_CACHE_SIZE = 40;


function regionNames(lang: string): (code: string, fallback: string) => string {
  try {
    const names = new Intl.DisplayNames([lang], { type: "region" });
    return (code, fallback) => names.of(code) ?? fallback;
  } catch {
    return (_code, fallback) => fallback;
  }
}

const Equalizer: FC = () => (
  <span aria-hidden style={{ display: "inline-flex", alignItems: "flex-end", gap: 2, height: 12 }}>
    {[7, 12, 9].map((h, i) => <span key={i} style={{ width: 3, height: h, borderRadius: 1, background: theme.color.accent }} />)}
  </span>
);


const StationRow: FC<{ station: Station; playing: boolean; favorite: boolean; favoriteLabel: string; onPlay: () => void; onFavorite: () => void; menu?: ItemMenu }> = ({ station, playing, favorite, favoriteLabel, onPlay, onFavorite, menu }) => (
  <Focusable
    flow-children="row"
    style={{
      display: "flex",
      alignItems: "center",
      gap: 10,
      padding: 8,
      borderRadius: theme.radius.md,
      background: playing ? `rgba(${theme.color.accentRgb},0.12)` : "transparent",
      boxShadow: playing ? `inset 0 0 0 1px rgba(${theme.color.accentRgb},0.45)` : "none",
    }}
  >
    <Focusable {...menuHandlers(menu)} onActivate={onPlay} onClick={onPlay} style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0, cursor: "pointer", borderRadius: theme.radius.sm }}>
      <Artwork src={station.favicon} label={station.name} size={40} />
      <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0, flex: 1 }}>
        <span style={{ ...oneLine, fontSize: 13, fontWeight: 600, color: theme.color.textPrimary }}>{station.name}</span>
        <span style={{ ...oneLine, fontSize: theme.font.caption, color: theme.color.textMuted }}>{stationSubtitle(station) || station.country}</span>
      </div>
      {playing && <Equalizer />}
    </Focusable>
    <RoundButton label={favoriteLabel} onActivate={onFavorite} active={favorite} size={32}>
      <LuHeart size={15} fill={favorite ? "currentColor" : "none"} />
    </RoundButton>
  </Focusable>
);

const PAGE = 40;
const MAX_STATIONS = 400;


export const StationsBody: FC<{ initialTab: LibraryTab; purpose: LibraryPurpose; onClose?: () => void }> = ({ initialTab, purpose, onClose }) => {
  const { t, lang } = useI18n();
  const { runtime, snapshot } = useAmbient();
  useEffect(() => runtime?.showLibrary(), [runtime]);
  const [tab, setTab] = useState<LibraryTab>(initialTab);
  const [catalog, setCatalog] = useState<RadioCatalog>({ countries: [], tags: [] });
  const [filters, setFilters] = useState<RadioFilters>({ order: "popular" });
  const [query, setQuery] = useState("");
  const [stations, setStations] = useState<Station[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [exhausted, setExhausted] = useState(false);
  const [allStyles, setAllStyles] = useState(false);
  const [listRef, listHeight] = useMeasuredHeight();
  const [view, setView] = useState<MapView>({ zoom: 1, center: { x: 500, y: 250 }, nearestCountry: null });
  const [geoStations, setGeoStations] = useState<Station[]>([]);
  const [geoLoading, setGeoLoading] = useState(false);
  const geoCache = useRef(new Map<string, Station[]>());
  const request = useRef(0);
  const offsetRef = useRef(0);
  const regionName = useMemo(() => regionNames(lang), [lang]);
  const [home, setHome] = useState<string | null>(null);

  useEffect(() => {
    if (runtime && purpose === "playback") void runtime.radioCatalog().then(setCatalog);
    if (purpose === "playback") void homeCountry().then(setHome);
  }, [runtime]);

  useEffect(() => {
    if (!runtime || tab !== "discover") return;
    const id = ++request.current;
    offsetRef.current = 0;
    setLoading(true);
    setExhausted(false);
    const timer = setTimeout(() => {
      void runtime.discoverRadio({ ...filters, limit: PAGE }).then((result) => {
        if (id !== request.current) return;
        setStations(result);
        setExhausted(result.length === 0);
        setLoading(false);
      });
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [runtime, filters, tab]);

  const cityLevel = view.zoom >= CITY_ZOOM;
  const areaQuery = useMemo((): { key: string; query: RadioFilters } | null => {
    if (view.zoom < STATION_ZOOM) return null;
    const style = { tag: filters.tag, minBitrate: filters.minBitrate, order: "popular" as const, hasGeo: true };
    if (cityLevel) {
      const { lat, lon } = unproject(view.center.x, view.center.y);
      const radiusKm = viewRadiusKm(1000 / view.zoom, lat);
      const grid = Math.max(0.02, radiusKm / 111 / 2);
      const cell = `${Math.round(lat / grid)}:${Math.round(lon / grid)}`;
      const near = { lat, lon, radiusKm };
      return { key: `near|${view.zoom}|${cell}|${filters.tag ?? ""}|${filters.minBitrate ?? ""}`, query: { ...style, near, limit: 100 } };
    }
    const country = filters.country ?? view.nearestCountry;
    if (!country) return null;
    return { key: `country|${country}|${filters.tag ?? ""}|${filters.minBitrate ?? ""}`, query: { ...style, country, limit: 150 } };
  }, [view.zoom, view.center, view.nearestCountry, filters.country, filters.tag, filters.minBitrate, cityLevel]);

  useEffect(() => {
    if (!runtime || !areaQuery) {
      setGeoStations([]);
      setGeoLoading(false);
      return;
    }
    const cached = geoCache.current.get(areaQuery.key);
    if (cached) {
      setGeoStations(cached);
      setGeoLoading(false);
      return;
    }
    let cancelled = false;
    setGeoLoading(true);
    const timer = setTimeout(() => {
      void runtime.discoverRadio(areaQuery.query).then((stations) => {
        if (cancelled) return;
        const result = stations.filter((s) => s.geo);
        geoCache.current.set(areaQuery.key, result);
        if (geoCache.current.size > GEO_CACHE_SIZE) geoCache.current.delete(geoCache.current.keys().next().value!);
        setGeoStations(result);
        setGeoLoading(false);
      });
    }, GEO_SETTLE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [runtime, areaQuery?.key]);

  if (!runtime || !snapshot) return null;

  const loadMore = () => {
    if (loading || exhausted || !stations || stations.length >= MAX_STATIONS) return;
    offsetRef.current += PAGE;
    const id = request.current;
    setLoading(true);
    void runtime.discoverRadio({ ...filters, limit: PAGE, offset: offsetRef.current }).then((page) => {
      if (id !== request.current) return;
      setStations((current) => {
        const seen = new Set((current ?? []).map((s) => s.id));
        return [...(current ?? []), ...page.filter((s) => !seen.has(s.id))];
      });
      setExhausted(page.length === 0);
      setLoading(false);
    });
  };

  const update = (patch: RadioFilters) => setFilters((current) => ({ ...current, ...patch }));
  const playing = snapshot.player.track && trackSource(snapshot.player.track) === "radio" ? snapshot.player.track : null;
  const countryOptions = [
    { data: "", label: t("ambient.stations.allCountries") },
    ...catalog.countries.map((c) => ({ data: c.code, label: `${regionName(c.code, c.name)} (${c.count})` })),
  ];
  const extraTags = catalog.tags.filter((tag) => !MOODS.some((m) => m.tag === tag.name)).slice(0, 48);
  const orderOptions: { value: RadioOrder; label: string }[] = [
    { value: "popular", label: t("ambient.stations.order.popular") },
    { value: "trending", label: t("ambient.stations.order.trending") },
    { value: "votes", label: t("ambient.stations.order.votes") },
  ];
  const mood = MOODS.find((m) => m.tag === filters.tag);
  const styleLabel = mood ? t(`ambient.mood.${mood.id}`) : filters.tag ?? null;
  const heading = [filters.country ? regionName(filters.country, filters.country) : null, styleLabel].filter(Boolean).join(", ") || t("ambient.stations.worldwide");

  const row = (station: Station) => {
    const favorite = runtime.isFavoriteStation(station);
    return (
      <StationRow
        station={station}
        playing={playing?.url === station.url}
        favorite={favorite}
        favoriteLabel={favorite ? t("ambient.stations.unfavorite") : t("ambient.stations.favorite")}
        onPlay={() => runtime.playStation(station)}
        onFavorite={() => void runtime.toggleFavoriteStation(station)}
        menu={{ title: station.name, hint: t("ambient.menu.options"), actions: [
          { label: t("ambient.queue.addEnd"), onSelect: () => runtime.enqueueStation(station, "end") },
          { label: t("ambient.queue.playNext"), onSelect: () => runtime.enqueueStation(station, "next") },
        ] }}
      />
    );
  };

  const header = (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
        <LuLibrary size={20} style={{ color: theme.color.accent, flexShrink: 0 }} />
        <span style={{ fontSize: 18, fontWeight: 700, color: theme.color.textPrimary }}>{t("ambient.lib.title")}</span>
        {!(tab === "music" && snapshot.player.video) && <LibraryPlayback inline runtime={runtime} player={snapshot.player} />}
      </div>
      <div style={{ width: "100%" }}>
        <Segmented value={tab} options={[
          { value: "music", label: t("ambient.lib.files") },
          { value: "discover", label: t("ambient.lib.tab.radio") },
          { value: "links", label: t("ambient.lib.tab.links") },
          { value: "lists", label: t("ambient.lists.title") },
          { value: "queue", label: snapshot.player.queue.length ? `${t("ambient.queue.title")} (${snapshot.player.queue.length})` : t("ambient.queue.title") },
        ].filter((option) => purpose === "playback" || option.value === "music" || option.value === "links")} onChange={(value) => setTab(value as LibraryTab)} />
      </div>
    </div>
  );

  if (tab === "music") {
    return <Sheet><FilesTab runtime={runtime} snapshot={snapshot} purpose={purpose} header={header} onClose={onClose} /></Sheet>;
  }

  if (tab === "queue") {
    return <Sheet><QueueTab runtime={runtime} snapshot={snapshot} header={header} /></Sheet>;
  }

  if (tab === "lists") {
    return (
      <Sheet>
        <PlaylistsTab runtime={runtime} playlists={snapshot.state?.settings.radio.playlists ?? []} header={header} row={row} />
      </Sheet>
    );
  }

  if (tab === "links") {
    return <Sheet><LinksTab runtime={runtime} snapshot={snapshot} purpose={purpose} header={header} row={row} /></Sheet>;
  }

  return (
    <Sheet>
      {header}
      <div style={{ display: "flex", gap: theme.space.sm, alignItems: "center" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <TextField
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key !== "Enter") return;
              e.preventDefault();
              e.stopPropagation();
              update({ name: query.trim() || undefined });
            }}
          />
        </div>
        <Button primary label={<><LuSearch size={14} /> {t("ambient.radio.searchAction")}</>} onActivate={() => update({ name: query.trim() || undefined })} style={{ height: 40 }} />
      </div>


      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.15fr) minmax(0, 1fr)", gap: theme.space.md, alignItems: "stretch", flex: 1, minHeight: 0 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, minWidth: 0, minHeight: 0, overflow: "hidden" }}>
          <WorldMap
            countries={catalog.countries}
            stations={geoStations}
            loadingStations={geoLoading}
            loadingLabel={t("ambient.stations.loadingArea")}
            selected={filters.country ?? null}
            playingUrl={playing?.url ?? null}
            playingCountry={playing?.countryCode ?? null}
            onSelect={(code) => update({ country: code ?? undefined })}
            onPlay={(station) => runtime.playStation(station)}
            onViewChange={setView}
            zoomInLabel={t("ambient.stations.zoomIn")}
            zoomOutLabel={t("ambient.stations.zoomOut")}
          />
          <Dropdown menuLabel={t("ambient.stations.country")} selectedOption={filters.country ?? ""} rgOptions={countryOptions} onChange={(option) => update({ country: option.data || undefined })} />
          <Focusable flow-children="row" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {home && <Chip icon={<LuGlobe size={13} />} label={t("ambient.stations.nearYou")} active={filters.country === home} onActivate={() => update({ country: filters.country === home ? undefined : home })} />}
            <Chip label={t("ambient.stations.highQuality")} active={filters.minBitrate === HIGH_QUALITY_KBPS} onActivate={() => update({ minBitrate: filters.minBitrate ? undefined : HIGH_QUALITY_KBPS })} />
          </Focusable>
          <Focusable flow-children="row" style={{ display: "flex", gap: 6, flexWrap: "wrap", alignContent: "flex-start", overflowY: "auto", flex: 1, minHeight: 0 }}>
            <Chip label={t("ambient.stations.allStyles")} active={!filters.tag} onActivate={() => update({ tag: undefined })} />
            {MOODS.map((m) => (
              <Chip key={m.id} label={t(`ambient.mood.${m.id}`)} active={filters.tag === m.tag} onActivate={() => update({ tag: filters.tag === m.tag ? undefined : m.tag })} />
            ))}
            {allStyles && extraTags.map((tag) => (
              <Chip key={tag.name} label={tag.name} active={filters.tag === tag.name} onActivate={() => update({ tag: filters.tag === tag.name ? undefined : tag.name })} />
            ))}
            <Chip label={allStyles ? t("ambient.stations.fewerStyles") : t("ambient.stations.moreStyles")} active={false} subtle onActivate={() => setAllStyles((v) => !v)} />
          </Focusable>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0, minHeight: 0 }}>
          <Segmented value={filters.order ?? "popular"} options={orderOptions} onChange={(value) => update({ order: value as RadioOrder })} />
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, padding: "4px 6px 2px" }}>
            <span style={{ ...oneLine, fontSize: 14, fontWeight: 700, color: theme.color.textPrimary, flex: 1 }}>{heading}</span>
            <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, whiteSpace: "nowrap" }}>
              {loading ? t("ambient.radio.searching") : stations ? t("ambient.stations.count", { n: stations.length }) : ""}
            </span>
          </div>
          <div ref={listRef} style={{ flex: 1, minHeight: 0 }}>
            {!stations && loading
              ? <Empty text={t("ambient.radio.searching")} />
              : stations && stations.length === 0
                ? <Empty text={t("ambient.radio.noResults")} />
                : listHeight > 0 && <VirtualList items={stations ?? []} rowHeight={ROW_HEIGHT} height={listHeight} keyOf={(s) => s.id} renderRow={row} onEndReached={loadMore} />}
          </div>
        </div>
      </div>
    </Sheet>
  );
};


const LibraryModal: FC<{ tab: LibraryTab; purpose: LibraryPurpose; closeModal?: () => void }> = ({ tab, purpose, closeModal }) => (
  <ModalRoot closeModal={backToPanel(closeModal)} onOK={() => undefined} bAllowFullSize>
    <FocusRoot>
      <DimDialog />
      <StationsBody initialTab={tab} purpose={purpose} onClose={backToPanel(closeModal)} />
    </FocusRoot>
  </ModalRoot>
);

export function openLibrary(purpose: LibraryPurpose, tab: LibraryTab = "music"): void {
  leavePanel();
  showModal(<LibraryModal purpose={purpose} tab={purpose === "background" && tab !== "links" ? "music" : tab} />, window);
}

export function openMediaLibrary(tab: LibraryTab = "music"): void {
  openLibrary("playback", tab);
}
