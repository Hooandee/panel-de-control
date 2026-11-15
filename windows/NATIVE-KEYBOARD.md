# Teclado táctil nativo: Terciopelo experimental

Esta implementación prepara la integración y el descubrimiento del teclado de
Windows 11. **Todavía no aplica Terciopelo.** El bloqueo concreto es identificar
las teclas y sus estados en el árbol real de `TextInputHost.exe`, comprobar si
son elementos XAML modificables y validar el transporte de sus texturas. No se
han sustituido esos requisitos por cambios de color del registro.

## Arquitectura y alcance

El widget usa el companion existente para solicitar una exploración. El contrato
se añade como operación y campo opcional del pipe de Temas, conservando el estado
de Steam separado. La intención dura solo la sesión del companion y arranca
desactivada. `connected` describe la última exploración, no una conexión vigente:
la DLL se desuscribe antes de entregar su recibo. Los errores locales también
ofrecen un diagnóstico sanitizado copiable. El companion
lanza `NativeKeyboard/PanelDeControl.KeyboardHost.exe discover` como el usuario
interactivo, sin elevación. El host solo acepta un `TextInputHost.exe` de la misma
sesión y usuario, bajo `Windows/SystemApps`, x64 y con `Windows.UI.Xaml.dll`
observada. Mantiene abierto el proceso durante la operación y comprueba el PID
del emisor del recibo. Windows ARM64, otros frameworks y destinos ambiguos se
rechazan. Esto es una lista de capacidades candidatas, no una certificación de
todas las versiones de Windows 11.

`PanelDeControl.KeyboardTap.dll` es un servidor COM propio, sin registro global,
cargado por `InitializeXamlDiagnosticsEx`. Implementa `IObjectWithSite` y escucha
`IVisualTreeService` en un trabajador. El host prueba como máximo cuatro nombres
de conexión; la DLL observa tres segundos, con un máximo de 512 nodos. Devuelve
solo tipo, handle efímero y relación padre; nunca `Name`, `Text`, valores de
propiedades, contraseñas, contexto de error XAML ni eventos de entrada.

El pipe es local, de una instancia, con acceso del usuario y escritura para
el SID AppContainer del destino, si lo tiene; el receptor exige el PID del proceso previamente autorizado.
El host deriva el namespace de la tubería del token real de TextInputHost.
El acceso desde ese AppContainer está pendiente de comprobar. La conexión
a una sesión de diagnóstico ya ocupada también puede ser rechazada. No se
instala Windhawk, no se alteran binarios de Windows, servicios, ACL de Windows,
registro de personalización ni preferencias anteriores del teclado.

La DLL desuscribe al terminar. Si falla la desuscripción mantiene su objeto y
referencia de módulo para no dejar callbacks colgantes; no reintenta sin límite.
Windows puede mantener la DLL cargada hasta cerrar TextInputHost. No se fuerza
su descarga ni se termina el teclado desde Panel. Una caída del helper no deja
estilos porque esta versión no escribe propiedades. El timeout del companion
termina únicamente su helper. El API externo de conexión puede bloquear; por
eso está aislado del companion y del event loop.

La elección de helper separado limita el impacto de un bloqueo en la conexión
XAML. El motor y los recursos del tema están separados; no se ha creado otro
teclado, un overlay de teclas ni un framework general de temas.

## Evidencia técnica y licencias

