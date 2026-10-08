import { ButtonItem, DialogButton, Focusable, ModalRoot, showModal } from "@decky/ui";
import { type CSSProperties, type ReactNode, useState } from "react";
import { LuFolderX, LuMonitor, LuRefreshCw, LuSend, LuShieldAlert, LuShieldCheck, LuSparkles, LuUndo2 } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import type { ThemeHealthFinding } from "../themes/themeHealth";
import { useThemeHealth, type ThemeHealthView } from "../themes/useThemeHealth";
import { useThemes, type ThemesController } from "../themes/useThemes";
import { FocusRoot } from "./FocusRoot";
import { openReportModal } from "./ReportModal";

const NAME_PREVIEW = 4;
const DISPLAY_FINDINGS = new Set<ThemeHealthFinding["id"]>(["steam_scale", "resolution", "external_display", "steam_beta"]);

// Third-party CSS Loader themes restyle Steam's dialogs too; the helper must stay legible under them.
const HEALTH_RESET = `
[data-pdc-theme-health] { color: ${theme.color.textPrimary} !important; }
[data-pdc-theme-health] [data-pdc-muted] { color: ${theme.color.textMuted} !important; }
[data-pdc-theme-health] [data-pdc-warn] { color: ${theme.color.warn} !important; }
`;

const ROW_STYLE: CSSProperties = {
  ...theme.card,
  display: "grid",
  gridTemplateColumns: "28px minmax(0, 1fr)",
  gap: theme.space.sm,
  padding: theme.space.md,
};

const PRIMARY_STYLE: CSSProperties = {
  minWidth: 150,
  borderRadius: theme.radius.sm,
  background: `linear-gradient(180deg, rgba(${theme.color.accentRgb},0.18), rgba(${theme.color.accentRgb},0.08))`,
  color: theme.color.textPrimary,
  fontWeight: 780,
  boxShadow: `inset 0 0 0 1px rgba(${theme.color.accentRgb},0.42)`,
};

const SECONDARY_STYLE: CSSProperties = {
  minWidth: 120,
  borderRadius: theme.radius.sm,
  background: "rgba(255,255,255,0.028)",
  color: theme.color.textMuted,
  boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
};

function problemCount(findings: readonly ThemeHealthFinding[]): number {
  return findings.filter((finding) => finding.severity !== "info").length;
}

function percent(value: number): string {
  return `${Math.round(value * 100)} %`;
}

function names(list: readonly string[]): string {
  const shown = list.slice(0, NAME_PREVIEW).join(", ");
  return list.length > NAME_PREVIEW ? `${shown} +${list.length - NAME_PREVIEW}` : shown;
}

function FindingRow({ finding }: { finding: ThemeHealthFinding }) {
  const { t } = useI18n();
  let icon: ReactNode = <LuShieldAlert size={18} />;
  let detail: string;
  switch (finding.id) {
    case "css_loader":
      detail = t(`themes.cssLoader.${finding.status}`);
      break;
    case "other_active":
    case "profile_active":
    case "several_hooandee":
      detail = names(finding.names);
      break;
    case "ghost_styles":
      detail = t("themes.health.ghost_styles.detail", { count: finding.count });
      break;
    case "set_aside":
      icon = <LuFolderX size={18} />;
      detail = names(finding.folders.map(({ folder, kind }) => `${folder} (${t(`themes.health.kind.${kind}`)})`));
      break;
    case "steam_scale":
      icon = <LuMonitor size={18} />;
      detail = t("themes.health.steam_scale.detail", { scale: percent(finding.scale), auto: percent(finding.autoScale) });
      break;
    case "resolution":
      icon = <LuMonitor size={18} />;
      detail = t("themes.health.resolution.detail", {
        drawn: `${finding.width}×${finding.height}`,
        panel: `${finding.panelWidth}×${finding.panelHeight}`,
      });
      break;
    default:
      icon = <LuMonitor size={18} />;
      detail = t(`themes.health.${finding.id}.detail`);
  }
  return (
    <div style={ROW_STYLE}>
      <span aria-hidden style={{ color: finding.severity === "info" ? theme.color.textMuted : theme.color.warn, paddingTop: 1 }}>{icon}</span>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 720 }}>{t(`themes.health.${finding.id}.title`)}</div>
        <div data-pdc-muted style={{ fontSize: theme.font.caption, lineHeight: 1.4, marginTop: 3, overflowWrap: "anywhere" }}>{detail}</div>
        {finding.severity === "setting" ? (
          <div data-pdc-muted style={{ fontSize: theme.font.caption, lineHeight: 1.4, marginTop: 3 }}>{t(`themes.health.${finding.id}.hint`)}</div>
        ) : null}
      </div>
    </div>
  );
}

