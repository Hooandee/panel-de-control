import { DropdownItem, SliderField, ToggleField } from "@decky/ui";
import type { CSSProperties, ReactNode } from "react";

import type { CssLoaderPatch } from "../themes/cssLoaderTypes";
import { theme } from "../theme";

interface Props {
  patch: CssLoaderPatch;
  disabled?: boolean;
  onChange(value: string): void;
}

const patchSurfaceStyle: CSSProperties = {
  ...theme.card,
  color: theme.color.textPrimary,
  minWidth: 0,
  minHeight: 54,
  boxSizing: "border-box",
  padding: "10px 11px",
  display: "flex",
  flexDirection: "column",
  justifyContent: "center",
};

const readOnlyStyle: CSSProperties = {
  minHeight: 34,
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: theme.space.sm,
};

function PatchSurface({
  children,
  disabled = false,
  slider = false,
}: {
  children: ReactNode;
  disabled?: boolean;
  slider?: boolean;
}) {
  return (
    <div
      data-testid="theme-patch-control"
      data-pdc-theme-patch-control="true"
      data-pdc-theme-slider={slider || undefined}
      style={{ ...patchSurfaceStyle, opacity: disabled ? 0.58 : 1 }}
    >
      {children}
    </div>
  );
}

function ReadOnlyPatch({ patch, value = patch.rawType }: { patch: CssLoaderPatch; value?: string }) {
  return (
    <PatchSurface>
      <div style={readOnlyStyle}>
        <span data-pdc-theme-patch-primary style={{ color: theme.color.textPrimary, fontSize: theme.font.body }}>{patch.name}</span>
        <span data-pdc-theme-patch-muted style={{ color: theme.color.textMuted, fontSize: theme.font.caption }}>{value}</span>
      </div>
    </PatchSurface>
  );
}

function isEditablePatch(patch: CssLoaderPatch): boolean {
  if (!patch.options.includes(patch.value)) return false;
  if (patch.type === "checkbox") {
    return patch.options.length === 2
      && patch.options.includes("No")
      && patch.options.includes("Yes");
  }
  if (patch.type === "dropdown") return patch.options.length > 0;
  if (patch.type === "slider") return patch.options.length > 1;
  return false;
}

export function ThemePatchControl({ patch, disabled = false, onChange }: Props) {
  const label = patch.name;
  if (!isEditablePatch(patch)) {
    const value = patch.type === "none" || patch.type === "unsupported"
      ? patch.rawType
      : patch.value;
    return <ReadOnlyPatch patch={patch} value={value} />;
  }

  if (patch.type === "checkbox") {
    return (
      <PatchSurface disabled={disabled}>
        <ToggleField
          label={label}
          checked={patch.value === "Yes"}
          disabled={disabled}
          onChange={(enabled) => onChange(enabled ? "Yes" : "No")}
          bottomSeparator="none"
        />
      </PatchSurface>
    );
  }

  if (patch.type === "dropdown") {
    return (
      <PatchSurface disabled={disabled}>
        <DropdownItem
          label={label}
          rgOptions={patch.options.map((option) => ({ label: option, data: option }))}
          selectedOption={patch.value}
          disabled={disabled}
          bottomSeparator="none"
          onChange={(option) => onChange(String(option.data))}
        />
      </PatchSurface>
    );
  }

  if (patch.type === "slider") {
    const selectedIndex = patch.options.indexOf(patch.value);
    const selectedLabel = patch.options[selectedIndex];
    return (
      <PatchSurface disabled={disabled} slider>
        <SliderField
          label={(
            <span style={{ display: "flex", width: "100%", justifyContent: "space-between", alignItems: "baseline", gap: theme.space.sm }}>
              <span data-pdc-theme-patch-primary style={{ color: theme.color.textPrimary, fontSize: theme.font.body }}>{label}</span>
              <span data-pdc-theme-patch-accent style={{ color: theme.color.accent, fontSize: theme.font.caption, fontWeight: 700 }}>{selectedLabel}</span>
            </span>
          )}
          value={selectedIndex}
          min={0}
          max={patch.options.length - 1}
          step={1}
          showValue={false}
          bottomSeparator="none"
          disabled={disabled}
          onChange={(nextIndex) => {
            if (disabled) return;
            const option = patch.options[Math.max(0, Math.min(patch.options.length - 1, Math.round(nextIndex)))];
            if (option !== undefined) onChange(option);
          }}
        />
      </PatchSurface>
    );
  }

  return <ReadOnlyPatch patch={patch} />;
}
