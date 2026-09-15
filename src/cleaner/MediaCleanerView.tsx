import { TextField } from "@decky/ui";
import { useEffect, useMemo, useState } from "react";
import type { FC } from "react";
import { LuCheck, LuFilter, LuImage, LuSearch, LuSquare, LuSquareCheck, LuTrash2, LuVideo } from "react-icons/lu";
import { GameCover } from "../components/GameCover";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { CleanerActionTray } from "./CleanerActionTray";
import { CleanerButton, CleanerNotice, CleanerResult, cleanerCaption, cleanerColumn } from "./CleanerControls";
import { formatBytes } from "./model";
import { readCleanerMetadata } from "./steamMetadata";
import type { MediaItem } from "./media";
import type { MediaCleanerController } from "./useMediaCleaner";

type MediaFilter = "all" | "recommended" | "selected";
const FILTERS: MediaFilter[] = ["all", "recommended", "selected"];

function formatDate(value: number, locale: string): string {
  if (!value) return "";
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric" }).format(new Date(value * 1000));
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "";
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  return minutes ? `${minutes} min ${remaining ? `${remaining} s` : ""}`.trim() : `${remaining} s`;
}

const MediaThumbnail: FC<{ item: MediaItem; name: string; coverUrls: string[] }> = ({ item, name, coverUrls }) => {
  if (item.thumbnailUrl) return <div style={{ width: 64, height: 42, flexShrink: 0, borderRadius: theme.radius.sm, overflow: "hidden", background: theme.color.surface }}>
    <img src={item.thumbnailUrl} alt="" loading="lazy" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
  </div>;
  return <GameCover urls={coverUrls} name={name} width={34} />;
};

