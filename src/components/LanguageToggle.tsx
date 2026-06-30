import { CSSProperties, FC } from "react";
import { Focusable } from "@decky/ui";
import { useI18n } from "../i18n";

const FlagES: FC = () => (
  <svg width={20} height={14} viewBox="0 0 20 14" xmlns="http://www.w3.org/2000/svg">
    <rect width={20} height={14} fill="#c60b1e" />
    <rect y={3.5} width={20} height={7} fill="#ffc400" />
  </svg>
);

const FlagEN: FC = () => (
  <svg width={20} height={14} viewBox="0 0 60 42" xmlns="http://www.w3.org/2000/svg">
    <rect width={60} height={42} fill="#012169" />
    <path d="M0,0 60,42 M60,0 0,42" stroke="#fff" strokeWidth={8} />
    <path d="M0,0 60,42 M60,0 0,42" stroke="#c8102e" strokeWidth={4} />
    <path d="M30,0 V42 M0,21 H60" stroke="#fff" strokeWidth={12} />
    <path d="M30,0 V42 M0,21 H60" stroke="#c8102e" strokeWidth={7} />
  </svg>
);

// Flag toggle mirroring decky-colores: two Focusable flag buttons, the active one
// at full opacity with a bright ring. Compact; the parent controls placement.
export const LanguageToggle: FC = () => {
  const { lang, setLang, t } = useI18n();

  const buttonStyle = (active: boolean): CSSProperties => ({
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: 28,
    height: 20,
    borderRadius: 5,
    cursor: "pointer",
    opacity: active ? 1 : 0.4,
    boxShadow: active ? "0 0 0 1.5px rgba(255,255,255,0.85)" : "0 0 0 1px rgba(255,255,255,0.15)",
    transition: "opacity 120ms ease, box-shadow 120ms ease",
  });

  return (
    <Focusable
      style={{ display: "flex", gap: 6, justifyContent: "flex-end", padding: "0 2px" }}
    >
      <Focusable
        onActivate={() => setLang("es")}
        onClick={() => setLang("es")}
        aria-label={t("lang.spanish")}
        style={buttonStyle(lang === "es")}
      >
        <FlagES />
      </Focusable>
      <Focusable
        onActivate={() => setLang("en")}
        onClick={() => setLang("en")}
        aria-label={t("lang.english")}
        style={buttonStyle(lang === "en")}
      >
        <FlagEN />
      </Focusable>
    </Focusable>
  );
};
