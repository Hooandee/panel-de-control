import { Navigation } from "@decky/ui";
import { useState, type FC } from "react";

import { setUpscalerIni } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { ActionButton, Chip, Note, Row } from "./parts";
import type { RecipeInfo } from "./types";

const WIKI_PAGE = "https://github.com/optiscaler/OptiScaler/wiki/";

/** What the OptiScaler wiki says about this game, and the settings it lists for special cases. */
export const WikiFacts: FC<{ appid: string; info: RecipeInfo; installed: boolean; onApplied: () => void }> = ({
  appid, info, installed, onApplied,
}) => {
  const { t } = useI18n();
  const [applied, setApplied] = useState<Record<string, "busy" | "done" | "failed">>({});
  const settings = Object.entries(info.settings ?? {});
  const suggestions = Object.entries(info.suggestions ?? {});
  if (!info.status && !settings.length && !suggestions.length) return null;

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
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, flexWrap: "wrap" }}>
        <span style={{ flex: 1, minWidth: 120, fontSize: theme.font.caption + 1, fontWeight: 700, color: theme.color.textPrimary }}>
          {t(`up.wiki.status.${info.status ?? "works"}`)}
        </span>
        {(info.inputs ?? []).map((input) => <Chip key={input}>{input}</Chip>)}
      </div>
      {info.linux && <Note>{t("up.wiki.linux")}</Note>}
      {info.optipatcher && <Note>{t("up.wiki.optipatcher")}</Note>}
      {settings.length > 0 && (
        <Note>{t("up.wiki.settings", { list: settings.map(([k, v]) => `${k}=${v}`).join(", ") })}</Note>
      )}
      {suggestions.length > 0 && (
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
