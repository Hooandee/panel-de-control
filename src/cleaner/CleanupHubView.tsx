import { PanelSectionRow, Focusable } from "@decky/ui";
import { useState } from "react";
import type { FC, ReactNode } from "react";
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

// Inactive tabs stay mounted to keep their state; Steam would still walk into them
// unless their children are taken out of gamepad navigation.
const CleanupPanel: FC<{ hidden: boolean; children: ReactNode }> = ({ hidden, children }) => (
  <Focusable role="tabpanel" aria-hidden={hidden} {...({ childFocusDisabled: hidden } as object)} style={{ display: hidden ? "none" : "block" }}>
    {children}
  </Focusable>
);

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
    { tab: "games" as const, bytes: (games.state?.totals.shadercache ?? 0) + (games.state?.totals.compatdata ?? 0), loading: games.loading || games.pending === "scan", icon: LuGamepad2 },
    { tab: "media" as const, bytes: media.items.reduce((sum, item) => sum + (item.bytes ?? 0), 0), loading: media.loading, icon: LuImages },
    { tab: "proton" as const, bytes: proton.state?.totals.bytes ?? 0, loading: proton.loading || proton.pending === "scan", icon: LuAtom },
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
        <Focusable flow-children="grid" role="tablist" aria-label={t("cleaner.categories")} style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 7, marginTop: 12 }}>
          {summaries.map(({ tab: category, bytes, loading, icon: Icon }) => <CleanerButton key={category} role="tab" label={t(`cleaner.tab.${category}`)} selected={tab === category} onActivate={() => setTab(category)} style={{ ...theme.tile, minHeight: 58, padding: "9px 8px", alignItems: "stretch", justifyContent: "center", flexDirection: "column", gap: 4 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 5, ...cleanerCaption }}><Icon size={13} color={theme.color.accent} /><span>{t(`cleaner.tab.${category}`)}</span></div>
            <div style={{ fontSize: loading ? 12 : 14, fontWeight: 650, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", textAlign: "left" }}>{loading ? t("cleaner.calculating") : formatBytes(bytes, lang)}</div>
          </CleanerButton>)}
        </Focusable>
      </div>
      <CleanupPanel hidden={tab !== "games"}><SteamCleanerView controller={games} embedded /></CleanupPanel>
      <CleanupPanel hidden={tab !== "media"}><MediaCleanerView controller={media} /></CleanupPanel>
      <CleanupPanel hidden={tab !== "proton"}><ProtonCleanerView controller={proton} /></CleanupPanel>
    </div>
  </PanelSectionRow>;
};
