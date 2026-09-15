import { Router } from "@decky/ui";
import { useEffect, useMemo, useState } from "react";
import type { FC } from "react";
import { LuCheck, LuExternalLink, LuFilter, LuShieldCheck, LuSquare, LuSquareCheck, LuTrash2, LuWandSparkles } from "react-icons/lu";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { CleanerActionTray } from "./CleanerActionTray";
import { CleanerButton, CleanerNotice, CleanerResult, cleanerCaption, cleanerColumn } from "./CleanerControls";
import { cleanerReasonKey } from "./errors";
import { formatBytes } from "./model";
import { readInstalledProtonMetadata } from "./steamMetadata";
import type { ProtonCleanerController } from "./useProtonCleaner";

type ProtonFilter = "all" | "recommended" | "selected";
const FILTERS: ProtonFilter[] = ["all", "recommended", "selected"];

export const ProtonCleanerView: FC<{ controller: ProtonCleanerController }> = ({ controller }) => {
  const { t, lang } = useI18n();
  const [selected, setSelected] = useState(new Set<string>());
  const [filter, setFilter] = useState<ProtonFilter>("all");
  const installed = useMemo(readInstalledProtonMetadata, []);
  const entries = controller.state?.entries ?? [];
  const shown = useMemo(() => entries.filter((entry) => filter === "all" || (filter === "recommended" ? entry.recommended : selected.has(entry.id))), [entries, filter, selected]);
  const chosen = entries.filter((entry) => selected.has(entry.id) && entry.selectable);

  useEffect(() => {
    const allowed = new Set(entries.filter((entry) => entry.selectable).map((entry) => entry.id));
    setSelected((previous) => {
      const next = new Set([...previous].filter((id) => allowed.has(id)));
      return next.size === previous.size ? previous : next;
    });
  }, [entries]);

  const recommended = shown.filter((entry) => entry.recommended && entry.selectable);
  const allRecommendedSelected = recommended.length > 0 && recommended.every((entry) => selected.has(entry.id));
  const chosenBytes = chosen.reduce((sum, entry) => sum + (entry.bytes ?? 0), 0);
  const error = controller.error || controller.state?.error;

  return <div style={cleanerColumn}>
    {error && <CleanerNotice warning>{t(cleanerReasonKey(error))}</CleanerNotice>}
    {controller.state?.scan_id && !controller.state.coverage_complete && <CleanerNotice warning>{t("cleaner.proton.coverageIncomplete")}</CleanerNotice>}
    {controller.result && <CleanerResult
      bytes={formatBytes(controller.result.estimated_bytes_removed, lang)}
      failed={controller.result.items.some((item) => item.status !== "deleted")}
      counts={t("cleaner.proton.result", {
        deleted: controller.result.items.filter((item) => item.status === "deleted").length,
        skipped: controller.result.items.filter((item) => item.status === "skipped").length,
        errors: controller.result.items.filter((item) => item.status === "error").length,
      })}
      onClose={controller.dismissResult}
    />}
    <CleanerButton label={t("cleaner.filterLabel")} onActivate={() => setFilter((value) => FILTERS[(FILTERS.indexOf(value) + 1) % FILTERS.length])} style={{ justifyContent: "flex-start" }}><LuFilter size={14} /><span>{t(`cleaner.proton.filter.${filter}`)}</span><span style={{ ...cleanerCaption, marginLeft: "auto" }}>{shown.length}</span></CleanerButton>
    {recommended.length > 0 && <CleanerButton label={t(allRecommendedSelected ? "cleaner.deselectRecommended" : "cleaner.selectRecommended")} onActivate={() => setSelected((previous) => {
      const next = new Set(previous);
      for (const entry of recommended) allRecommendedSelected ? next.delete(entry.id) : next.add(entry.id);
      return next;
    })} style={{ minHeight: 30, padding: "5px 3px", justifyContent: "flex-start", background: "transparent", boxShadow: "none", color: theme.color.textMuted }}><LuCheck size={15} />{t(allRecommendedSelected ? "cleaner.deselectRecommended" : "cleaner.selectRecommended")}</CleanerButton>}
    {(controller.loading || controller.pending === "scan") && entries.length === 0 && <div role="status" style={{ ...cleanerCaption, padding: 12 }}>{t("cleaner.proton.loading")}</div>}
    {(controller.loading || controller.pending === "scan") && entries.length === 0 && installed.map((entry) => <div key={entry.appid} style={{ ...theme.card, display: "flex", alignItems: "center", gap: 10, padding: 12 }}>
      <div style={{ width: 38, height: 38, flexShrink: 0, display: "grid", placeItems: "center", borderRadius: theme.radius.sm, background: `${theme.color.textMuted}18` }}><LuShieldCheck size={19} /></div>
      <span style={{ flex: 1, minWidth: 0 }}><span style={{ display: "block", fontWeight: 600 }}>{entry.name}</span><span style={{ ...cleanerCaption, display: "block" }}>{t("cleaner.proton.status.managed_by_steam")}</span></span>
      <span style={{ ...cleanerCaption, color: theme.color.textPrimary, whiteSpace: "nowrap" }}>{t("cleaner.calculating")}</span>
    </div>)}
    {shown.map((entry) => {
      const checked = selected.has(entry.id);
      const Check = entry.selectable ? (checked ? LuSquareCheck : LuSquare) : LuShieldCheck;
      return <div key={entry.id} style={{ ...theme.card, padding: 6 }}>
        <CleanerButton label={t("cleaner.proton.select", { name: entry.name })} checked={entry.selectable ? checked : undefined} disabled={controller.busy || !entry.selectable} onActivate={() => setSelected((previous) => {
          const next = new Set(previous);
          if (next.has(entry.id)) next.delete(entry.id); else next.add(entry.id);
          return next;
        })} style={{ justifyContent: "flex-start", textAlign: "left", padding: 8, background: checked ? `${theme.color.accent}14` : "transparent", boxShadow: "none" }}>
          <div style={{ width: 38, height: 38, flexShrink: 0, display: "grid", placeItems: "center", borderRadius: theme.radius.sm, background: entry.source === "steam" ? `${theme.color.textMuted}18` : `${theme.color.accent}18` }}>
            {entry.source === "steam" ? <LuShieldCheck size={19} /> : <LuWandSparkles size={19} color={theme.color.accent} />}
          </div>
          <span style={{ flex: 1, minWidth: 0 }}>
            <span style={{ display: "block", fontWeight: 600 }}>{entry.name}</span>
            <span style={{ ...cleanerCaption, display: "block" }}>{t(`cleaner.proton.status.${entry.status}`)}</span>
            {entry.recommended && <span style={{ ...cleanerCaption, display: "block", color: theme.color.accent }}>{t("cleaner.recommended")} · {t("cleaner.recommendation.unused_proton")}</span>}
            {entry.reason && !entry.recommended && <span style={{ ...cleanerCaption, display: "block" }}>{t(cleanerReasonKey(entry.reason))}</span>}
          </span>
          <span style={{ ...cleanerCaption, color: theme.color.textPrimary, whiteSpace: "nowrap" }}>{entry.bytes === null ? t("cleaner.sizeUnknown") : formatBytes(entry.bytes, lang)}</span>
          <Check size={18} color={checked ? theme.color.accent : theme.color.textMuted} />
        </CleanerButton>
        {entry.source === "steam" && entry.appid && <CleanerButton label={t("cleaner.proton.manageSteam")} onActivate={() => Router?.Navigate?.(`/library/app/${entry.appid}`)} style={{ minHeight: 30, padding: "5px 8px", justifyContent: "flex-start", background: "transparent", boxShadow: "none", color: theme.color.textMuted }}><LuExternalLink size={14} />{t("cleaner.proton.manageSteam")}</CleanerButton>}
      </div>;
    })}
    {!controller.loading && !controller.busy && shown.length === 0 && <div style={{ ...cleanerCaption, padding: 12 }}>{t(entries.length ? "cleaner.proton.noMatch" : "cleaner.proton.empty")}</div>}
    {chosen.length > 0 && <CleanerActionTray><CleanerButton label={t("cleaner.proton.clean")} primary disabled={controller.busy} onActivate={() => void controller.clean(chosen.map((entry) => entry.id))}><LuTrash2 size={16} /><span style={{ flex: 1, textAlign: "left" }}>{t("cleaner.proton.clean")}</span><span>{formatBytes(chosenBytes, lang)}</span></CleanerButton></CleanerActionTray>}
  </div>;
};
