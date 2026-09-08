// Glossary content lives here (not in the i18n dictionary) because it's bulky,
// multilingual prose. Only the modal's chrome strings go through i18n.

import type { Lang } from "../i18n";

export interface GlossaryTerm {
  id: string;
  term: string;
  termIt: string;
  termDe: string;
  es: string;
  en: string;
  it: string;
  de: string;
}

export interface GlossaryCategory {
  id: string;
  es: string; // category title
  en: string;
  it: string;
  de: string;
  terms: GlossaryTerm[];
}

/** Pick the text for the active language. Accepts a term or a category. */
export function pick(entry: { es: string; en: string; it: string; de: string }, lang: Lang): string {
  return entry[lang];
}

export function pickTerm(entry: GlossaryTerm, lang: Lang): string {
  if (lang === "it") return entry.termIt;
  if (lang === "de") return entry.termDe;
  return entry.term;
}

export const CATEGORIES: GlossaryCategory[] = [
  {
    id: "power",
    es: "Potencia y batería",
    en: "Power and battery",
    it: "Potenza e batteria",
    de: "Leistung und Akku",
    terms: [
      {
        id: "tdp",
        term: "TDP",
        termIt: "TDP",
        termDe: "TDP",
        es: "Es cuánta energía dejas que gaste el chip mientras juegas, medida en vatios. Si le das más, los juegos van más finos pero la consola calienta y la batería vuela. Si le das menos, aguantas más rato de partida y todo va más fresquito aunque pierdas algo de rendimiento. Es la palanca que más vas a tocar en este panel.",
        en: "It's how much energy you let the chip spend while you play, measured in watts. Give it more and games run smoother, but the console heats up and the battery flies. Give it less and you get more play time with everything cooler, even if you lose a bit of performance. It's the lever you'll reach for most in this panel.",
        it: "Indica quanta energia permetti al chip di consumare mentre giochi, misurata in watt. Se lo aumenti, i giochi girano meglio, ma il dispositivo si scalda e la batteria si scarica rapidamente. Se lo riduci, puoi giocare più a lungo e mantenere temperature più basse, rinunciando a un po' di prestazioni. È il controllo che userai più spesso in questo pannello.",
        de: "Gibt an, wie viel Energie der Chip beim Spielen verbrauchen darf, gemessen in Watt. Mit mehr TDP laufen Spiele flüssiger, das Gerät wird aber wärmer und der Akku leert sich schneller. Mit weniger TDP kannst du länger und kühler spielen, verlierst jedoch etwas Leistung. Diese Einstellung wirst du im Panel am häufigsten verwenden.",
      },
      {
        id: "watts",
        term: "Vatios (W)",
        termIt: "Watt (W)",
        termDe: "Watt (W)",
        es: "Es la unidad con la que se mide la potencia. Cuando ves un «17 W» es la energía que está tragando el chip en ese momento de la partida. Cuantos más vatios, más chicha y más calor.",
        en: "It's the unit power is measured in. When you see \"17 W\", that's the energy the chip is gulping down right then in your session. The more watts, the more muscle and the more heat.",
        it: "È l'unità con cui si misura la potenza. Quando leggi «17 W», indica quanta energia sta consumando il chip in quel momento. In generale, più watt significano più potenza e più calore.",
        de: "Watt ist die Einheit für Leistung. Wenn du 17 W siehst, verbraucht der Chip in diesem Moment so viel Energie. Mehr Watt bedeuten in der Regel mehr Leistung, aber auch mehr Wärme.",
      },
      {
        id: "auto-tdp",
        term: "Auto‑TDP",
        termIt: "Auto-TDP",
        termDe: "Auto-TDP",
        es: "En vez de fijar tú los vatios, la consola los sube y baja sola según lo que pida cada juego. En una pelea intensa te da caña y en un menú tranquilo afloja, para que no gastes batería de más sin enterarte.",
        en: "Instead of setting the watts yourself, the console raises and lowers them on its own based on what each game asks for. It pushes hard in a hectic fight and eases off in a quiet menu, so you don't burn extra battery without realising.",
        it: "Invece di impostare un valore fisso, il dispositivo aumenta e riduce da solo i watt in base alle richieste del gioco. Offre più potenza durante uno scontro intenso e la riduce in un menu tranquillo, evitando consumi inutili.",
        de: "Statt einen festen Wattwert einzustellen, erhöht oder senkt das Gerät die Leistung passend zum Bedarf des Spiels. In einem intensiven Kampf gibt es mehr Leistung, in einem ruhigen Menü weniger. So wird der Akku nicht unnötig belastet.",
      },
      {
        id: "boost",
        term: "Boost",
        termIt: "Boost",
        termDe: "Boost",
        es: "Un chute de potencia de unos segundos cuando el juego lo pide de golpe, como al entrar a una zona nueva o cargar una partida. Te da ese empujón puntual sin dejar el consumo alto todo el rato.",
        en: "A few-second shot of power when the game suddenly needs it, like walking into a new area or loading a save. It gives you that quick push without keeping your power draw high the whole time.",
        it: "Un breve aumento di potenza quando il gioco ne ha improvvisamente bisogno, ad esempio entrando in una nuova area o caricando una partita. Offre una spinta momentanea senza mantenere sempre elevato il consumo.",
        de: "Ein kurzer Leistungsschub, wenn ein Spiel plötzlich mehr benötigt, etwa beim Betreten eines neuen Gebiets oder beim Laden eines Spielstands. So steht vorübergehend mehr Leistung bereit, ohne den Verbrauch dauerhaft hoch zu halten.",
      },
      {
        id: "charge-limit",
        term: "Límite de carga",
        termIt: "Limite di carica",
        termDe: "Ladelimit",
        es: "Le dices a la consola que no llene la batería hasta arriba y se quede en un tope, por ejemplo el 80%. A las baterías les sienta mal vivir siempre llenas, así que si sueles jugar enchufado esto hace que te dure sana muchos más años.",
        en: "You tell the console to stop short of a full battery and hold at a cap, say 80%. Batteries hate sitting full all the time, so if you usually play plugged in this keeps yours healthy for many more years.",
        it: "Impedisce alla batteria di caricarsi completamente e la mantiene a una soglia, ad esempio l'80%. Restare sempre al 100% accelera l'usura, quindi questa opzione aiuta a conservarla più a lungo se giochi spesso con il caricatore collegato.",
        de: "Begrenzt den Akkustand auf einen Wert wie 80 Prozent, statt den Akku vollständig zu laden. Ein dauerhaft voller Akku altert schneller. Wenn du häufig am Netzteil spielst, kann ein Ladelimit seine Lebensdauer verlängern.",
      },
      {
        id: "battery-health",
        term: "Salud de la batería",
        termIt: "Stato di salute della batteria",
        termDe: "Akkuzustand",
        es: "Es cuánta batería le queda a tu consola comparada con el día que la estrenaste. Con el uso todas se van gastando, así que si marca 90% quiere decir que ahora aguanta un 90% de las partidas que aguantaba nueva.",
        en: "It's how much battery your console has left compared to the day it was new. They all wear down with use, so if it reads 90% it means it now lasts for 90% of the play it managed when new.",
        it: "Indica quanta capacità conserva la batteria rispetto a quando era nuova. Tutte le batterie si usurano nel tempo: un valore del 90% significa che oggi offre circa il 90% dell'autonomia iniziale.",
        de: "Zeigt, wie viel Kapazität der Akku im Vergleich zum Neuzustand noch besitzt. Jeder Akku nutzt sich mit der Zeit ab. Ein Wert von 90 Prozent bedeutet, dass heute noch ungefähr 90 Prozent der ursprünglichen Laufzeit verfügbar sind.",
      },
    ],
  },
  {
    id: "image",
    es: "Imagen y fluidez",
    en: "Image and smoothness",
    it: "Immagine e fluidità",
    de: "Bild und flüssige Darstellung",
    terms: [
      {
        id: "fps",
        term: "FPS",
        termIt: "FPS",
        termDe: "FPS",
        es: "Son los fotogramas por segundo, o sea cuántas imágenes te dibuja el juego cada segundo. Cuantos más, más suave se mueve todo. A 60 se siente mantequilla y por debajo de 30 empieza a dar tirones molestos.",
        en: "Frames per second, meaning how many images the game draws you each second. The more, the smoother everything moves. At 60 it feels like butter, and below 30 it starts to stutter and get annoying.",
        it: "Sono i fotogrammi al secondo, cioè quante immagini il gioco disegna ogni secondo. Più sono, più il movimento appare fluido. A 60 FPS l'immagine è molto scorrevole, mentre sotto i 30 gli scatti iniziano a farsi notare.",
        de: "Frames pro Sekunde, also die Anzahl der Bilder, die ein Spiel pro Sekunde zeichnet. Je höher der Wert, desto flüssiger wirken Bewegungen. 60 FPS fühlen sich sehr geschmeidig an, unter 30 werden Ruckler deutlich spürbar.",
      },
      {
        id: "fsr",
        term: "FSR",
        termIt: "FSR",
        termDe: "FSR",
        es: "Un truco de AMD que hace que el juego se vea casi igual de bien pero pidiéndole menos a la consola, así ganas fluidez y batería sin apenas notar la diferencia. Se activa dentro del juego o en Steam, no desde aquí.",
        en: "An AMD trick that keeps a game looking nearly as good while asking less of the console, so you gain smoothness and battery with barely any difference. You switch it on inside the game or in Steam, not from here.",
        it: "Una tecnologia AMD che riduce il lavoro richiesto al dispositivo mantenendo una buona qualità dell'immagine. In questo modo puoi guadagnare fluidità e autonomia con differenze visive minime. Si attiva nel gioco o in Steam, non da questo pannello.",
        de: "Eine AMD-Technik, die ein Spiel mit weniger Rechenaufwand fast genauso gut aussehen lässt. Dadurch gewinnst du Leistung und Akkulaufzeit bei meist kleinen sichtbaren Unterschieden. Aktiviert wird sie im Spiel oder in Steam, nicht in diesem Panel.",
      },
      {
        id: "dlss",
        term: "DLSS",
        termIt: "DLSS",
        termDe: "DLSS",
        es: "La misma idea que FSR pero de NVIDIA. Sube la fluidez y la imagen queda casi igual de nítida, aunque solo va en equipos con gráfica NVIDIA, que no suelen ser las portátiles (casi todas montan AMD).",
        en: "The same idea as FSR but from NVIDIA. It bumps up smoothness and the image stays nearly as sharp, though it only runs on machines with NVIDIA graphics, which handhelds usually aren't (nearly all use AMD).",
        it: "La tecnologia NVIDIA basata sulla stessa idea di FSR. Aumenta la fluidità mantenendo l'immagine quasi altrettanto nitida, ma funziona solo con GPU NVIDIA, poco comuni sui dispositivi portatili che usano quasi tutti AMD.",
        de: "NVIDIAs Variante derselben Grundidee wie FSR. Sie verbessert die Leistung, während das Bild fast genauso scharf bleibt. DLSS funktioniert jedoch nur mit NVIDIA-GPUs, die in Handhelds selten sind, weil dort meistens AMD-Hardware steckt.",
      },
      {
        id: "xess",
        term: "XeSS",
        termIt: "XeSS",
        termDe: "XeSS",
        es: "La versión de Intel del mismo truco que FSR y DLSS. Sirve para que el juego corra más suave sin que pierdas una nitidez que se note.",
        en: "Intel's take on the same trick as FSR and DLSS. It helps a game run smoother without a drop in sharpness you'd actually notice.",
        it: "La versione Intel della stessa tecnologia usata da FSR e DLSS. Aiuta il gioco a essere più fluido senza una perdita di nitidezza evidente.",
        de: "Intels Variante derselben Technik wie FSR und DLSS. Sie lässt ein Spiel flüssiger laufen, ohne dass die Bildschärfe sichtbar stark nachlässt.",
      },
      {
        id: "frame-gen",
        term: "Generación de fotogramas",
        termIt: "Generazione di fotogrammi",
        termDe: "Frame-Generierung",
        es: "La consola calcula fotogramas de relleno y los cuela entre los reales para que el movimiento se vea más suave. Ayuda a que todo fluya, pero tiene truco: gasta algo de gráfica y a veces los controles responden un pelín más tarde.",
        en: "The console works out filler frames and slips them between the real ones so motion looks smoother. It helps everything flow, but there's a catch: it uses some graphics power and the controls can feel a touch slower to respond.",
        it: "Il dispositivo calcola fotogrammi aggiuntivi e li inserisce tra quelli reali per rendere il movimento più fluido. Il risultato può essere ottimo, ma richiede parte della potenza grafica e può aggiungere un lieve ritardo ai comandi.",
        de: "Das Gerät berechnet zusätzliche Bilder und fügt sie zwischen den echten Frames ein, damit Bewegungen flüssiger wirken. Das Ergebnis kann sehr gut aussehen, benötigt aber einen Teil der Grafikleistung und kann die Eingabeverzögerung leicht erhöhen.",
      },
      {
        id: "optiscaler",
        term: "Optiscaler",
        termIt: "OptiScaler",
        termDe: "OptiScaler",
        es: "Una herramienta de la comunidad que te deja meter estos trucos de fluidez, como FSR, en juegos que no los traían de fábrica. Es un extra que instalas aparte y no tiene que ver con este panel.",
        en: "A community tool that lets you drop these smoothness tricks, like FSR, into games that didn't ship with them. It's an extra you install separately and has nothing to do with this panel.",
        it: "Uno strumento della community che permette di aggiungere tecnologie come FSR ai giochi che non le includevano. Si installa separatamente e non fa parte di questo pannello.",
        de: "Ein Community-Werkzeug, das Techniken wie FSR in Spiele einbindet, die sie ursprünglich nicht unterstützen. Es wird separat installiert und gehört nicht zu diesem Panel.",
      },
      {
        id: "vrr",
        term: "VRR",
        termIt: "VRR",
        termDe: "VRR",
        es: "La pantalla acompasa su ritmo al del juego para que no veas cortes raros en la imagen cuando los FPS bailan arriba y abajo. No sube los FPS, pero deja el movimiento más limpio y agradable.",
        en: "The screen paces itself to the game so you don't get those ugly torn frames when the FPS bounces up and down. It won't raise your FPS, but it keeps the motion cleaner and nicer to play on.",
        it: "Sincronizza la frequenza dello schermo con il ritmo del gioco per evitare tagli nell'immagine quando gli FPS cambiano. Non aumenta gli FPS, ma rende il movimento più pulito e piacevole.",
        de: "Passt die Bildwiederholrate des Displays an die Bildrate des Spiels an. So entstehen bei schwankenden FPS keine störenden Bildrisse. VRR erhöht die FPS nicht, lässt Bewegungen aber sauberer und angenehmer wirken.",
      },
      {
        id: "refresh",
        term: "Tasa de refresco (Hz)",
        termIt: "Frequenza di aggiornamento (Hz)",
        termDe: "Bildwiederholrate (Hz)",
        es: "Cuántas veces por segundo se refresca la pantalla. Una de 90 Hz puede enseñarte hasta 90 imágenes por segundo, y cuanto más alta sea, más fluido puedes llegar a ver el juego.",
        en: "How many times per second the screen refreshes. A 90 Hz one can show you up to 90 images per second, and the higher it goes, the smoother the game can look.",
        it: "Indica quante volte al secondo si aggiorna lo schermo. Un pannello a 90 Hz può mostrare fino a 90 immagini al secondo e, in generale, una frequenza più alta permette un movimento più fluido.",
        de: "Gibt an, wie oft sich das Display pro Sekunde aktualisiert. Ein 90-Hz-Display kann bis zu 90 Bilder pro Sekunde zeigen. Je höher die Bildwiederholrate, desto flüssiger können Bewegungen aussehen.",
      },
    ],
  },
  {
    id: "hardware",
    es: "El chip por dentro",
    en: "Inside the chip",
    it: "Dentro il chip",
    de: "Im Inneren des Chips",
    terms: [
      {
        id: "apu",
        term: "APU",
        termIt: "APU",
        termDe: "APU",
        es: "Es el chip principal de la consola. Tiene la gracia de juntar en una sola pieza el cerebro (el procesador) y la parte que dibuja los gráficos, lo que ahorra sitio y batería, algo que le viene de perlas a una portátil.",
        en: "It's the console's main chip. Its neat trick is packing the brain (the processor) and the graphics into one piece, which saves space and battery, something a handheld really appreciates.",
        it: "È il chip principale del dispositivo. Riunisce in un solo componente il processore e la parte grafica, risparmiando spazio ed energia, due vantaggi importanti per un dispositivo portatile.",
        de: "Der Hauptchip des Geräts. Er vereint Prozessor und Grafik in einem einzigen Bauteil. Das spart Platz und Energie, was bei einem Handheld besonders wichtig ist.",
      },
      {
        id: "cpu",
        term: "CPU (procesador)",
        termIt: "CPU (processore)",
        termDe: "CPU (Prozessor)",
        es: "El cerebro de la consola. Se encarga de la lógica del juego, la física, lo que hacen los enemigos y todo lo que no sea pintar la imagen en pantalla.",
        en: "The console's brain. It handles the game logic, the physics, what the enemies do and everything that isn't painting the picture on screen.",
        it: "È il cervello del dispositivo. Gestisce la logica del gioco, la fisica, il comportamento dei nemici e tutto ciò che non riguarda direttamente la creazione dell'immagine sullo schermo.",
        de: "Das Gehirn des Geräts. Die CPU verarbeitet Spiellogik, Physik, das Verhalten von Gegnern und alles, was nicht direkt das Bild auf dem Bildschirm zeichnet.",
      },
      {
        id: "gpu",
        term: "GPU (gráfica)",
        termIt: "GPU",
        termDe: "GPU (Grafik)",
        es: "La parte del chip que dibuja todo lo que ves en pantalla. En los juegos suele ser la que más suda, y por eso el panel se fija sobre todo en ella para saber cuánta potencia hace falta.",
        en: "The part of the chip that draws everything you see. In games it's usually the one sweating hardest, which is why the panel watches it most to gauge how much power you need.",
        it: "È la parte del chip che disegna tutto ciò che vedi sullo schermo. Nei giochi è spesso il componente più impegnato, quindi il pannello la osserva soprattutto per capire quanta potenza serve.",
        de: "Der Teil des Chips, der alles auf dem Bildschirm zeichnet. In Spielen ist die GPU meist am stärksten ausgelastet. Deshalb beobachtet das Panel vor allem sie, um den benötigten Leistungswert zu bestimmen.",
      },
      {
        id: "cores-threads",
        term: "Núcleos e hilos",
        termIt: "Core e thread",
        termDe: "Kerne und Threads",
        es: "Los núcleos son como las manos del procesador: cuantas más tenga, más cosas puede hacer a la vez. Los hilos son los carriles de trabajo de cada mano, y algunos chips le dan dos carriles a cada núcleo para exprimirlo mejor.",
        en: "Cores are like the processor's hands: the more it has, the more it can do at once. Threads are each hand's work lanes, and some chips give every core two lanes to squeeze more out of it.",
        it: "I core sono come le mani del processore: più ne ha, più attività può svolgere contemporaneamente. I thread sono i flussi di lavoro di ogni core e alcuni chip ne assegnano due a ciascun core per sfruttarlo meglio.",
        de: "Kerne sind wie die Hände des Prozessors: Je mehr er besitzt, desto mehr Aufgaben kann er gleichzeitig erledigen. Threads sind die Arbeitsbahnen jedes Kerns. Manche Chips geben jedem Kern zwei davon, um ihn besser auszulasten.",
      },
      {
        id: "smt",
        term: "Multihilo (SMT)",
        termIt: "Multithreading (SMT)",
        termDe: "Simultanes Multithreading (SMT)",
        es: "Deja que cada núcleo del procesador lleve dos tareas a la vez en lugar de una. Encendido rinde algo más y apagado gasta y calienta un poco menos. Jugando la diferencia es mínima.",
        en: "Lets each processor core juggle two tasks at once instead of one. On, it performs a bit more; off, it uses and heats a little less. While gaming the difference is tiny.",
        it: "Permette a ogni core del processore di gestire due attività alla volta invece di una. Quando è attivo offre un po' più di prestazioni, mentre da disattivato riduce leggermente consumi e calore. Nei giochi la differenza è minima.",
        de: "Erlaubt jedem Prozessorkern, zwei Aufgaben gleichzeitig statt nur einer zu bearbeiten. Aktiviert bringt SMT etwas mehr Leistung, deaktiviert etwas weniger Verbrauch und Wärme. Beim Spielen ist der Unterschied meist gering.",
      },
      {
        id: "rdna",
        term: "RDNA",
        termIt: "RDNA",
        termDe: "RDNA",
        es: "Es el nombre de la tecnología gráfica de AMD que llevan casi todas estas consolas. Cada generación (RDNA 2, RDNA 3 y demás) es más nueva y potente. Vamos, que es el apellido de la parte que mueve los gráficos.",
        en: "It's the name of AMD's graphics tech inside almost all these consoles. Each generation (RDNA 2, RDNA 3 and so on) is newer and stronger. In short, it's the surname of the bit that pushes the graphics.",
        it: "È il nome della tecnologia grafica AMD usata da quasi tutti questi dispositivi. Ogni generazione, come RDNA 2 o RDNA 3, è più recente e potente. In pratica identifica l'architettura della parte che gestisce la grafica.",
        de: "Der Name der AMD-Grafikarchitektur, die in fast allen diesen Geräten steckt. Jede Generation, etwa RDNA 2 oder RDNA 3, ist neuer und leistungsfähiger. RDNA bezeichnet also die technische Familie der integrierten Grafik.",
      },
    ],
  },
  {
    id: "cooling",
    es: "Ventiladores y temperatura",
    en: "Fans and temperature",
    it: "Ventole e temperatura",
    de: "Lüfter und Temperatur",
    terms: [
      {
        id: "fan-curve",
        term: "Curva de ventilador",
        termIt: "Curva della ventola",
        termDe: "Lüfterkurve",
        es: "Es la norma que decide a qué velocidad giran los ventiladores según lo caliente que vaya la consola. Puedes ponerla más silenciosa para no oír ruido o más marchosa para jugar fresco, y el panel también puede aprenderla por ti a base de ver cómo juegas.",
        en: "It's the rule that decides how fast the fans spin based on how hot the console runs. You can set it quieter to keep the noise down or more aggressive to play cool, and the panel can also learn it for you by watching how you play.",
        it: "È la regola che decide la velocità delle ventole in base alla temperatura del dispositivo. Puoi renderla più silenziosa per ridurre il rumore o più aggressiva per mantenere temperature basse. Il pannello può anche imparare una curva adatta osservando come giochi.",
        de: "Legt fest, wie schnell sich die Lüfter bei einer bestimmten Gerätetemperatur drehen. Du kannst sie leiser einstellen oder für niedrigere Temperaturen stärker kühlen lassen. Das Panel kann auch aus deiner Nutzung eine passende Kurve lernen.",
      },
      {
        id: "rpm",
        term: "RPM",
        termIt: "RPM",
        termDe: "RPM",
        es: "Son las vueltas por minuto del ventilador, o sea lo rápido que está girando. A más RPM, mejor enfría pero más se le oye.",
        en: "The fan's revolutions per minute, meaning how fast it's spinning. Higher RPM cools better but you hear it more.",
        it: "Sono i giri al minuto della ventola e indicano quanto velocemente sta ruotando. Più RPM migliorano il raffreddamento, ma aumentano anche il rumore.",
        de: "Die Umdrehungen des Lüfters pro Minute, also seine Drehzahl. Mehr RPM sorgen für bessere Kühlung, sind aber auch deutlicher hörbar.",
      },
      {
        id: "temp",
        term: "Temperatura",
        termIt: "Temperatura",
        termDe: "Temperatur",
        es: "Lo caliente que va el chip, en grados. Que suba mientras juegas es de lo más normal, y para eso están los ventiladores y el TDP, para mantenerla a raya y que la consola no sufra.",
        en: "How hot the chip runs, in degrees. It's perfectly normal for it to climb while you play, and that's what the fans and TDP are for, keeping it in check so the console doesn't suffer.",
        it: "Indica in gradi quanto è caldo il chip. È del tutto normale che aumenti mentre giochi: ventole e TDP servono proprio a tenerla sotto controllo e proteggere il dispositivo.",
        de: "Zeigt in Grad an, wie warm der Chip ist. Dass die Temperatur beim Spielen steigt, ist völlig normal. Lüfter und TDP halten sie im sicheren Bereich und schützen das Gerät.",
      },
    ],
  },
  {
    id: "general",
    es: "El mundo de las portátiles",
    en: "The handheld world",
    it: "Il mondo dei dispositivi portatili",
    de: "Die Welt der Handhelds",
    terms: [
      {
        id: "handheld",
        term: "Consola portátil (handheld)",
        termIt: "Console portatile (handheld)",
        termDe: "Handheld-Gaming-PC",
        es: "Un PC con pinta de consola que juegas con las manos, como la Steam Deck, la ROG Ally o la Legion Go. Mueven juegos de PC de verdad pero con batería y allá donde te los lleves.",
        en: "A PC shaped like a console that you play holding in your hands, like the Steam Deck, ROG Ally or Legion Go. They run real PC games but on battery and wherever you take them.",
        it: "Un PC con la forma e i comandi di una console, come Steam Deck, ROG Ally o Legion Go. Esegue veri giochi per PC, ma funziona anche a batteria e puoi portarlo ovunque.",
        de: "Ein PC im Format einer tragbaren Konsole, den du in den Händen hältst, etwa Steam Deck, ROG Ally oder Legion Go. Er führt echte PC-Spiele aus, besitzt aber einen Akku und lässt sich überallhin mitnehmen.",
      },
      {
        id: "decky",
        term: "Decky Loader",
        termIt: "Decky Loader",
        termDe: "Decky Loader",
        es: "Es el programa que te permite instalar complementos como este panel en la consola. Piénsalo como una tienda de apps que le añade funciones nuevas al menú de Steam.",
        en: "It's the program that lets you install add-ons like this panel on your console. Think of it as an app store that adds new features to the Steam menu.",
        it: "È il programma che permette di installare plugin come questo pannello sul dispositivo. Puoi considerarlo uno store di app che aggiunge nuove funzioni al menu di Steam.",
        de: "Das Programm, mit dem du Plugins wie dieses Panel auf deinem Gerät installierst. Du kannst es dir wie einen App-Store vorstellen, der dem Steam-Menü neue Funktionen hinzufügt.",
      },
      {
        id: "qam",
        term: "Menú de acceso rápido (QAM)",
        termIt: "Menu di accesso rapido (QAM)",
        termDe: "Schnellzugriffsmenü (QAM)",
        es: "Es ese menú lateral que abres con un botón sin salir del juego, donde tocas brillo, volumen y complementos como este. Es la casa de este panel.",
        en: "It's that side menu you pop open with a button without leaving the game, where you tweak brightness, volume and add-ons like this one. It's this panel's home.",
        it: "È il menu laterale che apri con un pulsante senza uscire dal gioco. Da qui regoli luminosità, volume e plugin come questo. È la schermata in cui vive il pannello.",
        de: "Das Seitenmenü, das du per Taste öffnest, ohne das Spiel zu verlassen. Dort stellst du Helligkeit und Lautstärke ein und erreichst Plugins wie dieses. Hier ist das Kontrollzentrum zu Hause.",
      },
      {
        id: "telemetry",
        term: "Aprendizaje / telemetría",
        termIt: "Apprendimento / telemetria",
        termDe: "Lernen / Telemetrie",
        es: "El panel va apuntando cómo se porta cada juego (temperatura, potencia, ventilador) para poder recomendarte los mejores ajustes. Todo se queda dentro de tu consola y no sale de ahí jamás, y lo puedes apagar cuando te apetezca.",
        en: "The panel keeps notes on how each game behaves (temperature, power, fan) so it can recommend the best settings for you. It all stays inside your console and never leaves, and you can turn it off whenever you like.",
        it: "Il pannello registra come si comporta ogni gioco, ad esempio temperatura, potenza e ventola, per consigliarti le impostazioni più adatte. Tutti i dati restano sul dispositivo e non vengono mai inviati altrove. Puoi disattivare questa funzione in qualsiasi momento.",
        de: "Das Panel merkt sich, wie sich einzelne Spiele bei Temperatur, Leistung und Lüfter verhalten, um passende Einstellungen vorzuschlagen. Alle Daten bleiben auf deinem Gerät und werden niemals übertragen. Du kannst die Funktion jederzeit deaktivieren.",
      },
    ],
  },
];
