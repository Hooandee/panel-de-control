# Terciopelo para el teclado táctil de Windows

Integración experimental para `TextInputHost.exe`, Windows 11 x64 build 26300.
Panel permite activar Terciopelo, comprobar el estado confirmado por el runtime,
probar la escritura y desactivar restaurando el aspecto anterior. La solicitud
es de la sesión del companion: no se activa por defecto ni modifica preferencias
persistentes de personalización de Windows. No es `osk.exe` ni el teclado de Steam.

## Arquitectura

La tarjeta de Temas usa el contrato existente del companion. Este inicia
`NativeKeyboard/PanelDeControl.KeyboardHost.exe serve` sin elevación, mantiene
su entrada abierta y procesa recibos JSONL acotados. `stop` o EOF solicitan
restauración. El host se conecta mediante `InitializeXamlDiagnosticsEx` a nuestra
DLL COM y mantiene un heartbeat; la DLL restaura al perderlo durante cuatro
segundos. Las escrituras y la limpieza ocurren en el Dispatcher de XAML.

El destino debe ser un único TextInputHost de la misma sesión y usuario, x64,
bajo Windows/SystemApps y con Windows.UI.Xaml observado. Se conserva el handle
del proceso; PID y tiempo de creación identifican su ejecución. Cada conexión
usa un nonce distinto, transmitido por la API de inicialización, y una tubería
local cuyo ACL permite al usuario y al AppContainer exacto del destino. El host
verifica el PID del cliente. No se empaqueta Windhawk, no se parchean ejecutables,
no se desactiva seguridad ni se necesita un servicio privilegiado para el tema.

El helper observa reinicios del proceso a intervalos de dos segundos, con hasta
tres intentos de conexión por ejecución. Las teclas nuevas llegan por el árbol
visual; una reconciliación de 250 ms verifica identidad, disposición de los
nodos propios, cambios de plantilla y caducidad. No lee ni registra texto,
contraseñas, teclas escritas, códigos de teclas ni secuencias de pulsaciones.
Los eventos de puntero solo cambian el aspecto local: no consumen eventos ni
capturan el puntero.

Se conservan los valores locales y bindings de las propiedades modificadas.
Restaurar un valor heredado usa ClearValue; un binding se repone tras limpiar el
override. Los callbacks quedan inertes al comenzar la restauración. Una limpieza
parcial conserva su seguimiento, informa del fallo y limita sus reintentos.
El módulo permanece fijado para que ningún delegado pueda apuntar a código
liberado; puede seguir cargado hasta que Windows cierre TextInputHost.

## Reglas y recursos

El motor y los tokens de Terciopelo están separados (`styler.cpp`, `terciopelo.h`
y `themes/terciopelo`). Se conserva la distribución y el contenido nativo, sin
coordenadas de una distribución española ni teclas dibujadas por encima.

La forma observada de una tecla es:

```text
KeyboardKey
  Grid
    Grid
      Border
      ContentControl
```

El motor valida esta forma, inserta una decoración no interactiva entre Border
y ContentControl, y verifica su pertenencia real. La placa se coloca solo en el
Grid que pertenece a KeyboardGrid y cuyos hijos son KeyboardKey. El marco se extiende al Grid padre de KeyboardGrid cuando contiene el GripperBar
observado: placa original, fondo oscuro y controles estándar de su barra. Se
conservan el radio, clipping y sombra nativos; no se dibuja fuera de la ventana
ni se modifica el contenido de emoji, portapapeles o campos de texto.
Las teclas visibles con forma desconocida impiden confirmar cobertura completa.

Terciopelo 0.2.13 aporta estos recursos y propiedades, extraídos de su CSS real:

