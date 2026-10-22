import { DialogButton, Focusable, ToggleField } from "@decky/ui";
import { LuMapPin } from "react-icons/lu";
import { FC, useState } from "react";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { openCityModal } from "./CityModal";

export const SCENE_THEMES: { id: string; from: string; to: string }[] = [
  { id: "aurora", from: "#b078ff", to: "#40dcff" },
  { id: "sunset", from: "#ff963c", to: "#ff4678" },
  { id: "mint", from: "#5af0aa", to: "#3caaff" },
  { id: "mono", from: "#ebe8fa", to: "#c8c4e1" },
  { id: "ledbar", from: "#ff71ce", to: "#01cdfe" },
];

const Swatch: FC<{ id: string; from: string; to: string; selected: boolean; onPick: () => void }> = ({ id, from, to, selected, onPick }) => {
  const { t } = useI18n();
  const [focused, setFocused] = useState(false);
  return (
    <Focusable
      onActivate={onPick}
      onClick={onPick}
      onGamepadFocus={() => setFocused(true)}
      onGamepadBlur={() => setFocused(false)}
      aria-label={t(`accessories.theme.${id}`)}
      style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 5, flex: 1, padding: "6px 0", borderRadius: theme.radius.sm,
        background: focused ? "rgba(255,255,255,0.08)" : "transparent" }}
    >
      <span style={{
        width: 26, height: 26, borderRadius: 13, background: `linear-gradient(135deg, ${from}, ${to})`,
        boxShadow: selected ? `0 0 0 2px ${theme.color.surfaceRaised}, 0 0 0 4px ${theme.color.accent}, 0 0 12px ${from}88` : `0 0 8px ${from}44`,
        transform: focused ? "scale(1.1)" : "scale(1)", transition: "transform 120ms ease, box-shadow 160ms ease",
      }} />
      <span style={{ fontSize: 10, fontWeight: 650, color: selected ? theme.color.textPrimary : theme.color.textMuted }}>
        {t(`accessories.theme.${id}`)}
      </span>
    </Focusable>
  );
};

export const SceneOptions: FC<{
  options: string[];
  values: Record<string, unknown>;
  onChange: (values: Record<string, unknown>) => void;
}> = ({ options, values, onChange }) => {
  const { t } = useI18n();
  if (!options.length) return null;
  const current = typeof values.theme === "string" ? values.theme : "aurora";
  return (
    <div style={{ ...theme.card, padding: `${theme.space.sm}px ${theme.space.md}px`, display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      {options.includes("theme") && (
        <Focusable flow-children="row" style={{ display: "flex", gap: 4 }}>
          {SCENE_THEMES.map((swatch) => (
            <Swatch key={swatch.id} {...swatch} selected={current === swatch.id}
              onPick={() => onChange({ ...values, theme: swatch.id })} />
          ))}
        </Focusable>
      )}
      {options.includes("city") && (
        <DialogButton onClick={() => openCityModal((city) => onChange({ ...values, city }))}
          style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.sm }}>
          <LuMapPin size={15} />
          {typeof (values.city as { name?: string } | undefined)?.name === "string"
            ? (values.city as { name: string }).name
            : t("accessories.city.pick")}
        </DialogButton>
      )}
      {options.includes("hour12") && (
        <ToggleField label={t("accessories.hour12")} checked={values.hour12 === true}
          onChange={(on) => onChange({ ...values, hour12: on })} bottomSeparator="none" />
      )}
    </div>
  );
};
