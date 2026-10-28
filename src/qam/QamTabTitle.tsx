import { useSyncExternalStore } from "react";
import { staticClasses } from "@decky/ui";
import { getCurrentLanguage, subscribeLanguage, translate } from "../i18n";

// Translate the existing tab without replacing its registration or content lifecycle.
export function QamTabTitle({ label, labelKey }: { label?: string; labelKey: string }) {
  useSyncExternalStore(subscribeLanguage, getCurrentLanguage);
  return <div className={staticClasses.Title}>{label || translate(labelKey)}</div>;
}
