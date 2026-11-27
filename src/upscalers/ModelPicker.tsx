import { GiSharkFin } from "react-icons/gi";
import { Focusable } from "@decky/ui";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { LuCheck, LuChevronDown, LuChevronUp, LuFileCode, LuLayers } from "react-icons/lu";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { createThemeNavigationAccess } from "../themes/runtime/navigationAccess";
import { Bars, PickerButton } from "./parts";
import { buildBlocker, buildLabel, offered } from "./model";
import type { TestedDefault } from "./testedDefaults";
import type { BuildInfo, UpscalerChoice } from "./types";

function showScalerIcon(element: HTMLSpanElement | null) {
  element?.querySelector("svg")?.style.setProperty("display", "inline-block", "important");
}

function TestedMark({ description, announce = false }: { description: string; announce?: boolean }) {
  return <span data-pdc-up-tested role={announce ? "img" : undefined} aria-label={announce ? description : undefined}
    aria-hidden={announce ? undefined : true} title={announce ? undefined : description}
    style={{ flexShrink: 0, lineHeight: 1 }}>{"★\uFE0E"}</span>;
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

export function ModelPicker({ builds, choice, inputs, protonEnv, disabled, onChange, dllTargets = [], spatial = false, onSpatial, onPendingChoice, duo = false, appid = "", gpu = "unknown", testedDefault }: {
  testedDefault?: TestedDefault;
  gpu?: string;
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
  // What actually runs on this GPU, under the name: a pill beside it pushed the name onto two lines.
  // A version this GPU may not run stays selectable, with a short line saying so.
  const note = (build: BuildInfo) => offered(build, builds, gpu).warn ? t("up.build.mayNotRun")
    : build.may_fallback ? t("up.build.mayUse", { version: build.may_fallback }) : null;
  const modeOption = (value: typeof mode, name: string, icon: ReactNode) => {
    const description = testedDefault?.mode === value ? t("up.mode.tested") : undefined;
    return {
      value, valueLabel: name, description,
      label: <span ref={showScalerIcon} style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs }}>
        {icon}<span>{name}</span>{description && <TestedMark description={description} announce={duo} />}
      </span>,
    };
  };
  const testedLabel = (build: BuildInfo, model: string | null) => testedDefault && testedDefault.mode !== "mako"
    && testedDefault.build === build.id && testedDefault.model === model
    ? t("up.model.tested") : undefined;
  const named = (build: BuildInfo, model: string | null) => {
    const description = testedLabel(build, model);
    const label = <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs }}>
      <span>{optionLabel(build, model)}</span>
      {description && <TestedMark description={description} />}
    </span>;
    const warning = note(build);
    return warning ? <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
      {label}
      <span style={{ fontSize: theme.font.caption - 1, fontWeight: 400, color: theme.color.textMuted }}>{warning}</span>
    </span> : label;
  };
  const options = builds.filter((build) => mode !== "mako" && build.available && offered(build, builds, gpu).show && (mode === "dll" ? build.engine === "dll" && supportsDllTargets(build, dllTargets) : build.engine !== "dll") && !buildBlocker(build, inputs, protonEnv))
    .sort((a, b) => Number(b.supported) - Number(a.supported))
    .flatMap((build) => (build.models?.length ? build.models : [null]).map((model) => ({ build, model })));
  const currentModel = choice.model ?? current?.models?.[0] ?? null;
  const selectedIndex = Math.max(0, options.findIndex(({ build, model }) => choice.build === build.id && currentModel === model));
  const currentDescription = mode === choiceMode && current
    ? [optionLabel(current, currentModel), testedLabel(current, currentModel)].filter(Boolean).join(". ") : undefined;
  return <Focusable flow-children="column" style={{ ...theme.card, padding: theme.space.sm, fontSize: theme.font.caption, lineHeight: 1.35, minWidth: 0, overflowWrap: "normal", wordBreak: "normal" }}>
    <PickerButton duo={duo} controlId={`${appid}:scaler-engine`} label={t("up.models.title")} value={mode} disabled={disabled}
      options={[
        modeOption("dll", "DLL", <LuFileCode className="pdc-up-dll-icon" aria-hidden size={16} />),
        modeOption("optiscaler", "OptiScaler", <LuLayers className="pdc-up-optiscaler-icon" aria-hidden size={16} />),
        ...(onSpatial ? [modeOption("mako", "Mako", <GiSharkFin className="pdc-up-mako-icon" aria-hidden size={16} />)] : []),
      ]}
      onChange={next => { if (disabled) return; setMode(next); onSpatial?.(next === "mako"); setOpen(next !== "mako"); }} />
    {mode !== "mako" && <Focusable data-pdc-part="disclosure" ref={trigger} role="button" aria-label={t("up.section.model")} aria-expanded={open} aria-disabled={disabled}
      aria-description={currentDescription}
      onClick={toggle} onActivate={toggle} onCancel={open ? (event) => { event.stopPropagation(); close(); } : undefined}
      style={{ padding: theme.space.sm, cursor: "pointer", color: theme.color.textPrimary, fontWeight: 600, display: "flex", alignItems: "center", gap: theme.space.sm }}>
      <span style={{ flex: 1, minWidth: 0 }}>{mode === choiceMode && current ? named(current, currentModel) : t("up.section.model")}</span>
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
          const checked = choice.build === build.id && currentModel === model;
          const select = () => {
            if (disabled) return;
            onSpatial?.(false);
            onChange({ ...choice, build: build.id, model });
            close();
          };
          return <Focusable key={`${build.id}:${model}`} ref={index === selectedIndex ? selectedOption : undefined}
            role="radio" aria-label={optionLabel(build, model)} aria-checked={checked} aria-disabled={disabled}
            aria-description={testedLabel(build, model)}
            onActivate={select} onClick={select}
            style={{ display: "flex", alignItems: "center", padding: `${theme.space.sm}px 0`, minHeight: 44,
              boxSizing: "border-box", borderTop: `1px solid ${theme.color.hairline}`, cursor: "pointer", fontSize: theme.font.caption, minWidth: 0 }}>
            <span style={{ width: 20, flexShrink: 0, display: "flex" }}>{checked && <LuCheck size={14} />}</span>
            <span style={{ flex: 1, minWidth: 0, overflowWrap: "normal", wordBreak: "normal" }}>{named(build, model)}</span>
            <span style={{ display: "inline-flex", flexShrink: 0, width: 80 }} aria-hidden="true"><Bars value={build.image} /><Bars value={4 - build.cost} /></span>
          </Focusable>;
        })}
      </Focusable>
    </Focusable>}
  </Focusable>;
}
