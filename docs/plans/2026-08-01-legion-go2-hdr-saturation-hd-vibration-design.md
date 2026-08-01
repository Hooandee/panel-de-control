# Saturación HDR y vibración HD en Legion Go 2

Fecha: 2026-08-01

## Objetivo

Integrar en Panel de Control dos capacidades de la Lenovo Legion Go 2 sin importar
backends completos de otros plugins:

1. Saturación independiente para contenido SDR y PQ/HDR, con perfiles globales y por
   juego.
2. Intensidad, patrón de vibración HD y háptica del touchpad mediante el driver Linux
   `hid-lenovo-go`, también con perfiles globales y por juego.

La implementación debe ampliar los backends actuales de Pantalla y Mandos. Los proyectos
externos sirven como evidencia de viabilidad y referencia de comportamiento, no como una
segunda arquitectura dentro del plugin.

## Fuera de alcance

- Instalar o ejecutar DeckyVibranceHDR, LeGo-Vibe-Control o LeGo2BrightnessFix.
- Copiar sus stores, servicios, detección, RPC o frontend.
- Sustituir HHD o InputPlumber como propietarios del enrutado y la emulación del mando.
- Instalar automáticamente un script de pantalla o modificar el EDID publicado por
  gamescope.
- Mostrar controles si la interfaz real no está disponible.
- Tratar la saturación SDR y HDR como el mismo valor.
- Prometer confirmación de hardware donde el driver solo confirma que aceptó una
  escritura.

## Evidencia y fuentes

### Pantalla

- Lenovo especifica para la Legion Go 8ASP2 un panel OLED de 1920×1200, hasta 144 Hz,
  1100 nits de pico HDR, 100% DCI-P3 y DisplayHDR True Black 1000:
  https://psref.lenovo.com/syspool/Sys/PDF/Legion/Legion_Go_8ASP2/Legion_Go_8ASP2_Spec.html
- Gamescope mantiene looks separados por EOTF gamma 2.2 y PQ. Su protocolo Wayland
  `set_look` recibe ambos LUT de forma coordinada:
  https://github.com/ValveSoftware/gamescope/blob/master/protocol/gamescope-control.xml
- Gamescope aplica el look 3D antes de linealizar, hacer gamut mapping y tone mapping:
  https://github.com/ValveSoftware/gamescope/blob/master/src/color_helpers.cpp
- ITU-R BT.2100 define ICtCp y las funciones necesarias para representar HDR:
  https://www.itu.int/rec/R-REC-BT.2100/en
- DeckyVibranceHDR demuestra que un LUT PQ en ICtCp permite variar crominancia sin
  modificar intencionadamente intensidad ni tono:
  https://github.com/Rayekkk/DeckyVibranceHDR

### Mandos

- Lenovo documenta cuatro intensidades integradas: apagada, débil, media y fuerte:
  https://support.lenovo.com/au/en/manuals/legion_go_8
- El driver oficial `hid-lenovo-go` publica intensidad global, patrón por asa y controles
  separados para la vibración del touchpad. Sus índices definen `off`, `low`, `medium`,
  `high` y los patrones `fps`, `racing`, `standard`, `spg`, `rpg`:
  https://github.com/torvalds/linux/blob/master/drivers/hid/hid-lenovo-go.c
- LeGo-Vibe-Control confirma el uso real de esas superficies, la reescritura tras
  reconexión/suspensión y su utilidad en perfiles por juego:
  https://github.com/Rayekkk/LeGo-Vibe-Control

### Compatibilidad legal

Las implementaciones de referencia están publicadas bajo BSD-3-Clause, con partes antiguas
del plugin de vibración bajo MIT. Panel de Control no copiará sus backends. Si durante la
implementación resultara imprescindible adaptar una función protegible, se aislará, se
conservará la atribución requerida y se actualizará `THIRD_PARTY_NOTICES.md`. Las fórmulas
de color se implementarán independientemente contra BT.2100 y el pipeline oficial de
gamescope.

## Matriz de consumidores

