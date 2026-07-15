# Panel de Control

**Español** · [English](README.en.md)

<p align="center">
  <a href="https://ko-fi.com/hooandee"><img src="https://img.shields.io/badge/Ko--fi-Inv%C3%ADtame%20un%20caf%C3%A9-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Ko-fi"></a>
  <a href="https://www.patreon.com/hooandee"><img src="https://img.shields.io/badge/Patreon-Ap%C3%B3yame-FF424D?style=for-the-badge&logo=patreon&logoColor=white" alt="Patreon"></a>
  <a href="https://www.youtube.com/channel/UCDsSJByXklp6xc_WwQJI7Lw/join"><img src="https://img.shields.io/badge/YouTube-Hazte%20miembro-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="YouTube"></a>
  <a href="https://discord.gg/x2ZNARy"><img src="https://img.shields.io/badge/Discord-%C3%9Anete-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://linktr.ee/hooandee"><img src="https://img.shields.io/badge/Todos%20mis%20enlaces-Linktree-43E660?style=for-the-badge&logo=linktree&logoColor=white" alt="Linktree"></a>
</p>

<p align="center">
  <a href="https://github.com/Hooandee/panel-de-control/actions/workflows/ci.yml"><img src="https://github.com/Hooandee/panel-de-control/actions/workflows/ci.yml/badge.svg" alt="Estado del CI"></a>
  <a href="https://github.com/Hooandee/panel-de-control/releases/latest"><img src="https://img.shields.io/github/v/release/Hooandee/panel-de-control?label=%C3%BAltima%20versi%C3%B3n&color=blue" alt="Última versión"></a>
</p>

El centro de control que le faltaba a tu Handheld PC. Ajusta la potencia, las curvas de
ventilador, la batería, la pantalla y los mandos desde un único panel dentro del menú de acceso
rápido de Steam, sin salir del juego y sin memorizar rutas de sysfs.

