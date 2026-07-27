import { ListRow, canLabel } from "./model";

export type HudValueUnit =
  | "px"
  | "percent"
  | "multiplier"
  | "decimal"
  | "signed-decimal";

export const hasLocalEditor = (row: ListRow): boolean => {
  if (row.kind === "separator") return false;
  if (row.kind === "block" || row.kind === "text" || row.kind === "spacer") return true;
  return canLabel(row.id) || row.id === "fps" || row.id === "frametime";
};

export const formatHudValue = (value: number, unit: HudValueUnit): string => {
  if (unit === "px") return `${value} px`;
  if (unit === "percent") return `${value}%`;
  if (unit === "multiplier") {
    return `${(value / 100).toFixed(2).replace(/\.?0+$/, "")}×`;
  }
  if (unit === "decimal") {
    return `${(value / 10).toFixed(1).replace(/\.0$/, "")} px`;
  }
  const shown = (value / 100).toFixed(2);
  return shown.startsWith("-") ? `−${shown.slice(1)}` : shown;
};
