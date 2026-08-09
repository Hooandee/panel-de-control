import type { Lang } from "../i18n";

interface UpdaterStrings {
  panel: {
    version: string;
    latest: string;
    newPrefix: string;
    checking: string;
    check: string;
    update: string;
    error: string;
  };
  modal: {
    title: string;
    noNotes: string;
    install: string;
    installing: string;
    installed: string;
    restartNote: string;
    restart: string;
    failed: string;
  };
  availableTitle: string;
}

const STRINGS: Record<Lang, UpdaterStrings> = {
  es: {
    panel: {
      version: "Versión",
      latest: "(última)",
      newPrefix: "nueva",
      checking: "buscando…",
      check: "Buscar actualizaciones",
      update: "Ver novedades e instalar",
      error: "No se pudo comprobar. Revisa tu conexión.",
    },
    modal: {
      title: "Novedades",
      noNotes: "Sin notas para esta versión.",
      install: "Instalar actualización",
      installing: "Instalando…",
      installed: "Actualización instalada.",
      restartNote: "Reinicia Decky para aplicarla.",
      restart: "Reiniciar Decky",
      failed: "No se pudo instalar. Inténtalo de nuevo.",
    },
    availableTitle: "Actualización disponible",
  },
  en: {
    panel: {
      version: "Version",
      latest: "(latest)",
      newPrefix: "new",
      checking: "checking…",
      check: "Check for updates",
      update: "See what's new & install",
      error: "Couldn't check. Check your connection.",
    },
    modal: {
      title: "What's new",
      noNotes: "No notes for this release.",
      install: "Install update",
      installing: "Installing…",
      installed: "Update installed.",
      restartNote: "Restart Decky to apply it.",
      restart: "Restart Decky",
      failed: "Install failed. Please try again.",
    },
    availableTitle: "Update available",
  },
  it: {
    panel: {
      version: "Versione",
      latest: "(più recente)",
      newPrefix: "disponibile",
      checking: "verifica in corso…",
      check: "Cerca aggiornamenti",
      update: "Scopri le novità e installa",
      error: "Verifica non riuscita. Controlla la connessione.",
    },
    modal: {
      title: "Novità",
      noNotes: "Nessuna nota per questa versione.",
      install: "Installa l'aggiornamento",
      installing: "Installazione in corso…",
      installed: "Aggiornamento installato.",
      restartNote: "Riavvia Decky per applicare l'aggiornamento.",
      restart: "Riavvia Decky",
      failed: "Installazione non riuscita. Riprova.",
    },
    availableTitle: "Aggiornamento disponibile",
  },
};

export function getUpdaterStrings(lang: Lang): UpdaterStrings {
  return STRINGS[lang];
}
