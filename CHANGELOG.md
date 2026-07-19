# Changelog

## [0.22.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.21.0...panel-de-control-v0.22.0) (2026-07-19)


### Features

* harden the experimental fan control (safe EC writes, honest state, reset) ([#238](https://github.com/Hooandee/panel-de-control/issues/238)) ([97b0b12](https://github.com/Hooandee/panel-de-control/commit/97b0b12caff54634d8dc5d468d98ca73ac666902))

## [0.21.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.20.1...panel-de-control-v0.21.0) (2026-07-19)


### Features / Novedades

* The Legion Go S now reaches its real TDP ceiling, 33W on battery and 40W on the charger, instead of stopping short. The Power tab gets a "reset to default" link that puts TDP back to your device's default value, global or per game. And the plugin now follows your system language: with Steam in English it starts in English and shows as "Control Panel", while any other language stays in Spanish, and a manual choice always wins. It also tidies a stray line under the experimental fan control on the Go S. ([#236](https://github.com/Hooandee/panel-de-control/issues/236)) ([d9e922a](https://github.com/Hooandee/panel-de-control/commit/d9e922a72efc44acd28e43d90ad8ac326c21b616))
* **ES:** La Legion Go S ahora llega a su techo real de TDP, 33W en batería y 40W con el cargador, en vez de quedarse corta. La pestaña Potencia gana un enlace de "restablecer al valor predeterminado" que devuelve el TDP al valor por defecto de tu equipo, global o por juego. Y el plugin ahora sigue el idioma del sistema: con Steam en inglés arranca en inglés y se muestra como "Control Panel", mientras que en cualquier otro idioma sigue en español, y tu elección manual siempre manda. Además limpia una línea que sobraba bajo el control experimental de ventilador en la Go S. ([#236](https://github.com/Hooandee/panel-de-control/issues/236)) ([d9e922a](https://github.com/Hooandee/panel-de-control/commit/d9e922a72efc44acd28e43d90ad8ac326c21b616))

## [0.20.1](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.20.0...panel-de-control-v0.20.1) (2026-07-18)


### Bug Fixes / Correcciones

* The TDP slider reaches your machine's real maximum again. On several handhelds it could get stuck below the top (a Legion Go S locked at 15W, a ROG Ally X capped at 25W even with the charger connected) because the plugin read the firmware limit once at startup and kept a low reading forever. Now the range comes from your device's known values, the firmware limit is read live, and what actually gets applied always follows what the hardware accepts. Unplugging the charger no longer leaves the TDP stuck low either. ([#216](https://github.com/Hooandee/panel-de-control/issues/216)) ([c9be207](https://github.com/Hooandee/panel-de-control/commit/c9be2079b73556d3c2d7c4c489a214bc78755a0a))
* **ES:** El deslizador de TDP vuelve a llegar al máximo real de tu equipo. En varias consolas se quedaba por debajo del tope (una Legion Go S clavada en 15W, una ROG Ally X limitada a 25W incluso con el cargador conectado) porque el plugin leía el límite del firmware una vez al arrancar y se quedaba con una lectura baja para siempre. Ahora el rango sale de los valores conocidos de tu equipo, el límite del firmware se lee en vivo, y lo que se aplica sigue siempre lo que el hardware acepta. Desenchufar el cargador tampoco deja el TDP atascado bajo. ([#216](https://github.com/Hooandee/panel-de-control/issues/216)) ([c9be207](https://github.com/Hooandee/panel-de-control/commit/c9be2079b73556d3c2d7c4c489a214bc78755a0a))

## [0.20.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.19.0...panel-de-control-v0.20.0) (2026-07-17)


### Features / Novedades

* Panel de Control now spots when another power manager is running (Handheld Daemon or SimpleDeckyTDP) and takes charge instead of quietly fighting it, which was the real reason a game could run worse than with another tool. The first time it finds a conflict it asks, full screen, whether to turn the others off; if you leave it for later, a card in the Power tab keeps a one-tap button for each rival (all reversible) until only one manager is left. A new TDP control switch in Settings lets you hand power management to whatever tool you prefer, and while it's off (or on a machine that can't set TDP, like a desktop) the Power tab just monitors. Turning on Auto-TDP now shows a one-time note about what to expect. ([#214](https://github.com/Hooandee/panel-de-control/issues/214)) ([17a55ef](https://github.com/Hooandee/panel-de-control/commit/17a55ef8a51b36d3263a864754b3357a04fade24))
* **ES:** Panel de Control ahora detecta cuando hay otro gestor de energía en marcha (Handheld Daemon o SimpleDeckyTDP) y toma el mando en vez de pelearse con él por detrás, que era la razón real de que un juego fuera peor que con otra herramienta. La primera vez que encuentra un conflicto te pregunta, a pantalla completa, si apagar los demás; si lo dejas para luego, una tarjeta en la pestaña Potencia mantiene un botón por cada rival (todo reversible) hasta que solo quede un gestor. Un nuevo interruptor Control de TDP en Ajustes te deja ceder la gestión a la herramienta que prefieras, y mientras está apagado (o en un equipo que no puede fijar el TDP, como un sobremesa) la pestaña Potencia solo monitoriza. Al activar Auto-TDP ahora se muestra un aviso único de qué esperar. ([#214](https://github.com/Hooandee/panel-de-control/issues/214)) ([17a55ef](https://github.com/Hooandee/panel-de-control/commit/17a55ef8a51b36d3263a864754b3357a04fade24))

## [0.19.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.18.0...panel-de-control-v0.19.0) (2026-07-15)


### Features / Novedades

* The whole panel is now fully usable with a controller. Whatever the cursor is on shows a clear colored outline and glow, across every section and the full-screen dialogs, so you no longer need the touchscreen. Switching tabs with L1/R1 carries the focus along, and read-only screens like the glossary scroll with the d-pad. You can also pick the panel's accent color from a palette under Customize interface, and it survives reboots. ([#201](https://github.com/Hooandee/panel-de-control/issues/201)) ([7740403](https://github.com/Hooandee/panel-de-control/commit/77404037c998f2e14a8c25573690fa28317bc193))
* **ES:** Ya puedes manejar todo el panel con el mando. El elemento en el que está el cursor se marca con un borde y un brillo de color, en todas las secciones y en las ventanas a pantalla completa, así que ya no hace falta la pantalla táctil. Al cambiar de pestaña con L1/R1 el foco te sigue, y las pantallas de solo lectura como el glosario se recorren con la cruceta. Además puedes elegir el color de acento del panel desde una paleta en Personalizar interfaz, y se mantiene tras reiniciar. ([#201](https://github.com/Hooandee/panel-de-control/issues/201)) ([7740403](https://github.com/Hooandee/panel-de-control/commit/77404037c998f2e14a8c25573690fa28317bc193))

## [0.18.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.17.0...panel-de-control-v0.18.0) (2026-07-14)


### Features / Novedades

* Global and per-game now work the same everywhere. Power (TDP, auto-TDP, GPU clock, boost mode), Fans, Display (color, calibration, HDR) and CPU (SMT, boost, active cores) each get a Global / game switch, and controller remaps are per-game on InputPlumber. Pick Global and the running game follows your global profile; pick the game and it uses its own, and switching never deletes either. A new "Per-game profiles" panel in Settings shows what you've set for each game, section by section, and lets you reset one back to global. Non-Steam games keep their profile across relaunches. This is a big release that touched every section, so if something that worked before now behaves oddly, please report it from Settings. ([#175](https://github.com/Hooandee/panel-de-control/issues/175)) ([881831e](https://github.com/Hooandee/panel-de-control/commit/881831e07e67390d84dda7662d59590078a48235))
* **ES:** Global y por-juego ahora funcionan igual en todas partes. Potencia (TDP, auto-TDP, frecuencia de GPU, modo de boost), Ventiladores, Pantalla (color, calibración, HDR) y CPU (SMT, boost, núcleos activos) tienen su selector Global / juego, y los mandos se remapean por juego en InputPlumber. Eliges Global y el juego en marcha sigue tu perfil global; eliges el juego y usa el suyo, y cambiar de uno a otro nunca borra ninguno. Un nuevo panel "Perfiles por juego" en Ajustes muestra lo que has configurado en cada juego, sección por sección, y te deja restablecer uno a global. Los juegos que no son de Steam conservan su perfil entre relanzamientos. Es una versión grande que tocó todas las secciones, así que si algo que antes funcionaba ahora va raro, repórtalo desde Ajustes. ([#175](https://github.com/Hooandee/panel-de-control/issues/175)) ([881831e](https://github.com/Hooandee/panel-de-control/commit/881831e07e67390d84dda7662d59590078a48235))

## [0.17.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.16.1...panel-de-control-v0.17.0) (2026-07-14)


### Features / Novedades

* On the original Legion Go the power section now offers the firmware performance modes (Quiet, Balanced, Performance) as presets under the arc. Picking one hands power, fan and LED to the firmware, and the plugin no longer forces the custom profile on every change, so a mode you set stops flipping back to turbo on its own. The fan section says clearly when a mode is running the fan, and the fan monitor now reads the speed straight from the controller on kernels whose driver doesn't publish it, so it shows up instead of looking undetected. ([#187](https://github.com/Hooandee/panel-de-control/issues/187)) ([e7a9a6d](https://github.com/Hooandee/panel-de-control/commit/e7a9a6dc19d1f0d31e38640c120f28c331e94d47))
* **ES:** En la Legion Go original la sección de potencia ahora ofrece los modos de rendimiento del firmware (Silencioso, Equilibrado, Rendimiento) como presets debajo del arco. Al elegir uno, el firmware pasa a llevar la potencia, el ventilador y el LED, y el plugin ya no fuerza el perfil personalizado en cada cambio, así que el modo que pongas deja de saltar solo a turbo. La sección de ventiladores dice con claridad cuándo es un modo el que lleva el ventilador, y el monitor ahora lee la velocidad directamente del controlador en los kernels cuyo driver no la publica, así aparece en vez de salir como no detectada. ([#187](https://github.com/Hooandee/panel-de-control/issues/187)) ([e7a9a6d](https://github.com/Hooandee/panel-de-control/commit/e7a9a6dc19d1f0d31e38640c120f28c331e94d47))

## [0.16.1](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.16.0...panel-de-control-v0.16.1) (2026-07-13)


### Bug Fixes / Correcciones

* Panel color (and HDR) now comes back on its own after a reboot or a full power-cycle. It was getting lost because the look is loaded into gamescope, which drops it while the session is still starting up, so the plugin now keeps re-applying it during startup until it sticks. ([#183](https://github.com/Hooandee/panel-de-control/issues/183)) ([a523a78](https://github.com/Hooandee/panel-de-control/commit/a523a7863fde7e60560b27628623ef3f891a1291))
* **ES:** El color del panel (y el HDR) ahora vuelve solo tras reiniciar o apagar y encender. Se perdía porque el look se carga en gamescope, que lo descarta mientras la sesión todavía arranca, así que el plugin ahora lo reaplica durante el arranque hasta que queda fijo. ([#183](https://github.com/Hooandee/panel-de-control/issues/183)) ([a523a78](https://github.com/Hooandee/panel-de-control/commit/a523a7863fde7e60560b27628623ef3f891a1291))

## [0.16.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.15.0...panel-de-control-v0.16.0) (2026-07-13)


### Features / Novedades

* Power boost is now a choice, not a hidden extra. A new Boost control picks how the SPPT and FPPT limits behave: Stable (what you set is what it draws, and the new default), Auto (a managed boost margin) or Custom (set the margins by hand). Existing setups move to Stable, so at the same TDP the handheld stops pulling more than you asked for. Some machines' firmware keeps a minimum, so the panel always shows the resulting limits. ([#176](https://github.com/Hooandee/panel-de-control/issues/176)) ([1f43847](https://github.com/Hooandee/panel-de-control/commit/1f43847f9e1491a1c2f25a39d74ba2f1556ab7c7))
* **ES:** El boost de potencia ahora se elige, ya no es un extra oculto. Un nuevo control de Boost decide cómo se comportan los límites SPPT y FPPT: Estable (lo que fijas es lo que gasta, y el nuevo modo por defecto), Auto (un margen de boost gestionado) o Personalizado (fijas los márgenes a mano). Los perfiles existentes pasan a Estable, así al mismo TDP el equipo deja de tirar más de lo que le pediste. El firmware de algunas máquinas mantiene un mínimo, por eso el panel siempre muestra los límites resultantes. ([#176](https://github.com/Hooandee/panel-de-control/issues/176)) ([1f43847](https://github.com/Hooandee/panel-de-control/commit/1f43847f9e1491a1c2f25a39d74ba2f1556ab7c7))

## [0.15.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.14.0...panel-de-control-v0.15.0) (2026-07-12)


### Features / Novedades

* The Display tab becomes a small color lab: one-tap looks (Native, Cinema, Vivid, Comfort) tuned per panel, an advanced mode with gamma, hue, black level, vibrance and manual RGB white balance on top of saturation and temperature/contrast, a night mode that warms the screen always or on the schedule you choose, and an HDR on/off toggle on the HDR-capable OLED panels (Steam Deck OLED, Legion Go 2). ([#168](https://github.com/Hooandee/panel-de-control/issues/168)) ([e1e5c4d](https://github.com/Hooandee/panel-de-control/commit/e1e5c4d6323561d1e47a29c7ffb1c3d92b003659))
* **ES:** La pestaña Pantalla se convierte en un pequeño laboratorio de color: ambientes de un toque (Nativo, Cine, Vivo, Cómodo) afinados por panel, un modo avanzado con gamma, tono, nivel de negro, vivacidad y balance manual de blancos (RGB) sobre la saturación y la temperatura/contraste, un modo nocturno que calienta la pantalla siempre o en el horario que elijas, y un interruptor de HDR en los paneles OLED con HDR (Steam Deck OLED, Legion Go 2). ([#168](https://github.com/Hooandee/panel-de-control/issues/168)) ([e1e5c4d](https://github.com/Hooandee/panel-de-control/commit/e1e5c4d6323561d1e47a29c7ffb1c3d92b003659))

## [0.14.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.13.0...panel-de-control-v0.14.0) (2026-07-11)


### Features / Novedades

* Adds support for five more handhelds, all experimental: the Legion Go 2 with the plain Ryzen Z2, the ROG Xbox Ally with the Ryzen Z2 A (whose bogus 100 W firmware ceiling is now capped to the safe 20 W it really runs at), the OneXPlayer F1 Pro, the GPD Win 5 and the GPD Win Max 2. Each gets a safe TDP ceiling and its own presets instead of landing on the 15 W generic profile. The GPD Win 5 also gets an opt-in "external cooler attached" toggle that raises its ceiling to 75 W once you confirm the cooler is on. ([#159](https://github.com/Hooandee/panel-de-control/issues/159)) ([ac56e21](https://github.com/Hooandee/panel-de-control/commit/ac56e212962d521580127a4a4138ec59b243aa98))
* **ES:** Añade soporte para cinco máquinas más, todas experimentales: la Legion Go 2 con el Ryzen Z2 normal, la ROG Xbox Ally con el Ryzen Z2 A (cuyo tope de firmware falso de 100 W queda capado a los 20 W seguros que de verdad usa), la OneXPlayer F1 Pro, la GPD Win 5 y la GPD Win Max 2. Cada una con su techo de TDP seguro y sus presets en vez de caer en el perfil genérico de 15 W. La GPD Win 5 además trae un interruptor opcional de "cooler externo puesto" que sube su techo a 75 W cuando confirmas que el cooler está conectado. ([#159](https://github.com/Hooandee/panel-de-control/issues/159)) ([ac56e21](https://github.com/Hooandee/panel-de-control/commit/ac56e212962d521580127a4a4138ec59b243aa98))

## [0.13.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.12.0...panel-de-control-v0.13.0) (2026-07-11)


### Features / Novedades

* Fan curves on the original Legion Go: the fan section turns into a drag-to-set curve editor, with presets and per-game curves, on the kernels that ship the Legion fan driver. Where the driver isn't there yet it stays a read-only RPM monitor and turns on by itself once the kernel includes it. ([#158](https://github.com/Hooandee/panel-de-control/issues/158)) ([342b585](https://github.com/Hooandee/panel-de-control/commit/342b5855e4c7d9fa1715b8ab6d666064ac13d895))
* **ES:** Curvas de ventilador en la Legion Go original: la sección de ventiladores pasa a un editor de curvas que arrastras con el dedo, con presets y curvas por juego, en los kernels que traen el driver de ventilador de la Legion. Donde el driver aún no está, se queda en monitor de RPM de solo lectura y se enciende solo en cuanto el kernel lo incluye. ([#158](https://github.com/Hooandee/panel-de-control/issues/158)) ([342b585](https://github.com/Hooandee/panel-de-control/commit/342b5855e4c7d9fa1715b8ab6d666064ac13d895))

## [0.12.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.11.0...panel-de-control-v0.12.0) (2026-07-11)


### Features / Novedades

* Adds support for the GPD Win Mini 2025 (Ryzen AI 9 HX 370/365) and the MSI Claw A8 (Ryzen Z2 Extreme). They're now recognised by name instead of landing on the generic profile, so their TDP can reach a safe 35 W instead of being capped at 15 W, each with tuned quick presets. Battery, CPU, colour, GPU clock and the fan monitor come along too. Experimental until it's confirmed on the devices. ([#153](https://github.com/Hooandee/panel-de-control/issues/153)) ([3dedcd7](https://github.com/Hooandee/panel-de-control/commit/3dedcd70fe51970603a545d20e2afaa07c4ad805))
* **ES:** Añade soporte para la GPD Win Mini 2025 (Ryzen AI 9 HX 370/365) y la MSI Claw A8 (Ryzen Z2 Extreme). Ahora se reconocen por su nombre en vez de caer en el perfil genérico, así su TDP llega a unos 35 W seguros en lugar de quedarse capado a 15 W, cada una con sus presets rápidos afinados. También llegan la batería, la CPU, el color, la frecuencia de GPU y el monitor de ventiladores. Experimental hasta confirmarlo en los equipos. ([#153](https://github.com/Hooandee/panel-de-control/issues/153)) ([3dedcd7](https://github.com/Hooandee/panel-de-control/commit/3dedcd70fe51970603a545d20e2afaa07c4ad805))

## [0.11.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.10.0...panel-de-control-v0.11.0) (2026-07-10)


### Features / Novedades

* Adds support for the AOKZOE A1X handheld (Ryzen AI 9 HX 370). It's now recognised by name instead of landing on the generic profile, so its TDP can reach the real 30 W instead of being capped at 15 W, with quick presets at 12 / 18 / 30 W. Experimental until it's confirmed on the device. ([#130](https://github.com/Hooandee/panel-de-control/issues/130)) ([5bb4882](https://github.com/Hooandee/panel-de-control/commit/5bb488236925fe7e00a0d812b228ccd47175db58))
* **ES:** Añade soporte para el handheld AOKZOE A1X (Ryzen AI 9 HX 370). Ahora se reconoce por su nombre en vez de caer en el perfil genérico, así su TDP llega a los 30 W reales en lugar de quedarse capado a 15 W, con presets rápidos a 12 / 18 / 30 W. Experimental hasta confirmarlo en el equipo. ([#130](https://github.com/Hooandee/panel-de-control/issues/130)) ([5bb4882](https://github.com/Hooandee/panel-de-control/commit/5bb488236925fe7e00a0d812b228ccd47175db58))

## [0.10.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.9.0...panel-de-control-v0.10.0) (2026-07-09)


### Features / Novedades

* The Power tab now shows the TDP the firmware is actually holding, not just the value you set, so download mode and changes made from other tools show up. Adds curated quick presets on the ROG Ally X and Xbox Ally X (with the active one highlighted), dims the screen right away in download mode, and ignores a bogus firmware TDP ceiling so the slider can never offer a dangerous value. ([#119](https://github.com/Hooandee/panel-de-control/issues/119)) ([cbc8e0e](https://github.com/Hooandee/panel-de-control/commit/cbc8e0ed33de5b489879c3cfce8c0e6491f8261a))
* **ES:** La pestaña de Potencia ahora muestra el TDP que el firmware tiene puesto de verdad, no solo el que fijaste tú, así se reflejan el modo descarga y los cambios hechos desde otras herramientas. Añade presets rápidos a medida en la ROG Ally X y la Xbox Ally X (con el activo resaltado), atenúa la pantalla al instante en modo descarga, e ignora un tope de TDP erróneo del firmware para que el slider nunca ofrezca un valor peligroso. ([#119](https://github.com/Hooandee/panel-de-control/issues/119)) ([cbc8e0e](https://github.com/Hooandee/panel-de-control/commit/cbc8e0ed33de5b489879c3cfce8c0e6491f8261a))

## [0.9.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.8.4...panel-de-control-v0.9.0) (2026-07-09)


### Features / Novedades

* Fan control on the Legion Go S: you can now set a fan curve on the Go S through a new experimental, opt-in mode. It's off by default, drives the fan over an unofficial path, and keeps a safety speed cap. ([#112](https://github.com/Hooandee/panel-de-control/issues/112)) ([2281a33](https://github.com/Hooandee/panel-de-control/commit/2281a33c127fe98b2eb9298725b4fe6b0f4c3a1b))
* **ES:** Control de ventilador en la Legion Go S: ya puedes poner una curva de ventilador en la Go S con un modo experimental y opcional. Viene desactivado, controla el ventilador por una vía no oficial y mantiene un tope de velocidad de seguridad. ([#112](https://github.com/Hooandee/panel-de-control/issues/112)) ([2281a33](https://github.com/Hooandee/panel-de-control/commit/2281a33c127fe98b2eb9298725b4fe6b0f4c3a1b))

## [0.8.4](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.8.3...panel-de-control-v0.8.4) (2026-07-08)


### Bug Fixes

* persist language and UI preferences across reboot ([#98](https://github.com/Hooandee/panel-de-control/issues/98)) ([0feb60e](https://github.com/Hooandee/panel-de-control/commit/0feb60e62e3a0a8c64443a9bd2fd811c6725b1a7))

## [0.8.3](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.8.2...panel-de-control-v0.8.3) (2026-07-08)


### Bug Fixes / Correcciones

* Download mode no longer fights your screen brightness: it keeps the level you set, the flicker to dark is gone, and it dims smoothly when you leave the device alone. ([#95](https://github.com/Hooandee/panel-de-control/issues/95)) ([31daef5](https://github.com/Hooandee/panel-de-control/commit/31daef590cd6bbc75a8186bb1f9d76468ae08d74))
* **ES:** El Modo Descarga ya no se pelea con el brillo de la pantalla: respeta el nivel que pongas, se acabaron los parpadeos a oscuro y atenúa de forma suave cuando dejas el equipo quieto. ([#95](https://github.com/Hooandee/panel-de-control/issues/95)) ([31daef5](https://github.com/Hooandee/panel-de-control/commit/31daef590cd6bbc75a8186bb1f9d76468ae08d74))

## [0.8.2](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.8.1...panel-de-control-v0.8.2) (2026-07-08)


### Features / Novedades

* Improved the problem report: it now includes the controller manager's log, so controller issues (like the rear buttons after waking from sleep) can be diagnosed without needing the device in hand. ([#93](https://github.com/Hooandee/panel-de-control/issues/93)) ([5d3fe99](https://github.com/Hooandee/panel-de-control/commit/5d3fe9985828297dc54aa3134469f54c4469fa47))
* **ES:** Mejorado el reporte de problemas: ahora incluye el registro del gestor de mandos, así los problemas de mando (como los botones traseros al salir de suspensión) se pueden diagnosticar sin tener el equipo delante. ([#93](https://github.com/Hooandee/panel-de-control/issues/93)) ([5d3fe99](https://github.com/Hooandee/panel-de-control/commit/5d3fe9985828297dc54aa3134469f54c4469fa47))


### Miscellaneous Chores

* release panel-de-control 0.8.2 ([bc89561](https://github.com/Hooandee/panel-de-control/commit/bc895615dccf63b3bccbbbf65eaf523044605bd4))

## [0.8.1](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.8.0...panel-de-control-v0.8.1) (2026-07-07)


### Bug Fixes / Correcciones

* Reporting a problem now needs a short description before you can send it, so I actually know what went wrong. On the Legion Go the fan monitor now shows a single real fan instead of a phantom second one stuck at 0. ([#81](https://github.com/Hooandee/panel-de-control/issues/81)) ([a4be837](https://github.com/Hooandee/panel-de-control/commit/a4be83700d79108b376d58b27aa006a4f7c60eb5))
* **ES:** Reportar un problema ahora pide una breve descripción antes de poder enviarlo, así sé de verdad qué falló. En la Legion Go el monitor de ventiladores ahora muestra un solo ventilador real en vez de un segundo fantasma clavado en 0. ([#81](https://github.com/Hooandee/panel-de-control/issues/81)) ([a4be837](https://github.com/Hooandee/panel-de-control/commit/a4be83700d79108b376d58b27aa006a4f7c60eb5))

## [0.8.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.7.0...panel-de-control-v0.8.0) (2026-07-07)


### Features / Novedades

* The OneXPlayer OneXFly Apex is now recognised by name instead of showing up as a generic device, and it gets working TDP control through the generic AMD path. Fans and the charge limit stay off until they can be confirmed on the hardware, so the device is marked experimental for now. Bug reports also gather more device detail, which makes it easier to add support for new handhelds like this one. ([#78](https://github.com/Hooandee/panel-de-control/issues/78)) ([e407d17](https://github.com/Hooandee/panel-de-control/commit/e407d17b74a70f35669dbaf12241111c3e3bf6e7))
* **ES:** La OneXPlayer OneXFly Apex ahora se reconoce por su nombre en lugar de aparecer como dispositivo genérico, y obtiene control de TDP por la vía genérica de AMD. Los ventiladores y el límite de carga quedan desactivados hasta poder confirmarlos en el equipo, así que de momento va marcada como experimental. Los reportes de problemas también recogen más detalle del dispositivo, lo que facilita dar soporte a equipos nuevos como este. ([#78](https://github.com/Hooandee/panel-de-control/issues/78)) ([e407d17](https://github.com/Hooandee/panel-de-control/commit/e407d17b74a70f35669dbaf12241111c3e3bf6e7))

## [0.7.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.6.0...panel-de-control-v0.7.0) (2026-07-07)


### Features / Novedades

* The volume and brightness buttons can now show the exact value on screen without opening the panel: turn on "Show value when changing volume or brightness" under Ajustes and a small toast shows the number as you adjust, speaker/sun icon, silent, and off by default. ([#73](https://github.com/Hooandee/panel-de-control/issues/73)) ([27bb34a](https://github.com/Hooandee/panel-de-control/commit/27bb34adba25d0949493d9c236d4e1380786d1cb))
* **ES:** Los botones de volumen y brillo ahora pueden mostrar el valor exacto en pantalla sin abrir el panel: activa «Mostrar valor al cambiar volumen o brillo» en Ajustes y un pequeño aviso muestra el número mientras ajustas, con icono de altavoz/sol, silencioso y desactivado por defecto. ([#73](https://github.com/Hooandee/panel-de-control/issues/73)) ([27bb34a](https://github.com/Hooandee/panel-de-control/commit/27bb34adba25d0949493d9c236d4e1380786d1cb))

## [0.6.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.5.0...panel-de-control-v0.6.0) (2026-07-06)


### Features / Novedades

* You can now hide the battery health info (health, charge cycles and capacity) from the Battery card, with a single toggle under Ajustes → Personalizar, for anyone who'd rather not keep an eye on it. You can also move between tabs with the L1/R1 shoulder buttons. ([#51](https://github.com/Hooandee/panel-de-control/issues/51)) ([bbba2ed](https://github.com/Hooandee/panel-de-control/commit/bbba2ed325b863c94cb75b09513af28c1b4610d2))
* **ES:** Ahora puedes ocultar la información de salud de la batería (salud, ciclos de carga y capacidad) de la tarjeta de Batería, con un solo interruptor en Ajustes → Personalizar, para quien prefiera no estar pendiente de ella. Además puedes cambiar de pestaña con los gatillos L1/R1. ([#51](https://github.com/Hooandee/panel-de-control/issues/51)) ([bbba2ed](https://github.com/Hooandee/panel-de-control/commit/bbba2ed325b863c94cb75b09513af28c1b4610d2))

## [0.5.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.4.2...panel-de-control-v0.5.0) (2026-07-06)


### Features / Novedades

* MSI Claw: the Ventiladores tab now shows the fan curve your Claw's firmware applies, read-only, with the live temperature marker, so you can see how it behaves even though its driver doesn't let apps edit the curve yet. The fan RPM monitor also shows both fans correctly. Editable, safe fan-speed control for the Claw is in progress. ([#42](https://github.com/Hooandee/panel-de-control/issues/42)) ([414fca1](https://github.com/Hooandee/panel-de-control/commit/414fca15c6f7e9cd5f305e7a38aa3d29d4d6f246))
* **ES:** MSI Claw: la pestaña Ventiladores ahora muestra la curva de ventilación que aplica el firmware de tu Claw, en solo lectura, con la marca de temperatura en vivo, así ves cómo se comporta aunque su driver todavía no deje a las apps editar la curva. El monitor de RPM también muestra bien los dos ventiladores. El control editable y seguro de la velocidad del ventilador para el Claw está en desarrollo. ([#42](https://github.com/Hooandee/panel-de-control/issues/42)) ([414fca1](https://github.com/Hooandee/panel-de-control/commit/414fca15c6f7e9cd5f305e7a38aa3d29d4d6f246))

## [0.4.2](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.4.1...panel-de-control-v0.4.2) (2026-07-06)


### Performance Improvements / Mejoras de rendimiento

* The control panel and its live readouts stay responsive even when a system tool (the display compositor, the fan service) is slow to answer, the heavy work now runs in the background instead of briefly freezing the panel. ([#40](https://github.com/Hooandee/panel-de-control/issues/40)) ([c404201](https://github.com/Hooandee/panel-de-control/commit/c4042011f88502ef2afaabbc094a07a312a1f51a))
* **ES:** El panel y sus lecturas en vivo siguen respondiendo aunque una herramienta del sistema (el compositor de pantalla, el servicio de ventiladores) tarde en contestar, el trabajo pesado ahora corre en segundo plano en vez de congelar el panel un instante. ([#40](https://github.com/Hooandee/panel-de-control/issues/40)) ([c404201](https://github.com/Hooandee/panel-de-control/commit/c4042011f88502ef2afaabbc094a07a312a1f51a))

## [0.4.1](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.4.0...panel-de-control-v0.4.1) (2026-07-05)


### Bug Fixes / Correcciones

* Keep panel color working when gamescope's socket appears after load: the Pantalla (display color) tab no longer vanishes when the plugin starts before gamescope is ready, detection now recovers on its own instead of staying off for the whole session. ([d3fd9d2](https://github.com/Hooandee/panel-de-control/commit/d3fd9d22d8165793c5d0f695148e339b44d92ef4))
* **ES:** El control de color sigue funcionando cuando el socket de gamescope aparece tras el arranque: la pestaña Pantalla ya no desaparece si el plugin arranca antes de que gamescope esté listo, la detección se recupera sola en vez de quedarse desactivada toda la sesión. ([d3fd9d2](https://github.com/Hooandee/panel-de-control/commit/d3fd9d22d8165793c5d0f695148e339b44d92ef4))

## [0.4.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.3.0...panel-de-control-v0.4.0) (2026-07-05)


### Features

* author channel link in Settings ([00490fc](https://github.com/Hooandee/panel-de-control/commit/00490fc856509fe24c060de95a46068f689909ac))
* author channel link in Settings ([55ab769](https://github.com/Hooandee/panel-de-control/commit/55ab769e6eca046279e0c440d912a41ad875ee4d))

## [0.3.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.2.4...panel-de-control-v0.3.0) (2026-07-04)


### Features

* capability-probe fallbacks for unrecognised handhelds ([0515652](https://github.com/Hooandee/panel-de-control/commit/051565214091b6ce8fe0731548b80f715c27f4f8))
* capability-probe fallbacks for unrecognised handhelds ([87053e6](https://github.com/Hooandee/panel-de-control/commit/87053e609f8bb438e3e85cf2d54bf2582a2d50d3))
* control-center UI polish, Steam Deck fan control, Legion Go S refinements ([#14](https://github.com/Hooandee/panel-de-control/issues/14)) ([9958268](https://github.com/Hooandee/panel-de-control/commit/99582683e92fe15fcc193316de9401d42b980c95))
* controller manager hub with per-device remap (Mandos) ([cc6e5b8](https://github.com/Hooandee/panel-de-control/commit/cc6e5b8a06e025fe06c7b18e754cd2bf7f53ffb3))
* display color calibration, active CPU cores, and GPU clock controls ([30eec65](https://github.com/Hooandee/panel-de-control/commit/30eec652381d80ae0c26b7cc02c59f5a190153cb))
* in-plugin problem reporter ([1752878](https://github.com/Hooandee/panel-de-control/commit/1752878a0c3b73c9f44bf34892e88ee574fce4de))
* in-plugin problem reporter ([59afbd7](https://github.com/Hooandee/panel-de-control/commit/59afbd7db71fc7b48c5bd874c6f8133d889287b1))
* Legion Go S support (detection, fan monitor, fan modes) ([2bed969](https://github.com/Hooandee/panel-de-control/commit/2bed969e2da300f092f3156b4ea5bb56afc98702))
* plain-language glossary of handheld terms in Settings ([9a95918](https://github.com/Hooandee/panel-de-control/commit/9a959180eb000c0fd1df396b7bdddd4d00139768))
* RGB lighting card, open or install Colores from Sistema ([5e96f91](https://github.com/Hooandee/panel-de-control/commit/5e96f91a0ad3b75e43e5a17b0243925235cdf789))


### Bug Fixes

* spawn modprobe (MSI) and gamescopectl (color) via clean_env + absolute path ([#15](https://github.com/Hooandee/panel-de-control/issues/15)) ([160611f](https://github.com/Hooandee/panel-de-control/commit/160611fa195948d99243c27ad50505ff653d5da9))

## [0.2.4](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.2.3...panel-de-control-v0.2.4) (2026-07-02)


### Bug Fixes

* minor fixes ([78ab7bd](https://github.com/Hooandee/panel-de-control/commit/78ab7bd69fb26db2f6bad429a84e08b3849168f1))

## [0.2.3](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.2.2...panel-de-control-v0.2.3) (2026-07-02)


### Bug Fixes

* minor fixes ([0cd1723](https://github.com/Hooandee/panel-de-control/commit/0cd1723f7fec8c33a328f5a74cdfcddb5a05ae2e))

## [0.2.2](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.2.1...panel-de-control-v0.2.2) (2026-07-02)


### Bug Fixes

* show the changelog in a formatted modal instead of raw inline text ([c7a7b8f](https://github.com/Hooandee/panel-de-control/commit/c7a7b8f4ef5c96b4a11f40b990c0b60bc448c15e))

## [0.2.1](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.2.0...panel-de-control-v0.2.1) (2026-07-02)


### Bug Fixes

* match GitHub's dotted release asset name ([3d71531](https://github.com/Hooandee/panel-de-control/commit/3d71531b2d2a5f279b7da7916f98f80db0bea55b))

## [0.2.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.1.0...panel-de-control-v0.2.0) (2026-07-02)


### Features

* add advanced boost controls to the Potencia panel ([0b6bf88](https://github.com/Hooandee/panel-de-control/commit/0b6bf88f6a873784fc36b3a2d233cee6723b84d8))
* add advanced TDP level types and bridges to api ([bafa2d4](https://github.com/Hooandee/panel-de-control/commit/bafa2d491767e1f90b3b1933dc2f77891ce285f8))
* add asus fan-curve control backend with safe sanitisation ([295f65a](https://github.com/Hooandee/panel-de-control/commit/295f65afb1542454d45dcb07c2b11ebbd5000323))
* add control-center shell with tabbed sections ([0c5a768](https://github.com/Hooandee/panel-de-control/commit/0c5a768711902acb256889f0f3b63c73697e08fb))
* add device detection with per-device profiles and generic fallback ([5a3ef4c](https://github.com/Hooandee/panel-de-control/commit/5a3ef4cae77935613d167d270e0cd2c3d487b494))
* add firmware-attributes TDP backend (ASUS/Lenovo/MSI) ([862461d](https://github.com/Hooandee/panel-de-control/commit/862461da04541a174d8c90b88cd27f32e71b8264))
* add FPS-target auto-TDP control loop and RPCs ([365ff41](https://github.com/Hooandee/panel-de-control/commit/365ff4161446396a50c6b728a2a678027c02308b))
* add FPS-target selector and live FPS gauge ([8fe8205](https://github.com/Hooandee/panel-de-control/commit/8fe8205843756e2b653d78d7fb4a2227f890a482))
* add in-plugin self-updater ([22ff447](https://github.com/Hooandee/panel-de-control/commit/22ff44752ad943214bc355011fdd9f342601b19f))
* add PdC UI theme, device header and language toggle ([c973ab3](https://github.com/Hooandee/panel-de-control/commit/c973ab3ceed420b60fc653e24c0260f8faf5263c))
* add per-device TDP backend factory with graceful fallback ([9a9bcf9](https://github.com/Hooandee/panel-de-control/commit/9a9bcf9dad45f4b5e6028d17000a3ebabbb77e7b))
* add per-PL limits and explicit level control to TDP backends ([f380339](https://github.com/Hooandee/panel-de-control/commit/f3803391ba09f503e78e3ca68d04bf0c60b3c0d0))
* add power-arc TDP gauge component ([917e4f1](https://github.com/Hooandee/panel-de-control/commit/917e4f131311bfabc6ec713fd9f91805c4abb8e0))
* add pure helpers for boost margin math ([23a1ec4](https://github.com/Hooandee/panel-de-control/commit/23a1ec4e40f3a176ecddd96fc7ea0399c2c7e7e1))
* add pure TDP view logic (zones, arc color, angle) ([c838005](https://github.com/Hooandee/panel-de-control/commit/c83800525b6ccc376bfd06232dedaca663d5de6a))
* add read-only fan monitor (Ventiladores section) ([4209b3f](https://github.com/Hooandee/panel-de-control/commit/4209b3f5ab6c727961969102082f0ad7219d99d4))
* add running-game detection hook for per-game TDP ([a94731f](https://github.com/Hooandee/panel-de-control/commit/a94731fe5092d01bfb6cf546607ca4a8744a84ba))
* add ryzenadj generic AMD fallback TDP backend ([2a291ab](https://github.com/Hooandee/panel-de-control/commit/2a291ab8f7e35d1ff8e8ab12ddbc7d6744b73078))
* add Spanish-first i18n with English fallback ([dae76f7](https://github.com/Hooandee/panel-de-control/commit/dae76f7d838d7413a61bc5e12ce70ceb4b831d3e))
* add Steam Deck hwmon power-cap TDP backend ([5f35477](https://github.com/Hooandee/panel-de-control/commit/5f354772301999ff894d82dc4a46d6e1cb39d549))
* add TDP lifecycle re-apply on resume and AC/DC transitions ([75442a6](https://github.com/Hooandee/panel-de-control/commit/75442a619ed414d3feec9fda5ad5aee06c27144b))
* add TDP profile selector and presets ([b23fec2](https://github.com/Hooandee/panel-de-control/commit/b23fec240fd2b2f043bde6f80e333141c3543517))
* add TDP ProfileStore with per-game inheritance ([23d193a](https://github.com/Hooandee/panel-de-control/commit/23d193a7a37577166693307ed85f8c2a09a38bab))
* add TDP RPC bridges and types to api.ts ([3e57de3](https://github.com/Hooandee/panel-de-control/commit/3e57de3f43f8881349fd1ef0def632d411e1207e))
* add TDP value types (TdpLimits, TdpResult) ([9e07983](https://github.com/Hooandee/panel-de-control/commit/9e07983ad01d59dbf1b0adf43e71b0767d51cf8a))
* add TDPBackend interface and NullBackend ([9004015](https://github.com/Hooandee/panel-de-control/commit/900401516a35ac780d30cbb0b1a13b8d05d42ac5))
* add usage telemetry store and sampler ([d609dd8](https://github.com/Hooandee/panel-de-control/commit/d609dd8b4d4e1caeb2e59d2190083ca7ccabd39a))
* advanced TDP, auto-TDP, battery ceiling, telemetry and fan-curve control ([b7ca38d](https://github.com/Hooandee/panel-de-control/commit/b7ca38d50a1b5a2e390be43d87c5c35727590578))
* assistive auto-adaptation, GPU-driven auto-TDP, adaptive fan mode, learning ([3bd6488](https://github.com/Hooandee/panel-de-control/commit/3bd64889349b174f67741c909fd0d8d2f8bd95c8))
* assistive fan-curve suggestions + multi-device fan & TDP control ([74bf87e](https://github.com/Hooandee/panel-de-control/commit/74bf87ebf05196732ac47144931d9794e94c6a18))
* assistive fan-curve suggestions + multi-device fan & TDP control ([44f5d12](https://github.com/Hooandee/panel-de-control/commit/44f5d12c39238fb64eea1b18313b4bf2ca98bb80))
* cap TDP to a device-aware battery ceiling on DC power ([38516c2](https://github.com/Hooandee/panel-de-control/commit/38516c23556afa03396d0daa77601c3a4a9ae001))
* customizable tab and block layout ([03f5cea](https://github.com/Hooandee/panel-de-control/commit/03f5cea757f9b49f07d724e40f6a181a860f2252))
* expose advanced PL levels and reset over TDP RPC ([87264ae](https://github.com/Hooandee/panel-de-control/commit/87264aeb34c46e9205a6778fa116f7e2d4f8785d))
* expose detected device profile via get_device RPC ([7cf5621](https://github.com/Hooandee/panel-de-control/commit/7cf5621f8aa9ab96735d9223893eb6f91d47e2d9))
* expose fan-curve RPCs and restore-auto fail-safe on unload ([9043bf9](https://github.com/Hooandee/panel-de-control/commit/9043bf9a7513428f65c9afd79faf2471b10f6d5c))
* expose global_watts in TDP state for accurate scope display ([8ae72a2](https://github.com/Hooandee/panel-de-control/commit/8ae72a29bae7411abf7b4d385027166938db27c1))
* expose TDP RPCs and wire lifecycle manager ([223feaf](https://github.com/Hooandee/panel-de-control/commit/223feaf232140a0d9e3f08dfcdb0d65dc9519e25))
* fan-curve editor, sensor dashboard, and usage-telemetry opt-out ([d8d39b4](https://github.com/Hooandee/panel-de-control/commit/d8d39b4f640fbdfc731c2443adb76aca9a04056f))
* fan-curve editor, sensor dashboard, and usage-telemetry opt-out ([7a3fb9c](https://github.com/Hooandee/panel-de-control/commit/7a3fb9cd742c81eb929db3f0107db7f3ecdf5a9b))
* live auto-TDP gauge and ceiling note in the power panel ([87eb7c2](https://github.com/Hooandee/panel-de-control/commit/87eb7c263924ff1cbefa6fd6dfd909399d50713a))
* move language flags below device header with spacing ([7a3f97c](https://github.com/Hooandee/panel-de-control/commit/7a3f97c7e9f36411d28afa5ec83bfd1c6a913875))
* read actual APU power draw via hwmon ([123461f](https://github.com/Hooandee/panel-de-control/commit/123461f745c219c62394388ead206f91571dd5c7))
* read GPU load and add auto-TDP controller ([6fa88ec](https://github.com/Hooandee/panel-de-control/commit/6fa88ecb2cb751cf4e8bddea605b65839a181da6))
* read real game FPS from gamescope stats pipe ([3c7c486](https://github.com/Hooandee/panel-de-control/commit/3c7c486901149953f07a730aaef460419c94be43))
* render device header and language switch in the panel ([af3afb5](https://github.com/Hooandee/panel-de-control/commit/af3afb5d2a482a8e9fe9fcac54df64bd81414f99))
* replace emoji icons with Lucide (react-icons/lu) ([dccde53](https://github.com/Hooandee/panel-de-control/commit/dccde53f7ea2cf1e5c04bd46005b302223f590dd))
* sample telemetry in-game and expose get_telemetry RPC ([0331c8f](https://github.com/Hooandee/panel-de-control/commit/0331c8f84f455b638068adec99072928bf283e98))
* scaffold Panel de Control Decky plugin skeleton ([50ebdb8](https://github.com/Hooandee/panel-de-control/commit/50ebdb845b1ff6ac30c0a9590a568deabeaffaeb))
* store per-PL levels in TDP ProfileStore with migration ([61cd7bb](https://github.com/Hooandee/panel-de-control/commit/61cd7bb80d8edaabbdb7b5887e45846a882e67f1))
* store TDP boost as auto/manual margins with derivation ([a62d093](https://github.com/Hooandee/panel-de-control/commit/a62d093f0ad0e126b2c353032976c488a2fbb2b8))
* **system:** battery card with health, cycles and per-device charge limit ([08a3c07](https://github.com/Hooandee/panel-de-control/commit/08a3c07cd1be43bfb604f34043ea96c5034492f0))
* **system:** CPU controls (SMT + turbo boost) and collapsible cards ([4e1345c](https://github.com/Hooandee/panel-de-control/commit/4e1345cdeb5a530718df455b9a82475422af1951))
* **system:** download mode (low-power) with ambient screen dim ([52c68c0](https://github.com/Hooandee/panel-de-control/commit/52c68c07307cc9fdfe8005e7bc7f1d9f6655314a))
* **system:** persist collapsed state of cards per section ([b7bc1d4](https://github.com/Hooandee/panel-de-control/commit/b7bc1d431e5cb379162c215f0cff903131911b1d))
* use Colores-style flag language toggle instead of dropdown ([f21d321](https://github.com/Hooandee/panel-de-control/commit/f21d3210a023dee200bb4fbc1bd31c2d1168c49f))
* wire auto-TDP control loop and RPCs ([d8d3aab](https://github.com/Hooandee/panel-de-control/commit/d8d3aab4bcb80957598b020895dd7eb159b559a6))
* wire TDP power-arc section into the panel ([4dcacd5](https://github.com/Hooandee/panel-de-control/commit/4dcacd56f306d4097dbdf005e5b7cd353521e905))


### Bug Fixes

* average GPU busy over a short burst to fix noisy Deck readings ([0e44bc4](https://github.com/Hooandee/panel-de-control/commit/0e44bc4a95bc18c264ffb0655162b389db366ba3))
* average GPU busy over a short burst to fix noisy Steam Deck readings ([47cec1f](https://github.com/Hooandee/panel-de-control/commit/47cec1fa61455d029b967c8d5703709a2d1f7f4f))
* contain power sliders within their card and make boost math NaN-safe ([07efd45](https://github.com/Hooandee/panel-de-control/commit/07efd4503976e80ff82e4e81b464f545617ba872))
* **customize:** guard against a corrupt saved layout bricking the panel ([f90ea01](https://github.com/Hooandee/panel-de-control/commit/f90ea01e0d98176e63fed732a30cf54ae62ef70e))
* enforce auto/manual margin invariant on profile load ([382e538](https://github.com/Hooandee/panel-de-control/commit/382e538696d440792305f95b1228c06d0c81598b))
* harden TDP RPC against bad scope/appid, keep lifecycle poller alive, guard atomic save path ([6fdb2c6](https://github.com/Hooandee/panel-de-control/commit/6fdb2c69a103a60e3ce92aebd35269ab903e1fad))
* keep auto-reset UI consistent and hide unbounded boost rails ([7cab9b4](https://github.com/Hooandee/panel-de-control/commit/7cab9b4d89cc3cf7f30ceae7fbcd5f9064fbac90))
* make advanced boost sliders optimistic and independent ([1025ad7](https://github.com/Hooandee/panel-de-control/commit/1025ad717ca41003627ab7515fbd31cc5b159053))
* remove unused pytest import (ruff in CI lints tests/) ([e3afb5b](https://github.com/Hooandee/panel-de-control/commit/e3afb5b6c8006dbcb56c055c1626870052a7f89e))
* ruff lint failure on main (unused import in tests/) ([cd831dd](https://github.com/Hooandee/panel-de-control/commit/cd831dd2b2f03793384e0d2027ce64bc88063cda))
* **system:** drive volume to the output channel (audioType 1) ([a979d49](https://github.com/Hooandee/panel-de-control/commit/a979d49b4dd0a5a16b1598ddf99a7f2c137237e4))
* **system:** hide battery cycle count when the firmware reports a fake 0 ([e7c04f3](https://github.com/Hooandee/panel-de-control/commit/e7c04f30f7802cf0ebf94fd94623c23308b6a888))
* **system:** show the real CPU model and label max frequency honestly ([6d91471](https://github.com/Hooandee/panel-de-control/commit/6d9147103ec7092b7f46859804b97e60dc21e0b8))
* **system:** stop the brightness/volume slider jumping on stale echoes ([eadc141](https://github.com/Hooandee/panel-de-control/commit/eadc14168b665dc4a09e2560a6a599a8f3156b81))
* tighten control-center spacing, iconography and layout ([6dfebe2](https://github.com/Hooandee/panel-de-control/commit/6dfebe2115d275fd592d99f1193e1e4c7c12b905))


### Performance Improvements

* **customize:** memoize tab/block id resolution on the render path ([42dcbdb](https://github.com/Hooandee/panel-de-control/commit/42dcbdbc3c42af8d0083d5902d79906a3c757408))
