# Lobo Blanco para el teclado nativo de Windows 11

El paquete de `native/keyboard/themes/lobo-blanco/` conserva los recursos del
teclado Steam **Lobo Blanco 0.9.11** como referencia de su adaptación nativa. Su identidad
es `hooandee-lobo-blanco`, su nombre CSS Loader es `Hooandee Lobo Blanco` y el
catálogo acredita a Hooandee como autor. `theme.json` enumera tamaños y SHA-256 de
todos los recursos y describe los valores de referencia. La presencia de un
recurso no implica que su efecto esté implementado o validado en Windows.

## Inventario visual

| Recursos | Dimensiones originales | Función |
|---|---|---|
| `assets/plate.webp` | 1708 × 478 | Placa oscura con anillas, medallón de lobo central tenue, viñeta lateral y línea roja superior. |
| `assets/plush-silver.png`, `plush-silver-press.png` | 216 × 168 | Tecla plateada normal y pulsada. |
| `assets/plush-red.png`, `plush-red-press.png` | 216 × 168 | Teclas especiales rojo sangre, normales y pulsadas. |
| `assets/plush-hot.png`, `plush-hot-press.png` | 216 × 168 | Foco coral con filo claro y halo rojo; foco pulsado. |
| `assets/plush-maroon.png` | 216 × 168 | Modificador activo o de un uso en granate. |
| `assets/sign-igni.png`, `sign-aard.png`, `sign-quen.png`, `sign-yrden.png`, `sign-axii.png` | 60 × 60 | Runas de Intro, Retroceso, Mayús, Bloq Mayús y Tab, respectivamente. |
| `assets/fx-igni.webp` | 2560 × 130 | Tira de fuego de 16 fotogramas de 160 × 130; también alimenta las brasas pequeñas. |
| `fonts/originals/cinzel-latin.woff2` | 15 184 bytes | Cinzel Bold, 228 glifos y 220 puntos Unicode. |
| `fonts/originals/marcellus-latin.woff2` | 14 552 bytes | Marcellus Regular, 218 glifos y 214 puntos Unicode. |

Las caras tienen biseles, centro liso y sombra inferior ya dibujados en el PNG.
Aunque sus nombres contienen `plush`, el original no muestra pelo ni requiere
añadir una textura de terciopelo. La placa, las siete caras, las runas y las
fuentes forman la identidad visual propia de Lobo Blanco.

## Geometría y tinta

Las caras originales utilizan nueve regiones: corte de **54 píxeles** de la
imagen, borde dibujado de **18 px**, expansión exterior de **6 px**, centro relleno
y regiones estiradas. El margen de cara es 3 px arriba y a los lados, 4 px abajo.
El redondeado está en el recurso; el radio CSS de la cara es cero. La placa ocupa
el rectángulo completo del teclado y se estira en ambos ejes.

La tinta normal es `#3a0906`; la suave usa ese color al 55 %. Las especiales usan
esmalte `#fbf1ea`, y el foco `#fff8f3`. El fondo de reserva es `#0e0f11`. Estos
valores afectan a texto y superficies auxiliares: los colores de los biseles y
halos permanecen en sus imágenes originales.

Letras y caracteres principales: 20 px, peso solicitado 700. Primera fila de
números: 16 px; especiales: 9,5 px; AltGr y Pegar: 11 px. Etiquetas secundarias:
10 px arriba, opacidad 0,78; terciarias: 9 px, opacidad 0,6. La pulsación desplaza
el texto **2 px** hacia abajo. El original usa Marcellus Regular con negrita
sintética; Cinzel ya contiene los contornos Bold.

Cada runa ocupa 13 × 13 px, a 9 px del borde superior y 12 px del lateral. Bloq
Mayús y Mayús izquierda la llevan a la izquierda; las demás, a la derecha. Sus
etiquetas reservan espacio para evitar solaparse. Los valores completos están
en `theme.json`.

## Tipografía y selección por cobertura

`fonts/Cinzel.ttf` conserva toda la cobertura de la WOFF2 suministrada. Su familia
es **Cinzel**, estilo **Bold**. `fonts/Marcellus.ttf` conserva completa la WOFF2 de
referencia, familia **Marcellus**, estilo **Regular**; no debe colocarse primero
en la cadena de fuentes del teclado porque capturaría también sus números.

`fonts/LoboBlancoLetras.ttf`, familia **Lobo Blanco Letras**, estilo **Regular**,
es una derivada de Marcellus con únicamente la cobertura de los rangos CSS:
`U+0041–005A`, `U+0061–007A`, `U+00C0–00FF`, `U+0152–0153`. Los rangos son literales:
incluyen × y ÷. No incluye espacio, dígitos ni otros signos fuera de esos rangos.
Una cadena nativa con su URI primero y la URI de Cinzel después reproduce la
selección por cobertura sin leer ni clasificar el texto de las etiquetas.

La derivada tiene nombre propio porque Marcellus declara un nombre reservado en
la OFL. No se redibujaron sus contornos ni se alteraron sus métricas.
`fonts/prepare_fonts.py` reproduce ambas conversiones completas y la derivada,
verifica los originales y comprueba su cobertura, contornos y métricas. Las
versiones de herramientas, hashes originales, metadatos y fuentes oficiales
están en `fonts/SOURCE.txt`.

## Estados originales