function summaryKey(health: ThemeHealthView): string {
  if (health.checking && health.findings.length === 0) return "themes.health.summary.checking";
  if (health.unavailable) return "themes.health.summary.unavailable";
  return problemCount(health.findings) === 0 ? "themes.health.summary.clean" : "themes.health.summary.issues";
}

function HealthBody({ controller, health, closeModal }: { controller: ThemesController; health: ThemeHealthView; closeModal?: () => void }) {
  const { t } = useI18n();
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<"cleaned" | "restored" | "failed" | null>(null);
  const busy = health.checking || controller.operation !== null;
  const problems = health.findings.filter((finding) => !DISPLAY_FINDINGS.has(finding.id));
  const display = health.findings.filter((finding) => DISPLAY_FINDINGS.has(finding.id));
  const plan = health.plan;
  const cssReady = controller.snapshot.status === "ready";

  const runAction = async (action: () => Promise<boolean>, success: "cleaned" | "restored") => {
    setConfirming(false);
    setResult(null);
    setResult(await action() ? success : "failed");
  };

  return (
    <div data-pdc-theme-health style={{ display: "flex", flexDirection: "column", gap: theme.space.md, maxWidth: 640, margin: "0 auto", padding: "4px 8px 18px" }}>
      <style>{HEALTH_RESET}</style>
      <header style={{ display: "flex", alignItems: "center", gap: theme.space.md }}>
        <span aria-hidden style={{ color: problemCount(health.findings) ? theme.color.warn : theme.color.accent }}>
          {problemCount(health.findings) ? <LuShieldAlert size={26} /> : <LuShieldCheck size={26} />}
        </span>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 20, fontWeight: 780 }}>{t("themes.health.title")}</div>
          <div role="status" aria-live="polite" data-pdc-muted style={{ marginTop: 3 }}>
            {t(summaryKey(health), { count: problemCount(health.findings) })}
          </div>
        </div>
      </header>

      {result ? (
        <div role="status" data-pdc-warn={result === "failed" ? true : undefined} style={{ ...theme.card, padding: theme.space.md }}>
          {t(`themes.health.result.${result}`)}
          {result === "failed" && controller.errorCode ? (
            <div data-pdc-muted style={{ fontSize: theme.font.caption, marginTop: 4 }}>{t("themes.operation.code", { code: controller.errorCode })}</div>
          ) : null}
        </div>
      ) : null}

      {problems.length ? (
        <section style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
          <div style={theme.sectionLabel}>{t("themes.health.group.themes")}</div>
          {problems.map((finding) => <FindingRow key={finding.id} finding={finding} />)}
        </section>
      ) : null}

      {display.length ? (
        <section style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
          <div style={theme.sectionLabel}>{t("themes.health.group.display")}</div>
          {display.map((finding) => <FindingRow key={finding.id} finding={finding} />)}
        </section>
      ) : null}

      {confirming && plan ? (
        <div role="group" style={{ ...theme.card, padding: theme.space.md, boxShadow: `inset 0 0 0 1px rgba(${theme.color.accentRgb},0.35)` }}>
          <div style={{ fontWeight: 760 }}>{t("themes.health.confirm.title")}</div>
          <ul data-pdc-muted style={{ margin: "6px 0 0", paddingLeft: 18, lineHeight: 1.5 }}>
            {plan.disable.length ? <li>{t("themes.health.confirm.disable", { count: plan.disable.length })}</li> : null}
            {plan.setAside ? <li>{t("themes.health.confirm.setAside", { count: plan.setAside })}</li> : null}
            <li>{t("themes.health.confirm.reload")}</li>
            <li>{t("themes.health.confirm.undo")}</li>
          </ul>
          <Focusable style={{ display: "flex", justifyContent: "flex-end", gap: theme.space.sm, marginTop: theme.space.md }}>
            <DialogButton style={SECONDARY_STYLE} onClick={() => setConfirming(false)}>{t("themes.install.confirm.cancel")}</DialogButton>
            <DialogButton style={PRIMARY_STYLE} disabled={busy} onClick={() => void runAction(health.cleanUp, "cleaned")}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 7 }}><LuSparkles size={15} aria-hidden />{t("themes.health.clean.ok")}</span>
            </DialogButton>
          </Focusable>
        </div>
      ) : null}

      <Focusable style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        {health.needsCleanup && !confirming ? (
          <ButtonItem layout="below" disabled={busy || !cssReady} onClick={() => setConfirming(true)}>
            <LuSparkles size={14} aria-hidden /> {t(controller.operation?.kind === "cleaning" ? "themes.health.cleaning" : "themes.health.clean")}
          </ButtonItem>
        ) : null}
        {health.undo?.available ? (
          <ButtonItem layout="below" disabled={busy || !cssReady} description={t("themes.health.undo.desc", { moved: health.undo.moved, disabled: health.undo.disabled })} onClick={() => void runAction(health.undoCleanup, "restored")}>
            <LuUndo2 size={14} aria-hidden /> {t(controller.operation?.kind === "restoring" ? "themes.health.restoring" : "themes.health.undo")}
          </ButtonItem>
        ) : null}
        <ButtonItem layout="below" disabled={busy} onClick={() => { setResult(null); void controller.refresh().then(health.recheck); }}>
          <LuRefreshCw size={14} aria-hidden /> {t("themes.health.recheck")}
        </ButtonItem>
        <ButtonItem layout="below" description={t("themes.health.report.desc")} onClick={() => { closeModal?.(); openReportModal(["themes"]); }}>
          <LuSend size={14} aria-hidden /> {t("themes.health.report")}
        </ButtonItem>
      </Focusable>
    </div>
  );
}

