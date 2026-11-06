import { Navigation } from "@decky/ui";
import { useState, type FC } from "react";

import { setUpscalerIni } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { ActionButton, Note, Row } from "./parts";
import type { RecipeInfo } from "./types";

const WIKI_PAGE = "https://github.com/optiscaler/OptiScaler/wiki/";

/** What the OptiScaler wiki says about this game, and the settings it lists for special cases. */
export const WikiFacts: FC<{ appid: string; info: RecipeInfo; installed: boolean; onApplied: () => void }> = ({
  appid, info, installed, onApplied,
}) => {
  const { t } = useI18n();
  const [applied, setApplied] = useState<Record<string, "busy" | "done" | "failed">>({});
  const suggestions = Object.entries(info.suggestions ?? {});
  const warning = info.status === "partial" || info.status === "broken";
  if (!warning && (!installed || suggestions.length === 0)) return null;

  const apply = async (key: string, value: string) => {
    setApplied((s) => ({ ...s, [key]: "busy" }));
    try {
      await setUpscalerIni(appid, key, value);
      setApplied((s) => ({ ...s, [key]: "done" }));
      onApplied();
    } catch {
      setApplied((s) => ({ ...s, [key]: "failed" }));
    }
  };

  return (
    <div style={{ ...theme.card, padding: `${theme.space.sm}px ${theme.space.md}px`, display: "flex", flexDirection: "column", gap: 6 }}>
      {warning && <Note tone="warn">{t(`up.wiki.status.${info.status}`)}</Note>}
      {installed && suggestions.length > 0 && (
        <>
          <Note>{t(installed ? "up.wiki.suggestions" : "up.wiki.suggestions.later")}</Note>
          {installed && suggestions.map(([key, value]) => (
            <Row key={key}>
              <ActionButton
                label={applied[key] === "done" ? t("up.wiki.applied", { setting: `${key}=${value}` }) : `${key}=${value}`}
                busy={applied[key] === "busy"}
                disabled={applied[key] === "busy" || applied[key] === "done"}
                onPress={() => void apply(key, value)}
              />
            </Row>
          ))}
          {suggestions.some(([key]) => applied[key] === "failed") && <Note tone="warn">{t("up.wiki.applyFailed")}</Note>}
        </>
      )}
      {info.page && (
        <Row>
          <ActionButton label={t("up.wiki.open")} onPress={() => Navigation.NavigateToExternalWeb(WIKI_PAGE + encodeURI(info.page!))} />
        </Row>
      )}
    </div>
  );
};
