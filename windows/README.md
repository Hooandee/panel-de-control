# Panel de Control para Xbox Game Bar

La versión de Windows es experimental. Ofrece un widget x64 para Xbox Game Bar
y un proceso auxiliar empaquetado con telemetría de lectura y ajuste verificado
del volumen del sistema.

## Alcance inicial

- Identificación estricta de la ROG Xbox Ally X mediante fabricante y producto.
- Batería y estado de alimentación mediante la API de energía de Windows.
- Carga y temperatura de CPU/GPU cuando LibreHardwareMonitor publica un sensor
  compatible.
- Lectura y ajuste del volumen principal del dispositivo de audio predeterminado
  mediante Windows Core Audio.
- Lectura y ajuste del silencio principal del mismo dispositivo mediante la
  capacidad estándar de Windows Core Audio.
- Estados explícitos para dato disponible, no disponible, permiso requerido y
  fallo de lectura o control.
- Canal de control independiente, limitado al paquete y al usuario actual, para
  que una lectura lenta de hardware no bloquee el volumen.

Cada operación abre el endpoint de reproducción predeterminado actual
(`eRender`/`eConsole`). El volumen y el silencio principal se leen con Core
Audio y el silencio se cambia con `GetMute`/`SetMute`. Después de una escritura,
el companion vuelve a leer el valor en esa misma sesión: el volumen solo se da
por aplicado dentro de una tolerancia de 0,01 y el silencio solo cuando el valor
observado coincide exactamente con el solicitado. Si el readback falla o no
coincide, el widget conserva el estado observado cuando existe y muestra el
cambio como no verificable, nunca como aplicado.

No hay reintento después de una escritura, incluida una cuyo resultado sea
incierto. Tampoco se persiste ni reaplica la intención de volumen o silencio,
ni se controla el audio o el silencio por aplicación. El control corresponde al
endpoint principal de Windows; una aplicación en modo exclusivo puede impedir
la verificación y se informa como tal.

No se escriben valores de TDP, ventiladores, GPU, batería ni firmware. Un campo
sin lectura verificable aparece como `Sin datos`; nunca se sustituye por un
valor inventado.

LibreHardwareMonitor solo se inicializa cuando el DMI coincide con la ROG Xbox
Ally X. En cualquier otro equipo, el companion conserva únicamente la lectura
estándar de batería/AC y marca el resto como dispositivo no compatible.
El volumen no depende de esa identificación: se habilita por la capacidad
estándar de Windows y por la disponibilidad de un endpoint de audio
predeterminado.

## Compilar

Requisitos:

- Windows 11 x64.
- Visual Studio 2022 con **Universal Windows Platform development** y el SDK de
  Windows 11 22621.
- .NET SDK 8.
- Xbox Game Bar instalada y actualizada.

Desde una terminal de desarrollador:

```powershell
dotnet restore windows\src\PanelDeControl.Hardware\PanelDeControl.Hardware.csproj --locked-mode
msbuild windows\src\PanelDeControl.GameBar\PanelDeControl.GameBar.csproj /restore /target:Build /property:RestoreLockedMode=true /property:Configuration=Release /property:Platform=x64 /property:AppxPackageSigningEnabled=false /property:GenerateAppxPackageOnBuild=true /property:AppxBundle=Never
```

El paquete generado no está firmado. Para una instalación reproducible fuera de
Visual Studio hace falta firmarlo con un certificado cuya identidad coincida con
el `Publisher` del manifiesto.

## Validación física pendiente

Esta validación no bloquea el desarrollo automatizado, pero sí cualquier
declaración de compatibilidad física. En una ROG Xbox Ally X RC73XA:

1. Instalar el paquete y abrir Xbox Game Bar con `Win+G`.
2. Abrir **Panel de Control** desde el menú de widgets.
3. Confirmar que el widget puede enfocarse y manejarse con el mando.
4. Comparar fabricante y producto con `Win32_ComputerSystem`.
5. Registrar qué lecturas aparecen, su proveedor y sus rangos durante batería,
   corriente, reposo y reanudación.
6. Ajustar el volumen y activar/desactivar el silencio principal con teclado y
   mando; comparar ambos estados con el mezclador de Windows.
7. Cambiar el dispositivo de audio predeterminado y confirmar que la siguiente
   lectura usa el endpoint nuevo sin reaplicar valores anteriores.
8. Comprobar con una aplicación en modo exclusivo que un readback bloqueado o
   discordante no produce un falso estado de éxito.
9. Ocultar y volver a mostrar el widget durante una operación de silencio y
   confirmar que no reaplica la intención anterior; confirmar además que al
   cerrar el widget el proceso auxiliar termina tras su periodo de inactividad.
10. Confirmar que un sensor ausente aparece como `Sin datos` y que un valor real
    de cero se conserva.

Hasta completar esta prueba, las lecturas de CPU y GPU son candidatas
experimentales y el control de volumen/silencio no tiene compatibilidad física
confirmada.
