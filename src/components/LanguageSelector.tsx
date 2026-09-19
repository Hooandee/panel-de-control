import { FC } from "react";
import { Dropdown } from "@decky/ui";

import { useI18n } from "../i18n";
import { LANGUAGE_OPTIONS, type Lang } from "../i18n/languages";

const FLAG_SVGS: Record<Lang, string> = {
  es: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 16"><path fill="#c60b1e" d="M0 0h24v16H0z"/><path fill="#ffc400" d="M0 4h24v8H0z"/></svg>',
  en: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 16"><path fill="#012169" d="M0 0h24v16H0z"/><path stroke="#fff" stroke-width="3.4" d="m0 0 24 16M24 0 0 16"/><path stroke="#c8102e" stroke-width="1.6" d="m0 0 24 16M24 0 0 16"/><path stroke="#fff" stroke-width="4.6" d="M12 0v16M0 8h24"/><path stroke="#c8102e" stroke-width="2.6" d="M12 0v16M0 8h24"/></svg>',
  it: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 16"><path fill="#009246" d="M0 0h8v16H0z"/><path fill="#fff" d="M8 0h8v16H8z"/><path fill="#ce2b37" d="M16 0h8v16h-8z"/></svg>',
  de: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 16"><path d="M0 0h24v5.33H0z"/><path fill="#d00" d="M0 5.33h24v5.34H0z"/><path fill="#ffce00" d="M0 10.67h24V16H0z"/></svg>',
  "pt-BR": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 16"><path fill="#009739" d="M0 0h24v16H0z"/><path fill="#fedd00" d="m12 2 9 6-9 6-9-6z"/><circle cx="12" cy="8" r="3.5" fill="#012169"/><path fill="none" stroke="#fff" stroke-width=".7" d="M8.8 7.2c2.2-.7 4.4-.3 6.5 1"/></svg>',
};

const LanguageFlag: FC<{ lang: Lang }> = ({ lang }) => (
  <img
    src={`data:image/svg+xml,${encodeURIComponent(FLAG_SVGS[lang])}`}
    width={24}
    height={16}
    alt=""
    aria-hidden="true"
    data-language-flag={lang}
    style={{ flexShrink: 0, display: "block", borderRadius: 2, boxShadow: "0 0 0 1px rgba(255,255,255,0.22)" }}
  />
);

const LanguageOptionLabel: FC<{ lang: Lang; label: string }> = ({ lang, label }) => (
  <span style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
    <LanguageFlag lang={lang} />
    <span>{label}</span>
  </span>
);

const DROPDOWN_OPTIONS = LANGUAGE_OPTIONS.map(({ data, label }) => ({
  data,
  label: <LanguageOptionLabel key={data} lang={data} label={label} />,
}));

export const LanguageSelector: FC = () => {
  const { lang, setLang, t } = useI18n();

  return (
    <div style={{ width: 190, minWidth: 0 }}>
      <Dropdown
        rgOptions={DROPDOWN_OPTIONS}
        selectedOption={lang}
        menuLabel={t("settings.language")}
        onChange={(option) => setLang(option.data)}
      />
    </div>
  );
};
