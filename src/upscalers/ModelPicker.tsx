import { Focusable } from "@decky/ui";
import { useEffect, useRef, useState } from "react";
import { LuCheck, LuChevronDown, LuChevronUp } from "react-icons/lu";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { createThemeNavigationAccess } from "../themes/runtime/navigationAccess";
import { buildBlocker, buildLabel } from "./model";
import type { BuildInfo, UpscalerChoice } from "./types";

const navigation = createThemeNavigationAccess({ allowInactiveContext: true });
const cellStyle = { minWidth: 0, overflowWrap: "anywhere" as const };
const gridStyle = { display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 8, minWidth: 0 };

export function ModelPicker({ builds, choice, inputs, protonEnv, disabled, onChange }: {
  builds: BuildInfo[];
  choice: UpscalerChoice;
  inputs: Record<string, unknown>;
  protonEnv: string | null;
  disabled?: boolean;
  onChange: (choice: UpscalerChoice) => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLDivElement>(null);
  const selectedOption = useRef<HTMLDivElement>(null);
  const restoreFocus = useRef(false);
  useEffect(() => {
    if (!open && !restoreFocus.current) return;
    const target = open ? selectedOption.current : trigger.current;
    restoreFocus.current = false;
    const timer = window.setTimeout(() => {
      if (target?.isConnected) navigation.focus(target);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [open]);
  const close = () => {
    restoreFocus.current = true;
    setOpen(false);
  };
  const current = builds.find((build) => build.id === choice.build);
  const toggle = () => { if (!disabled) { if (open) close(); else setOpen(true); } };
  const modelLabel = (model: string | null) => {
    if (!model) return t("up.models.default");
    const translated = t(`up.model.${model}`);
    return translated === `up.model.${model}` ? model : translated;
  };
  return <Focusable flow-children="column" style={{ ...theme.card, padding: theme.space.sm, fontSize: theme.font.body, lineHeight: 1.35, minWidth: 0, overflowWrap: "anywhere" }}>
    <Focusable ref={trigger} role="button" aria-label={t("up.models.title")} aria-expanded={open} aria-disabled={disabled}
      onClick={toggle} onActivate={toggle} onCancel={open ? (event) => { event.stopPropagation(); close(); } : undefined}
      style={{ padding: theme.space.sm, cursor: "pointer", fontWeight: 600, display: "flex", alignItems: "center", gap: theme.space.sm }}>
      <span style={{ display: "flex", flexDirection: "column", flex: 1, minWidth: 0 }}>
        <span>{current ? buildLabel(current) : choice.build}</span>
        <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{modelLabel(choice.model ?? current?.models?.[0] ?? null)}</span>
      </span>
      {open ? <LuChevronUp size={16} /> : <LuChevronDown size={16} />}
    </Focusable>
    {open && <Focusable flow-children="column" onCancel={(event) => { event.stopPropagation(); close(); }} style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("up.models.hint")}</div>
      <div role="table" aria-label={t("up.models.title")} style={{ fontSize: theme.font.caption, lineHeight: 1.35, minWidth: 0, overflowWrap: "anywhere" }}>
        <div role="row" style={gridStyle}>
          {["family", "version", "model"].map((column) => <span role="columnheader" key={column} style={cellStyle}>{t(`up.models.${column}`)}</span>)}
        </div>
        {builds.map((build, buildIndex) => {
          const blocker = buildBlocker(build, inputs, protonEnv);
          const reason = !build.available ? t("up.models.unavailable") : !build.supported ? t("up.models.unsupported") : blocker ? t(blocker === "needsProton" ? "up.proton.needsProton" : "up.helix.needsFsr31", { name: buildLabel(build) }) : null;
          return (build.models?.length ? build.models : [null]).map((model, modelIndex) => {
            const checked = choice.build === build.id && (choice.model ?? build.models?.[0] ?? null) === model;
            const select = () => {
              if (disabled || reason) return;
              onChange({ ...choice, build: build.id, model });
              close();
            };
            return <div role="row" key={`${build.id}:${model}`} style={{ borderTop: `1px solid ${theme.color.hairline}` }}>
              <Focusable ref={checked || (!current && buildIndex === 0 && modelIndex === 0) ? selectedOption : undefined} role="button" aria-pressed={checked} aria-disabled={!!reason || disabled} onActivate={select} onClick={select}
                style={{ ...gridStyle, padding: "8px 0", minHeight: 44, boxSizing: "border-box", alignItems: "center", fontSize: theme.font.caption, lineHeight: 1.35, opacity: reason ? 0.6 : 1, cursor: "pointer" }}>
                <span role="cell" style={{ ...cellStyle, display: "flex", alignItems: "flex-start", gap: 4 }}>
                  {checked && <LuCheck size={14} style={{ flexShrink: 0, marginTop: 2 }} />}
                  <span style={cellStyle}>{build.family === "helixsr" ? "HelixSR" : build.family === "proton" ? "Proton" : build.family === "xess" ? "XeSS" : "FSR"}</span>
                </span>
                <span role="cell" style={cellStyle}>{build.version}{build.channel === "beta" ? " Beta" : ""}{build.id.endsWith("-rdna2") ? " (RDNA2)" : ""}</span>
                <span role="cell" style={cellStyle}>{modelLabel(model)}</span>
              </Focusable>
              {reason && <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{reason}</div>}
            </div>;
          });
        })}
      </div>
    </Focusable>}
  </Focusable>;
}