| Consumidor | Saturación HDR | Vibración HD | Comportamiento esperado |
|---|---:|---:|---|
| Legion Go 2 + gamescope con look PQ | Sí | Si existe `hid-lenovo-go` | Capacidades completas y perfiles por juego |
| Legion Go 2 sin look PQ | No | Si existe `hid-lenovo-go` | Ocultar HDR, mantener vibración |
| Legion Go 2 sin `hid-lenovo-go` | Según gamescope | No | Mantener fallback de vibración existente, sin modos inventados |
| Legion Go original | Según EDID/gamescope | Solo superficies realmente descubiertas | No asumir paridad con Go 2 |
| Legion Go S | Según EDID/gamescope | No mientras el driver no publique los atributos | Mantener `FF_GAIN` si está disponible |
| ROG Ally | Según EDID/gamescope | Backend ASUS actual | Sin cambios de comportamiento |
| Pantalla externa | No | Sin cambios | Retirar temporalmente el look HDR del panel interno |
| Plataforma Windows experimental | Fuera de esta entrega | Fuera de esta entrega | Sin falsa paridad con Linux |

## Diseño de saturación HDR

### Estado y perfiles

`ColorStore` incorporará `hdr_saturation`, entero en porcentaje:

- `100`: identidad.
- Rango permitido inicial: `100..150`.
- Aviso visual por encima de `130`, donde aumenta el riesgo de clipping de canal.
- Ámbito global y por juego mediante el mismo `ScopedProfileStore` ya usado por el perfil
  de pantalla.

El campo existente `saturation` conserva su significado y sus datos, pero el frontend lo
etiquetará como saturación SDR cuando el control HDR también esté disponible. La migración
añade `hdr_saturation: 100` a perfiles antiguos sin reinterpretar su saturación guardada.

Los presets de color existentes siguen afectando al look SDR. No alterarán automáticamente
la saturación HDR: un preset diseñado en gamma 2.2 no es una calibración de contenido PQ.

### Backend

Se ampliará `GamescopeColorBackend`; no se añadirá un backend paralelo.

1. El generador gamma 2.2 actual seguirá produciendo el look SDR completo.
2. Un generador PQ nuevo construirá un LUT de 33³ entradas:
   - decodificación SMPTE ST 2084/PQ;
   - conversión BT.2020 lineal → LMS → ICtCp;
   - multiplicación exclusiva de Ct y Cp por `hdr_saturation / 100`;
   - conversión inversa y codificación PQ;
   - clamp únicamente al terminar el viaje de ida y vuelta.
3. El backend publicará ambos looks juntos con
   `gamescopectl set_look <g22.cube> <pq.cube>` para que una actualización no borre la
   otra mitad.
4. Los archivos se escribirán en dos slots alternos mediante temporal, `fsync` y rename.
5. La generación costosa tendrá debounce; no se generará en cada tick del slider.

El LUT PQ identidad también se enviará cuando sea necesario conservar simultáneamente el
look SDR. No se ejecutará `unset_look` de manera que pueda borrar accidentalmente el otro
EOTF.

### Detección y ciclo de vida

La capacidad HDR de saturación exige simultáneamente:

- panel interno activo;
- EDID legible que anuncie SMPTE ST 2084/PQ;
- gamescope accesible;
- soporte de look en el gamescope instalado;
- aplicación satisfactoria de una pareja de LUT de prueba/identidad.

El panel deja de afirmar soporte si falla cualquiera de esas condiciones. Al conectar una
pantalla externa se carga una pareja que no aplique la personalización del panel interno y
se conserva el deseo del usuario. Al volver al panel interno se reaplica.

Se reutilizarán los mecanismos actuales de cambio de juego, cambio HDR, arranque y
reaplicación. Se añadirá detección de reinicialización de gamescope tras suspensión y un
reintento acotado. Los diagnósticos registrarán socket, versión/capacidad, EOTF, rutas de LUT,
último comando, código de salida y valor deseado, sin presentar esos datos como readback
visual del panel.

### Interfaz

En Pantalla:

