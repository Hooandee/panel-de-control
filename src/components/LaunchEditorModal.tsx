import { FC, ReactNode, useEffect, useState } from "react";
import { ModalRoot, showModal, Focusable } from "@decky/ui";
import { LuGamepad2, LuCheck, LuTriangleAlert, LuShieldCheck, LuChevronDown, LuChevronRight, LuStar } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { Loading } from "./Loading";
import { LaunchRow } from "./LaunchRow";
import { LaunchPreview } from "./LaunchPreview";
import { GameEntry } from "../launch/steamApi";
import { getLaunchTools, LaunchTools } from "../api";
import { useLaunchEditor } from "../launch/useLaunchEditor";
import { CATALOG, SUBGROUP_ORDER, Pill, Section, frequentPills, ownedTokens } from "../launch/catalog";

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

/** Rows for a subgroup within a section. */
const Subgroup: FC<{ section: Section; subgroup: string; ed: Editor; tools: LaunchTools }> = ({ section, subgroup, ed, tools }) => {
  const { t } = useI18n();
  const pills = CATALOG.filter((p) => p.section === section && p.subgroup === subgroup);
  if (pills.length === 0) return null;
  return (
    <div>
      <Heading>{t(subgroup)}</Heading>
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

  useEffect(() => {
    let cancelled = false;
    getLaunchTools()
      .then((tt) => !cancelled && setTools(tt))
      .catch(() => !cancelled && setTools(TOOLS_FALLBACK));
    return () => {
      cancelled = true;
    };
  }, []);

  const advancedCount = CATALOG.filter((p) => p.section === "advanced" && !!ed.selections[p.id]).length;
  const owned = ownedTokens(ed.selections);
  const frequents: Pill[] = tools ? frequentPills(ed.usage, tools) : [];

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
          <div style={{ fontSize: theme.font.caption, color: theme.color.ok, display: "flex", alignItems: "center", gap: 6 }}>
            <LuShieldCheck size={14} /> {t("params.reassure")}
          </div>

          {frequents.length > 0 && (
            <div>
              <Heading icon={<LuStar size={13} />}>{t("params.frequent")}</Heading>
              {frequents.map((p) => (
                <LaunchRow key={`fav-${p.id}`} pill={p} ed={ed} tools={tools} />
              ))}
            </div>
          )}

          {SUBGROUP_ORDER.common.map((sg) => (
            <Subgroup key={sg} section="common" subgroup={sg} ed={ed} tools={tools} />
          ))}

          <Fold title={t("params.advanced")} summary={advancedCount > 0 ? `${advancedCount}` : ""}>
            {SUBGROUP_ORDER.advanced.map((sg) => (
              <Subgroup key={sg} section="advanced" subgroup={sg} ed={ed} tools={tools} />
            ))}
          </Fold>

          <Fold title={t("params.showCommand")}>
            <LaunchPreview preview={ed.preview} owned={owned} />
          </Fold>

          <Focusable
            style={{
              display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.sm,
              padding: "10px 12px", borderRadius: theme.radius.sm,
              background: ed.dirty ? theme.color.accent : theme.color.surfaceRaised,
              boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
              color: ed.dirty ? theme.color.onAccent : theme.color.textMuted,
              fontSize: theme.font.body, fontWeight: 600,
              cursor: ed.dirty ? "pointer" : "default",
              opacity: ed.dirty || ed.result === "ok" ? 1 : 0.6,
            }}
            onActivate={() => ed.dirty && ed.apply()}
            onClick={() => ed.dirty && ed.apply()}
          >
            <LuCheck size={16} />
            {ed.result === "ok" && !ed.dirty ? t("params.applied") : t("params.apply")}
          </Focusable>
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