| Estado | Cara |
|---|---|
| Normal | `plush-silver.png` |
| Intro, Retroceso, Mayús, Bloq Mayús, Tab | `plush-red.png` y su runa |
| Foco | `plush-hot.png` |
| Pulsada | `plush-silver-press.png` o `plush-red-press.png` |
| Foco y pulsación | `plush-hot-press.png` |
| Mayús/Bloq/AltGr activo o de un uso | `plush-maroon.png`; con foco, `plush-hot.png` |
| Tecla muerta pendiente | `plush-red.png` y esmalte hasta completar la composición |

El CSS original coloca las reglas de modificador activo después de las de
pulsación: la cara granate, o caliente con foco, prevalece en ese caso. No existe
una cara `maroon-press` ni otra específica de hover. La regla de tecla muerta va
al final y usa la cara roja. Las teclas extendidas conservan las caras silver/hot
en un panel oscuro con degradado `#2a2d32` → `#121316`, radio 10 px, padding 4 px y
separación 2 px. Mayús intercambia el carácter principal con el secundario.

## Movimiento y sonido de referencia

Cada pulsación reproduce una brasa de 72 × 58 px durante **380 ms**, centrada
horizontalmente y a 42 % del borde inferior de la tecla. Intro reproduce Igni de
160 × 130 px durante **620 ms**, a 30 % del borde inferior. Ambos recorren la misma
tira en 16 pasos, con `steps(15,end)`; mantienen opacidad hasta el 75 % del tiempo
y después desaparecen. Se reutiliza una capa por tecla dentro de un overlay que
no recibe input ni desplaza el layout.

Las cinco especiales añaden un brillo radial de **420 ms**, curva
`cubic-bezier(.2,.7,.2,1)`, escala 0,9 → 1 → 1,08 y opacidad 0 → 1 → 0; el máximo
ocurre al 25 %. Se expande 6 px y usa radio 14 px. Igni es naranja, Aard azul,
Quen dorado, Yrden violeta y Axii verde; sus valores RGBA están en el manifiesto.

La salida común del teclado dura **300 ms**: las filas, en orden inverso, bajan
26 px y desaparecen con 28 ms de escalonamiento. No hay una entrada propia de
Lobo Blanco: la aporta el host Steam. El mínimo visual de pulsación es 70 ms,
o 90 ms para teclado físico.

El sonido original es sintetizado, sin muestras empaquetadas: clic metálico,
Igni con barrido highpass y armónicos, Aard grave y las demás runas con dos tonos
triangulares. Las opciones son Apagado, Suave y Normal; Suave es el valor inicial
(ganancia 0,35; Normal, 0,7). Los efectos vienen activados. El control común debe
evitar duplicar el clic nativo y mantener la síntesis fuera del hilo de UI.

## Licencias y alcance

Cinzel y Marcellus tienen licencia **SIL Open Font License 1.1**: se incluyen sus
dos avisos completos y sus metadatos originales. La derivada Lobo Blanco Letras
permanece bajo OFL-1.1. Los enlaces oficiales y la revisión fijada figuran en
`fonts/SOURCE.txt`.

Los raster se conservan como recursos originales suministrados del tema cuyo
catálogo acredita a Hooandee. La fuente Steam no incluye una licencia gráfica
separada ni una atribución adicional verificable; este paquete no les asigna
una licencia nueva ni los atribuye a terceros.

El destino es el teclado táctil nativo de Windows 11, `TextInputHost.exe`. Este
inventario no declara builds validadas ni equivalencia visual en dispositivo.
La integración debe conservar el layout, foco, etiquetas, indicadores y entrada
de Windows y verificar por separado las capas gráficas, estados, tipografía,
runas, efectos, sonido, teclado extendido y composición de caracteres.


## Adaptación nativa

El motor compartido carga las siete caras, placa y sprites originales desde RCDATA.
Reproduce las brasas de 380 ms, Igni de 620 ms y los brillos de 420 ms mediante
Composition. Mantiene distribución, tamaños, clipping, opacidad y fuentes de
iconos de Windows. Aplica las tintas originales, peso 700 a letras y el descenso
de 2 px al pulsar, sin sustituir transformaciones nativas que ya estén activas.
Las runas quedan arriba a la izquierda para reservar el indicador Xbox nativo.

Intro, Retroceso, Mayús y Tab se identifican por glifos de las fuentes nativas
de iconos; Tab también admite la etiqueta exacta observada en el modo numérico. En Emoji SIP Fluent Icons, el glifo de Mayús con
candado permite aplicar la cara granate; sus cambios se observan y se retira el
callback al restaurar. La fuente del sistema se consulta, nunca se redistribuye.
No se lee el texto de campos ni se envían pulsaciones a los diagnósticos.

La adaptación conserva el sonido y las transiciones de apertura y cierre de
Windows. No incorpora el sintetizador de Steam, la salida por filas ni controles
de sonido/efectos. Los efectos responden al puntero y no imponen el mínimo de
pulsación de 70/90 ms. El foco XAML se conserva; no acredita navegación con mando.

No hay detección general de Mayús de un uso, AltGr, Bloq Mayús independiente o
teclas muertas. La presencia de la cara granate o la runa Yrden en el paquete no
acredita esos estados. Los caracteres extendidos conservan su presentación nativa.
Estas diferencias impiden declarar equivalencia visual completa con Steam.

La [guía del runtime](NATIVE-KEYBOARD.md) describe selección, restauración,
compilación, despliegue y comprobaciones. El inventario anterior es la referencia
original, no una lista de funciones confirmadas en todas las versiones de Windows.