| Fuente | Hecho documentado o deducido | Límite |
|---|---|---|
| [InitializeXamlDiagnosticsEx](https://learn.microsoft.com/en-us/windows/win32/api/xamlom/nf-xamlom-initializexamldiagnosticsex) | API documentada: PID, DLL TAP y CLSID que implementa IObjectWithSite | No promete acceso a cada tecla de Windows |
| [IVisualTreeService](https://learn.microsoft.com/en-us/windows/win32/api/xamlom/nn-xamlom-ivisualtreeservice) | Suscripción, creación y escritura de propiedades XAML | No demuestra que el teclado publique teclas como controles |
| [UWPSpy](https://github.com/m417z/UWPSpy/blob/main/UWPSpy/UWPSpy.cpp), [watcher](https://github.com/m417z/UWPSpy/blob/main/UWPSpy/visualtreewatcher.cpp) | Del código: export de Windows.UI.Xaml, conexiones VisualDiagConnectionN; suscripción fuera del hilo que entrega el site para evitar un bloqueo observado por el autor | Nombres de conexión y uso entre hilos son dependencias de implementación; no contrato público |
| [Notification Center Styler](https://github.com/ramensoftware/windhawk-mods/blob/main/mods/windows-11-notification-center-styler.wh.cpp) | Motor con overrides de propiedades y estados, integrado con APIs y hooks Windhawk | No es una DLL independiente directamente redistribuible sin su host |
| [AromaKitsune](https://github.com/AromaKitsune/Windows-XAML-Styles/blob/main/styles/NotificationCenter-Dark.yaml) | Ejemplo real para TextInputHost: SuggestionUIGrid y panel/título de sugerencias; usa WindhawkBlur | No contiene un mapa de teclas; WindhawkBlur no es un control XAML estándar |
| [Image.NineGrid](https://learn.microsoft.com/en-us/uwp/api/windows.ui.xaml.controls.image.ninegrid) | XAML puede preservar zonas de una imagen | No equivale automáticamente a border-image con outset ni prueba que se pueda insertar en la plantilla del teclado |
| [ImageBrush.ImageSource](https://learn.microsoft.com/en-us/uwp/api/windows.ui.xaml.media.imagebrush.imagesource) | Carga asíncrona; hay que observar ImageOpened/ImageFailed | Un setter sin excepción no confirma una textura visible |

Panel tiene licencia GPL-3.0. UWPSpy y el mod concreto Notification Center
Styler declaran GPL-3.0; no se ha trasladado su código. Windhawk tiene GPL-3.0 en
raíz, pero incluye dependencias con licencias propias (por ejemplo MIT/BSD en
bibliotecas del motor y su extensión de VS Code con su propio LICENSE). No se
empaqueta ni enlaza ninguno de esos componentes. AromaKitsune usa MIT: sus
selectores se citan como evidencia, sin copiar sus estilos. La implementación
nueva usa directamente interfaces del SDK de Windows; no trae un styler
Windhawk escondido.

## Inventario visual original

Origen: Terciopelo 0.2.13, `keyboard.css`, `theme.json` y recursos del tema
original. `themes/terciopelo/theme.json` conserva tokens, hashes SHA-256 y los
nombres de sus cinco estados. Las imágenes se copian sin transformar. El
manifiesto declara `applicationEnabled: false` y no inventa bindings XAML.

| Recurso/propiedad | Original | Estado aquí |
|---|---|---|
| Placa | velvet-plate.webp, 1708×478; fondo #0b0b0c | Empaquetada, integridad comprobable; no aplicada |
| Caras | idle, hover, focus, press-v3, focus-press-v3; PNG RGBA 216×168 | Cinco originales empaquetados; no aplicados |
| Geometría | border-image 54 fill / 18px / 6px stretch; margen 3px 3px 4px | Inventariada; nine-slice con outset pendiente |
| Tinta | #f0dcb2; secundaria al 60%; especiales #d9c197 | Tokens inventariados; no aplicados |
| Pulsación | tinta #fff3da; texto baja 3px | Necesita estados reales; no se capturan pulsaciones |
| Modificadores | #f6d68c y halo dorado, capa radial | Necesita estado latched/dead-key real |
| Fuente | Terciopelo Josefin 400/600, WOFF2, fallback Motiva Sans | No empaquetada: falta licencia original adjunta y verificar formato XAML |
| Tamaños CSS | letras 19px, números 16px, secundarias 10/9px, especiales 9.5px | No trasladar directamente a DIPs sin comparar escalado |
| Extensiones | radio 10px; gradiente #1d1c20 a #0f0e11 | Depende de árbol real |
| Emojis | radio 8px; foco champagne, texto #121113 | No modificar emoji/sugerencias por coincidir en el mismo proceso |
| Polvo | velvet-dust.webp, 3240×140; 18 frames/720ms | Original empaquetado; efecto pendiente |

Los tamaños de las imágenes y los hashes quedan separados de cualquier regla
por distribución. No se fijan posiciones ni se dibujan letras sobre el teclado.
El sonido sintetizado del tema Steam no se migra en esta fase visual.

### Transporte de texturas pendiente

Una ruta `ms-appx` se resuelve en el contexto del paquete de TextInputHost, no
necesariamente en el de Panel. Tampoco se asume que el AppContainer pueda abrir
una ruta local de nuestro MSIX o que WebP/WOFF2 se decodifiquen allí. La primera
prueba debe verificar acceso, decodificación y `ImageOpened` en el proceso real.
Si el acceso directo falla, evaluar enviar bytes verificados desde el companion
y cargar un stream en memoria; no conceder acceso amplio al disco ni usar una
URL remota. No se ha implementado esa alternativa sin evidencia del control
destino. Antes de escribir una propiedad habrá que conservar su valor local,
restaurar con ClearValue si originalmente no existía, respetar bindings/animaciones
y comprobar el readback en el hilo propietario de cada control. La recuperación
por pérdida del companion debe residir en la DLL, porque instalador y
actualizador pueden terminar el companion forzosamente.

## Compilar

Windows 11 x64, Visual Studio 2022 con Desktop development with C++ y SDK de
Windows, CMake 3.24 o posterior. Desde PowerShell:

```powershell
./windows/native/keyboard/build.ps1
./windows/native/keyboard/dist/PanelDeControl.KeyboardHost.exe discover
```

La salida queda en `windows/native/keyboard/dist`. No ejecuta ni registra el
runtime al compilar. El workflow `Native keyboard runtime` compila y empaqueta
estos binarios de prueba; Windows CI los construye antes del MSIX. El companion
publica esa carpeta en `HardwareBroker/NativeKeyboard` dentro de su paquete.
Para compilar el widget completo, seguir los requisitos de [Windows](README.md),
generando primero `pnpm build:windows-theme-host` y ejecutando el script nativo.

Comprobaciones locales que no requieren Windows:

```sh
python3 windows/native/keyboard/tests/test_theme_package.py
clang++ -std=c++17 -Wall -Wextra -Werror windows/native/keyboard/tests/protocol_test.cpp -o /tmp/keyboard-protocol-test
/tmp/keyboard-protocol-test
dotnet test windows/tests/PanelDeControl.Hardware.Tests/PanelDeControl.Hardware.Tests.csproj -c Release --filter NativeKeyboard
```

El test C++ valida recibos acotados, caracteres y versiones, no la ABI de Windows.
Los tests de integridad protegen contra cambiar o perder los recursos originales.
Compilar correctamente no prueba la inyección ni la apariencia del teclado.

## Primera prueba manual

1. Instalar el MSIX experimental por el procedimiento existente. Abrir el teclado
   táctil desde Windows y un campo de texto de prueba sin datos sensibles.
2. En Panel > Temas > teclado de Windows, solicitar Terciopelo. Debe quedar
   experimental y pendiente de descubrimiento, **nunca Aplicado** en esta versión.
   Guardar el diagnóstico de versión, arquitectura, conexión, HRESULT y nodos.
3. Probar también el comando `discover` directamente, redirigiendo stdout a
   `keyboard-discovery.json`. Repetir con teclado cerrado y abierto: comparar
   qué tipos pertenecen a teclas, sugerencias, emoji y contenedor.
4. Abrir/cerrar el teclado; cambiar idioma, tamaño y modo acoplado/flotante.
   Repetir explícitamente la exploración tras cada cambio. No hay sondeo ni
   reconexión automática en esta versión de descubrimiento.
5. Probar letras, Mayús, Bloq Mayús, espacio, Intro, borrar, AltGr y teclas muertas.
   El teclado debe comportarse igual y su texto no debe aparecer en el JSON.
6. Desactivar desde Panel; comprobar intención desactivada y teclado original.
   No se ha escrito ninguna preferencia persistente ni aplicado estilo alguno.
7. Cerrar/reabrir TextInputHost manualmente y repetir. No reutilizar handles de
   otra ejecución; su identidad solo sirve dentro de un recibo.
8. Probar runtime ausente, otro helper en curso, denegación de acceso y timeout.
   Panel debe comunicar el fallo, sin reintentar indefinidamente ni afectar Steam.
9. Si la DLL no puede desuscribir, cerrar/reabrir TextInputHost o cerrar sesión
   elimina su módulo residente. Panel no mata el teclado automáticamente. Una
   desinstalación elimina los archivos de Panel; el módulo ya cargado puede
   persistir hasta que Windows cierre ese proceso.

Para desbloquear la adaptación visual hacen falta una captura estructural del
teclado (sin texto de usuario), tipos/control templates y grupos de estados
observados por build; luego una prueba aislada de color, borde, radio, tipografía
y textura con rollback. La versión que escriba estilos necesitará pruebas
adicionales de pérdida del companion, actualización y desinstalación. Esta
entrega no acredita esos recorridos ni una migración visual terminada.

## Prueba temporal de textura por CLI

`probe-key-face` es una prueba separada del descubrimiento de Panel, limitada a
Windows x64 build 26300. Busca únicamente la estructura observada
`KeyboardKey > Grid > Grid > Border + ContentControl`. No identifica letras ni
lee nombres, texto o pulsaciones. Requiere una tecla visible de al menos 36 DIP.

```powershell
./windows/native/keyboard/dist/PanelDeControl.KeyboardHost.exe probe-key-face
```

Con el teclado táctil ya abierto, coloca una decoración no interactiva entre el
borde y el contenido nativos de una sola tecla. Un Canvas sin tamaño deseado aloja
el SpriteVisual; no se cambian propiedades ni recursos de los elementos nativos.
La textura idle original se incorpora como RCDATA y se decodifica desde un stream
en memoria, sin asumir acceso a rutas o URI desde AppContainer. El nine-grid
usa cortes de 54 píxeles fuente y escala 18/54; el outset CSS de 6 píxeles, las
fuentes y los estados de interacción todavía no se adaptan.

La decoración solo se inserta después de LoadCompleted/Success, se retira tras
ocho segundos o un cambio de tamaño del padre, y se comprueba su ausencia por
identidad. El recibo sale tras once segundos. `probeFlags` combina inicio=1,
imagen cargada=2, inserción=4, retirada=8, fallo=16 y geometría cambiada=32.
`probe_restored` requiere inserción y retirada confirmadas sin fallo; no significa
que el tema esté aplicado. Un timeout no acredita restauración.

Es una prueba por proceso: el módulo queda fijado y conserva un pequeño estado
de control para que ningún callback apunte a código descargado. Los eventos se
retiran al limpiar. Para repetir o recuperarse de un fallo de limpieza, cerrar
y volver a abrir TextInputHost. No se termina automáticamente el teclado. Esta
prueba no depende del helper para retirarse y no modifica preferencias de Windows.
Debe comprobarse visualmente durante y después; compilarla no verifica textura,
escalado, restauración ni funciones del teclado.
