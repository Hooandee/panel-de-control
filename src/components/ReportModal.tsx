import { FC, ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  ModalRoot,
  showModal,
  Focusable,
  DialogButton,
  TextField,
  getFocusNavController,
} from "@decky/ui";
import { LuBug, LuLightbulb } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { getDevice, submitReport, DeviceInfo, ReportResult } from "../api";
import {
  REPORT_CATEGORIES,
  ReportCategory,
  ReportKind,
  buildReportContext,
  canSubmit,
  toggleCategory,
} from "../report/logic";
import { steamOverlay } from "../mangohud/steamOverlay";
import { FocusRoot } from "./FocusRoot";
import { launchReportContext } from "../launch/reportContext";
import { quickAccessTabDiagnostics } from "../deckyInternal";
import { getQamDocument } from "../qamDocument";

type Phase = "form" | "sending" | "done" | "error";

const ReportKindCard: FC<{
  label: string;
  icon: ReactNode;
  selected: boolean;
  color: string;
  tint: string;
  preferredFocus?: boolean;
  onSelect: () => void;
}> = ({ label, icon, selected, color, tint, preferredFocus, onSelect }) => {
  const [focused, setFocused] = useState(false);
  return (
    <Focusable
      role="radio"
      aria-checked={selected}
      {...(preferredFocus ? { preferredFocus: true } : {})}
      onActivate={onSelect}
      onClick={onSelect}
      onGamepadFocus={() => setFocused(true)}
      onGamepadBlur={() => setFocused(false)}
      noFocusRing
      style={{
        ...theme.card,
        flex: "1 1 0",
        minWidth: 0,
        minHeight: 150,
        padding: theme.space.lg,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: theme.space.md,
        textAlign: "center",
        color: theme.color.textPrimary,
        background: focused || selected ? tint : theme.color.surfaceRaised,
        boxShadow: `inset 0 0 0 ${focused ? 2 : 1}px ${focused || selected ? color : theme.color.hairline}`,
      }}
    >
      <div
        aria-hidden="true"
        style={{
          width: 56,
          height: 56,
          borderRadius: theme.radius.md,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color,
          background: tint,
          boxShadow: `inset 0 0 0 1px ${color}55`,
        }}
      >
        {icon}
      </div>
      <span style={{ fontSize: 20, fontWeight: 700, lineHeight: 1.15 }}>{label}</span>
    </Focusable>
  );
};