| Propiedad | Adaptación |
|---|---|
| Cinco caras PNG 216×168: idle, hover, focus, press-v3 y focus-press-v3 | Incrustadas sin transformar; nine-grid de cortes 54, grosor 18 y outset 6 |
| Placa WebP 1708×478, fondo #0b0b0c | Textura original bajo el área de teclas |
| Tinta #f0dcb2, acento #d9c197, pulsación #fff3da | Aplicada a las etiquetas nativas, con restauración |
| Josefin Sans 400/600 | TTF oficial variable con licencia OFL; se preservan fuentes de iconos |
| Pulsación, hover y foco | Caras originales; cancelación y pérdida de captura restablecen la cara |
| Letras, números, iconos y distribuciones | Contenido nativo; se conservan tamaños y posiciones de Windows |
| Bloqueo de Mayús y teclas muertas | Se conservan cambios nativos de glifo y contenido; el halo dorado específico necesita un estado nativo observado |
| Polvo WebP 3240×140, 18 frames/720 ms | Sprite de 126×98 al pulsar, avance discreto y fundido en los últimos 144 ms, animado por Composition |
| Desplazamiento de texto pulsado | 3 px cuando el contenido nativo no tiene una transformación propia; restaurado al soltar |
| Sonido del teclado Steam | No se modifica el sonido nativo |

Los PNG y WebP se cargan desde RCDATA mediante un stream en memoria, sin depender
de acceso a rutas de Panel desde AppContainer. Se exige LoadCompleted/Success.
Josefin se extrae a un archivo propio de nombre único en TemporaryFolder del
proceso destino y se referencia mediante ms-appdata. No se instala globalmente.
Se verifica una diferencia de métricas frente al fallback con una cadena fija,
y se contrasta visualmente la tipografía; no se inspecciona texto del teclado.
La restauración repone FontFamily y elimina el archivo propio cuando el sistema
lo permite. Si sigue en uso, se conserva una sola ruta y se verifican sus bytes
antes de reutilizarla; no se sobrescriben archivos ajenos.

## Estado y diagnóstico

`Requested` expresa intención; `applied` requiere conexión vigente, imágenes y
fuente resueltas, y todas las teclas candidatas visibles confirmadas, sin tareas
pendientes ni errores. Una preferencia guardada o un proceso arrancado no bastan.
El teclado cerrado queda esperando, y los errores o silencios retiran el estado
aplicado. La UI muestra restauración sin confirmar si falta el recibo necesario.

Los diagnósticos incluyen build, arquitectura, PID, HRESULT, cobertura de teclas,
restauraciones y un árbol acotado de tipos/handles efímeros/padres. El catálogo de
estados solo admite nombres definidos y deduplicados, sin estados actuales por
tecla ni transiciones. En la plantilla observada de build 26300 no se encontraron
grupos VSM en KeyboardKey y sus dos Grid; no se inventan selectores de latched.
El campo de prueba de Panel no envía su texto al companion ni a los diagnósticos.

## Fuentes y licencias

Panel es GPL-3.0. UWPSpy y el mod Notification Center Styler declaran GPL-3.0,
pero no se ha trasladado su código. Windhawk contiene dependencias con licencias
propias: no se empaqueta ni enlaza ningún componente suyo. AromaKitsune usa MIT;
sus estilos solo sirven como referencia de viabilidad para otras superficies.
Josefin se distribuye sin modificar, desde una revisión inmutable de google/fonts,
con su OFL y procedencia en `themes/terciopelo/fonts`.

