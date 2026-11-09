import { GiSharkFin } from "react-icons/gi";
import { Focusable } from "@decky/ui";
import { useEffect, useRef, useState } from "react";
import { LuCheck, LuChevronDown, LuChevronUp, LuFileCode, LuLayers } from "react-icons/lu";
import { ExperimentalBadge } from "../components/ExperimentalBadge";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { createThemeNavigationAccess } from "../themes/runtime/navigationAccess";
import { Bars, PickerButton } from "./parts";
import { buildBlocker, buildLabel } from "./model";
import type { BuildInfo, UpscalerChoice } from "./types";

function showScalerIcon(element: HTMLSpanElement | null) {
  element?.querySelector("svg")?.style.setProperty("display", "inline-block", "important");
}

const navigation = createThemeNavigationAccess({ allowInactiveContext: true });

function supportsDllTargets(build: BuildInfo, targets: string[]): boolean {
  const provider = "amd_fidelityfx_upscaler_dx12.dll";
  const loader = "amd_fidelityfx_loader_dx12.dll";
  const files = build.dll_names ?? [];
  if (!targets.length || !files.includes(provider)) return false;
  const legacyFiles = new Set([...files, ...(build.dll_legacy_names ?? [])]);
  const entries = targets.map(path => {
    const separator = path.lastIndexOf("/");
    return { directory: path.slice(0, separator + 1), name: path.slice(separator + 1).toLowerCase() };
  });
  const providerDirectories = new Set(entries.filter(entry => entry.name === provider || entry.name === "amd_fidelityfx_dx12.dll").map(entry => entry.directory));
  return entries.every(({ directory, name }) => {
    if (name === "amd_fidelityfx_dx12.dll") return legacyFiles.has(loader) && legacyFiles.has("amd_fidelityfx_framegeneration_dx12.dll");
    if (name === loader) return files.includes(loader) || providerDirectories.has(directory);
    return files.includes(name);
  });
}