const SelectionChip: FC<{
  label: string;
  on: boolean;
  onClick: () => void;
}> = ({
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
      aria-hidden="true"
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
  const [kind, setKind] = useState<ReportKind | null>(null);
  const [choosingKind, setChoosingKind] = useState(true);
  const [selected, setSelected] = useState<ReportCategory[]>([]);
  const [text, setText] = useState("");
  const [phase, setPhase] = useState<Phase>("form");
  const [result, setResult] = useState<ReportResult | null>(null);
  const [copied, setCopied] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getDevice().then(setDevice).catch(() => {});
  }, []);

  const submit = async () => {
    if (kind === null) return;
    setPhase("sending");
    const launchContext = selected.includes("launch")
      ? await launchReportContext().catch(() => ({}))
      : {};
    const steamDisplay =
      typeof SteamClient === "undefined" ? undefined : SteamClient?.System?.Display;
    const context = buildReportContext(
      selected,
      steamDisplay,
      launchContext,
      quickAccessTabDiagnostics(window, getQamDocument()),
      kind,
      selected.includes("hud") ? steamOverlay.diagnostics() : undefined,
    );
    submitReport(selected, text, context)
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
    } catch {}
  };

  const wrap = (children: React.ReactNode) => (
    <div
      ref={rootRef}
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
  const copyKey = (key: string) => kind === "feature" ? `${key}.feature` : key;
  const chooseKind = (next: ReportKind) => {
    setKind(next);
    setChoosingKind(false);
  };

  useLayoutEffect(() => {
    if (!choosingKind || kind === null) return;
    const target = rootRef.current?.querySelector<HTMLElement>(
      '[role="radio"][aria-checked="true"]',
    );
    if (!target) return;
    try {
      const controller = getFocusNavController();
      if (typeof controller?.FocusElement === "function") {
        controller.FocusElement(target);
        return;
      }
    } catch {}
    target.focus({ preventScroll: true });
  }, [choosingKind, kind]);

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
          {t(copyKey("report.done.thanks"))}
        </div>
        <div style={{ ...theme.card, padding: theme.space.md, minWidth: 220 }}>
          <div style={theme.sectionLabel}>{t("report.code.label")}</div>
          <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: 2, color: theme.color.accent, fontFamily: "monospace" }}>
            {result?.code}
          </div>
        </div>
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, maxWidth: 340 }}>
          {t(copyKey("report.code.hint"))}
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

  if (choosingKind || kind === null) {
    return wrap(
      <>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: theme.font.value, fontWeight: 700, color: theme.color.textPrimary }}>
            {t("report.title")}
          </div>
          <div style={{ marginTop: theme.space.xs, fontSize: theme.font.body, color: theme.color.textMuted }}>
            {t("report.section.kind")}
          </div>
        </div>
        <Focusable
          role="radiogroup"
          aria-label={t("report.section.kind")}
          flow-children="row"
          noFocusRing
          style={{ display: "flex", gap: theme.space.md, width: "100%" }}
        >
          <ReportKindCard
            label={t("report.kind.bug")}
            icon={<LuBug size={36} />}
            selected={kind === "bug"}
            color={theme.color.danger}
            tint="rgba(224,90,90,0.12)"
            preferredFocus={kind === null}
            onSelect={() => chooseKind("bug")}
          />
          <ReportKindCard
            label={t("report.kind.feature")}
            icon={<LuLightbulb size={36} />}
            selected={kind === "feature"}
            color={theme.color.accent}
            tint={`rgba(${theme.color.accentRgb},0.12)`}
            onSelect={() => chooseKind("feature")}
          />
        </Focusable>
      </>,
    );
  }

  return wrap(
    <>
      <div
        style={{
          ...theme.card,
          padding: `${theme.space.sm}px ${theme.space.md}px`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: theme.space.md,
        }}
      >
        <div style={{ display: "flex", flex: "1 1 auto", minWidth: 0, alignItems: "center", gap: theme.space.sm, color: theme.color.textPrimary }}>
          {kind === "bug"
            ? <LuBug size={22} color={theme.color.danger} aria-hidden="true" />
            : <LuLightbulb size={22} color={theme.color.accent} aria-hidden="true" />}
          <span style={{ fontSize: theme.font.body, fontWeight: 700 }}>{t(`report.kind.${kind}`)}</span>
        </div>
        <DialogButton
          style={{ width: 112, minWidth: 112, flex: "0 0 auto" }}
          onClick={() => setChoosingKind(true)}
        >
          {t("report.kind.change")}
        </DialogButton>
      </div>

      <div style={{ fontSize: theme.font.body, color: theme.color.textMuted }}>
        {t(copyKey("report.intro"))}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <div style={theme.sectionLabel}>{t(copyKey("report.section.what"))}</div>
        {/* Each chip is its own Focusable, so the gamepad reaches them without a
            wrapping Focusable; a plain flex row keeps them wrapping. */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.sm }}>
          {REPORT_CATEGORIES.map((id) => (
            <SelectionChip
              key={id}
              label={t(`report.cat.${id}`)}
              on={selected.includes(id)}
              onClick={() => setSelected((s) => toggleCategory(s, id))}
            />
          ))}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <div style={theme.sectionLabel}>{t(copyKey("report.section.describe"))}</div>
        <TextField
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        {text.trim().length === 0 && (
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {t(copyKey("report.describe.hint"))}
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

export function openReportModal(): void {
  showModal(<ReportModal />, window);
}
