import { FC, ReactNode, useEffect, useState } from "react";
import { ModalRoot, showModal, Focusable } from "@decky/ui";
import { LuGamepad2, LuCheck, LuTriangleAlert, LuWrench } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { Loading } from "./Loading";
import { Collapsible } from "./Collapsible";
import { TogglePill, ValuePills } from "./LaunchPills";
import { LaunchPreview } from "./LaunchPreview";
import { GameEntry } from "../launch/steamApi";
import { getLaunchTools, LaunchTools } from "../api";
import { useLaunchEditor, LaunchEditor } from "../launch/useLaunchEditor";
import { CATALOG, GROUP_ORDER, Pill, PillGroup, isPillAvailable, ownedTokens } from "../launch/catalog";

// If tool detection can't be read, assume tools absent (pills that need one show
// disabled) rather than claim they're present.
const TOOLS_FALLBACK: LaunchTools = {
  lsfg: false, mangohud: false, gamemode: false, gamescope: false,
  distro: "other", locale_reliable: true,
};

const GroupLabel: FC<{ children: ReactNode }> = ({ children }) => (
  <div style={{ ...theme.sectionLabel, marginBottom: theme.space.sm }}>{children}</div>
);

/** Render one pill: a value pill becomes a chip row, everything else a toggle. */
function renderPill(pill: Pill, ed: LaunchEditor, tools: LaunchTools, t: (k: string) => string, showValueLabel: boolean) {
  if (pill.options) {
    return (
      <div key={pill.id} style={{ marginBottom: theme.space.sm }}>
        {showValueLabel && (
          <div style={{ fontSize: theme.font.body, color: theme.color.textPrimary, marginBottom: theme.space.xs }}>
            {t(pill.labelKey)}
          </div>
        )}
        <ValuePills
          offLabel={t("params.off")}
          options={pill.options.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
          current={(ed.selections[pill.id] as string | undefined) ?? null}
          onSelect={(v) => ed.set(pill.id, v)}
        />
      </div>
    );
  }
  const available = isPillAvailable(pill, tools);
  return (
    <TogglePill
      key={pill.id}
      label={t(pill.labelKey)}
      active={!!ed.selections[pill.id]}
      disabled={!available}
      disabledNote={t("params.notDetected")}
      onToggle={() => ed.set(pill.id, !ed.selections[pill.id])}
    />
  );
}

/** A group's pills: toggles wrapped in one flex row, value pills as their own blocks. */
const GroupBody: FC<{ group: PillGroup; ed: LaunchEditor; tools: LaunchTools }> = ({ group, ed, tools }) => {
  const { t } = useI18n();
  const pills = CATALOG.filter((p) => p.group === group);
  const toggles = pills.filter((p) => !p.options);
  const values = pills.filter((p) => p.options);
  const showValueLabel = toggles.length > 0 || values.length > 1;
  const localeCaveat = group === "langStart" && tools.locale_reliable === false;
  return (
    <>
      {toggles.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.sm, marginBottom: values.length ? theme.space.md : 0 }}>
          {toggles.map((p) => renderPill(p, ed, tools, t, showValueLabel))}
        </div>
      )}
      {values.map((p) => renderPill(p, ed, tools, t, showValueLabel))}
      {localeCaveat && (
        <div style={{ fontSize: theme.font.caption, color: theme.color.warn, display: "flex", gap: 6, alignItems: "flex-start", marginTop: theme.space.xs }}>
          <LuTriangleAlert size={13} style={{ marginTop: 1, flexShrink: 0 }} />
          <span>{t("params.caveat.locale")}</span>
        </div>
      )}
    </>
  );
};

const LaunchEditorBody: FC<{ game: GameEntry }> = ({ game }) => {
  const { t } = useI18n();
  const ed = useLaunchEditor(game);
  const [tools, setTools] = useState<LaunchTools | null>(null);

  // Detect host tools once for this editor. Until it resolves we show a spinner
  // rather than flash "not detected" on pills whose tool is actually installed.
  useEffect(() => {
    let cancelled = false;
    getLaunchTools()
      .then((tt) => !cancelled && setTools(tt))
      .catch(() => !cancelled && setTools(TOOLS_FALLBACK));
    return () => {
      cancelled = true;
    };
  }, []);

  const advancedCount = CATALOG.filter((p) => p.advanced && !!ed.selections[p.id]).length;
  const owned = ownedTokens(ed.selections);

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
          {GROUP_ORDER.filter((g) => g !== "advanced").map((g) => (
            <div key={g}>
              <GroupLabel>{t(`params.group.${g}`)}</GroupLabel>
              <GroupBody group={g} ed={ed} tools={tools} />
            </div>
          ))}

          <Collapsible
            id="params-advanced"
            icon={<LuWrench size={15} />}
            title={t("params.group.advanced")}
            summary={advancedCount > 0 ? `${advancedCount}` : ""}
          >
            <GroupBody group="advanced" ed={ed} tools={tools} />
          </Collapsible>

          <LaunchPreview preview={ed.preview} owned={owned} />

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
