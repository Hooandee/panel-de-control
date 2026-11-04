import duoCover from "../assets/duo-cover.jpg";
import eclipseCover from "../assets/eclipse-cover.jpg";
import hooandeeCover from "../assets/hooandee-cover.jpg";
import luminousAtlasCover from "../assets/luminous-atlas-cover.jpg";
import vidaCover from "../assets/vida-cover.jpg";
import type { Lang } from "../i18n/languages";
import { localizePublishedText, type PublishedThemeRelease } from "./remotePublication";

// Each Hooandee theme's cover, short line and description in every language Panel speaks, all in one place. The
// published catalog and early list carry es/en/it only (older Panels reject extra keys): there they are the fallback
// for those Panels and for themes that are not Hooandee's. Keep the three in step with the theme's registry entry.
interface ThemePresentation {
  cssLoaderName: string;
  cover: string;
  tagline: Readonly<Record<Lang, string>>;
  description: Readonly<Record<Lang, string>>;
}

const PRESENTATIONS: Readonly<Record<string, ThemePresentation>> = {
  "hooandee-vida": {
    cssLoaderName: "Hooandee Vida",
    cover: vidaCover,
    tagline: {
      es: "Un launcher con todo el espíritu de PS Vita",
      en: "A launcher with all the spirit of the PS Vita",
      it: "Un launcher con tutto lo spirito di PS Vita",
      de: "Ein Launcher mit dem Geist der PS Vita",
      "pt-BR": "Um launcher com todo o espírito do PS Vita",
      fr: "Un launcher avec tout l'esprit de la PS Vita",
    },
    description: {
      es: "Un launcher con todo el espíritu de PS Vita: tus juegos flotan como burbujas de cristal, con Amigos, Trofeos, música y sonidos propios.",
      en: "A launcher with all the spirit of the PS Vita: your games float as glass bubbles, with its own Friends, Trophies, music and sounds.",
      it: "Un launcher con tutto lo spirito di PS Vita: i tuoi giochi fluttuano come bolle di vetro, con Amici, Trofei, musica e suoni propri.",
      de: "Ein Launcher mit dem ganzen Geist der PS Vita: Deine Spiele schweben als Glasblasen, mit eigenen Freunden, Trophäen, Musik und Sounds.",
      "pt-BR": "Um launcher com todo o espírito do PS Vita: seus jogos flutuam como bolhas de vidro, com Amigos, Troféus, música e sons próprios.",
      fr: "Un launcher avec tout l'esprit de la PS Vita : vos jeux flottent comme des bulles de verre, avec ses propres Amis, Trophées, musique et sons.",
    },
  },
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
      es: "Duo es un tema inspirado en una de las consolas más queridas, con acceso directo a tus juegos, sonidos propios y una experiencia de lo más divertida.",
      en: "Duo is a theme inspired by one of the most beloved consoles, with quick access to your games, its own sounds and a really fun experience.",
      it: "Duo è un tema ispirato a una delle console più amate, con accesso diretto ai tuoi giochi, suoni propri e un'esperienza davvero divertente.",
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
      es: "Mi primer tema. Una versión más elegante de Steam inspirada en el cristal y las transparencias, con capas translúcidas y detalles sutiles que aportan profundidad sin perder claridad.",
      en: "My first theme. A more elegant take on Steam inspired by glass and transparency, with translucent layers and subtle details that add depth without sacrificing clarity.",
      it: "Il mio primo tema. Una versione più elegante di Steam ispirata al vetro e alle trasparenze, con strati traslucidi e dettagli discreti che aggiungono profondità senza rinunciare alla chiarezza.",
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
      es: "Un tema táctico inspirado en los menús de atlas y mapas de los RPG de estrategia. Pergamino verde oscuro, tinta marfil y marcos de latón, con portadas personalizables, menú de acceso rápido y elementos dinámicos.",
      en: "A tactical theme inspired by the atlas and map menus of strategy RPGs. Dark green parchment, ivory ink and brass frames, with customizable covers, a quick access menu and dynamic elements.",
      it: "Un tema tattico ispirato ai menu da atlante e mappa dei giochi di ruolo strategici. Pergamena verde scura, inchiostro avorio e cornici d'ottone, con copertine personalizzabili, menu di accesso rapido ed elementi dinamici.",
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
      es: "Un tema inspirado en el espacio y los eclipses. Tus juegos se convierten en planetas sobre un fondo negro de verdad, con estrellas y un brillo suave en lo que tienes seleccionado. Pensado para pantallas OLED, que es donde más luce.",
      en: "A theme inspired by space and eclipses. Your games become planets over a truly black background, with stars and a soft glow on whatever you have selected. Made for OLED screens, which is where it looks its best.",
      it: "Un tema ispirato allo spazio e alle eclissi. I tuoi giochi diventano pianeti su uno sfondo nero davvero, con le stelle e un bagliore leggero su ciò che hai selezionato. Pensato per gli schermi OLED, dove rende al meglio.",
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
  return presentationFor(release)?.description[lang] ?? localizePublishedText(release.description, lang);
}

export function themeTaglineFor(release: PublishedThemeRelease, lang: Lang): string {
  return presentationFor(release)?.tagline[lang] ?? themeDescriptionFor(release, lang);
}
