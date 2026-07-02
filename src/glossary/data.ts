// Glossary content lives here (not in the i18n dictionary) because it's bulky,
// bilingual prose. Only the modal's chrome strings go through i18n.
//
// Tone: written for a gamer who has never heard the term. Plain, conversational,
// and centred on how it affects your games. `term` is the display name (usually
// the same in both languages); the human explanation lives in `es` / `en`.

export interface GlossaryTerm {
  id: string;
  term: string;
  es: string;
  en: string;
}

export interface GlossaryCategory {
  id: string;
  es: string; // category title
  en: string;
  terms: GlossaryTerm[];
}

/** Pick the text for the active language. Accepts a term or a category. */
export function pick(entry: { es: string; en: string }, lang: "es" | "en"): string {
  return lang === "en" ? entry.en : entry.es;
}

export const CATEGORIES: GlossaryCategory[] = [
  {
    id: "power",
    es: "Potencia y batería",
    en: "Power and battery",
    terms: [
      {
        id: "tdp",
        term: "TDP",
        es: "Es cuánta energía dejas que gaste el chip mientras juegas, medida en vatios. Si le das más, los juegos van más finos pero la consola calienta y la batería vuela. Si le das menos, aguantas más rato de partida y todo va más fresquito aunque pierdas algo de rendimiento. Es la palanca que más vas a tocar en este panel.",
        en: "It's how much energy you let the chip spend while you play, measured in watts. Give it more and games run smoother, but the console heats up and the battery flies. Give it less and you get more play time with everything cooler, even if you lose a bit of performance. It's the lever you'll reach for most in this panel.",
      },
      {
        id: "watts",
        term: "Vatios (W)",
        es: "Es la unidad con la que se mide la potencia. Cuando ves un «17 W» es la energía que está tragando el chip en ese momento de la partida. Cuantos más vatios, más chicha y más calor.",
        en: "It's the unit power is measured in. When you see \"17 W\", that's the energy the chip is gulping down right then in your session. The more watts, the more muscle and the more heat.",
      },
      {
        id: "auto-tdp",
        term: "Auto‑TDP",
        es: "En vez de fijar tú los vatios, la consola los sube y baja sola según lo que pida cada juego. En una pelea intensa te da caña y en un menú tranquilo afloja, para que no gastes batería de más sin enterarte.",
        en: "Instead of setting the watts yourself, the console raises and lowers them on its own based on what each game asks for. It pushes hard in a hectic fight and eases off in a quiet menu, so you don't burn extra battery without realising.",
      },
      {
        id: "boost",
        term: "Boost",
        es: "Un chute de potencia de unos segundos cuando el juego lo pide de golpe, como al entrar a una zona nueva o cargar una partida. Te da ese empujón puntual sin dejar el consumo alto todo el rato.",
        en: "A few-second shot of power when the game suddenly needs it, like walking into a new area or loading a save. It gives you that quick push without keeping your power draw high the whole time.",
      },
      {
        id: "charge-limit",
        term: "Límite de carga",
        es: "Le dices a la consola que no llene la batería hasta arriba y se quede en un tope, por ejemplo el 80%. A las baterías les sienta mal vivir siempre llenas, así que si sueles jugar enchufado esto hace que te dure sana muchos más años.",
        en: "You tell the console to stop short of a full battery and hold at a cap, say 80%. Batteries hate sitting full all the time, so if you usually play plugged in this keeps yours healthy for many more years.",
      },
      {
        id: "battery-health",
        term: "Salud de la batería",
        es: "Es cuánta batería le queda a tu consola comparada con el día que la estrenaste. Con el uso todas se van gastando, así que si marca 90% quiere decir que ahora aguanta un 90% de las partidas que aguantaba nueva.",
        en: "It's how much battery your console has left compared to the day it was new. They all wear down with use, so if it reads 90% it means it now lasts for 90% of the play it managed when new.",
      },
    ],
  },
  {
    id: "image",
    es: "Imagen y fluidez",
    en: "Image and smoothness",
    terms: [
      {
        id: "fps",
        term: "FPS",
        es: "Son los fotogramas por segundo, o sea cuántas imágenes te dibuja el juego cada segundo. Cuantos más, más suave se mueve todo. A 60 se siente mantequilla y por debajo de 30 empieza a dar tirones molestos.",
        en: "Frames per second, meaning how many images the game draws you each second. The more, the smoother everything moves. At 60 it feels like butter, and below 30 it starts to stutter and get annoying.",
      },
      {
        id: "fsr",
        term: "FSR",
        es: "Un truco de AMD que hace que el juego se vea casi igual de bien pero pidiéndole menos a la consola, así ganas fluidez y batería sin apenas notar la diferencia. Se activa dentro del juego o en Steam, no desde aquí.",
        en: "An AMD trick that keeps a game looking nearly as good while asking less of the console, so you gain smoothness and battery with barely any difference. You switch it on inside the game or in Steam, not from here.",
      },
      {
        id: "dlss",
        term: "DLSS",
        es: "La misma idea que FSR pero de NVIDIA. Sube la fluidez y la imagen queda casi igual de nítida, aunque solo va en equipos con gráfica NVIDIA, que no suelen ser las portátiles (casi todas montan AMD).",
        en: "The same idea as FSR but from NVIDIA. It bumps up smoothness and the image stays nearly as sharp, though it only runs on machines with NVIDIA graphics, which handhelds usually aren't (nearly all use AMD).",
      },
      {
        id: "xess",
        term: "XeSS",
        es: "La versión de Intel del mismo truco que FSR y DLSS. Sirve para que el juego corra más suave sin que pierdas una nitidez que se note.",
        en: "Intel's take on the same trick as FSR and DLSS. It helps a game run smoother without a drop in sharpness you'd actually notice.",
      },
      {
        id: "frame-gen",
        term: "Generación de fotogramas",
        es: "La consola calcula fotogramas de relleno y los cuela entre los reales para que el movimiento se vea más suave. Ayuda a que todo fluya, pero tiene truco: gasta algo de gráfica y a veces los controles responden un pelín más tarde.",
        en: "The console works out filler frames and slips them between the real ones so motion looks smoother. It helps everything flow, but there's a catch: it uses some graphics power and the controls can feel a touch slower to respond.",
      },
      {
        id: "optiscaler",
        term: "Optiscaler",
        es: "Una herramienta de la comunidad que te deja meter estos trucos de fluidez, como FSR, en juegos que no los traían de fábrica. Es un extra que instalas aparte y no tiene que ver con este panel.",
        en: "A community tool that lets you drop these smoothness tricks, like FSR, into games that didn't ship with them. It's an extra you install separately and has nothing to do with this panel.",
      },
      {
        id: "vrr",
        term: "VRR",
        es: "La pantalla acompasa su ritmo al del juego para que no veas cortes raros en la imagen cuando los FPS bailan arriba y abajo. No sube los FPS, pero deja el movimiento más limpio y agradable.",
        en: "The screen paces itself to the game so you don't get those ugly torn frames when the FPS bounces up and down. It won't raise your FPS, but it keeps the motion cleaner and nicer to play on.",
      },
      {
        id: "refresh",
        term: "Tasa de refresco (Hz)",
        es: "Cuántas veces por segundo se refresca la pantalla. Una de 90 Hz puede enseñarte hasta 90 imágenes por segundo, y cuanto más alta sea, más fluido puedes llegar a ver el juego.",
        en: "How many times per second the screen refreshes. A 90 Hz one can show you up to 90 images per second, and the higher it goes, the smoother the game can look.",
      },
    ],
  },
  {
    id: "hardware",
    es: "El chip por dentro",
    en: "Inside the chip",
    terms: [
      {
        id: "apu",
        term: "APU",
        es: "Es el chip principal de la consola. Tiene la gracia de juntar en una sola pieza el cerebro (el procesador) y la parte que dibuja los gráficos, lo que ahorra sitio y batería, algo que le viene de perlas a una portátil.",
        en: "It's the console's main chip. Its neat trick is packing the brain (the processor) and the graphics into one piece, which saves space and battery, something a handheld really appreciates.",
      },
      {
        id: "cpu",
        term: "CPU (procesador)",
        es: "El cerebro de la consola. Se encarga de la lógica del juego, la física, lo que hacen los enemigos y todo lo que no sea pintar la imagen en pantalla.",
        en: "The console's brain. It handles the game logic, the physics, what the enemies do and everything that isn't painting the picture on screen.",
      },
      {
        id: "gpu",
        term: "GPU (gráfica)",
        es: "La parte del chip que dibuja todo lo que ves en pantalla. En los juegos suele ser la que más suda, y por eso el panel se fija sobre todo en ella para saber cuánta potencia hace falta.",
        en: "The part of the chip that draws everything you see. In games it's usually the one sweating hardest, which is why the panel watches it most to gauge how much power you need.",
      },
      {
        id: "cores-threads",
        term: "Núcleos e hilos",
        es: "Los núcleos son como las manos del procesador: cuantas más tenga, más cosas puede hacer a la vez. Los hilos son los carriles de trabajo de cada mano, y algunos chips le dan dos carriles a cada núcleo para exprimirlo mejor.",
        en: "Cores are like the processor's hands: the more it has, the more it can do at once. Threads are each hand's work lanes, and some chips give every core two lanes to squeeze more out of it.",
      },
      {
        id: "smt",
        term: "Multihilo (SMT)",
        es: "Deja que cada núcleo del procesador lleve dos tareas a la vez en lugar de una. Encendido rinde algo más y apagado gasta y calienta un poco menos. Jugando la diferencia es mínima.",
        en: "Lets each processor core juggle two tasks at once instead of one. On, it performs a bit more; off, it uses and heats a little less. While gaming the difference is tiny.",
      },
      {
        id: "rdna",
        term: "RDNA",
        es: "Es el nombre de la tecnología gráfica de AMD que llevan casi todas estas consolas. Cada generación (RDNA 2, RDNA 3 y demás) es más nueva y potente. Vamos, que es el apellido de la parte que mueve los gráficos.",
        en: "It's the name of AMD's graphics tech inside almost all these consoles. Each generation (RDNA 2, RDNA 3 and so on) is newer and stronger. In short, it's the surname of the bit that pushes the graphics.",
      },
    ],
  },
  {
    id: "cooling",
    es: "Ventiladores y temperatura",
    en: "Fans and temperature",
    terms: [
      {
        id: "fan-curve",
        term: "Curva de ventilador",
        es: "Es la norma que decide a qué velocidad giran los ventiladores según lo caliente que vaya la consola. Puedes ponerla más silenciosa para no oír ruido o más marchosa para jugar fresco, y el panel también puede aprenderla por ti a base de ver cómo juegas.",
        en: "It's the rule that decides how fast the fans spin based on how hot the console runs. You can set it quieter to keep the noise down or more aggressive to play cool, and the panel can also learn it for you by watching how you play.",
      },
      {
        id: "rpm",
        term: "RPM",
        es: "Son las vueltas por minuto del ventilador, o sea lo rápido que está girando. A más RPM, mejor enfría pero más se le oye.",
        en: "The fan's revolutions per minute, meaning how fast it's spinning. Higher RPM cools better but you hear it more.",
      },
      {
        id: "temp",
        term: "Temperatura",
        es: "Lo caliente que va el chip, en grados. Que suba mientras juegas es de lo más normal, y para eso están los ventiladores y el TDP, para mantenerla a raya y que la consola no sufra.",
        en: "How hot the chip runs, in degrees. It's perfectly normal for it to climb while you play, and that's what the fans and TDP are for, keeping it in check so the console doesn't suffer.",
      },
    ],
  },
  {
    id: "general",
    es: "El mundo de las portátiles",
    en: "The handheld world",
    terms: [
      {
        id: "handheld",
        term: "Consola portátil (handheld)",
        es: "Un PC con pinta de consola que juegas con las manos, como la Steam Deck, la ROG Ally o la Legion Go. Mueven juegos de PC de verdad pero con batería y allá donde te los lleves.",
        en: "A PC shaped like a console that you play holding in your hands, like the Steam Deck, ROG Ally or Legion Go. They run real PC games but on battery and wherever you take them.",
      },
      {
        id: "decky",
        term: "Decky Loader",
        es: "Es el programa que te permite instalar complementos como este panel en la consola. Piénsalo como una tienda de apps que le añade funciones nuevas al menú de Steam.",
        en: "It's the program that lets you install add-ons like this panel on your console. Think of it as an app store that adds new features to the Steam menu.",
      },
      {
        id: "qam",
        term: "Menú de acceso rápido (QAM)",
        es: "Es ese menú lateral que abres con un botón sin salir del juego, donde tocas brillo, volumen y complementos como este. Es la casa de este panel.",
        en: "It's that side menu you pop open with a button without leaving the game, where you tweak brightness, volume and add-ons like this one. It's this panel's home.",
      },
      {
        id: "telemetry",
        term: "Aprendizaje / telemetría",
        es: "El panel va apuntando cómo se porta cada juego (temperatura, potencia, ventilador) para poder recomendarte los mejores ajustes. Todo se queda dentro de tu consola y no sale de ahí jamás, y lo puedes apagar cuando te apetezca.",
        en: "The panel keeps notes on how each game behaves (temperature, power, fan) so it can recommend the best settings for you. It all stays inside your console and never leaves, and you can turn it off whenever you like.",
      },
    ],
  },
];
