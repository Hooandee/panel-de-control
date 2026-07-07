# Changelog

## [0.8.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.7.0...panel-de-control-v0.8.0) (2026-07-07)


### Features

* recognise the OneXPlayer OneXFly Apex with a generic AMD TDP path ([#78](https://github.com/Hooandee/panel-de-control/issues/78)) ([e407d17](https://github.com/Hooandee/panel-de-control/commit/e407d17b74a70f35669dbaf12241111c3e3bf6e7))

## [0.7.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.6.0...panel-de-control-v0.7.0) (2026-07-07)


### Features / Novedades

* The volume and brightness buttons can now show the exact value on screen without opening the panel: turn on "Show value when changing volume or brightness" under Ajustes and a small toast shows the number as you adjust — speaker/sun icon, silent, and off by default. ([#73](https://github.com/Hooandee/panel-de-control/issues/73)) ([27bb34a](https://github.com/Hooandee/panel-de-control/commit/27bb34adba25d0949493d9c236d4e1380786d1cb))
* **ES:** Los botones de volumen y brillo ahora pueden mostrar el valor exacto en pantalla sin abrir el panel: activa «Mostrar valor al cambiar volumen o brillo» en Ajustes y un pequeño aviso muestra el número mientras ajustas — con icono de altavoz/sol, silencioso y desactivado por defecto. ([#73](https://github.com/Hooandee/panel-de-control/issues/73)) ([27bb34a](https://github.com/Hooandee/panel-de-control/commit/27bb34adba25d0949493d9c236d4e1380786d1cb))

## [0.6.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.5.0...panel-de-control-v0.6.0) (2026-07-06)


### Features / Novedades

* You can now hide the battery health info — health, charge cycles and capacity — from the Battery card, with a single toggle under Ajustes → Personalizar, for anyone who'd rather not keep an eye on it. You can also move between tabs with the L1/R1 shoulder buttons. ([#51](https://github.com/Hooandee/panel-de-control/issues/51)) ([bbba2ed](https://github.com/Hooandee/panel-de-control/commit/bbba2ed325b863c94cb75b09513af28c1b4610d2))
* **ES:** Ahora puedes ocultar la información de salud de la batería —salud, ciclos de carga y capacidad— de la tarjeta de Batería, con un solo interruptor en Ajustes → Personalizar, para quien prefiera no estar pendiente de ella. Además puedes cambiar de pestaña con los gatillos L1/R1. ([#51](https://github.com/Hooandee/panel-de-control/issues/51)) ([bbba2ed](https://github.com/Hooandee/panel-de-control/commit/bbba2ed325b863c94cb75b09513af28c1b4610d2))

## [0.5.0](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.4.2...panel-de-control-v0.5.0) (2026-07-06)


### Features / Novedades

* MSI Claw: the Ventiladores tab now shows the fan curve your Claw's firmware applies, read-only, with the live temperature marker — so you can see how it behaves even though its driver doesn't let apps edit the curve yet. The fan RPM monitor also shows both fans correctly. Editable, safe fan-speed control for the Claw is in progress. ([#42](https://github.com/Hooandee/panel-de-control/issues/42)) ([414fca1](https://github.com/Hooandee/panel-de-control/commit/414fca15c6f7e9cd5f305e7a38aa3d29d4d6f246))
* **ES:** MSI Claw: la pestaña Ventiladores ahora muestra la curva de ventilación que aplica el firmware de tu Claw, en solo lectura, con la marca de temperatura en vivo — así ves cómo se comporta aunque su driver todavía no deje a las apps editar la curva. El monitor de RPM también muestra bien los dos ventiladores. El control editable y seguro de la velocidad del ventilador para el Claw está en desarrollo. ([#42](https://github.com/Hooandee/panel-de-control/issues/42)) ([414fca1](https://github.com/Hooandee/panel-de-control/commit/414fca15c6f7e9cd5f305e7a38aa3d29d4d6f246))

## [0.4.2](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.4.1...panel-de-control-v0.4.2) (2026-07-06)


### Performance Improvements / Mejoras de rendimiento

* The control panel and its live readouts stay responsive even when a system tool (the display compositor, the fan service) is slow to answer — the heavy work now runs in the background instead of briefly freezing the panel. ([#40](https://github.com/Hooandee/panel-de-control/issues/40)) ([c404201](https://github.com/Hooandee/panel-de-control/commit/c4042011f88502ef2afaabbc094a07a312a1f51a))
* **ES:** El panel y sus lecturas en vivo siguen respondiendo aunque una herramienta del sistema (el compositor de pantalla, el servicio de ventiladores) tarde en contestar — el trabajo pesado ahora corre en segundo plano en vez de congelar el panel un instante. ([#40](https://github.com/Hooandee/panel-de-control/issues/40)) ([c404201](https://github.com/Hooandee/panel-de-control/commit/c4042011f88502ef2afaabbc094a07a312a1f51a))

## [0.4.1](https://github.com/Hooandee/panel-de-control/compare/panel-de-control-v0.4.0...panel-de-control-v0.4.1) (2026-07-05)


### Bug Fixes / Correcciones

* Keep panel color working when gamescope's socket appears after load: the Pantalla (display color) tab no longer vanishes when the plugin starts before gamescope is ready — detection now recovers on its own instead of staying off for the whole session. ([d3fd9d2](https://github.com/Hooandee/panel-de-control/commit/d3fd9d22d8165793c5d0f695148e339b44d92ef4))
* **ES:** El control de color sigue funcionando cuando el socket de gamescope aparece tras el arranque: la pestaña Pantalla ya no desaparece si el plugin arranca antes de que gamescope esté listo — la detección se recupera sola en vez de quedarse desactivada toda la sesión. ([d3fd9d2](https://github.com/Hooandee/panel-de-control/commit/d3fd9d22d8165793c5d0f695148e339b44d92ef4))

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
* RGB lighting card — open or install Colores from Sistema ([5e96f91](https://github.com/Hooandee/panel-de-control/commit/5e96f91a0ad3b75e43e5a17b0243925235cdf789))


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
* assistive auto-adaptation — GPU-driven auto-TDP, adaptive fan mode, learning ([3bd6488](https://github.com/Hooandee/panel-de-control/commit/3bd64889349b174f67741c909fd0d8d2f8bd95c8))
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
