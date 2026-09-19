import { CSSProperties, FC, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Focusable, PanelSectionRow, TextField } from "@decky/ui";
import { LuArrowDownUp, LuCheck, LuChevronDown, LuChevronRight, LuCircleAlert, LuCircleCheck, LuFilter, LuHardDrive, LuInfo, LuRefreshCw, LuSearch, LuShieldCheck, LuSquare, LuSquareCheck, LuSquareMinus, LuTrash2, LuX } from "react-icons/lu";
import { GameCover } from "../components/GameCover";
import { CleanerActionTray } from "./CleanerActionTray";
import { useI18n } from "../i18n";
import { onPrefsHealed, readFlag, writeFlag } from "../system/pdcStorage";
import { theme } from "../theme";
import { cleanerReasonKey } from "./errors";
import { CleanerFilter, CleanerGame, CleanerSort, eligibleCaches, filterGames, formatBytes, groupEntries, toggleCaches, toggleEntry } from "./model";
import { readCleanerMetadata, readInstalledCleanerMetadata } from "./steamMetadata";
import type { CleanerController } from "./useSteamCleaner";
import type { CleanerEntry } from "./types";

const column: CSSProperties = { display: "flex", flexDirection: "column", gap: theme.space.sm, minWidth: 0 };
const caption: CSSProperties = { fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.5 };
const FILTERS: CleanerFilter[] = ["all", "cleanable", "not_installed", "selected"];
const HELP_DISMISSED_KEY = "pdc:cleanerHelpDismissed";

function libraryLabel(entry: Pick<CleanerEntry, "library_label" | "library_internal">, internalStorage: string): string {
  return entry.library_internal === true ? internalStorage : entry.library_label;
}

const CleanerAction: FC<{
  label: string; children: ReactNode; onActivate: () => void; disabled?: boolean;
  checked?: boolean | "mixed"; primary?: boolean; danger?: boolean; style?: CSSProperties;
}> = ({ label, children, onActivate, disabled, checked, primary, danger, style }) => {
  const activate = () => { if (!disabled) onActivate(); };
  return (
    <Focusable
      role={checked === undefined ? "button" : "checkbox"}
      aria-label={label}
      title={label}
      aria-checked={checked}
      aria-disabled={!!disabled}
      tabIndex={disabled ? -1 : 0}
      onActivate={activate}
      onClick={activate}
      onOKActionDescription={label}
      style={{ width: "100%", minWidth: 0, padding: 0, borderRadius: theme.radius.sm }}
    >
      <div style={{
        ...theme.card, width: "100%", boxSizing: "border-box", minHeight: 40,
        display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
        padding: "10px 12px", borderRadius: theme.radius.sm, fontSize: theme.font.body,
        color: primary ? theme.color.onAccent : danger ? theme.color.danger : theme.color.textPrimary,
        background: primary ? theme.color.accent : theme.color.surfaceRaised,
        opacity: disabled ? 0.4 : 1, cursor: disabled ? "default" : "pointer", ...style,
      }}>{children}</div>
    </Focusable>
  );
};

const Notice: FC<{ children: ReactNode; warning?: boolean }> = ({ children, warning }) => (
  <div style={{ ...caption, display: "flex", alignItems: "flex-start", gap: 8, padding: "9px 10px", borderRadius: theme.radius.sm, background: warning ? `${theme.color.warn}10` : theme.color.surfaceRaised, color: warning ? theme.color.warn : theme.color.textMuted }}>
    <LuCircleAlert size={15} style={{ flexShrink: 0, marginTop: 1 }} /><span>{children}</span>
  </div>
);

