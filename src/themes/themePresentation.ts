import eclipseCover from "../assets/eclipse-cover.jpg";
import hooandeeCover from "../assets/hooandee-cover.jpg";
import luminousAtlasCover from "../assets/luminous-atlas-cover.jpg";
import type { Lang } from "../i18n/languages";
import { localizePublishedText, type PublishedThemeRelease } from "./remotePublication";

// The published catalog only carries es/en/it and rejects extra keys on older Panels, so the
// remaining languages of each Hooandee theme ship here, next to its cover.
type LocalLanguage = "de" | "pt-BR";

interface ThemePresentation {
  cssLoaderName: string;
  cover: string;
  description: Readonly<Record<LocalLanguage, string>>;
}

const PRESENTATIONS: Readonly<Record<string, ThemePresentation>> = {
  "hooandee-gallery": {
    cssLoaderName: "Hooandee Gallery",
    cover: hooandeeCover,
    description: {
      de: "Mein erstes Theme. Eine elegantere Version von Steam, inspiriert von Glas und Transparenz, mit durchscheinenden Ebenen und dezenten Details, die Tiefe geben, ohne an Klarheit zu verlieren.",
      "pt-BR": "Meu primeiro tema. Uma versão mais elegante do Steam inspirada no vidro e nas transparências, com camadas translúcidas e detalhes sutis que dão profundidade sem perder a clareza.",
    },
  },
  "hooandee-luminous-atlas": {
    cssLoaderName: "Hooandee Luminous Atlas",
    cover: luminousAtlasCover,
    description: {
      de: "Ein taktisches Theme, inspiriert von den Atlas- und Kartenmenüs strategischer Rollenspiele. Dunkelgrünes Pergament, elfenbeinfarbene Tinte und Messingrahmen, mit anpassbaren Covern, einem Schnellzugriffsmenü und dynamischen Elementen.",
      "pt-BR": "Um tema tático inspirado nos menus de atlas e mapas dos RPGs de estratégia. Pergaminho verde-escuro, tinta marfim e molduras de latão, com capas personalizáveis, menu de acesso rápido e elementos dinâmicos.",
    },
  },
  "hooandee-eclipse": {
    cssLoaderName: "Hooandee Eclipse",
    cover: eclipseCover,
    description: {
      de: "Ein Theme, inspiriert vom Weltall und von Sonnenfinsternissen. Deine Spiele werden zu Planeten auf einem wirklich schwarzen Hintergrund, mit Sternen und einem sanften Leuchten auf dem, was du gerade ausgewählt hast. Gemacht für OLED-Bildschirme, denn dort kommt es am besten zur Geltung.",
      "pt-BR": "Um tema inspirado no espaço e nos eclipses. Seus jogos viram planetas sobre um fundo preto de verdade, com estrelas e um brilho suave no que você tem selecionado. Feito para telas OLED, que é onde ele fica mais bonito.",
    },
  },
};

function presentationFor(release: PublishedThemeRelease): ThemePresentation | undefined {
  const entry = Object.prototype.hasOwnProperty.call(PRESENTATIONS, release.catalogId) ? PRESENTATIONS[release.catalogId] : undefined;
  return entry?.cssLoaderName === release.cssLoaderName ? entry : undefined;
}

export function themeCoverFor(release: PublishedThemeRelease): string | undefined {
  return presentationFor(release)?.cover;
}

export function themeDescriptionFor(release: PublishedThemeRelease, lang: Lang): string {
  const local = lang === "de" || lang === "pt-BR" ? presentationFor(release)?.description[lang] : undefined;
  return local ?? localizePublishedText(release.description, lang);
}
