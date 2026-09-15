import { PanelSectionRow } from "@decky/ui";
import { useState } from "react";
import type { FC } from "react";
import { LuAtom, LuGamepad2, LuImages, LuRefreshCw } from "react-icons/lu";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { CleanerButton, cleanerCaption, cleanerColumn } from "./CleanerControls";
import { formatBytes } from "./model";
import { MediaCleanerView } from "./MediaCleanerView";
import { ProtonCleanerView } from "./ProtonCleanerView";
import { SteamCleanerView } from "./SteamCleanerView";
import type { CleanerController } from "./useSteamCleaner";
import type { MediaCleanerController } from "./useMediaCleaner";
import type { ProtonCleanerController } from "./useProtonCleaner";

type CleanupTab = "games" | "media" | "proton";

export const CleanupHubView: FC<{
  games: CleanerController;
  media: MediaCleanerController;
  proton: ProtonCleanerController;
  onRefresh: () => void;
  refreshing: boolean;
}> = ({ games, media, proton, onRefresh, refreshing }) => {
  const { t, lang } = useI18n();
  const [tab, setTab] = useState<CleanupTab>("games");
  const summaries = [
    { tab: "games" as const, bytes: (games.state?.totals.shadercache ?? 0) + (games.state?.totals.compatdata ?? 0), loading: games.loading || games.pending === "scan", unknown: (games.state?.totals.unknown ?? 0) > 0 || games.state?.coverage_complete === false, icon: LuGamepad2 },
    { tab: "media" as const, bytes: media.items.reduce((sum, item) => sum + (item.bytes ?? 0), 0), loading: media.loading, unknown: media.error !== null || media.items.some((item) => item.bytes === null), icon: LuImages },
    { tab: "proton" as const, bytes: proton.state?.totals.bytes ?? 0, loading: proton.loading || proton.pending === "scan", unknown: (proton.state?.totals.unknown ?? 0) > 0 || proton.state?.coverage_complete === false, icon: LuAtom },
  ];

  return <PanelSectionRow>
    <div style={cleanerColumn}>
      <div style={{ ...theme.card, padding: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 15, fontWeight: 650 }}>{t("cleaner.title")}</div>
            <div style={cleanerCaption}>{t("cleaner.subtitle")}</div>
          </div>
          <div style={{ width: 34 }}><CleanerButton label={t("cleaner.scanAgain")} disabled={refreshing} onActivate={onRefresh} style={{ minHeight: 32, padding: 7, background: "transparent", boxShadow: "none" }}><LuRefreshCw size={15} /></CleanerButton></div>
        </div>
        <div role="tablist" aria-label={t("cleaner.categories")} style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 7, marginTop: 12 }}>
          {summaries.map(({ tab: category, bytes, loading, unknown = false, icon: Icon }) => <CleanerButton key={category} role="tab" label={t(`cleaner.tab.${category}`)} selected={tab === category} onActivate={() => setTab(category)} style={{ ...theme.tile, minHeight: 58, padding: "9px 8px", alignItems: "stretch", justifyContent: "center", flexDirection: "column", gap: 4 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 5, ...cleanerCaption }}><Icon size={13} color={theme.color.accent} /><span>{t(`cleaner.tab.${category}`)}</span></div>
            <div style={{ fontSize: loading || unknown ? 12 : 14, fontWeight: 650, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", textAlign: "left" }}>{loading ? t("cleaner.calculating") : unknown ? t("cleaner.sizeUnknown") : formatBytes(bytes, lang)}</div>
          </CleanerButton>)}
        </div>
      </div>
      <div role="tabpanel" aria-hidden={tab !== "games"} style={{ display: tab === "games" ? "block" : "none" }}><SteamCleanerView controller={games} embedded /></div>
      <div role="tabpanel" aria-hidden={tab !== "media"} style={{ display: tab === "media" ? "block" : "none" }}><MediaCleanerView controller={media} /></div>
      <div role="tabpanel" aria-hidden={tab !== "proton"} style={{ display: tab === "proton" ? "block" : "none" }}><ProtonCleanerView controller={proton} /></div>
    </div>
  </PanelSectionRow>;
};