const EntryChoice: FC<{ entry: CleanerEntry; selected: boolean; disabled: boolean; onToggle: () => void }> = ({ entry, selected, disabled, onToggle }) => {
  const { t, lang } = useI18n();
  const title = t(`cleaner.kind.${entry.kind}`);
  const storage = libraryLabel(entry, t("cleaner.internalStorage"));
  const Check = selected ? LuSquareCheck : LuSquare;
  return (
    <div style={{ ...column, gap: 4 }}>
      <CleanerAction label={`${title} · ${storage}`} checked={selected} disabled={disabled || !!entry.blocked_reason} onActivate={onToggle} style={{ textAlign: "left", justifyContent: "flex-start", background: selected ? `${theme.color.accent}14` : theme.color.surface }}>
        {entry.blocked_reason ? <LuShieldCheck size={17} style={{ flexShrink: 0 }} /> : <Check size={17} color={selected ? theme.color.accent : theme.color.textMuted} style={{ flexShrink: 0 }} />}
        <span style={{ flex: 1, minWidth: 0 }}><span style={{ display: "block" }}>{title}</span><span style={caption}>{storage}</span></span>
        <span style={{ ...caption, flexShrink: 0, fontVariantNumeric: "tabular-nums", color: theme.color.textPrimary }}>{entry.bytes === null ? t("cleaner.sizeUnknown") : formatBytes(entry.bytes, lang)}</span>
      </CleanerAction>
      {entry.blocked_reason && <div style={{ ...caption, paddingInline: 8 }}>{t(cleanerReasonKey(entry.blocked_reason))}</div>}
      {!entry.blocked_reason && entry.warnings.filter((warning) => warning !== "prefix_data").map((warning) => <div key={warning} style={{ ...caption, paddingInline: 8 }}>{t(warning === "unknown_identity" ? "cleaner.warning.unknown_identity" : cleanerReasonKey(warning))}</div>)}
    </div>
  );
};

