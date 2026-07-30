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
- Estados explícitos para dato disponible, no disponible, permiso requerido y
  fallo de lectura o control.
- Canal de control independiente, limitado al paquete y al usuario actual, para
  que una lectura lenta de hardware no bloquee el volumen.

El volumen se confirma leyendo de nuevo el mismo endpoint después de cada
escritura. Si no puede verificarse, el widget lo indica y no informa el cambio
como aplicado. No hay reintento de una escritura cuyo resultado sea incierto.
Tampoco hay control de mute, persistencia ni intervención sobre sesiones que
usen audio en modo exclusivo.

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
6. Ajustar el volumen con teclado y mando, y comparar el valor mostrado con el
   mezclador de Windows.
7. Cambiar el dispositivo de audio predeterminado y confirmar que la siguiente
   lectura usa el endpoint nuevo sin reaplicar valores anteriores.
8. Comprobar que una aplicación en modo exclusivo no produce un falso estado de
   éxito.
9. Confirmar que cerrar el widget hace terminar el proceso auxiliar tras su
   periodo de inactividad.
10. Confirmar que un sensor ausente aparece como `Sin datos` y que un valor real
   de cero se conserva.

Hasta completar esta prueba, las lecturas de CPU y GPU son candidatas
experimentales, no soporte de hardware confirmado.
