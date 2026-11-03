import { Dropdown, TextField } from "@decky/ui";
import { useMemo, useState, type FC } from "react";

import { getUpscalerIni, setUpscalerIni } from "../api";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { ActionButton, Note, Row, Skeleton } from "./parts";
import type { IniKey, IniSection } from "./types";

/** Every OptiScaler.ini key, read from the installed file; the help is OptiScaler's own. */
export const AdvancedIni: FC<{ appid: string }> = ({ appid }) => {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [sections, setSections] = useState<IniSection[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = async () => {
    setFailed(false);
    try {
      setSections((await getUpscalerIni(appid)).sections);
    } catch {
      setFailed(true);
    }
  };

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!sections || !needle) return sections;
    return sections
      .map((s) => ({ ...s, keys: s.keys.filter((k) => `${s.name} ${k.key} ${k.help.join(" ")}`.toLowerCase().includes(needle)) }))
      .filter((s) => s.keys.length);
  }, [sections, query]);

  const save = async (section: string, key: IniKey, value: string) => {
    if (value === key.value) return;
    setMessage(null);
    try {
      await setUpscalerIni(appid, `${section}.${key.key}`, value);
      setSections((current) => current?.map((s) => s.name !== section ? s
        : { ...s, keys: s.keys.map((k) => k.key === key.key ? { ...k, value } : k) }) ?? null);
      setMessage(t("up.ini.saved"));
    } catch (error) {
      const code = String((error as Error)?.message ?? "");
      setMessage(t(`up.error.${code}`) === `up.error.${code}` ? t("up.error.generic") : t(`up.error.${code}`));
    }
  };

  if (!open) {
    return <Row><ActionButton label={t("up.ini.open")} onPress={() => { setOpen(true); void load(); }} /></Row>;
  }

  const count = sections?.reduce((n, s) => n + s.keys.length, 0) ?? 0;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <Row><ActionButton label={t("up.ini.close")} onPress={() => setOpen(false)} /></Row>
      <Note>{t("up.ini.note", { count })}</Note>
      {failed && <Row><ActionButton label={t("load.retry")} onPress={() => void load()} /></Row>}
      {!sections && !failed && <Skeleton height={96} />}
      {sections && (
        <TextField
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          // @ts-expect-error Decky TextField forwards input attrs; placeholder is valid.
          placeholder={t("up.ini.search")}
        />
      )}
      {message && <Note>{message}</Note>}
      {filtered?.map((section) => {
        const isOpen = expanded === section.name || !!query.trim();
        return (
          <div key={section.name} style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
            <ActionButton
              label={`${section.name} (${section.keys.length})`}
              onPress={() => setExpanded(isOpen && !query.trim() ? null : section.name)}
            />
            {isOpen && section.keys.map((key) => (
              <IniRow key={key.key} section={section.name} entry={key} onSave={save} />
            ))}
          </div>
        );
      })}
    </div>
  );
};

const IniRow: FC<{ section: string; entry: IniKey; onSave: (section: string, key: IniKey, value: string) => void }> = ({
  section, entry, onSave,
}) => {
  const { t } = useI18n();
  const [draft, setDraft] = useState(entry.value);
  return (
    <div style={{ ...theme.card, padding: `${theme.space.xs}px ${theme.space.sm}px`, display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs }}>
        <span style={{ flex: 1, fontSize: theme.font.caption + 1, color: theme.color.textPrimary, overflowWrap: "anywhere" }}>{entry.key}</span>
        {entry.managed && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("up.ini.managed")}</span>}
      </div>
      {entry.managed ? (
        <span style={{ fontSize: theme.font.caption + 1, color: theme.color.textPrimary }}>{entry.value}</span>
      ) : entry.choices ? (
        <Dropdown
          rgOptions={entry.choices.map((c) => ({ data: c, label: c === entry.default ? `${c} (${t("up.ini.default")})` : c }))}
          selectedOption={entry.value}
          onChange={(option) => onSave(section, entry, String(option.data))}
        />
      ) : (
        <TextField
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => onSave(section, entry, draft.trim())}
        />
      )}
      {entry.help[0] && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.35 }}>{entry.help[0]}</span>}
    </div>
  );
};
