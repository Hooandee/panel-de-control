# Panel de Control para Xbox Game Bar

La versión de Windows es experimental. La primera vertical ofrece un widget x64
para Xbox Game Bar y un proceso auxiliar empaquetado que expone únicamente
telemetría de lectura.

## Alcance inicial

- Identificación estricta de la ROG Xbox Ally X mediante fabricante y producto.
- Batería y estado de alimentación mediante la API de energía de Windows.
- Carga y temperatura de CPU/GPU cuando LibreHardwareMonitor publica un sensor
  compatible.
- Estados explícitos para dato disponible, no disponible, permiso requerido y
  fallo de lectura.
- Comunicación local entre procesos mediante una tubería con nombre limitada al
  mismo paquete.

No se escriben valores de TDP, ventiladores, GPU, batería ni firmware. Un campo
sin lectura verificable aparece como `Sin datos`; nunca se sustituye por un valor
inventado.

LibreHardwareMonitor solo se inicializa cuando el DMI coincide con la ROG Xbox
Ally X. En cualquier otro equipo, el companion conserva únicamente la lectura
estándar de batería/AC y marca el resto como dispositivo no compatible.

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

## Prueba física obligatoria

Antes de declarar una lectura compatible en una ROG Xbox Ally X RC73XA:

1. Instalar el paquete y abrir Xbox Game Bar con `Win+G`.
2. Abrir **Panel de Control** desde el menú de widgets.
3. Confirmar que el widget puede enfocarse y manejarse con el mando.
4. Comparar fabricante y producto con `Win32_ComputerSystem`.
5. Registrar qué lecturas aparecen, su proveedor y sus rangos durante batería,
   corriente, reposo y reanudación.
6. Confirmar que cerrar el widget hace terminar el proceso auxiliar tras su
   periodo de inactividad.
7. Confirmar que un sensor ausente aparece como `Sin datos` y que un valor real
   de cero se conserva.

Hasta completar esta prueba, las lecturas de CPU y GPU son candidatas
experimentales, no soporte de hardware confirmado.