Es un plugin para [Decky Loader](https://decky.xyz/). Está pensado para Steam Deck, ROG Ally, Legion
Go, MSI Claw y compañía, con una idea fija: que cada control se vea bien, muestre siempre el modelo
real de tu equipo arriba, y nunca te mienta sobre lo que de verdad está pasando en el hardware.

La interfaz viene en español por defecto y se pone defecto en inglés si tu sistema lo pide.

## Vídeo

En este vídeo enseño y explico el plugin a fondo:

[![Panel de Control en acción](https://img.youtube.com/vi/sDpXFTxG7NQ/maxresdefault.jpg)](https://youtu.be/sDpXFTxG7NQ)

> [!WARNING]
> Este plugin corre con **privilegios de root** y cambia ajustes de bajo nivel de potencia,
> temperatura y firmware de tu equipo. Solo habla con interfaces documentadas del kernel y está
> diseñado para fallar de forma segura, pero lo usas **bajo tu propia responsabilidad**. No hay
> garantía (mira la [LICENCIA](LICENSE)).

## Qué hace

El panel se organiza en pestañas. Cada una cubre una parte del equipo.

### Potencia

El corazón del plugin. Un arco visual que se llena con el TDP a lo largo del rango real de tu
máquina (no valores inventados: los lee del firmware). Ajustas los vatios con un deslizador, tienes
presets rápidos, y puedes guardar un perfil global o uno propio por juego.

- **Auto-TDP.** Un modo automático que observa la carga de la GPU y sube o baja la potencia sola
  para darte los fotogramas que necesitas gastando lo mínimo. Aprende de cómo juegas y se
  autocorrige; no hace falta que toques nada.
- **Boost.** Si tu firmware lo permite, eliges cómo se comportan los raíles SPPT y FPPT: Estable
  (lo que fijas es lo que gasta, el modo por defecto), Auto (un margen de boost gestionado) o
  Personalizado (ajustas los márgenes a mano).
- **Frecuencia de GPU.** Fija el reloj mínimo y máximo de la gráfica.

### Sistema

Todo lo que no es potencia pura pero sí gestión del día a día.

- **Batería.** Estado, salud, ciclos y capacidad, con una tarjeta que se rellena y cambia de color.
  Incluye límite de carga (topar la carga en un porcentaje para cuidar la batería), adaptado a cómo
  lo expone cada fabricante.
- **CPU.** Interruptores para el multihilo (SMT) y el turbo boost, con una vista de núcleos e hilos
  y el rango de frecuencia base a turbo.
- **Brillo y volumen.** Deslizadores que muestran el número exacto, algo que los controles nativos
  de Steam esconden.
- **Modo Descarga.** Un botón para dejar el equipo bajando un juego desatendido: baja el TDP al
  mínimo, apaga el boost y atenúa la pantalla cuando no lo estás tocando. Todo reversible.
- **Iluminación RGB.** Si tienes instalado el plugin hermano [Colores](https://github.com/Hooandee/decky-colores),
  esta tarjeta lo abre; si no, te ofrece instalarlo.

### Ventiladores

Empieza como un monitor en vivo (RPM y temperaturas de CPU y GPU con gráficas) y, en los equipos que
lo permiten, se convierte en un editor de curvas temperatura a velocidad que puedes arrastrar con el
dedo, con presets (silencioso, equilibrado, rendimiento) y curvas por juego.

Además aprende. Con el tiempo te propone una curva ajustada a cómo se comporta cada juego en tu
equipo, y puedes aplicarla de un toque. Si tu máquina no deja escribir la curva, el editor se oculta
y se te dice claramente por qué, en lugar de fingir que funciona.

### Pantalla

Calibración de color del panel a través de gamescope, convertida en un pequeño laboratorio: ambientes
de un toque (Nativo, Cine, Vivo, Cómodo) afinados por tipo de panel, saturación por juego y un modo
avanzado con temperatura, contraste, gamma, tono, nivel de negro, vivacidad y balance manual de
blancos (RGB). Incluye un modo nocturno que calienta la pantalla, siempre o en el horario que elijas,
y un preset "Aspecto OLED" para los paneles que no son OLED. Un temporizador de confirmación revierte
los cambios solo si algo se ve mal, para que no te quedes con una pantalla ilegible. En los paneles
con HDR (Steam Deck OLED y Legion Go 2) hay además un interruptor de HDR.

### Mandos

Remapeo de botones cooperando con el demonio que ya controla el mando en tu sistema (Handheld Daemon
en Bazzite, InputPlumber en SteamOS), en lugar de pelearse con él. Incluye un aviso en Ajustes si
detecta un conflicto de configuración. Esta parte está todavía en fase temprana.

### Ajustes

Idioma (con banderas, no un desplegable), el interruptor de "aprender de mi uso" (la telemetría es
100% local y se puede apagar), y un botón para borrar lo aprendido. En "Personalizar interfaz"
también puedes elegir el color de acento del panel de una paleta.

Todo el panel se maneja al 100% con el mando: el elemento en el que está el cursor se marca con un
borde de acento claro, así que no hace falta la pantalla táctil.

## Compatibilidad por equipo

Panel de Control conoce nueve modelos y, para cualquier otro, intenta funcionar sondeando las
capacidades reales del hardware. Esta tabla es honesta sobre qué está **comprobado en cada equipo**
y qué todavía no: prefiero enseñarte un "sin confirmar" antes que un "sí" falso. Las diferencias
vienen de lo que cada fabricante deja tocar por firmware y del kernel de cada distro.

Leyenda: **✅** comprobado en ese equipo · **⚠️** limitado o solo por defecto · **❌** no disponible
· **❔** el código lo soporta pero aún no está confirmado en ese equipo

| Característica | Steam Deck LCD | Steam Deck OLED | ROG Ally | ROG Ally X | ROG Xbox Ally X | Legion Go | Legion Go S | Legion Go 2 | MSI Claw 8 AI+ |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Límite de TDP | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Boost (SPPT/FPPT) | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ [¹](#notas) |
| Auto-TDP por carga de GPU | ✅ [²](#notas) | ✅ [²](#notas) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ [³](#notas) |
| Frecuencia de GPU | ❔ [⁴](#notas) | ❔ [⁴](#notas) | ❔ [⁴](#notas) | ❔ [⁴](#notas) | ❔ [⁴](#notas) | ❔ [⁴](#notas) | ❔ [⁴](#notas) | ❔ [⁴](#notas) | ❔ [⁴](#notas) |
| Batería: estado y salud | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Ciclos de batería | ❌ [⁵](#notas) | ❌ [⁵](#notas) | ❌ [⁵](#notas) | ❌ [⁵](#notas) | ❌ [⁵](#notas) | ✅ | ✅ | ✅ | ❌ [⁵](#notas) |
| Límite de carga | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ [⁶](#notas) | ❔ | ⚠️ [⁷](#notas) | ✅ |
| CPU: turbo boost | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CPU: multihilo (SMT) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ [⁸](#notas) |
| CPU: núcleos activos | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Brillo y volumen | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Modo Descarga | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Monitor de temperaturas | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ [⁹](#notas) |
| Monitor de RPM de ventilador | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ [¹⁰](#notas) | ✅ [⁹](#notas) |
| Curvas de ventilador | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ [¹¹](#notas) | ⚠️ [¹²](#notas) | ❔ [¹⁰](#notas) | ⚠️ [⁹](#notas) |
| Curvas aprendidas por juego | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ [¹¹](#notas) | ❌ [¹²](#notas) | ❔ [¹⁰](#notas) | ❌ [⁹](#notas) |
| Modos de firmware (perfiles) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ [¹¹](#notas) | ❌ | ❌ | ❌ |
| Calibración de color | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ [¹³](#notas) |
| Preset "Aspecto OLED" | ✅ | ❌ [¹⁴](#notas) | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ [¹⁴](#notas) | ✅ |
| Remapeo de mandos (beta) | ❌ | ❌ | ⚠️ [¹⁵](#notas) | ⚠️ [¹⁵](#notas) | ❌ [¹⁵](#notas) | ⚠️ [¹⁵](#notas) | ❌ [¹⁵](#notas) | ⚠️ [¹⁵](#notas) | ⚠️ [¹⁵](#notas) |
| Iluminación RGB (vía Colores) | ❌ [¹⁶](#notas) | ❌ [¹⁶](#notas) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

Cualquier otro portátil cae en un perfil **genérico experimental**: el plugin sondea las capacidades
reales y muestra lo que consigue, ocultando honestamente el resto.

El **OneXPlayer OneXFly Apex** (Ryzen AI Max+ 395) ya se reconoce por su nombre y entra como
experimental. El control de TDP va por la vía genérica de AMD, así que debería funcionar; los
ventiladores y el límite de carga se activan solo si el equipo expone los nodos, y hasta que
alguien lo pruebe en mano preferimos no dar nada por hecho. Si tienes uno, los reportes desde
Ajustes ayudan un montón a afinarlo.

El **AOKZOE A1X** (Ryzen AI 9 HX 370) también se reconoce por su nombre y entra como experimental.
Su TDP va por la misma vía genérica de AMD (ryzenadj), pero con un techo de 30 W en vez de quedarse
capado a los 15 W del perfil genérico. Igual que con el OneXFly no lo tenemos en mano, así que los
reportes desde Ajustes son oro para confirmar lo que responde de verdad.

La **GPD Win Mini 2025** (Ryzen AI 9 HX 370/365) y la **MSI Claw A8** (Ryzen Z2 Extreme) también se
reconocen por su nombre y entran como experimentales. Antes salían como genéricas y el TDP se
quedaba en 15 W; ahora suben hasta un techo seguro de 35 W (el máximo que homologa el fabricante,
muy por debajo del cTDP teórico del chip) con sus tres presets afinados. Van por la misma vía
genérica de AMD (ryzenadj) y no las tenemos en mano, así que los reportes desde Ajustes ayudan a
confirmarlo.

En la misma tanda se reconocen unas cuantas más, todas experimentales y con un techo seguro
homologado: la **OneXPlayer F1 Pro** (Ryzen AI 9 HX 370, hasta 30 W), la **GPD Win 5** (Ryzen AI
Max 385 "Strix Halo", hasta 55 W), la **GPD Win Max 2** (Ryzen 7 8840U, hasta 35 W) y la **ROG Xbox
Ally** con el Ryzen Z2 A (la blanca), que además tenía un tope de firmware falso de 100 W y ahora
queda capada a los 20 W reales que homologa ASUS. La **Legion Go 2** con el Ryzen Z2 normal (no
Extreme) también se detecta ya con su nombre en vez de como equipo genérico. En todo lo que no
tenemos en mano, los reportes desde Ajustes son los que confirman lo que responde de verdad.

### Notas

1. El Claw controla el TDP por `intel-rapl`, que solo expone el límite base (PL1); no hay raíles de
   boost separados que ajustar.
2. En Steam Deck la lectura de carga de GPU es instantánea y muy ruidosa; el auto-TDP la promedia
   antes de decidir.
3. El perfilado de consumo en Intel (RAPL / i915) todavía no está implementado, así que el auto-TDP
   por GPU no está disponible en el Claw. El resto del control de TDP sí funciona.
4. La escritura de frecuencia de GPU está implementada por dispositivo, pero aún no se ha confirmado
   con un cambio en vivo en ningún equipo. Marcado como sin confirmar hasta validarlo.
5. El contador de ciclos solo lo rellena el firmware de Lenovo; en ASUS, Steam Deck y MSI el nodo da
   un 0 falso, así que se oculta en vez de mostrar un cero inventado.
6. La Legion Go original (83E1) no expone `conservation_mode`, así que no ofrece límite de carga.
7. En Legion el límite de carga es un interruptor de "modo conservación" con un porcentaje fijo por
   firmware, no un valor ajustable.
8. El Intel Core Ultra del Claw no tiene hyperthreading, así que no hay multihilo que activar o
   desactivar.
9. En el MSI Claw el chip de ventilador (`msi_wmi_platform`) expone las RPM (el monitor sí muestra los
   dos ventiladores; a temperatura baja giran a 0 en modo silencioso), pero su kernel no permite
   escribir la curva. La curva que aplica el firmware se lee por el EC y se muestra en modo solo
   lectura; la edición está en desarrollo (el control de velocidad se ajustará de forma segura).
10. La Legion Go 2 no expone un ventilador escribible por hwmon; el RPM tendría que leerse por el EC
    y en la build actual no está apareciendo en el monitor. Por eso lo marco como no disponible / sin
    confirmar hasta que pueda revisarlo.
11. La Legion Go original controla la curva de ventilador por el driver de kernel `legion_wmi_fan`, que
    va en los kernels que lo incluyen y se enciende solo cuando está presente. Donde no está (SteamOS
    actual y algunos kernels), el ventilador lo gobiernan los **modos de firmware**
    (Silencioso/Equilibrado/Rendimiento) desde el arco de Potencia, que ajustan potencia y ventilador a
    la vez. El monitor de velocidad funciona siempre: si el driver no publica el nodo hwmon, la RPM se
    lee por el EC.
12. La Legion Go S controla el ventilador por una vía no oficial del controlador integrado (EC), así
    que es un control experimental y opcional: hay que activarlo a mano, con un tope de velocidad de
    seguridad. Desactivado, se queda solo en monitor.
13. En Intel el color solo se aplica mientras el compositor está activo, así que se fuerza esa ruta y
    se avisa del pequeño coste.
14. El preset "Aspecto OLED" se oculta en los paneles que ya son OLED (Steam Deck OLED, Legion Go 2)
    porque no tiene sentido allí.
15. El remapeo coopera con el demonio del sistema (HHD en Bazzite, InputPlumber en SteamOS) y está en
    fase temprana. En Steam Deck no aparece; en Legion Go S y ROG Xbox Ally X la app indica que
    todavía no hay remapeo para ese mando. En Legion algunos botones traseros aún no se detectan bien.
16. La Steam Deck no lleva iluminación RGB, así que esta tarjeta no aparece.

> Las celdas marcadas **❔** son las que aún no he confirmado en ese equipo concreto. Si tienes el
> hardware delante y ves que algo va (o no va), dímelo y lo corrijo: la idea es que esta tabla
> refleje la realidad, no lo que el código intenta hacer.

## Instalación

Panel de Control se distribuye fuera de la tienda de Decky. Instala primero
[Decky Loader](https://decky.xyz/) y luego:

1. Descarga `Panel de Control.zip` de la [última release](https://github.com/Hooandee/panel-de-control/releases/latest).
2. En Decky, usa **Modo desarrollador → Instalar plugin desde ZIP** (o tu método de instalación
   manual preferido).

Una vez instalado, el plugin puede actualizarse solo desde sus ajustes.

### Verificar la descarga (recomendado)

Las releases publicadas una vez el repositorio es público se firman con build provenance. Cuando la
firma esté disponible, puedes confirmar que el zip salió de verdad del pipeline de este repositorio:

```sh
gh attestation verify "Panel de Control.zip" --repo Hooandee/panel-de-control
```

## Cómo aprende (y por qué es local)

La gracia de Panel de Control no es solo tener botones bonitos, es que aprende de cómo usas cada
juego para proponerte una configuración mejor: qué curva de ventilador te mantiene fresco sin ruido,
qué potencia te da fotogramas estables sin vaciar la batería. Todo ese aprendizaje se queda en tu
equipo, no sale de él, y puedes apagarlo o borrarlo cuando quieras desde Ajustes.

El principio que atraviesa todo el proyecto: nunca fingir. Si una lectura no está disponible, se
oculta en vez de mostrar un cero falso. Si el hardware rechaza un cambio, la interfaz lo refleja. Un
número en pantalla es un número real.

## Agradecimientos

Este plugin se apoya en el trabajo de mucha gente de la comunidad de handhelds. Referencio las
interfaces del kernel (que son hechos, no código) con libertad, y cuando adapto una idea o algo de
código lo cito aquí. La lista completa con licencias está en [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

- **[SimpleDeckyTDP](https://github.com/aarron-lee/SimpleDeckyTDP)** (BSD-3, Aarron Lee). La
  referencia principal del mecanismo de TDP por dispositivo: las rutas de firmware-attributes de
  Lenovo y ASUS, el paso previo de `platform_profile=custom`, y el uso de ryzenadj.
- **[Handheld Daemon (HHD)](https://github.com/hhd-dev/hhd)** (LGPL-2.1). Referencia para la
  estrategia por dispositivo, la reaplicación al despertar y al cambiar de corriente, y la
  cooperación con el demonio de mandos. Solo miré el enfoque, no copié su código.
- **[RyzenAdj](https://github.com/FlyGoat/RyzenAdj)** (LGPL-3.0). Lo invocamos como proceso externo
  para el camino genérico de AMD cuando no hay una ruta de firmware mejor; no se empaqueta dentro del
  plugin.
- **[PowerControl](https://github.com/mengmeet/PowerControl)**. Origen de la ruta de
  firmware-attributes de Lenovo que hereda SimpleDeckyTDP.
- **[Fantastic](https://git.ngram.ca/NG-SD-Plugins/Fantastic)** y **[PowerTools](https://git.ngni.us/NG-SD-Plugins/PowerTools)**.
  Referencia para el monitor y el control de ventiladores y para la reaplicación periódica.
- **[Decky Loader](https://decky.xyz/)** y su plantilla de plugins. La base sobre la que corre todo
  esto.
- **La documentación del kernel de Linux** (firmware-attributes, powercap, asus-wmi, hwmon,
  power_supply). De donde salen las rutas de sysfs que leo y escribo.

## Contribuir

Las contribuciones son bienvenidas. Lee [CONTRIBUTING.md](CONTRIBUTING.md) y el
[Código de Conducta](CODE_OF_CONDUCT.md).

## Seguridad

¿Encontraste una vulnerabilidad? Repórtala en privado, mira la [Política de Seguridad](SECURITY.md).
No abras un issue público.

## Licencia

[BSD-3-Clause](LICENSE) © Hooandee. Las atribuciones de terceros y los detalles de licencia (incluido
ryzenadj, que se invoca como proceso externo y no se empaqueta) están en
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
