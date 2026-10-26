import type { FC } from "react";
import { DialogButton, ToggleField } from "@decky/ui";
import { useI18n } from "../i18n";
import type { PerformanceSettingControl } from "../steam/performanceSettings";
import { theme } from "../theme";
import { FocusReturningDropdown } from "./FocusReturningDropdown";
import { ContainedSlider } from "./ContainedSlider";

type ControlId = PerformanceSettingControl["id"];
export interface SteamPerformanceControlsProps {
  controls: PerformanceSettingControl[];
  disabled: boolean;
  onChange: (id: ControlId, value?: number | boolean) => void;
}

const groups: Array<{ name: string; ids: ControlId[] }> = [
  { name: "display", ids: ["legacyFrameRate", "appFrameRate", "disableFrameLimit", "refreshRate"] },
  { name: "fluidity", ids: ["variableResolution", "vrr", "allowTearing"] },
  { name: "scaling", ids: ["combinedScaling", "splitScalingFilter", "scalingMode", "sharpness", "fsrSharpness", "nisSharpness"] },
];

export const SteamPerformanceControls: FC<SteamPerformanceControlsProps> = ({ controls, disabled, onChange }) => {
  const { t } = useI18n();
  const renderControl = (control: PerformanceSettingControl) => {
    const labelId = control.id === "combinedScaling" ? "splitScalingFilter"
      : control.id === "fsrSharpness" || control.id === "nisSharpness" ? "sharpness" : control.id;
    const suffix = control.id === "fsrSharpness" ? " FSR" : control.id === "nisSharpness" ? " NIS" : "";
    const label = t(`steam.performance.control.${labelId}`) + suffix;
    const change = (value?: number | boolean) => { if (!disabled) onChange(control.id, value); };
    if (control.kind === "toggle") return <ToggleField key={control.id} label={label} checked={control.value} disabled={disabled} bottomSeparator="none" onChange={change} />;
    if (control.kind === "slider") return <ContainedSlider key={control.id} label={label} value={control.value} min={control.min} max={control.max} step={control.step} showValue disabled={disabled} onChange={change} />;
    if (control.kind === "options" && (control.id === "appFrameRate" || control.id === "legacyFrameRate")) {
      const position = control.options.findIndex((option) => option.value === control.value);
      const refreshHz = control.options[position]?.refreshHz;
      const display = control.value === 0 ? t("steam.performance.option.unlimited") : `${control.value} FPS${refreshHz === undefined ? "" : ` (${refreshHz} Hz)`}`;
      return <ContainedSlider key={control.id} label={`${label}: ${display}`}
        value={position} min={0} max={control.options.length - 1} step={1}
        showValue={false} disabled={disabled || control.options.length < 2}
        onChange={(index) => {
          if (!Number.isInteger(index)) return;
          const option = control.options[index];
          if (option) change(option.value);
        }} />;
    }
    if (control.kind === "options") return (
      <FocusReturningDropdown
        controlId={`steam-${control.id}`}
        key={control.id}
        label={label}
        selectedOption={control.value}
        disabled={disabled}
        bottomSeparator="none"
        rgOptions={control.options.map((option) => ({
          data: option.value,
          label: control.id === "combinedScaling" || control.id === "splitScalingFilter" || control.id === "scalingMode"
            ? ["fsr", "nis"].includes(option.label) ? option.label.toUpperCase() : t(`steam.performance.option.${option.label}`)
            : `${option.value} ${control.id === "refreshRate" ? "Hz" : "FPS"}`,
        }))}
        onChange={(option) => change(Number(option.data))}
      />
    );
    return <DialogButton key={control.id} disabled={disabled} onClick={() => change()} style={{ width: "100%", minWidth: 0 }}>{label}</DialogButton>;
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
      {groups.map((group) => {
        const rows = group.ids.flatMap((id) => controls.filter((control) => control.id === id));
        if (!rows.length) return null;
        const label = t(`steam.performance.group.${group.name}`);
        return (
          <section key={group.name} role="group" aria-label={label} style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
            <div style={theme.sectionLabel}>{label}</div>
            {rows.map(renderControl)}
          </section>
        );
      })}
      {controls.filter((control) => control.id === "reset" && control.kind === "action").map(renderControl)}
    </div>
  );
};