const GameRow: FC<{ game: CleanerGame; selected: ReadonlySet<string>; disabled: boolean; onCaches: () => void; onEntry: (entry: CleanerEntry) => void }> = ({ game, selected, disabled, onCaches, onEntry }) => {
  const { t, lang } = useI18n();
  const [open, setOpen] = useState(false);
  const name = game.name || t("cleaner.unknownGame");
  const caches = eligibleCaches(game.entries);
  const selectable = game.entries.filter((entry) => !entry.blocked_reason);
  const selectedCount = game.entries.filter((entry) => selected.has(entry.id)).length;
  const selectedKinds = [...new Set(game.entries.filter((entry) => selected.has(entry.id)).map((entry) => entry.kind))];
  const allSelected = selectable.length > 0 && selectable.every((entry) => selected.has(entry.id));
  const partiallySelected = selectedCount > 0 && !allSelected;
  const Check = allSelected ? LuSquareCheck : partiallySelected ? LuSquareMinus : LuSquare;
  const canSelectCaches = caches.length > 0;
  const Chevron = open ? LuChevronDown : LuChevronRight;
  const installation = game.entries[0].installation;
  return (
    <div style={{ ...theme.card, ...column, gap: 0, padding: 6 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <CleanerAction label={t(canSelectCaches ? "cleaner.selectGameCaches" : "cleaner.chooseGameData", { name })} checked={canSelectCaches ? allSelected ? true : partiallySelected ? "mixed" : false : undefined} disabled={disabled || selectable.length === 0} onActivate={canSelectCaches ? onCaches : () => setOpen(true)} style={{ background: "transparent", boxShadow: "none", padding: "6px", textAlign: "left", justifyContent: "flex-start" }}>
            <GameCover urls={game.coverUrls} name={name} width={38} />
            <span style={{ flex: 1, minWidth: 0 }}>
              <span style={{ display: "block", fontSize: theme.font.body, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</span>
              {(game.name || installation !== "unknown") && <span style={{ ...caption, display: "block" }}>{t(`cleaner.installation.${installation}`)}</span>}
              {installation === "not_installed" && <span style={{ ...caption, display: "block", color: theme.color.accent }}>{t("cleaner.recommended")} · {t("cleaner.recommendation.game_not_installed")}</span>}
              <span style={{ display: "block", marginTop: 3, fontSize: theme.font.caption, fontVariantNumeric: "tabular-nums", color: theme.color.accent }}>{game.entries.every((entry) => entry.bytes === null) ? t("cleaner.sizeUnknown") : `${formatBytes(game.bytes, lang)}${game.sizeUnknown ? ` · ${t("cleaner.partialSize")}` : ""}`}</span>
            </span>
            <Check size={18} color={selectedCount > 0 ? theme.color.accent : theme.color.textMuted} style={{ flexShrink: 0 }} />
          </CleanerAction>
        </div>
        <div style={{ width: 36, flexShrink: 0 }}>
          <CleanerAction label={t("cleaner.gameDetails", { name })} onActivate={() => setOpen((value) => !value)} style={{ padding: 8, background: "transparent", boxShadow: "none" }}><Chevron size={18} /></CleanerAction>
        </div>
      </div>
      {selectedCount > 0 && <div style={{ ...caption, color: theme.color.accent, padding: "2px 8px 6px" }}>{selectedKinds.map((kind) => t(`cleaner.kind.${kind}`)).join(" · ")}</div>}
      {open && <div style={{ ...column, padding: "6px" }}>
        {!game.name && <div style={caption}>{t("cleaner.steamIdentifier", { id: game.entries[0].appid })}</div>}
        {game.entries.map((entry) => <EntryChoice key={entry.id} entry={entry} selected={selected.has(entry.id)} disabled={disabled} onToggle={() => onEntry(entry)} />)}
      </div>}
    </div>
  );
};

const LoadingGameRow: FC<{ game: ReturnType<typeof readInstalledCleanerMetadata>[number] }> = ({ game }) => {
  const { t } = useI18n();
  return <div style={{ ...theme.card, display: "flex", alignItems: "center", gap: 10, padding: 12 }}>
    <GameCover urls={game.coverUrls} name={game.name} width={38} />
    <span style={{ flex: 1, minWidth: 0, fontSize: theme.font.body, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{game.name}</span>
    <span style={{ ...caption, color: theme.color.textPrimary, whiteSpace: "nowrap" }}>{t("cleaner.calculating")}</span>
  </div>;
};

export const SteamCleanerView: FC<{ controller: CleanerController; embedded?: boolean }> = ({ controller, embedded = false }) => {
  const { t, lang } = useI18n();
  const { state, plan, result, error, loading, busy, pending } = controller;
  const [selected, setSelected] = useState(new Set<string>());
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [sort, setSort] = useState<CleanerSort>("size");
  const [filter, setFilter] = useState<CleanerFilter>("all");
  const [resultsOpen, setResultsOpen] = useState(false);
  const [helpVisible, setHelpVisible] = useState(() => !readFlag(HELP_DISMISSED_KEY));
  const labels = useRef(new Map<string, CleanerEntry>());
  const metadata = useMemo(readCleanerMetadata, [state?.scan_id]);
  const installedMetadata = useMemo(() => readInstalledCleanerMetadata(metadata), [metadata]);
  const games = useMemo(() => groupEntries(state?.entries ?? [], metadata), [state?.entries, metadata]);
  const shown = useMemo(() => filterGames(games, query, filter, sort, selected), [games, query, filter, sort, selected]);
  const chosen = (state?.entries ?? []).filter((entry) => selected.has(entry.id) && !entry.blocked_reason);
  const chosenBytes = chosen.reduce((sum, entry) => sum + (entry.bytes ?? 0), 0);
  const shownEntries = shown.flatMap((game) => game.entries);
  const shownCaches = eligibleCaches(shownEntries);
  const allShownCachesSelected = shownCaches.length > 0 && shownCaches.every((entry) => selected.has(entry.id));
  const entries = state?.entries;
  const scanId = state?.scan_id;
  const hasScanData = !!state && (!!scanId || state.libraries.length > 0);
  const selectionDisabled = busy || !!plan || !scanId;
  const calculatingGames = embedded && (loading || pending === "scan" || state?.status === "scanning");

  useEffect(() => { setSelected(new Set()); }, [scanId]);
  useEffect(() => { setResultsOpen(false); }, [result?.operation_id]);
  useEffect(() => onPrefsHealed(() => setHelpVisible(!readFlag(HELP_DISMISSED_KEY))), []);
  useEffect(() => {
    if (!entries) return;
    for (const entry of entries) labels.current.set(entry.id, entry);
    const allowed = new Set(entries.filter((entry) => !entry.blocked_reason).map((entry) => entry.id));
    setSelected((previous) => {
      const next = new Set([...previous].filter((id) => allowed.has(id)));
      return next.size === previous.size ? previous : next;
    });
  }, [entries]);

  const errorNotice = error || state?.error;
  const failedNotice = errorNotice && <div style={column}><Notice warning>{t(cleanerReasonKey(errorNotice))}</Notice><CleanerAction label={t("cleaner.refreshState")} onActivate={() => void controller.refresh()}><LuRefreshCw size={15} />{t("cleaner.refreshState")}</CleanerAction></div>;

  return (
    <PanelSectionRow>
      <div style={column}>
        {!embedded && <div style={{ ...theme.card, padding: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <LuHardDrive size={17} color={theme.color.accent} /><span style={{ flex: 1, fontSize: 15, fontWeight: 650 }}>{t("cleaner.title")}</span>
            {hasScanData && <div style={{ width: 32 }}><CleanerAction label={t("cleaner.scanAgain")} disabled={busy || loading || !!plan} onActivate={() => { setSelected(new Set()); void controller.scan(); }} style={{ padding: 6, minHeight: 30, background: "transparent", boxShadow: "none" }}><LuRefreshCw size={15} /></CleanerAction></div>}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 8, marginTop: 12 }}>
            {(["shadercache", "compatdata"] as const).map((kind) => {
              const categoryEntries = entries?.filter((entry) => entry.kind === kind) ?? [];
              const sizeUnknown = categoryEntries.length === 0
                ? !state?.coverage_complete
                : categoryEntries.every((entry) => entry.bytes === null);
              const size = !hasScanData ? t("cleaner.notScanned")
                : sizeUnknown ? t("cleaner.sizeUnknown") : formatBytes(state!.totals[kind], lang);
              return <div key={kind} style={{ ...theme.tile, padding: "9px 10px" }}>
                <div style={caption}>{t(`cleaner.kind.${kind}`)}</div>
                <div style={{ fontSize: 18, fontWeight: 650, fontVariantNumeric: "tabular-nums", marginTop: 4 }}>{size}</div>
              </div>;
            })}
          </div>
          <div style={{ ...caption, marginTop: 9 }}>{t("cleaner.summaryHint")}</div>
          {!!state?.totals.unknown && <div style={{ ...caption, color: theme.color.warn }}>{t("cleaner.unknownSizes")}</div>}
        </div>}
        {failedNotice}
        {loading ? <div role="status" style={{ ...caption, padding: 12 }}>{t("cleaner.loading")}</div> : busy ? <div style={{ ...theme.card, ...column, padding: 12 }}>
          <div role="status" aria-live="polite" style={{ fontSize: theme.font.body }}>{t(pending === "prepare" ? "cleaner.preparing" : state?.status === "cleaning" || pending === "execute" ? "cleaner.cleaning" : "cleaner.scanning")}</div>
          {(state?.status === "scanning" || state?.status === "cleaning") && state.progress.total != null && <div style={{ ...caption, fontVariantNumeric: "tabular-nums" }}>{t("cleaner.progress", { done: state.progress.processed, total: state.progress.total })}</div>}
          {pending !== "prepare" && <CleanerAction label={t("cleaner.cancel")} disabled={controller.cancelling} onActivate={() => void controller.cancel()}><LuX size={15} />{t(controller.cancelling ? "cleaner.cancelling" : "cleaner.cancel")}</CleanerAction>}
          <div style={caption}>{t("cleaner.cancelHint")}</div>
        </div> : !hasScanData ? <CleanerAction label={t("cleaner.scan")} primary onActivate={() => { setSelected(new Set()); void controller.scan(); }}><LuRefreshCw size={16} />{t("cleaner.scan")}</CleanerAction> : null}
        {calculatingGames && installedMetadata.map((game) => <LoadingGameRow key={game.appid} game={game} />)}
        {state?.scan_id && !state.coverage_complete && <Notice warning>{t("cleaner.coverageIncomplete")}</Notice>}
        {state?.libraries.filter((library) => !library.available).map((library) => <Notice key={library.id} warning>{library.label} · {t(cleanerReasonKey(library.reason))}</Notice>)}
        {state && state.status !== "idle" && !loading && !busy && !state.available && <Notice>{t("cleaner.unavailable")}</Notice>}
        {result && !busy && <div style={{ ...theme.card, ...column, padding: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: theme.font.body, fontWeight: 600 }}>
            {result.items.some((item) => item.status !== "deleted") || result.cancelled ? <LuCircleAlert size={17} color={theme.color.warn} /> : <LuCircleCheck size={17} color={theme.color.ok} />}
            <span style={{ flex: 1, minWidth: 0 }}>{t(result.cancelled ? "cleaner.result.cancelled" : "cleaner.result.title")}</span>
            <div style={{ width: 30, flexShrink: 0 }}><CleanerAction label={t("cleaner.result.close")} onActivate={controller.dismissResult} style={{ minHeight: 30, padding: 6, background: "transparent", boxShadow: "none" }}><LuX size={15} /></CleanerAction></div>
          </div>
          <div style={{ fontSize: 22, fontWeight: 650, fontVariantNumeric: "tabular-nums" }}>{formatBytes(result.estimated_bytes_removed, lang)}</div>
          <div style={caption}>{t("cleaner.result.estimate")}</div>
          <div style={caption}>{t("cleaner.result.counts", { deleted: result.items.filter((item) => item.status === "deleted").length, skipped: result.items.filter((item) => item.status === "skipped").length, errors: result.items.filter((item) => item.status === "error").length })}</div>
          <CleanerAction label={t("cleaner.result.details")} onActivate={() => setResultsOpen((value) => !value)}>{t("cleaner.result.details")}{resultsOpen ? <LuChevronDown size={15} /> : <LuChevronRight size={15} />}</CleanerAction>
          {resultsOpen && result.items.map((item, index) => {
            const entry = item.entry ?? labels.current.get(item.id);
            return <div key={item.id} style={{ borderTop: `1px solid ${theme.color.hairline}`, paddingBlock: 8 }}>
              <div style={{ fontSize: theme.font.body }}>{entry ? entry.name || metadata.get(entry.appid)?.name || t("cleaner.unknownGame") : t("cleaner.result.item", { n: index + 1 })}</div>
              {entry && !entry.name && !metadata.get(entry.appid)?.name && <div style={caption}>{t("cleaner.steamIdentifier", { id: entry.appid })}</div>}
              {entry && <div style={caption}>{t(`cleaner.kind.${entry.kind}`)} · {libraryLabel(entry, t("cleaner.internalStorage"))}</div>}
              <div style={{ ...caption, color: item.status === "deleted" ? theme.color.ok : theme.color.warn }}>{t(`cleaner.result.${item.status}`)}{item.reason ? ` · ${t(cleanerReasonKey(item.reason))}` : ""}</div>
            </div>;
          })}
        </div>}
        {hasScanData && !scanId && !busy && <CleanerAction label={t("cleaner.scanAfterCleanup")} primary onActivate={() => void controller.scan()}><LuRefreshCw size={16} />{t("cleaner.scanAfterCleanup")}</CleanerAction>}
        {hasScanData && !calculatingGames && <>
          <div style={{ display: "flex", gap: 8 }}>
            <div style={{ flex: 1, minWidth: 0 }}><CleanerAction label={t("cleaner.filterLabel")} onActivate={() => setFilter((value) => FILTERS[(FILTERS.indexOf(value) + 1) % FILTERS.length])} style={{ justifyContent: "flex-start", paddingInline: 9 }}><LuFilter size={14} style={{ flexShrink: 0 }} /><span>{t(`cleaner.filter.${filter}`)}</span><span style={{ ...caption, marginLeft: "auto" }}>{shown.length}</span></CleanerAction></div>
            <div style={{ width: 36, flexShrink: 0 }}><CleanerAction label={`${t("cleaner.sortLabel")}: ${t(`cleaner.sort.${sort}`)}`} onActivate={() => setSort((value) => value === "size" ? "name" : "size")} style={{ padding: 8 }}><LuArrowDownUp size={15} /></CleanerAction></div>
            <div style={{ width: 42, flexShrink: 0 }}><CleanerAction label={t("cleaner.search")} onActivate={() => { setSearchOpen((value) => !value); setQuery(""); }} style={{ padding: 10 }}><LuSearch size={16} color={searchOpen ? theme.color.accent : undefined} /></CleanerAction></div>
          </div>
          {searchOpen && <TextField label={t("cleaner.search")} value={query} onChange={(event) => setQuery(event.target.value)} />}
          {helpVisible && <div style={{ ...theme.card, ...column, gap: 6, padding: "9px 10px" }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
              <LuInfo size={15} color={theme.color.accent} style={{ flexShrink: 0, marginTop: 1 }} />
              <div style={{ ...caption, display: "flex", flexDirection: "column", gap: 3 }}>
                <span>{t("cleaner.cacheHint")}</span>
                <span>{t("cleaner.prefixHint")}</span>
              </div>
            </div>
            <CleanerAction label={t("cleaner.help.dismiss")} onActivate={() => { writeFlag(HELP_DISMISSED_KEY, true); setHelpVisible(false); }} style={{ minHeight: 28, padding: "5px 8px", background: "transparent", boxShadow: "none", color: theme.color.accent }}>{t("cleaner.help.dismiss")}</CleanerAction>
          </div>}
          <div style={{ display: "flex", gap: 8 }}>
            <CleanerAction label={t(allShownCachesSelected ? "cleaner.deselectCaches" : "cleaner.selectCaches")} disabled={selectionDisabled || shownCaches.length === 0} onActivate={() => setSelected((value) => toggleCaches(shownEntries, value))} style={{ padding: "5px 3px", minHeight: 30, background: "transparent", boxShadow: "none", justifyContent: "flex-start", color: theme.color.textMuted }}><LuCheck size={15} style={{ flexShrink: 0 }} /><span>{t(allShownCachesSelected ? "cleaner.deselectCaches" : "cleaner.selectCaches")}</span></CleanerAction>
            {selected.size > 0 && <div style={{ width: 32, flexShrink: 0 }}><CleanerAction label={t("cleaner.clearSelection")} disabled={selectionDisabled} onActivate={() => setSelected(new Set())} style={{ padding: 6, minHeight: 30, background: "transparent", boxShadow: "none" }}><LuX size={15} /></CleanerAction></div>}
          </div>
          {shown.map((game) => <GameRow key={game.id} game={game} selected={selected} disabled={selectionDisabled} onCaches={() => setSelected((value) => toggleCaches(game.entries, value))} onEntry={(entry) => setSelected((value) => toggleEntry(entry, value))} />)}
          {shown.length === 0 && <div style={{ ...caption, padding: 12 }}>{t(games.length === 0 ? "cleaner.empty" : filter === "cleanable" && !query ? "cleaner.noCleanable" : filter === "not_installed" && !query ? "cleaner.noRecommendations" : "cleaner.noMatch")}</div>}
          {(plan || chosen.length > 0) && <CleanerActionTray>
            {plan ? <Focusable flow-children="column" onCancel={(event) => { event.stopPropagation(); controller.dismissPlan(); }} style={column}>
              <div style={{ fontSize: theme.font.body, fontWeight: 600 }}>{t("cleaner.confirm.title")}</div>
              <Notice warning>{t("cleaner.confirm.prefixWarning")}</Notice>
              <CleanerAction label={t("cleaner.confirm.delete")} danger disabled={busy} onActivate={() => void controller.execute(true)}><LuTrash2 size={16} /><span style={{ flex: 1, textAlign: "left" }}>{t("cleaner.confirm.delete")}</span><span style={{ whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>{formatBytes(plan.estimated_bytes, lang)}</span></CleanerAction>
              <CleanerAction label={t("cleaner.cancel")} disabled={busy} onActivate={controller.dismissPlan}>{t("cleaner.cancel")}</CleanerAction>
            </Focusable> : <CleanerAction label={t("cleaner.cleanSelection")} primary disabled={busy} onActivate={() => void controller.prepare(chosen.map((entry) => entry.id))}><span style={{ flex: 1, textAlign: "left" }}>{t("cleaner.cleanSelection")}</span><span style={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{formatBytes(chosenBytes, lang)}</span></CleanerAction>}
          </CleanerActionTray>}
        </>}
      </div>
    </PanelSectionRow>
  );
};
