import { TextField } from "@decky/ui";
import { useState, type FC, type ReactNode } from "react";
import { LuImage, LuPlus, LuTrash2 } from "react-icons/lu";

import { useI18n } from "../../i18n";
import { theme } from "../../theme";
import { linkName } from "../core/linkName";
import type { Station } from "../core/types";
import { favoriteToStation, type AmbientRuntime, type AmbientSnapshot } from "../steam/runtime";
import { RoundButton } from "./NowPlaying";
import { Button, Row } from "./primitives";
import { Empty, ROW_HEIGHT, oneLine, useMeasuredHeight } from "./stationsParts";
import { VirtualList } from "./VirtualList";
import { MediaPreview, MediaSelection } from "./FilesTab";
import { libraryFavorites, linkKind, type LibraryPurpose, type LibraryItem } from "./libraryModel";

const URL_PATTERN = /^https?:\/\/\S+$/i;

/** Paste a link and add it, right where the list is; the hint says what is accepted. */
export const AddLinkBar: FC<{ hint: string; onAdd: (url: string, name: string) => Promise<boolean> }> = ({ hint, onAdd }) => {
  const { t } = useI18n();
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const add = async () => {
    if (busy) return;
    const trimmed = url.trim();
    if (!URL_PATTERN.test(trimmed)) return setError(t("ambient.add.url.invalid"));
    setBusy(true);
    setError(null);
    try {
      if (await onAdd(trimmed, linkName(trimmed))) setUrl("");
      else setError(t("ambient.lib.actionFailed"));
    } catch { setError(t("ambient.lib.actionFailed")); }
    finally { setBusy(false); }
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div className="pdc-library-link" style={{ display: "flex", gap: theme.space.sm, alignItems: "flex-end" }}>
        <style>{`.pdc-library-link .DialogInputLabelGroup { margin-bottom: 0 !important; }`}</style>
        <div style={{ flex: 1, minWidth: 0 }}>
          <TextField
            label={t("ambient.add.url.field")}
            value={url}
            onChange={(e) => { setUrl(e.target.value); setError(null); }}
            onKeyDown={(e) => {
              if (e.key !== "Enter") return;
              e.preventDefault();
              e.stopPropagation();
              void add();
            }}
          />
        </div>
        <Button primary disabled={busy} label={<><LuPlus size={14} /> {t(busy ? "ambient.lib.working" : "ambient.lib.add")}</>} onActivate={() => void add()} style={{ height: 40, alignSelf: "flex-end" }} />
      </div>
      <span style={{ fontSize: theme.font.caption, color: error ? theme.color.warn : theme.color.textMuted, padding: "0 2px" }}>{error ?? hint}</span>
    </div>
  );
};

export const LinksTab: FC<{ runtime: AmbientRuntime; snapshot: AmbientSnapshot; header: ReactNode; purpose: LibraryPurpose; row: (station: Station) => ReactNode }> = ({ runtime, snapshot, header, row, purpose }) => {
  const { t } = useI18n();
  const [listRef, listHeight] = useMeasuredHeight();
  const [selected, setSelected] = useState<LibraryItem | null>(null);
  const favorites = libraryFavorites(snapshot.state?.settings.collections.favorites ?? [], snapshot.state?.settings.radio.favorites ?? [], purpose);
  return (
    <>
      {header}
      <AddLinkBar hint={t(purpose === "background" ? "ambient.add.url.formats" : "ambient.lib.links.hint")} onAdd={(url, name) => runtime.addFavorite(purpose === "background" ? "background" : "radio", url, name)} />
      <div style={{ display: "grid", gridTemplateColumns: purpose === "background" ? "minmax(0, 1fr) minmax(0, 1fr)" : "minmax(0, 1fr)", gap: theme.space.md, gridTemplateRows: purpose === "background" ? "minmax(0, 1fr) auto" : undefined, flex: 1, minHeight: 0 }}>
      <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div ref={listRef} style={{ flex: 1, minHeight: 0 }}>
        {favorites.length === 0
          ? <Empty text={t("ambient.lib.linksEmpty")} />
          : listHeight > 0 && <VirtualList items={favorites} rowHeight={ROW_HEIGHT} height={listHeight} keyOf={(s) => s.id} renderRow={(favorite) => <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <div style={{ flex: 1, minWidth: 0 }}>{purpose === "playback" ? row(favoriteToStation(favorite)) : <Row title={favorite.name} swatch={<LuImage size={18} />} selected={selected?.ref === "remote:" + favorite.url} onActivate={() => setSelected({ ref: "remote:" + favorite.url, name: favorite.name, kind: linkKind(favorite.url) ?? "image", collection: favorite.id })} />}</div>
            <RoundButton label={t("ambient.lib.remove")} size={30} onActivate={() => { setSelected(null); void runtime.removeItem("library", favorite.id); }}><LuTrash2 size={14} /></RoundButton>
          </div>} />}
      </div>
      </div>
      {purpose === "background" && <aside aria-label={selected?.name} style={{ minWidth: 0 }}>{selected && <MediaPreview key={selected.ref} item={selected} runtime={runtime} />}</aside>}
      {selected && purpose === "background" && <div style={{ gridColumn: 2 }}><MediaSelection key={selected.ref} item={selected} purpose={purpose} runtime={runtime} /></div>}
      </div>
      <span style={{ ...oneLine, fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("ambient.lib.sharedLinks")}</span>
    </>
  );
};
