import { ButtonItem, DialogButton, Focusable, ModalRoot, showModal } from "@decky/ui";
import { type CSSProperties, type ReactNode, useState } from "react";
import { LuCheck, LuFolderX, LuMonitor, LuRefreshCw, LuSend, LuShieldAlert, LuShieldCheck, LuSparkles, LuUndo2 } from "react-icons/lu";

import { useI18n } from "../i18n";
import type { Params } from "../i18n/format";
import { theme } from "../theme";
import type { ThemeCleanupPlan, ThemeHealthFinding } from "../themes/themeHealth";
import { useThemeHealth, type ThemeHealthOutcome, type ThemeHealthView } from "../themes/useThemeHealth";
import { useThemes, type ThemesController } from "../themes/useThemes";
import { FocusRoot } from "./FocusRoot";
import { openReportModal } from "./ReportModal";

const NAME_PREVIEW = 4;

// Third-party CSS Loader themes restyle Steam's dialogs too; the helper must stay legible under them.
const HEALTH_RESET = `
[data-pdc-theme-health] { color: ${theme.color.textPrimary} !important; }
[data-pdc-theme-health] [data-pdc-muted] { color: ${theme.color.textMuted} !important; }
[data-pdc-theme-health] [data-pdc-warn] { color: ${theme.color.warn} !important; }
`;

const BUTTON_STYLE: CSSProperties = {
  flex: "1 1 0",
  minWidth: 0,
  borderRadius: theme.radius.sm,
  background: "rgba(255,255,255,0.028)",
  color: theme.color.textPrimary,
  boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
};

const PRIMARY_STYLE: CSSProperties = {
  ...BUTTON_STYLE,
  background: `linear-gradient(180deg, rgba(${theme.color.accentRgb},0.18), rgba(${theme.color.accentRgb},0.08))`,
  fontWeight: 780,
  boxShadow: `inset 0 0 0 1px rgba(${theme.color.accentRgb},0.42)`,
};

const CHOICE_STYLE: CSSProperties = { ...BUTTON_STYLE, width: "auto", flex: "1 1 0" };

const CHOICE_SELECTED_STYLE: CSSProperties = {
  ...CHOICE_STYLE,
  background: `rgba(${theme.color.accentRgb},0.16)`,
  boxShadow: `inset 0 0 0 1px rgba(${theme.color.accentRgb},0.6)`,
};

type ResultKey = "cleaned" | "cleanedWithoutLoader" | "cleanedPartial" | "restored" | "restoredPartial" | "failed";

function problemCount(findings: readonly ThemeHealthFinding[]): number {
  return findings.filter((finding) => finding.severity === "problem").length;
}

function percent(value: number): string {
  return `${Math.round(value * 100)} %`;
}

function names(list: readonly string[]): string {
  const shown = list.slice(0, NAME_PREVIEW).join(", ");
  return list.length > NAME_PREVIEW ? `${shown} +${list.length - NAME_PREVIEW}` : shown;
}

function IconLabel({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7 }}>{icon}{children}</span>;
}

function FindingRow({ finding }: { finding: ThemeHealthFinding }) {
  const { t } = useI18n();
  let icon: ReactNode = <LuShieldAlert size={16} />;
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
      icon = <LuFolderX size={16} />;
      detail = names(finding.folders.map(({ folder, kind }) => `${folder} (${t(`themes.health.kind.${kind}`)})`));
      break;
    case "steam_scale":
      icon = <LuMonitor size={16} />;
      detail = t("themes.health.steam_scale.detail", { scale: percent(finding.scale), auto: percent(finding.autoScale) });
      break;
    case "resolution":
      icon = <LuMonitor size={16} />;
      detail = t("themes.health.resolution.detail", {
        drawn: `${finding.width}×${finding.height}`,
        panel: `${finding.panelWidth}×${finding.panelHeight}`,
      });
      break;
    default:
      icon = <LuMonitor size={16} />;
      detail = t(`themes.health.${finding.id}.detail`);
  }
  return (
    <li style={{ display: "grid", gridTemplateColumns: "24px minmax(0, 1fr)", gap: theme.space.sm, padding: `${theme.space.sm}px 0` }}>
      <span aria-hidden style={{ color: finding.severity === "problem" ? theme.color.warn : theme.color.textMuted, paddingTop: 2 }}>{icon}</span>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 720 }}>{t(`themes.health.${finding.id}.title`)}</div>
        <div data-pdc-muted style={{ fontSize: theme.font.caption, lineHeight: 1.4, marginTop: 2, overflowWrap: "anywhere" }}>{detail}</div>
      </div>
    </li>
  );
}

