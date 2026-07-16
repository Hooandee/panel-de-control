import { FC, ReactNode, useEffect, useState } from "react";
import { ModalRoot, showModal, Focusable } from "@decky/ui";
import {
  LuGamepad2, LuCheck, LuTriangleAlert, LuShieldCheck, LuChevronDown, LuChevronRight, LuStar, LuSparkles,
  LuGauge, LuLanguages, LuPlay, LuWrench, LuExpand, LuMonitor, LuImage, LuLibrary, LuTerminal,
} from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { Loading } from "./Loading";
import { LaunchRow } from "./LaunchRow";
import { LaunchPreview } from "./LaunchPreview";
import { GameEntry, readCompatTool } from "../launch/steamApi";
import { getDevice, getLaunchTools, LaunchTools } from "../api";
import { useLaunchEditor } from "../launch/useLaunchEditor";
import { CATALOG, SUBGROUP_ORDER, Pill, Section, frequentPills, recommendedPills, ownedTokens, pillVisible } from "../launch/catalog";
import { GpuGen, ProtonFamily, protonFamily } from "../launch/proton";

// Icon per sub-group heading so each group is scannable at a glance.
const SUBGROUP_ICONS: Record<string, ReactNode> = {
  "params.sub.perf": <LuGauge size={13} />,
  "params.sub.lang": <LuLanguages size={13} />,
  "params.sub.startup": <LuPlay size={13} />,
  "params.sub.proton": <LuWrench size={13} />,
  "params.sub.upscaling": <LuExpand size={13} />,
  "params.sub.display": <LuMonitor size={13} />,
  "params.sub.render": <LuImage size={13} />,
  "params.sub.dlls": <LuLibrary size={13} />,
  "params.sub.gameArgs": <LuTerminal size={13} />,
};

type Editor = ReturnType<typeof useLaunchEditor>;

const TOOLS_FALLBACK: LaunchTools = {
  lsfg: false, mangohud: false, gamemode: false, gamescope: false,
  distro: "other", locale_reliable: true,
};

const Heading: FC<{ icon?: ReactNode; children: ReactNode }> = ({ icon, children }) => (
  <div style={{ ...theme.sectionLabel, marginBottom: theme.space.sm, display: "flex", alignItems: "center", gap: 6 }}>
    {icon}
    {children}
  </div>
);

/** Lightweight collapsible for use inside the modal (no PanelSectionRow chrome). */
const Fold: FC<{ title: ReactNode; summary?: ReactNode; defaultOpen?: boolean; children: ReactNode }> = ({ title, summary, defaultOpen, children }) => {
  const [open, setOpen] = useState(!!defaultOpen);
  const Chevron = open ? LuChevronDown : LuChevronRight;
  return (
    <div>
      <Focusable
        style={{ display: "flex", alignItems: "center", gap: theme.space.sm, cursor: "pointer", padding: "9px 2px", borderTop: `1px solid ${theme.color.hairline}` }}
        onActivate={() => setOpen((o) => !o)}
        onClick={() => setOpen((o) => !o)}
      >
        <Chevron size={16} color={theme.color.textMuted} />
        <span style={{ flex: 1, fontSize: theme.font.body, color: theme.color.textPrimary }}>{title}</span>
        {!open && summary && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{summary}</span>}
      </Focusable>
      {open && <div style={{ marginTop: theme.space.sm }}>{children}</div>}
    </div>
  );
};

/** Rows for a subgroup within a section, filtered to the game's Proton family + GPU. */
const Subgroup: FC<{ section: Section; subgroup: string; ed: Editor; tools: LaunchTools; family: ProtonFamily; gpu: GpuGen }> = ({ section, subgroup, ed, tools, family, gpu }) => {
  const { t } = useI18n();
  const pills = CATALOG.filter((p) => p.section === section && p.subgroup === subgroup && pillVisible(p, family, gpu));
  if (pills.length === 0) return null;
  return (
    <div>
      <Heading icon={SUBGROUP_ICONS[subgroup]}>{t(subgroup)}</Heading>
      {pills.map((p) => (
        <LaunchRow
          key={p.id}
          pill={p}
          ed={ed}
          tools={tools}
          caveat={p.id === "langEs" && tools.locale_reliable === false ? t("params.caveat.locale") : undefined}
        />
      ))}
    </div>
  );
};

