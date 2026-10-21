import duoCover from "../assets/duo-cover.jpg";
import eclipseCover from "../assets/eclipse-cover.jpg";
import hooandeeCover from "../assets/hooandee-cover.jpg";
import luminousAtlasCover from "../assets/luminous-atlas-cover.jpg";
import type { Lang } from "../i18n/languages";
import { localizePublishedText, type PublishedThemeRelease } from "./remotePublication";

// The published catalog only carries es/en/it and rejects extra keys on older Panels, so the
// remaining languages of each Hooandee theme ship here, next to its cover.
type LocalLanguage = "de" | "pt-BR" | "fr";

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
      fr: "Un accueil façon console, avec dock et sons",
    },
    description: {
      de: "Duo ist ein Theme, inspiriert von einer der beliebtesten Konsolen, mit direktem Zugriff auf deine Spiele, eigenen Sounds und einem richtig unterhaltsamen Erlebnis.",
      "pt-BR": "Duo é um tema inspirado em um dos consoles mais queridos, com acesso direto aos seus jogos, sons próprios e uma experiência muito divertida.",
      fr: "Duo est un thème inspiré de l'une des consoles les plus appréciées, avec un accès direct à vos jeux, des sons bien à lui et une expérience vraiment amusante.",
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
      fr: "Steam en verre, clair ou sombre",
    },
    description: {
      de: "Mein erstes Theme. Eine elegantere Version von Steam, inspiriert von Glas und Transparenz, mit durchscheinenden Ebenen und dezenten Details, die Tiefe geben, ohne an Klarheit zu verlieren.",
      "pt-BR": "Meu primeiro tema. Uma versão mais elegante do Steam inspirada no vidro e nas transparências, com camadas translúcidas e detalhes sutis que dão profundidade sem perder a clareza.",
      fr: "Mon premier thème. Une version plus élégante de Steam, inspirée du verre et de la transparence, avec des couches translucides et des détails discrets qui apportent de la profondeur sans rien perdre en lisibilité.",
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
      fr: "Les menus de carte d'un RPG tactique",
    },
    description: {
      de: "Ein taktisches Theme, inspiriert von den Atlas- und Kartenmenüs strategischer Rollenspiele. Dunkelgrünes Pergament, elfenbeinfarbene Tinte und Messingrahmen, mit anpassbaren Covern, einem Schnellzugriffsmenü und dynamischen Elementen.",
      "pt-BR": "Um tema tático inspirado nos menus de atlas e mapas dos RPGs de estratégia. Pergaminho verde-escuro, tinta marfim e molduras de latão, com capas personalizáveis, menu de acesso rápido e elementos dinâmicos.",
      fr: "Un thème tactique inspiré des menus d'atlas et de cartes des RPG de stratégie. Parchemin vert foncé, encre ivoire et cadres en laiton, avec des jaquettes personnalisables, un menu d'accès rapide et des éléments dynamiques.",
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
      fr: "Vos jeux en planètes, pensé pour l'OLED",
    },
    description: {
      de: "Ein Theme, inspiriert vom Weltall und von Sonnenfinsternissen. Deine Spiele werden zu Planeten auf einem wirklich schwarzen Hintergrund, mit Sternen und einem sanften Leuchten auf dem, was du gerade ausgewählt hast. Gemacht für OLED-Bildschirme, denn dort kommt es am besten zur Geltung.",
      "pt-BR": "Um tema inspirado no espaço e nos eclipses. Seus jogos viram planetas sobre um fundo preto de verdade, com estrelas e um brilho suave no que você tem selecionado. Feito para telas OLED, que é onde ele fica mais bonito.",
      fr: "Un thème inspiré de l'espace et des éclipses. Vos jeux deviennent des planètes sur un fond vraiment noir, avec des étoiles et une douce lueur sur ce que vous avez sélectionné. Pensé pour les écrans OLED, car c'est là qu'il rend le mieux.",
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
  const local = lang === "de" || lang === "pt-BR" || lang === "fr" ? presentationFor(release)?.description[lang] : undefined;
  return local ?? localizePublishedText(release.description, lang);
}

export function themeTaglineFor(release: PublishedThemeRelease, lang: Lang): string {
  return presentationFor(release)?.tagline[lang] ?? themeDescriptionFor(release, lang);
}
