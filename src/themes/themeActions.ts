import { useSyncExternalStore } from "react";

import type { Lang } from "../i18n/languages";
import { themeActionsChannel } from "./runtime/themeActions";

type LocalizedText = Readonly<Partial<Record<Lang, string>>>;

export interface ThemeAction {
  id: string;
  label: LocalizedText;
  description?: LocalizedText;
  confirm?: LocalizedText;
  destructive: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function localized(value: unknown): LocalizedText | undefined {
  if (!isRecord(value)) return undefined;
  const entries = Object.entries(value).filter(([, text]) => typeof text === "string" && text.length > 0);
  return entries.length > 0 ? Object.freeze(Object.fromEntries(entries)) as LocalizedText : undefined;
}

// The backend (`theme_packages.theme_actions`) already applies the limits and drops malformed or
// repeated entries; this only keeps the shape the settings screen relies on.
export function parseThemeActions(value: unknown): readonly ThemeAction[] {
  if (!Array.isArray(value)) return [];
  const actions: ThemeAction[] = [];
  for (const entry of value) {
    if (!isRecord(entry) || typeof entry.id !== "string" || !entry.id) continue;
    const label = localized(entry.label);
    if (!label) continue;
    const description = localized(entry.description);
    const confirm = localized(entry.confirm);
    actions.push(Object.freeze({
      id: entry.id,
      label,
      ...(description ? { description } : {}),
      ...(confirm ? { confirm } : {}),
      destructive: entry.destructive === true,
    }));
  }
  return Object.freeze(actions);
}

export function themeActionText(text: LocalizedText, lang: Lang): string {
  return text[lang] ?? text.en ?? text.es ?? Object.values(text).find((value): value is string => typeof value === "string") ?? "";
}

/** Whether the theme's runtime is mounted and listening, so an action would reach someone. */
export function useThemeActionsListening(catalogId: string): boolean {
  return useSyncExternalStore(
    (listener) => themeActionsChannel.watch(listener),
    () => themeActionsChannel.listening(catalogId),
    () => themeActionsChannel.listening(catalogId),
  );
}