const LaunchEditorBody: FC<{ game: GameEntry }> = ({ game }) => {
  const { t } = useI18n();
  const ed = useLaunchEditor(game);
  const [tools, setTools] = useState<LaunchTools | null>(null);
  const [gpu, setGpu] = useState<GpuGen>("unknown");
  const [family, setFamily] = useState<ProtonFamily>("unknown");
  const [versionLabel, setVersionLabel] = useState("");

  useEffect(() => {
    let cancelled = false;
    getLaunchTools()
      .then((tt) => !cancelled && setTools(tt))
      .catch(() => !cancelled && setTools(TOOLS_FALLBACK));
    getDevice()
      .then((d) => !cancelled && setGpu((d.gpu_gen as GpuGen) || "unknown"))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // Read the game's Proton version once its app details are warm (after the editor
  // loads them). Empty/native → "unknown" family → only base pills show.
  useEffect(() => {
    if (ed.loading) return;
    const ct = readCompatTool(game.liveAppid);
    setFamily(protonFamily(ct.name));
    setVersionLabel(ct.display || ct.name);
  }, [ed.loading, game.liveAppid]);

  const advancedCount = CATALOG.filter((p) => p.section === "advanced" && !!ed.selections[p.id] && pillVisible(p, family, gpu)).length;
  const owned = ownedTokens(ed.selections);
  const frequents: Pill[] = tools ? frequentPills(ed.usage, tools).filter((p) => pillVisible(p, family, gpu)) : [];
  // No usage yet → offer a "Start here" set of safe recommended picks instead.
  const starters: Pill[] = tools && frequents.length === 0 ? recommendedPills(tools, family, gpu) : [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md, padding: theme.space.sm, maxWidth: 760, width: "100%", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
        <LuGamepad2 size={18} color={theme.color.accent} />
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: theme.font.value, color: theme.color.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{game.name}</div>
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {game.isNonSteam ? t("params.badge.nonSteam") : t("params.badge.steam")}
          </div>
        </div>
      </div>

      {ed.loading || tools === null ? (
        <Loading />
      ) : ed.malformed ? (
        <div>
          <div style={{ fontSize: theme.font.caption, color: theme.color.warn, display: "flex", gap: 6, alignItems: "flex-start", marginBottom: theme.space.sm }}>
            <LuTriangleAlert size={14} style={{ marginTop: 1, flexShrink: 0 }} />
            <span>{t("params.malformed")}</span>
          </div>
          <div style={{ ...theme.card, padding: theme.space.md, fontFamily: "monospace", fontSize: theme.font.caption, lineHeight: 1.7, wordBreak: "break-all", color: theme.color.textMuted }}>
            {ed.raw}
          </div>
        </div>
      ) : (
        <>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ fontSize: theme.font.caption, color: theme.color.ok, display: "flex", alignItems: "center", gap: 6 }}>
              <LuShieldCheck size={14} /> {t("params.reassure")}
            </div>
            {versionLabel && (
              <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
                {t("params.detectedProton", { name: versionLabel })}
              </div>
            )}
          </div>

          {frequents.length > 0 && (
            <div>
              <Heading icon={<LuStar size={13} />}>{t("params.frequent")}</Heading>
              {frequents.map((p) => (
                <LaunchRow key={`fav-${p.id}`} pill={p} ed={ed} tools={tools} />
              ))}
            </div>
          )}

          {starters.length > 0 && (
            <div>
              <Heading icon={<LuSparkles size={13} />}>{t("params.startHere")}</Heading>
              {starters.map((p) => (
                <LaunchRow key={`start-${p.id}`} pill={p} ed={ed} tools={tools} />
              ))}
            </div>
          )}

          {SUBGROUP_ORDER.common.map((sg) => (
            <Subgroup key={sg} section="common" subgroup={sg} ed={ed} tools={tools} family={family} gpu={gpu} />
          ))}

          <Fold title={t("params.advanced")} summary={advancedCount > 0 ? `${advancedCount}` : ""}>
            {SUBGROUP_ORDER.advanced.map((sg) => (
              <Subgroup key={sg} section="advanced" subgroup={sg} ed={ed} tools={tools} family={family} gpu={gpu} />
            ))}
          </Fold>

          <Fold title={t("params.showCommand")}>
            <LaunchPreview preview={ed.preview} owned={owned} />
          </Fold>

          {/* Autosave status — no manual button; changes apply on their own. */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, minHeight: 18, fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {ed.status === "saving" && <span>{t("params.saving")}</span>}
            {ed.status === "saved" && (
              <>
                <LuCheck size={14} color={theme.color.ok} />
                <span style={{ color: theme.color.ok }}>{t("params.saved")}</span>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
};

const LaunchEditorModal: FC<{ game: GameEntry; closeModal?: () => void }> = ({ game, closeModal }) => (
  <ModalRoot closeModal={closeModal} bAllowFullSize>
    <LaunchEditorBody game={game} />
  </ModalRoot>
);

/** Open the full-screen launch-options editor for a game. `onClosed` re-syncs the list. */
export function openLaunchEditorModal(game: GameEntry, onClosed: () => void): void {
  showModal(<LaunchEditorModal game={game} />, window, { fnOnClose: onClosed });
}