export const MediaCleanerView: FC<{ controller: MediaCleanerController }> = ({ controller }) => {
  const { t, lang } = useI18n();
  const [selected, setSelected] = useState(new Set<string>());
  const [filter, setFilter] = useState<MediaFilter>("all");
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const metadata = useMemo(readCleanerMetadata, []);
  const mediaName = (item: MediaItem) => metadata.get(item.gameId)?.name ?? item.title ?? t("cleaner.media.unassociated");
  const shown = controller.items.filter((item) => {
    const name = mediaName(item);
    const matches = !query.trim() || name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
    return matches && (filter === "all" || (filter === "recommended" ? item.recommendation !== null : selected.has(item.id)));
  }).sort((a, b) => (b.bytes ?? -1) - (a.bytes ?? -1));
  const chosen = controller.items.filter((item) => selected.has(item.id) && !item.active);
  const chosenBytes = chosen.reduce((sum, item) => sum + (item.bytes ?? 0), 0);

  useEffect(() => {
    const allowed = new Set(controller.items.filter((item) => !item.active).map((item) => item.id));
    setSelected((previous) => {
      const next = new Set([...previous].filter((id) => allowed.has(id)));
      return next.size === previous.size ? previous : next;
    });
  }, [controller.items]);

  const toggle = (item: MediaItem) => setSelected((previous) => {
    const next = new Set(previous);
    if (next.has(item.id)) next.delete(item.id); else if (!item.active) next.add(item.id);
    return next;
  });
  const recommended = shown.filter((item) => item.recommendation && !item.active);
  const allRecommendedSelected = recommended.length > 0 && recommended.every((item) => selected.has(item.id));

  return <div style={cleanerColumn}>
    {controller.error && <CleanerNotice warning>{t(`cleaner.reason.${controller.error}`)}</CleanerNotice>}
    {controller.result && <CleanerResult
      bytes={formatBytes(controller.result.bytesRemoved, lang)}
      failed={controller.result.items.some((item) => item.status === "error")}
      counts={t("cleaner.media.result", { deleted: controller.result.items.filter((item) => item.status === "deleted").length, errors: controller.result.items.filter((item) => item.status === "error").length })}
      onClose={controller.dismissResult}
    />}
    <div style={{ display: "flex", gap: 8 }}>
      <div style={{ flex: 1 }}><CleanerButton label={t("cleaner.filterLabel")} onActivate={() => setFilter((value) => FILTERS[(FILTERS.indexOf(value) + 1) % FILTERS.length])} style={{ justifyContent: "flex-start" }}><LuFilter size={14} /><span>{t(`cleaner.media.filter.${filter}`)}</span><span style={{ ...cleanerCaption, marginLeft: "auto" }}>{shown.length}</span></CleanerButton></div>
      <div style={{ width: 42 }}><CleanerButton label={t("cleaner.searchMedia")} onActivate={() => { setSearchOpen((value) => !value); setQuery(""); }}><LuSearch size={15} /></CleanerButton></div>
    </div>
    {searchOpen && <TextField label={t("cleaner.searchMedia")} value={query} onChange={(event) => setQuery(event.target.value)} />}
    {recommended.length > 0 && <CleanerButton label={t(allRecommendedSelected ? "cleaner.deselectRecommended" : "cleaner.selectRecommended")} disabled={controller.busy} onActivate={() => setSelected((previous) => {
      const next = new Set(previous);
      for (const item of recommended) allRecommendedSelected ? next.delete(item.id) : next.add(item.id);
      return next;
    })} style={{ minHeight: 30, padding: "5px 3px", justifyContent: "flex-start", background: "transparent", boxShadow: "none", color: theme.color.textMuted }}><LuCheck size={15} />{t(allRecommendedSelected ? "cleaner.deselectRecommended" : "cleaner.selectRecommended")}</CleanerButton>}
    {controller.loading && controller.items.length === 0 && <div role="status" style={{ ...cleanerCaption, padding: 12 }}>{t("cleaner.media.loading")}</div>}
    {shown.map((item) => {
      const visual = metadata.get(item.gameId);
      const name = mediaName(item);
      const checked = selected.has(item.id);
      const Check = checked ? LuSquareCheck : LuSquare;
      const KindIcon = item.kind === "screenshot" ? LuImage : LuVideo;
      const details = [t(`cleaner.media.kind.${item.kind}`), formatDate(item.createdAt, lang), formatDuration(item.durationSeconds)].filter(Boolean).join(" · ");
      return <div key={item.id} style={{ ...theme.card, padding: 6 }}>
        <CleanerButton label={t("cleaner.media.select", { name: item.title || name })} checked={checked} disabled={controller.busy || item.active} onActivate={() => toggle(item)} style={{ justifyContent: "flex-start", textAlign: "left", padding: 7, background: checked ? `${theme.color.accent}14` : "transparent", boxShadow: "none" }}>
          <MediaThumbnail item={item} name={name} coverUrls={visual?.coverUrls ?? []} />
          <span style={{ flex: 1, minWidth: 0 }}>
            <span style={{ display: "flex", alignItems: "center", gap: 5, fontWeight: 600 }}><KindIcon size={14} />{item.title || name}</span>
            <span style={{ ...cleanerCaption, display: "block" }}>{details}</span>
            {item.recommendation && <span style={{ ...cleanerCaption, display: "block", color: theme.color.accent }}>{t("cleaner.recommended")} · {t(`cleaner.recommendation.${item.recommendation}`)}</span>}
            {item.active && <span style={{ ...cleanerCaption, display: "block", color: theme.color.warn }}>{t("cleaner.media.active")}</span>}
          </span>
          <span style={{ ...cleanerCaption, color: theme.color.textPrimary, whiteSpace: "nowrap" }}>{item.bytes === null ? t(controller.loading ? "cleaner.calculating" : "cleaner.sizeUnknown") : formatBytes(item.bytes, lang)}</span>
          <Check size={18} color={checked ? theme.color.accent : theme.color.textMuted} />
        </CleanerButton>
      </div>;
    })}
    {!controller.loading && !controller.error && shown.length === 0 && <div style={{ ...cleanerCaption, padding: 12 }}>{t(controller.items.length ? "cleaner.media.noMatch" : "cleaner.media.empty")}</div>}
    {chosen.length > 0 && <CleanerActionTray><CleanerButton label={t("cleaner.media.clean")} primary disabled={controller.busy} onActivate={() => void controller.clean(chosen.map((item) => item.id))}><LuTrash2 size={16} /><span style={{ flex: 1, textAlign: "left" }}>{t("cleaner.media.clean")}</span><span>{formatBytes(chosenBytes, lang)}</span></CleanerButton></CleanerActionTray>}
  </div>;
};