- [Inicialización XAML](https://learn.microsoft.com/en-us/windows/win32/api/xamlom/nf-xamlom-initializexamldiagnosticsex): API documentada; no garantiza soporte de cada teclado futuro.
- [IVisualTreeService](https://learn.microsoft.com/en-us/windows/win32/api/xamlom/nn-xamlom-ivisualtreeservice): árbol y cambios dinámicos.
- [UWPSpy](https://github.com/m417z/UWPSpy/blob/main/UWPSpy/visualtreewatcher.cpp): referencia del mecanismo de conexión; los nombres VisualDiagConnectionN son detalles de implementación.
- [Notification Center Styler](https://github.com/ramensoftware/windhawk-mods/blob/main/mods/windows-11-notification-center-styler.wh.cpp): motor dependiente de Windhawk, no runtime independiente.
- [AromaKitsune](https://github.com/AromaKitsune/Windows-XAML-Styles): sus estilos de sugerencias no prueban la personalización de cada tecla.
- [CompositionNineGridBrush](https://learn.microsoft.com/en-us/uwp/api/windows.ui.composition.compositionninegridbrush): cortes y escalas independientes.
- [LoadedImageSurface](https://learn.microsoft.com/en-us/uwp/api/windows.ui.xaml.media.loadedimagesurface.startloadfromstream): decodificación desde memoria.
- [URI de recursos](https://learn.microsoft.com/en-us/windows/uwp/app-resources/uri-schemes): alcance de ms-appdata.
- [Fuentes UWP](https://learn.microsoft.com/en-gb/answers/questions/120521/loading-a-font-with-multiple-files): referencia de FontFamily desde datos locales.

## Compilar y probar

Windows x64, Visual Studio 2022 con Desktop development with C++ y SDK de
Windows, CMake 3.24 o posterior:

```powershell
./windows/native/keyboard/build.ps1
./windows/native/keyboard/dist/PanelDeControl.KeyboardHost.exe discover
./windows/native/keyboard/dist/PanelDeControl.KeyboardHost.exe serve
# Escribir stop y pulsar Intro para restaurar y terminar serve.
```

El runtime queda en `windows/native/keyboard/dist`. Windows CI lo integra en
`HardwareBroker/NativeKeyboard` del paquete MSIX. Para compilar Panel completo,
seguir [Windows](README.md), generando primero `pnpm build:windows-theme-host`
y ejecutando el script nativo. `probe-key-face` se conserva únicamente como
ensayo CLI de una tecla durante ocho segundos; Panel usa `serve`.

Comprobaciones locales:

```sh
python3 windows/native/keyboard/tests/test_theme_package.py
clang++ -std=c++17 -Wall -Wextra -Werror windows/native/keyboard/tests/protocol_test.cpp -o /tmp/keyboard-protocol-test
/tmp/keyboard-protocol-test
dotnet test windows/tests/PanelDeControl.Hardware.Tests/PanelDeControl.Hardware.Tests.csproj -c Release --filter NativeKeyboard
```

Recorrido manual:

1. Instalar el paquete experimental completo y abrir Panel > Temas > Teclado de Windows.
2. Activar Terciopelo; abrir el teclado y comprobar estado, cobertura y aspecto.
3. Escribir en el campo de prueba; comprobar letras, números, Mayús/Bloq Mayús,
   espacio, Intro, borrar, AltGr y teclas muertas. Comprobar hover, pulsación larga,
   cancelación, deslizamiento y uso de mando donde lo permita Windows.
4. Cerrar y abrir el teclado; cambiar distribución, tamaño y modo flotante.
   Comprobar incorporación de teclas nuevas, legibilidad y ausencia de recortes.
5. Reiniciar TextInputHost y comprobar reconexión sin activar otra instancia.
6. Desactivar desde Panel y confirmar aspecto, tipografía e indicadores originales.
7. Repetir con pérdida del helper, desactivación inmediata y cierre de Panel.
8. Si la restauración queda sin confirmar, guardar el diagnóstico y reiniciar
   TextInputHost o cerrar sesión. Panel no termina el teclado automáticamente.
9. Antes de extender compatibilidad, validar actualización y desinstalación con
   tema activo, versiones adicionales de Windows y las distribuciones afectadas.

La validación física disponible incluye aplicación y restauración de las 40
teclas del teclado estándar en ROG Xbox Ally X, build 26300 x64, con placa y fuente
privada. Las pruebas de compilación y protocolo no sustituyen las pruebas de
interacción, distribuciones y lifecycle del artefacto instalado completo.
