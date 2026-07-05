# Panel de Control

**Español** · [English](README.en.md)

El centro de control que le faltaba a tu PC portátil de juego. Ajusta la potencia, las curvas de
ventilador, la batería, la pantalla y los mandos desde un único panel dentro del menú de acceso
rápido de Steam, sin salir del juego y sin memorizar rutas de sysfs.

Es un plugin para [Decky Loader](https://decky.xyz/). Está pensado para Steam Deck, ROG Ally, Legion
Go, MSI Claw y compañía, con una idea fija: que cada control se vea bien, muestre siempre el modelo
real de tu equipo arriba, y nunca te mienta sobre lo que de verdad está pasando en el hardware.

La interfaz viene en español por defecto y cae a inglés si tu sistema lo pide.

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
- **Modos avanzados.** Si tu firmware lo permite, un apartado plegable para afinar los límites de
  boost (SPPT y FPPT) como márgenes sobre el límite base.
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

Calibración de color del panel a través de gamescope: saturación por juego, temperatura y contraste
globales, y un preset "Aspecto OLED" de un toque para los paneles que no son OLED. Trae un
temporizador de confirmación que revierte los cambios solo si algo se ve mal, para que no te quedes
con una pantalla ilegible.

### Mandos

Remapeo de botones cooperando con el demonio que ya controla el mando en tu sistema (Handheld Daemon
en Bazzite, InputPlumber en SteamOS), en lugar de pelearse con él. Incluye un aviso en Ajustes si
detecta un conflicto de configuración. Esta parte está todavía en fase temprana.

### Ajustes

Idioma (con banderas, no un desplegable), el interruptor de "aprender de mi uso" (la telemetría es
100% local y se puede apagar), y un botón para borrar lo aprendido.

## Compatibilidad por equipo

Panel de Control conoce nueve modelos y, para cualquier otro, intenta funcionar sondeando las
capacidades reales del hardware. Esta tabla resume qué encontrarás en cada familia. Las diferencias
suelen venir de lo que el fabricante deja tocar por firmware, no del plugin.

Leyenda: **●** funciona · **◐** limitado, solo lectura o valores por defecto · **○** no disponible

| Característica | Steam Deck | ROG Ally | Legion Go | MSI Claw 8 AI+ | Otros equipos |
|---|:---:|:---:|:---:|:---:|:---:|
| Límite de TDP | ● | ● | ● | ● | ◐ |
| Modos avanzados (SPPT/FPPT) | ○ | ● | ● | ○ | ○ |
| Auto-TDP por carga de GPU | ● [¹](#notas) | ● | ● | ○ [²](#notas) | ◐ |
| Frecuencia de GPU | ● | ● | ● | ● | ◐ |
| Batería: estado, salud, ciclos | ● | ● | ● | ● | ● |
| Límite de carga | ● | ● | ◐ [³](#notas) | ◐ | ◐ |
| CPU: turbo boost | ● | ● | ● | ● | ◐ |
| CPU: multihilo (SMT) | ● | ● | ● | ○ [⁴](#notas) | ◐ |
| CPU: núcleos activos | ● | ● | ● | ● | ● |
| Brillo y volumen | ● | ● | ● | ● | ● |
| Modo Descarga | ● | ● | ● | ● | ● |
| Monitor de ventiladores | ● | ● | ● | ● | ● |
| Curvas de ventilador | ● | ● | ◐ [⁵](#notas) | ● | ◐ |
| Curvas aprendidas por juego | ● | ● | ◐ [⁵](#notas) | ● | ◐ |
| Calibración de color | ● | ● | ● | ● [⁶](#notas) | ● |
| Preset "Aspecto OLED" | ◐ [⁷](#notas) | ● | ◐ [⁷](#notas) | ● | ● |
| Remapeo de mandos (beta) | ◐ | ◐ | ◐ | ◐ | ○ |
| Iluminación RGB (vía Colores) | ○ [⁸](#notas) | ● | ● | ● | ◐ |

Cada familia agrupa: **Steam Deck** (LCD y OLED), **ROG Ally** (Ally 2023, Ally X, Xbox Ally X),
**Legion Go** (Go, Go S, Go 2). El resto de portátiles caen en "Otros equipos", donde el plugin se
marca como experimental y funciona con lo que consiga sondear.

### Notas

1. En Steam Deck la lectura de carga de GPU es instantánea y muy ruidosa; el auto-TDP la promedia
   antes de decidir.
2. El perfilado de consumo en Intel (RAPL / i915) todavía no está implementado, así que el auto-TDP
   por GPU no está disponible en el Claw. El resto del control de TDP sí.
3. En Legion el límite de carga es un interruptor de "modo conservación" con un porcentaje fijo por
   firmware, no un valor ajustable. En el Claw depende de lo que exponga cada unidad.
4. El Intel Core Ultra del Claw no tiene hyperthreading, así que no hay multihilo que activar o
   desactivar.
5. Legion Go 2 tiene curva completa; Legion Go S solo modos gruesos (silencioso, equilibrado,
   rendimiento); el Legion Go original queda limitado según el sistema.
6. En Intel el color solo se aplica mientras el compositor está activo, así que se fuerza esa ruta y
   se avisa del pequeño coste.
7. El preset "Aspecto OLED" se oculta en los paneles que ya son OLED (Steam Deck OLED, Legion Go 2)
   porque no tiene sentido allí.
8. La Steam Deck no lleva iluminación RGB, así que esta tarjeta no aparece.

## Instalación

Panel de Control se distribuye fuera de la tienda de Decky. Instala primero
[Decky Loader](https://decky.xyz/) y luego:

1. Descarga `Panel de Control.zip` de la [última release](https://github.com/Hooandee/panel-de-control/releases/latest).
2. En Decky, usa **Modo desarrollador → Instalar plugin desde ZIP** (o tu método de instalación
   manual preferido).

Una vez instalado, el plugin puede actualizarse solo desde sus ajustes.

### Verificar la descarga (recomendado)

Cada zip de release va firmado con build provenance. Antes de instalar, confirma que de verdad salió
del pipeline de este repositorio:

```sh
gh attestation verify "Panel de Control.zip" --repo Hooandee/panel-de-control
```

## Compilar desde el código

Herramientas: **pnpm 10**, **Node 20**, **Python 3.11**.

```sh
pnpm install --frozen-lockfile
pnpm build          # genera dist/index.js
```

Copia la carpeta resultante a `~/homebrew/plugins/` en tu equipo y reinicia Decky. El backend en
Python necesita root (lo declara el plugin) para escribir en sysfs; la detección del modelo, en
cambio, no lo necesita. Mira [CONTRIBUTING.md](CONTRIBUTING.md) para el conjunto de pruebas completo
y la configuración de desarrollo.

## Cómo aprende (y por qué es local)

La gracia de Panel de Control no es solo tener botones bonitos, es que aprende de cómo usas cada
juego para proponerte una configuración mejor: qué curva de ventilador te mantiene fresco sin ruido,
qué potencia te da fotogramas estables sin vaciar la batería. Todo ese aprendizaje se queda en tu
equipo, no sale de él, y puedes apagarlo o borrarlo cuando quieras desde Ajustes.

El principio que atraviesa todo el proyecto: nunca fingir. Si una lectura no está disponible, se
oculta en vez de mostrar un cero falso. Si el hardware rechaza un cambio, la interfaz lo refleja. Un
número en pantalla es un número real.

## Agradecimientos

Este plugin se apoya en el trabajo de mucha gente de la comunidad de handhelds. Referenciamos
interfaces del kernel (que son hechos, no código) libremente, y cuando adaptamos ideas o código lo
citamos aquí. La lista completa con licencias está en [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

- **[SimpleDeckyTDP](https://github.com/aarron-lee/SimpleDeckyTDP)** (BSD-3, Aarron Lee). La
  referencia principal del mecanismo de TDP por dispositivo: las rutas de firmware-attributes de
  Lenovo y ASUS, el paso previo de `platform_profile=custom`, y el uso de ryzenadj.
- **[Handheld Daemon (HHD)](https://github.com/hhd-dev/hhd)** (LGPL-2.1). Referencia para la
  estrategia por dispositivo, la reaplicación al despertar y al cambiar de corriente, y la
  cooperación con el demonio de mandos. Solo consultamos el enfoque, no copiamos su código.
- **[RyzenAdj](https://github.com/FlyGoat/RyzenAdj)** (LGPL-3.0). Lo incluimos como binario para el
  camino genérico de AMD cuando no hay una ruta de firmware mejor.
- **[PowerControl](https://github.com/mengmeet/PowerControl)**. Origen de la ruta de
  firmware-attributes de Lenovo que hereda SimpleDeckyTDP.
- **[Fantastic](https://git.ngram.ca/NG-SD-Plugins/Fantastic)** y **[PowerTools](https://git.ngni.us/NG-SD-Plugins/PowerTools)**.
  Referencia para el monitor y el control de ventiladores y para la reaplicación periódica.
- **[Decky Loader](https://decky.xyz/)** y su plantilla de plugins. La base sobre la que corre todo
  esto.
- **La documentación del kernel de Linux** (firmware-attributes, powercap, asus-wmi, hwmon,
  power_supply). De donde salen las rutas de sysfs que leemos y escribimos.

## Contribuir

Las contribuciones son bienvenidas. Lee [CONTRIBUTING.md](CONTRIBUTING.md) y el
[Código de Conducta](CODE_OF_CONDUCT.md).

## Seguridad

¿Encontraste una vulnerabilidad? Repórtala en privado, mira la [Política de Seguridad](SECURITY.md).
No abras un issue público.

## Licencia

[BSD-3-Clause](LICENSE) © Hooandee. El binario de ryzenadj que se distribuye conserva su propia
licencia LGPL-3.0. Las atribuciones de terceros están en [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
