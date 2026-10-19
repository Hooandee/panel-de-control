import duoCover from "../assets/duo-cover.jpg";
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
  tagline: Readonly<Record<Lang, string>>;
  description: Readonly<Record<LocalLanguage, string>>;
}

const PRESENTATIONS: Readonly<Record<string, ThemePresentation>> = {
  "hooandee-duo": {
    cssLoaderName: "Hooandee Duo",
    cover: duoCover,
    tagline: {
      es: "Tu Inicio de consola, con dock y sonidos",
      en: "A console home with a dock and sounds",
      it: "Una home da console, con dock e suoni",
      de: "Konsolen-Startseite mit Dock und Sounds",
      "pt-BR": "Início de console, com dock e sons",
    },
    description: {
      de: "Duo ist ein Theme, inspiriert von einer der beliebtesten Konsolen, mit direktem Zugriff auf deine Spiele, eigenen Sounds und einem richtig unterhaltsamen Erlebnis.",
      "pt-BR": "Duo é um tema inspirado em um dos consoles mais queridos, com acesso direto aos seus jogos, sons próprios e uma experiência muito divertida.",
    },
  },
  "hooandee-gallery": {
    cssLoaderName: "Hooandee Gallery",
    cover: hooandeeCover,
    tagline: {
      es: "Steam en cristal, claro u oscuro",
      en: "Steam in glass, light or dark",
      it: "Steam in vetro, chiaro o scuro",
      de: "Steam aus Glas, hell oder dunkel",
      "pt-BR": "Steam em vidro, claro ou escuro",
    },
    description: {
      de: "Mein erstes Theme. Eine elegantere Version von Steam, inspiriert von Glas und Transparenz, mit durchscheinenden Ebenen und dezenten Details, die Tiefe geben, ohne an Klarheit zu verlieren.",
      "pt-BR": "Meu primeiro tema. Uma versão mais elegante do Steam inspirada no vidro e nas transparências, com camadas translúcidas e detalhes sutis que dão profundidade sem perder a clareza.",
    },
  },
  "hooandee-luminous-atlas": {
    cssLoaderName: "Hooandee Luminous Atlas",
    cover: luminousAtlasCover,
    tagline: {
      es: "Los menús de mapa de un RPG táctico",
      en: "The map menus of a tactics RPG",
      it: "I menu mappa di un GDR tattico",
      de: "Die Kartenmenüs eines Taktik-RPGs",
      "pt-BR": "Os menus de mapa de um RPG tático",
    },
    description: {
      de: "Ein taktisches Theme, inspiriert von den Atlas- und Kartenmenüs strategischer Rollenspiele. Dunkelgrünes Pergament, elfenbeinfarbene Tinte und Messingrahmen, mit anpassbaren Covern, einem Schnellzugriffsmenü und dynamischen Elementen.",
      "pt-BR": "Um tema tático inspirado nos menus de atlas e mapas dos RPGs de estratégia. Pergaminho verde-escuro, tinta marfim e molduras de latão, com capas personalizáveis, menu de acesso rápido e elementos dinâmicos.",
    },
  },
  "hooandee-eclipse": {
    cssLoaderName: "Hooandee Eclipse",
    cover: eclipseCover,
    tagline: {
      es: "Tus juegos como planetas, pensado para OLED",
      en: "Your games as planets, made for OLED",
      it: "I tuoi giochi come pianeti, pensato per OLED",
      de: "Deine Spiele als Planeten, für OLED gemacht",
      "pt-BR": "Seus jogos como planetas, feito para OLED",
    },
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

export function themeTaglineFor(release: PublishedThemeRelease, lang: Lang): string {
  return presentationFor(release)?.tagline[lang] ?? themeDescriptionFor(release, lang);
}