function summaryKey(health: ThemeHealthView): string {
  if (health.checking && health.findings.length === 0) return "themes.health.summary.checking";
  if (health.unavailable) return "themes.health.summary.unavailable";
  if (problemCount(health.findings)) return "themes.health.summary.issues";
  return health.findings.some((finding) => finding.severity === "setting")
    ? "themes.health.summary.settings"
    : "themes.health.summary.clean";
}

function planSummary(t: (key: string, params?: Params) => string, plan: ThemeCleanupPlan, chosen: string | null): string {
  const themes = plan.disable.length + (chosen ? plan.chooseOne.length - 1 : 0);
  const count = (amount: number, one: string, many: string) =>
    amount === 0 ? null : amount === 1 ? t(one) : t(many, { count: amount });
  return [
    count(themes, "themes.health.confirm.themesOne", "themes.health.confirm.themesMany"),
    count(plan.setAside, "themes.health.confirm.foldersOne", "themes.health.confirm.foldersMany"),
    t("themes.health.confirm.nothingDeleted"),
  ].filter(Boolean).join(" ");
}

function HealthBody({ controller, health, closeModal }: { controller: ThemesController; health: ThemeHealthView; closeModal?: () => void }) {
  const { t } = useI18n();
  const [confirming, setConfirming] = useState(false);
  const [keepActive, setKeepActive] = useState<string | null>(null);
  const [result, setResult] = useState<ResultKey | null>(null);
  const busy = health.checking || controller.operation !== null;
  const plan = health.plan;
  const mustChoose = (plan?.chooseOne.length ?? 0) > 1;
  const chosen = mustChoose && plan?.chooseOne.some((option) => option.name === keepActive) ? keepActive : null;
  const cssReady = controller.snapshot.status === "ready";
  const cssLoaderGone = controller.snapshot.status === "missing" || controller.snapshot.status === "disabled";
  const canAct = cssReady || cssLoaderGone;
  const issues = problemCount(health.findings);

  const runAction = async (action: () => Promise<ThemeHealthOutcome>, done: ResultKey, partial: ResultKey) => {
    setConfirming(false);
    setResult(null);
    const outcome = await action();
    setResult(outcome === "done" ? done : outcome === "partial" ? partial : "failed");
  };

  return (
    <div data-pdc-theme-health style={{ display: "flex", flexDirection: "column", gap: theme.space.md, maxWidth: 640, margin: "0 auto", padding: "4px 8px 18px" }}>
      <style>{HEALTH_RESET}</style>
      <header style={{ display: "flex", alignItems: "center", gap: theme.space.md }}>
        <span aria-hidden style={{ color: issues ? theme.color.warn : theme.color.accent }}>
          {issues ? <LuShieldAlert size={26} /> : <LuShieldCheck size={26} />}
        </span>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 20, fontWeight: 780 }}>{t("themes.health.title")}</div>
          <div role="status" aria-live="polite" data-pdc-muted style={{ marginTop: 3 }}>
            {result ? (
              <span data-pdc-warn={result === "failed" ? true : undefined}>
                {t(`themes.health.result.${result}`)}
                {result === "failed" && controller.errorCode ? ` ${t("themes.operation.code", { code: controller.errorCode })}` : ""}
              </span>
            ) : t(summaryKey(health), { count: issues })}
          </div>
        </div>
      </header>

      {health.findings.length ? (
        <ul style={{ listStyle: "none", margin: 0, padding: 0, borderTop: `1px solid ${theme.color.hairline}`, borderBottom: `1px solid ${theme.color.hairline}` }}>
          {health.findings.map((finding) => <FindingRow key={finding.id} finding={finding} />)}
        </ul>
      ) : null}

      {confirming && plan ? (
        <div role="group" aria-label={t("themes.health.confirm.title")} style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
          {mustChoose ? (
            <>
              <div style={{ fontWeight: 720 }}>{t("themes.health.choose.title")}</div>
              <Focusable style={{ display: "flex", flexWrap: "wrap", gap: theme.space.sm }}>
                {plan.chooseOne.map((option) => {
                  const selected = option.name === chosen;
                  return (
                    <DialogButton key={option.name} style={selected ? CHOICE_SELECTED_STYLE : CHOICE_STYLE} onClick={() => setKeepActive(option.name)}>
                      <IconLabel icon={selected ? <LuCheck size={14} aria-hidden /> : null}>{option.label}</IconLabel>
                    </DialogButton>
                  );
                })}
              </Focusable>
            </>
          ) : null}
          <div data-pdc-muted style={{ fontSize: theme.font.caption, lineHeight: 1.45 }}>{planSummary(t, plan, chosen)}</div>
          <Focusable style={{ display: "flex", gap: theme.space.sm }}>
            <DialogButton style={BUTTON_STYLE} onClick={() => setConfirming(false)}>{t("themes.install.confirm.cancel")}</DialogButton>
            <DialogButton
              style={PRIMARY_STYLE}
              disabled={busy || (mustChoose && !chosen)}
              onClick={() => void runAction(() => health.cleanUp(chosen ?? undefined), cssLoaderGone ? "cleanedWithoutLoader" : "cleaned", "cleanedPartial")}
            >
              <IconLabel icon={<LuSparkles size={15} aria-hidden />}>{t("themes.health.clean.ok")}</IconLabel>
            </DialogButton>
          </Focusable>
        </div>
      ) : (
        <Focusable style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
          {health.needsCleanup ? (
            <DialogButton style={PRIMARY_STYLE} disabled={busy || !canAct} onClick={() => setConfirming(true)}>
              <IconLabel icon={<LuSparkles size={15} aria-hidden />}>
                {t(controller.operation?.kind === "cleaning" ? "themes.health.cleaning" : "themes.health.clean")}
              </IconLabel>
            </DialogButton>
          ) : null}
          {health.undo?.available ? (
            <DialogButton style={BUTTON_STYLE} disabled={busy || !canAct} onClick={() => void runAction(health.undoCleanup, "restored", "restoredPartial")}>
              <IconLabel icon={<LuUndo2 size={15} aria-hidden />}>
                {t(controller.operation?.kind === "restoring" ? "themes.health.restoring" : "themes.health.undo")}
              </IconLabel>
            </DialogButton>
          ) : null}
          <div style={{ display: "flex", gap: theme.space.sm }}>
            <DialogButton style={BUTTON_STYLE} disabled={busy} onClick={() => { setResult(null); void controller.refresh().then(health.recheck); }}>
              <IconLabel icon={<LuRefreshCw size={14} aria-hidden />}>{t("themes.health.recheck")}</IconLabel>
            </DialogButton>
            <DialogButton style={BUTTON_STYLE} onClick={() => { closeModal?.(); openReportModal(["themes"]); }}>
              <IconLabel icon={<LuSend size={14} aria-hidden />}>{t("themes.health.report")}</IconLabel>
            </DialogButton>
          </div>
        </Focusable>
      )}
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
    <ButtonItem
      layout="below"
      description={t(summaryKey(health), { count })}
      onClick={() => openThemeHealthModal(() => void controller.refresh().then(health.recheck))}
    >
      <IconLabel icon={<span aria-hidden style={{ display: "flex", color: count ? theme.color.warn : theme.color.accent }}>
        {count ? <LuShieldAlert size={15} /> : <LuShieldCheck size={15} />}
      </span>}>
        {t("themes.health.title")}
      </IconLabel>
    </ButtonItem>
  );
}
