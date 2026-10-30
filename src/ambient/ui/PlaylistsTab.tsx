import { Dropdown, Focusable, TextField } from "@decky/ui";
import { useEffect, useMemo, useState, type FC, type ReactNode } from "react";
import { LuListPlus, LuTrash2 } from "react-icons/lu";

import { useI18n } from "../../i18n";
import { theme } from "../../theme";
import { filterChannels, topGroups } from "../core/playlists";
import type { Channel, Playlist, Station } from "../core/types";
import { channelToStation, type AmbientRuntime } from "../steam/runtime";
import { Button } from "./primitives";
import { Chip, Empty, ROW_HEIGHT, oneLine, useMeasuredHeight } from "./stationsParts";
import { openUrlModal } from "./UrlModal";
import { VirtualList } from "./VirtualList";

interface Props {
  runtime: AmbientRuntime;
  playlists: readonly Playlist[];
  header: ReactNode;
  row: (station: Station) => ReactNode;
}

/** M3U lists (IPTV, radio bundles): pick a list, filter by group or name, play a channel. */
export const PlaylistsTab: FC<Props> = ({ runtime, playlists, header, row }) => {
  const { t } = useI18n();
  const [selected, setSelected] = useState<string | null>(playlists[0]?.id ?? null);
  const [channels, setChannels] = useState<Channel[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState<string | null>(null);
  const [listRef, listHeight] = useMeasuredHeight();
  const current = playlists.find((p) => p.id === selected) ?? playlists[0] ?? null;

  useEffect(() => {
    if (!current) {
      setChannels(null);
      return;
    }
    let alive = true;
    setChannels(null);
    setError(null);
    setGroup(null);
    void runtime.playlist(current.id).then((contents) => {
      if (!alive) return;
      setChannels(contents.channels);
      setError(contents.error ?? null);
    });
    return () => {
      alive = false;
    };
  }, [runtime, current?.id]);

  const groups = useMemo(() => topGroups(channels ?? []), [channels]);
  const visible = useMemo(() => filterChannels(channels ?? [], query, group).map(channelToStation), [channels, query, group]);

  const addList = () => openUrlModal("ambient.lists.add", async (url, name) => {
    const ok = await runtime.addPlaylist(url, name);
    if (ok) {
      const added = runtime.getSnapshot().state?.settings.radio.playlists.find((p) => p.url === url);
      if (added) setSelected(added.id);
    }
    return ok;
  });

  return (
    <>
      {header}
      <div style={{ display: "flex", gap: theme.space.sm, alignItems: "center" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {playlists.length > 0 && (
            <Dropdown
              menuLabel={t("ambient.lists.title")}
              selectedOption={current?.id ?? ""}
              rgOptions={playlists.map((p) => ({ data: p.id, label: p.name }))}
              onChange={(option) => setSelected(option.data as string)}
            />
          )}
        </div>
        {current && <Button label={<LuTrash2 size={14} />} onActivate={() => void runtime.removePlaylist(current.id).then(() => setSelected(null))} style={{ height: 40 }} />}
        <Button primary label={<><LuListPlus size={14} /> {t("ambient.lists.add")}</>} onActivate={addList} style={{ height: 40 }} />
      </div>

      {current && (
        <>
          <TextField value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), e.stopPropagation())} />
          {groups.length > 1 && (
            <Focusable flow-children="row" style={{ display: "flex", gap: 6, overflowX: "auto" }}>
              <Chip label={t("ambient.lists.allGroups")} active={!group} onActivate={() => setGroup(null)} />
              {groups.map((g) => <Chip key={g} label={g} active={group === g} onActivate={() => setGroup(group === g ? null : g)} />)}
            </Focusable>
          )}
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, padding: "0 6px 2px" }}>
            <span style={{ ...oneLine, fontSize: 14, fontWeight: 700, color: theme.color.textPrimary, flex: 1 }}>{group ?? current.name}</span>
            <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, whiteSpace: "nowrap" }}>
              {channels ? t("ambient.lists.count", { n: visible.length }) : t("ambient.radio.searching")}
            </span>
          </div>
        </>
      )}

      <div ref={listRef} style={{ flex: 1, minHeight: 0 }}>
        {!current
          ? <Empty text={t("ambient.lists.empty")} />
          : !channels
            ? <Empty text={t("ambient.radio.searching")} />
            : channels.length === 0
              ? <Empty text={error ? t("ambient.lists.unreachable") : t("ambient.radio.noResults")} />
              : listHeight > 0 && <VirtualList items={visible} rowHeight={ROW_HEIGHT} height={listHeight} keyOf={(s) => s.id} renderRow={row} />}
      </div>
    </>
  );
};