- `Saturación SDR`: rango actual.
- `Saturación HDR`: 100–150%, solo cuando la capacidad está confirmada.
- Texto breve a partir de 135% indicando posible pérdida de detalle saturado.
- El selector global/por juego existente controla ambos campos del perfil.

No se mezclará con el interruptor que activa HDR. El usuario puede preparar una saturación
HDR por juego aunque el juego no esté emitiendo HDR en ese instante; el look solo afecta a
frames PQ.

## Diseño de vibración HD

### Extensión del backend existente

`VibrationController` conservará sus rutas ASUS, `FF_GAIN`, prueba evdev y fallback de
activación. Se añadirá un adaptador interno estrecho para `hid-lenovo-go` que tendrá
prioridad cuando encuentre exactamente una superficie coherente:

- `rumble_intensity` y `rumble_intensity_index`;
- `left_handle/rumble_mode` y su índice;
- `right_handle/rumble_mode` y su índice;
- `touchpad/vibration_enabled` y su índice;
- `touchpad/vibration_intensity` y su índice.

El adaptador no codificará como autoridad los textos conocidos. Leerá los `*_index` y solo
expondrá opciones presentes. Los valores oficiales conocidos sirven para ordenar y traducir,
no para fabricar capacidades ausentes.

### Modelo de estado

El bloque de vibración admitirá, además de los campos existentes:

- `intensity`: `off | low | medium | high`;
- `pattern`: `fps | racing | standard | spg | rpg`;
- `touchpad_enabled`: booleano;
- `touchpad_intensity`: `off | low | medium | high`;
- listas de opciones leídas del driver;
- `confirmation`: `driver_readback | accepted | unavailable`;
- resultado independiente de la última escritura de cada atributo.

El patrón visible es único y se escribe en ambas asas dentro de una operación coordinada.
Si una escritura funciona y la otra falla, el estado será parcial/fallido y se mostrará en
diagnósticos; no se afirmará que ambos mandos quedaron configurados.

### Persistencia por juego

Se ampliará el perfil de vibración ya implementado en la rama de Mandos. El perfil global y
cada juego podrán guardar intensidad, patrón y controles del touchpad. La resolución seguirá
el contrato actual de `follow_global`.

La configuración efectiva se reescribirá:

- al guardar el perfil;
- al entrar o salir de un juego;
- al arrancar Decky;
- al reaparecer el endpoint tras reconexión;
- varias veces, con espera acotada, después de suspensión si el dispositivo tarda en volver.

No se añadirá un segundo observador de juego ni otro store.

### Prueba y readback

La prueba seguirá usando el nodo evdev con `FF_RUMBLE` y VID:PID asociado al dispositivo
descubierto. Será temporal, no cambiará el perfil y restaurará cualquier estado que tenga que
tocar.

Algunos firmwares devuelven durante un instante el valor anterior. Una escritura aceptada no
equivale a confirmación física. El backend podrá reintentar una lectura estabilizada, pero si
no obtiene coincidencia reportará `accepted` y conservará el valor deseado, nunca un readback
inventado.

### Interfaz

En Mandos, cuando `hid-lenovo-go` publique las capacidades:

- selector de intensidad con los cuatro niveles disponibles;
- selector de patrón con los modos disponibles;
- interruptor de vibración del touchpad;
- selector de intensidad del touchpad;
- prueba de vibración;
- estado global/por juego mediante el selector existente.

En otras máquinas se seguirá dibujando exactamente la superficie que ofrezca su backend
actual. No aparecerán controles de patrón ni touchpad por nombre de máquina solamente.

## EDID y brillo de Legion Go 2

LeGo2BrightnessFix resuelve dos problemas independientes: brillo mientras el panel funciona
en PQ y metadatos incorrectos para juegos afectados por una versión antigua del parser de
DXVK. No forman parte del port de saturación o vibración.

Panel de Control añadirá a los diagnósticos de Pantalla, si están disponibles:

- identidad del panel interno;
- soporte PQ anunciado;
- luminancias HDR publicadas;
- ruta del EDID que gamescope entrega a Proton;
- presencia de un script de pantalla de la distribución.