export function ModelPicker({ builds, choice, inputs, protonEnv, disabled, onChange, dllTargets = [], spatial = false, onSpatial, onPendingChoice, duo = false, appid = "" }: {
  duo?: boolean;
  appid?: string;
  onPendingChoice?: (pending: boolean) => void;
  spatial?: boolean;
  onSpatial?: (value: boolean) => void;
  builds: BuildInfo[];
  choice: UpscalerChoice;
  inputs: Record<string, unknown>;
  dllTargets?: string[];
  protonEnv: string | null;
  disabled?: boolean;
  onChange: (choice: UpscalerChoice) => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const choiceMode = builds.find((build) => build.id === choice.build)?.engine === "dll" ? "dll" : "optiscaler";
  const [mode, setMode] = useState<"dll" | "optiscaler" | "mako">(spatial ? "mako" : choiceMode);
  useEffect(() => { if (!spatial) setMode(choiceMode); }, [choiceMode]);
  useEffect(() => setMode(previous => spatial ? "mako" : previous === "mako" ? choiceMode : previous), [spatial]);
  useEffect(() => { onPendingChoice?.(mode !== "mako" && mode !== choiceMode); }, [mode, choiceMode, onPendingChoice]);
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
  const optionLabel = (build: BuildInfo, model: string | null) => {
    const name = buildLabel({ ...build, channel: undefined });
    return model ? `${name} ${model === "lite" ? "Lite" : t(`up.model.${model}`)}` : name;
  };
  const fallbackBadge = (build: BuildInfo) => build.may_fallback
    ? <ExperimentalBadge>{t("up.build.mayUse", { version: build.may_fallback })}</ExperimentalBadge> : null;
  const options = builds.filter((build) => mode !== "mako" && build.available && build.supported && (mode === "dll" ? build.engine === "dll" && supportsDllTargets(build, dllTargets) : build.engine !== "dll") && !buildBlocker(build, inputs, protonEnv))
    .flatMap((build) => (build.models?.length ? build.models : [null]).map((model) => ({ build, model })));
  const selectedIndex = Math.max(0, options.findIndex(({ build, model }) => choice.build === build.id && (choice.model ?? build.models?.[0] ?? null) === model));
  return <Focusable flow-children="column" style={{ ...theme.card, padding: theme.space.sm, fontSize: theme.font.caption, lineHeight: 1.35, minWidth: 0, overflowWrap: "normal", wordBreak: "normal" }}>
    <PickerButton duo={duo} controlId={`${appid}:scaler-engine`} label={t("up.models.title")} value={mode} disabled={disabled}
      options={[
        { value: "dll", label: <span ref={showScalerIcon} style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs }}><LuFileCode className="pdc-up-dll-icon" aria-hidden size={16} />DLL</span> },
        { value: "optiscaler", label: <span ref={showScalerIcon} style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs }}><LuLayers className="pdc-up-optiscaler-icon" aria-hidden size={16} />OptiScaler</span> },
        ...(onSpatial ? [{ value: "mako" as const, label: <span ref={showScalerIcon} style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs }}><GiSharkFin className="pdc-up-mako-icon" aria-hidden size={16} />Mako</span> }] : []),
      ]}
      onChange={next => { if (disabled) return; setMode(next); onSpatial?.(next === "mako"); setOpen(next !== "mako"); }} />
    {mode !== "mako" && <Focusable ref={trigger} role="button" aria-label={t("up.section.model")} aria-expanded={open} aria-disabled={disabled}
      onClick={toggle} onActivate={toggle} onCancel={open ? (event) => { event.stopPropagation(); close(); } : undefined}
      style={{ padding: theme.space.sm, cursor: "pointer", fontWeight: 600, display: "flex", alignItems: "center", gap: theme.space.sm }}>
      <span style={{ flex: 1, minWidth: 0 }}>{mode === choiceMode && current ? optionLabel(current, choice.model ?? current.models?.[0] ?? null) : t("up.section.model")}</span>
      {mode === choiceMode && current && fallbackBadge(current)}
      {open ? <LuChevronUp size={16} /> : <LuChevronDown size={16} />}
    </Focusable>}
    {open && mode !== "mako" && <Focusable flow-children="column" onCancel={(event) => { event.stopPropagation(); close(); }} style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      {mode === "dll" && dllTargets.length === 0 && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("up.mode.noDll")}</span>}
      {options.length > 0 && <div style={{ display: "flex", justifyContent: "flex-end", fontSize: theme.font.caption, color: theme.color.textMuted }}>
        <span style={{ width: 40, textAlign: "center" }}>{t("up.bar.image")}</span>
        <span style={{ width: 40, textAlign: "center" }}>{t("up.bar.perf")}</span>
      </div>}
      <Focusable role="radiogroup" aria-label={t("up.models.title")} flow-children="column" style={{ display: "flex", flexDirection: "column" }}>
        {options.map(({ build, model }, index) => {
          const checked = choice.build === build.id && (choice.model ?? build.models?.[0] ?? null) === model;
          const select = () => {
            if (disabled) return;
            onSpatial?.(false);
            onChange({ ...choice, build: build.id, model });
            close();
          };
          return <Focusable key={`${build.id}:${model}`} ref={index === selectedIndex ? selectedOption : undefined}
            role="radio" aria-label={optionLabel(build, model)} aria-checked={checked} aria-disabled={disabled}
            onActivate={select} onClick={select}
            style={{ display: "flex", alignItems: "center", padding: `${theme.space.sm}px 0`, minHeight: 44,
              boxSizing: "border-box", borderTop: `1px solid ${theme.color.hairline}`, cursor: "pointer", fontSize: theme.font.caption, minWidth: 0 }}>
            <span style={{ width: 20, flexShrink: 0, display: "flex" }}>{checked && <LuCheck size={14} />}</span>
            <span style={{ flex: 1, minWidth: 0, overflowWrap: "normal", wordBreak: "normal" }}>{optionLabel(build, model)}</span>
            {fallbackBadge(build)}
            <span style={{ display: "inline-flex", flexShrink: 0, width: 80 }} aria-hidden="true"><Bars value={build.image} /><Bars value={4 - build.cost} /></span>
          </Focusable>;
        })}
      </Focusable>
    </Focusable>}
  </Focusable>;
}
