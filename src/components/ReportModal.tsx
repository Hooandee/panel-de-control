import { FC, useEffect, useState } from "react";
import { ModalRoot, showModal, Focusable, DialogButton, TextField } from "@decky/ui";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { getDevice, submitReport, DeviceInfo, ReportResult } from "../api";
import {
  REPORT_CATEGORIES,
  ReportCategory,
  canSubmit,
  toggleCategory,
} from "../report/logic";
import { FocusRoot } from "./FocusRoot";

type Phase = "form" | "sending" | "done" | "error";

// One selectable category row: a checkbox box + label, accent-outlined when on.
const CategoryChip: FC<{ label: string; on: boolean; onClick: () => void }> = ({
  label,
  on,
  onClick,
}) => (
  <Focusable
    onActivate={onClick}
    onClick={onClick}
    noFocusRing
    style={{
      display: "flex",
      alignItems: "center",
      gap: theme.space.sm,
      padding: `${theme.space.sm}px ${theme.space.md}px`,
      borderRadius: theme.radius.sm,
      boxShadow: `inset 0 0 0 1px ${on ? theme.color.accent : theme.color.hairline}`,
      background: on ? `rgba(${theme.color.accentRgb},0.12)` : "transparent",
      fontSize: theme.font.body,
      color: theme.color.textPrimary,
      flex: "1 1 45%",
      minWidth: 0,
    }}
  >
    <div
      style={{
        width: 18,
        height: 18,
        flex: "0 0 auto",
        borderRadius: 5,
        boxShadow: `inset 0 0 0 2px ${on ? theme.color.accent : theme.color.textMuted}`,
        background: on ? theme.color.accent : "transparent",
        color: theme.color.onAccent,
        fontSize: 12,
        lineHeight: "18px",
        textAlign: "center",
      }}
    >
      {on ? "✓" : ""}
    </div>
    <span>{label}</span>
  </Focusable>
);

const ReportBody: FC<{ closeModal?: () => void }> = ({ closeModal }) => {
  const { t } = useI18n();
  const [device, setDevice] = useState<DeviceInfo | null>(null);
  const [selected, setSelected] = useState<ReportCategory[]>([]);
  const [text, setText] = useState("");
  const [phase, setPhase] = useState<Phase>("form");
  const [result, setResult] = useState<ReportResult | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    getDevice().then(setDevice).catch(() => {});
  }, []);

  const submit = () => {
    setPhase("sending");
    submitReport(selected, text)
      .then((r) => {
        setResult(r);
        setPhase(r.ok ? "done" : "error");
      })
      .catch(() => {
        setResult({ ok: false, error: "network" });
        setPhase("error");
      });
  };

  const copy = () => {
    if (!result?.code) return;
    try {
      navigator.clipboard?.writeText(result.code);
      setCopied(true);
    } catch {
      /* clipboard may be unavailable in gamescope - ignore */
    }
  };

  const wrap = (children: React.ReactNode) => (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: theme.space.lg,
        padding: theme.space.sm,
        maxWidth: 720,
        width: "100%",
        margin: "0 auto",
      }}
    >
      {device && (
        <div style={{ fontSize: theme.font.value, color: theme.color.textPrimary }}>
          {device.display_name}
        </div>
      )}
      {children}
    </div>
  );

  if (phase === "sending") {
    return wrap(
      <div style={{ fontSize: theme.font.body, color: theme.color.textMuted }}>
        {t("report.sending")}
      </div>,
    );
  }

  if (phase === "done") {
    return wrap(
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md, alignItems: "center", textAlign: "center" }}>
        <div style={{ fontSize: 40 }}>✅</div>
        <div style={{ fontSize: theme.font.value, color: theme.color.textPrimary }}>
          {t("report.done.title")}
        </div>
        <div style={{ fontSize: theme.font.body, color: theme.color.textMuted }}>
          {t("report.done.thanks")}
        </div>
        <div style={{ ...theme.card, padding: theme.space.md, minWidth: 220 }}>
          <div style={theme.sectionLabel}>{t("report.code.label")}</div>
          <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: 2, color: theme.color.accent, fontFamily: "monospace" }}>
            {result?.code}
          </div>
        </div>
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, maxWidth: 340 }}>
          {t("report.code.hint")}
        </div>
        <Focusable style={{ display: "flex", gap: theme.space.sm }}>
          <DialogButton onClick={copy}>
            {copied ? t("report.copied") : t("report.copy")}
          </DialogButton>
          <DialogButton onClick={() => closeModal?.()}>{t("report.close")}</DialogButton>
        </Focusable>
      </div>,
    );
  }

  if (phase === "error") {
    return wrap(
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
        <div style={{ fontSize: theme.font.body, color: theme.color.danger }}>
          {t("report.error.title")}
        </div>
        {result?.saved_path && (
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {t("report.error.saved", { path: result.saved_path })}
          </div>
        )}
        <Focusable style={{ display: "flex", gap: theme.space.sm }}>
          <DialogButton onClick={submit}>{t("report.retry")}</DialogButton>
          <DialogButton onClick={() => closeModal?.()}>{t("report.close")}</DialogButton>
        </Focusable>
      </div>,
    );
  }

  // phase === "form"
  return wrap(
    <>
      <div style={{ fontSize: theme.font.body, color: theme.color.textMuted }}>
        {t("report.intro")}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <div style={theme.sectionLabel}>{t("report.section.what")}</div>
        {/* Each chip is its own Focusable, so the gamepad reaches them without a
            wrapping Focusable; a plain flex row keeps them wrapping. */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.sm }}>
          {REPORT_CATEGORIES.map((id) => (
            <CategoryChip
              key={id}
              label={t(`report.cat.${id}`)}
              on={selected.includes(id)}
              onClick={() => setSelected((s) => toggleCategory(s, id))}
            />
          ))}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <div style={theme.sectionLabel}>{t("report.section.describe")}</div>
        <TextField
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        {text.trim().length === 0 && (
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {t("report.describe.hint")}
          </div>
        )}
      </div>

      <div
        style={{
          ...theme.card,
          padding: theme.space.md,
          display: "flex",
          flexDirection: "column",
          gap: theme.space.xs,
          fontSize: theme.font.caption,
          color: theme.color.textMuted,
          lineHeight: 1.5,
        }}
      >
        <div style={theme.sectionLabel}>{t("report.privacy.title")}</div>
        <div><span style={{ color: theme.color.ok }}>●</span> {t("report.privacy.public")}</div>
        <div><span style={{ color: theme.color.warn }}>●</span> {t("report.privacy.private")}</div>
        <div><span style={{ color: theme.color.ok }}>✓</span> {t("report.privacy.nopii")}</div>
      </div>

      <Focusable>
        <DialogButton disabled={!canSubmit(selected, text)} onClick={submit}>
          {t("report.send")}
        </DialogButton>
      </Focusable>
    </>,
  );
};

const ReportModal: FC<{ closeModal?: () => void }> = ({ closeModal }) => (
  <ModalRoot closeModal={closeModal} bAllowFullSize>
    <FocusRoot>
      <ReportBody closeModal={closeModal} />
    </FocusRoot>
  </ModalRoot>
);

/** Open the full-screen "report a problem" flow. */
export function openReportModal(): void {
  showModal(<ReportModal />, window);
}