function ThemeHealthModal({ closeModal }: { closeModal?: () => void }) {
  const controller = useThemes();
  const health = useThemeHealth(controller);
  return (
    <ModalRoot onCancel={closeModal} onEscKeypress={closeModal}>
      <FocusRoot>
        <HealthBody controller={controller} health={health} closeModal={closeModal} />
      </FocusRoot>
    </ModalRoot>
  );
}

export function openThemeHealthModal(onClosed?: () => void): void {
  showModal(<ThemeHealthModal />, window, { fnOnClose: onClosed });
}

export function ThemeHealthCard({ controller }: { controller: ThemesController }) {
  const { t } = useI18n();
  const health = useThemeHealth(controller);
  const count = problemCount(health.findings);
  return (
    <div style={{ ...theme.card, padding: theme.space.md }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, fontWeight: 750, color: theme.color.textPrimary }}>
        <span aria-hidden style={{ display: "flex", color: count ? theme.color.warn : theme.color.accent }}>
          {count ? <LuShieldAlert size={17} /> : <LuShieldCheck size={17} />}
        </span>
        {t("themes.health.title")}
      </div>
      <div role="status" aria-live="polite" style={{ color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.45, marginTop: theme.space.xs }}>
        {t(summaryKey(health), { count })}
      </div>
      <div style={{ marginTop: theme.space.sm }}>
        <ButtonItem layout="below" onClick={() => openThemeHealthModal(() => void controller.refresh().then(health.recheck))}>
          {t(count ? "themes.health.open.fix" : "themes.health.open")}
        </ButtonItem>
      </div>
    </div>
  );
}
