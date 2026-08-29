import { DropdownItem, ToggleField } from "@decky/ui";

import type { CssLoaderPatch } from "../themes/cssLoaderTypes";
import type { Lang } from "../i18n";
import { theme } from "../theme";
import { ContainedSlider } from "./ContainedSlider";
import { presentThemePatchText } from "../themes/patchPresentation";

interface Props {
  patch: CssLoaderPatch;
  disabled?: boolean;
  lang?: Lang;
  onChange(value: string): void;
}

const readOnlyStyle = {
  ...theme.card,
  padding: theme.space.md,
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: theme.space.sm,
} as const;

function ReadOnlyPatch({ patch, lang, value = patch.rawType }: { patch: CssLoaderPatch; lang: Lang; value?: string }) {
  return (
    <div style={readOnlyStyle}>
      <span style={{ color: theme.color.textPrimary, fontSize: theme.font.body }}>{presentThemePatchText(patch.name, lang)}</span>
      <span style={{ color: theme.color.textMuted, fontSize: theme.font.caption }}>{presentThemePatchText(value, lang)}</span>
    </div>
  );
}

export function ThemePatchControl({ patch, disabled = false, lang = "es", onChange }: Props) {
  const label = presentThemePatchText(patch.name, lang);
  if (
    (patch.type === "checkbox" || patch.type === "dropdown" || patch.type === "slider")
    && !patch.options.includes(patch.value)
  ) {
    return <ReadOnlyPatch patch={patch} lang={lang} value={patch.value} />;
  }

  if (patch.type === "checkbox") {
    return (
      <ToggleField
        label={label}
        checked={patch.value === "Yes"}
        disabled={disabled}
        onChange={(enabled) => onChange(enabled ? "Yes" : "No")}
        bottomSeparator="none"
      />
    );
  }

  if (patch.type === "dropdown") {
    return (
      <DropdownItem
        label={label}
        rgOptions={patch.options.map((option) => ({ label: presentThemePatchText(option, lang), data: option }))}
        selectedOption={patch.value}
        disabled={disabled}
        onChange={(option) => onChange(String(option.data))}
      />
    );
  }

  if (patch.type === "slider" && patch.options.length > 0) {
    const selectedIndex = patch.options.indexOf(patch.value);
    return (
      <div style={{ ...theme.card, padding: theme.space.md }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: theme.space.sm }}>
          <span style={{ color: theme.color.textPrimary, fontSize: theme.font.body }}>{label}</span>
          <span style={{ color: theme.color.accent, fontSize: theme.font.caption, fontWeight: 700 }}>
            {presentThemePatchText(patch.options[selectedIndex], lang)}
          </span>
        </div>
        <ContainedSlider
          value={selectedIndex}
          min={0}
          max={patch.options.length - 1}
          step={1}
          showValue={false}
          onChange={(nextIndex) => {
            if (disabled) return;
            const option = patch.options[Math.max(0, Math.min(patch.options.length - 1, Math.round(nextIndex)))];
            if (option !== undefined) onChange(option);
          }}
        />
      </div>
    );
  }

  return <ReadOnlyPatch patch={patch} lang={lang} />;
}