No reemplazará ese script ni reescribirá el EDID en esta entrega. Bazzite y SteamOS pueden
resolver estas carencias de forma distinta; una corrección futura deberá nacer de evidencia
recogida en la máquina y ser específica, reversible y compatible con la distribución.

## Fallos y recuperación

- Gamescope no soporta pareja de looks: se mantiene SDR actual y se oculta saturación HDR.
- Generación PQ falla: se conserva el último LUT válido, se registra el fallo y no se cambia
  el valor aplicado declarado.
- Cambio de pantalla: se retira el look específico del panel interno y se reaplica al volver.
- Endpoint `hid-lenovo-go` ambiguo: no se escribe; diagnósticos enumeran candidatos.
- Un atributo desaparece entre detección y escritura: la operación falla de forma parcial,
  se invalida la caché y se redescubre.
- Reconexión o suspensión: reintento acotado, sin bucles infinitos.
- Otro componente sobrescribe una superficie: se informa del conflicto; el plugin no entra
  en una pelea de escrituras continua.
- Perfil corrupto o con opción ya no publicada por el driver: se sanea a una opción segura
  disponible y se conserva diagnóstico del valor descartado.

## Estrategia de pruebas

### Unitarias de color

- PQ encode/decode dentro de tolerancia de código de 10 bits.
- Identidad exacta al 100%.
- Negro permanece negro y los grises mantienen Ct/Cp nulos.
- Intensidad ICtCp estable dentro de tolerancia.
- Saturación creciente monotónica en muestras dentro de gamut.
- Ninguna salida fuera de `0..1`.
- Orden rojo-rápido compatible con el cargador `.cube` de gamescope.
- Coordinación: actualizar PQ no borra G22 y viceversa.
- Migración de perfiles: saturación antigua queda en SDR, HDR empieza neutral.

### Unitarias de vibración

- Detección exige una superficie completa y no ambigua.
- Opciones proceden de `*_index`.
- Aplicación escribe ambas asas y detecta fallo parcial.
- Touchpad es independiente de los motores de las asas.
- Resolución global/por juego y `follow_global`.
- Reaplicación tras cambio de juego, reconexión y suspensión.
- Estado `accepted` no se presenta como readback confirmado.
- Fallback ASUS y `FF_GAIN` permanecen sin regresiones.

### Integración y gates

- Suite backend y frontend completa.
- Ruff, typecheck y build de producción.
- Gate transversal vigente sobre el diff final.
- Inspección de diagnóstico sin escribir en hardware no soportado.

### Validación física en Legion Go 2

1. Registrar distribución, kernel, gamescope, EDID y endpoints antes de escribir.
2. Comparar 100%, 115%, 130% y 150% en un juego HDR real, verificando que Steam/SDR no
   cambia y que el LUT PQ activo coincide con el perfil.
3. Cambiar entre dos juegos con valores HDR distintos y volver al escritorio.
4. Conectar y retirar una pantalla externa.
5. Suspender/reanudar con HDR y con cada patrón de vibración.
6. Probar las cuatro intensidades y los cinco patrones, confirmando ambos mandos.
7. Probar touchpad activado, desactivado y con intensidad independiente.
8. Desconectar/reconectar los mandos y comprobar que vuelve el perfil efectivo.
9. Repetir comprobaciones de no regresión en Legion Go, Legion Go S y ROG Ally según
   disponibilidad.

## Criterios de aceptación

- Saturación HDR modifica únicamente contenido PQ y persiste por juego.
- La saturación SDR existente mantiene datos y comportamiento.
- Ninguna mitad del look de gamescope borra la otra.
- Legion Go 2 ofrece únicamente los modos publicados por su driver.
- Intensidad, patrón y touchpad se restauran al cambiar de juego, suspender o reconectar.
- Las demás máquinas mantienen sus backends y superficies actuales.
- Pantalla externa, ausencia de driver y kernels antiguos degradan de forma segura.
- UI y diagnósticos distinguen valor deseado, escritura aceptada y readback confirmado.
- No se ha importado ningún backend externo completo.
