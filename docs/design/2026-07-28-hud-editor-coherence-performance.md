# Coherencia y rendimiento del editor HUD

## Objetivo

El editor debe responder de inmediato en el QAM, aplicar únicamente el último estado solicitado y
explicar las capacidades reales de MangoHud sin exponer su configuración técnica como si fueran
opciones independientes por elemento. Cuando no hay métricas propias de Panel de Control visibles,
el subsistema HUD no debe realizar trabajo periódico.

## Interacción

- La previsualización utiliza siempre el modelo local más reciente.
- Los cambios se guardan automáticamente después de 700 ms sin interacción.
- Solo puede existir una persistencia en curso. Si el usuario sigue editando, se conserva un único
  modelo pendiente y sustituye cualquier estado intermedio anterior.
- Activar, desactivar, recargar o cerrar la sección fuerza el último modelo completo sin crear
  escrituras duplicadas.
- Los estados remotos antiguos nunca sustituyen una edición local más reciente.

## Controles de tamaño

MangoHud no admite tamaño por elemento. La interfaz presenta su jerarquía real en un único bloque:

1. **Tamaño general**: escala todo el HUD.
2. **Todo al mismo tamaño**: desactiva la fuente pequeña nativa y alinea detalles y unidades con
   las métricas principales.

El modelo conserva compatibilidad interna con `font_scale`, `font_size`, `font_size_secondary` y
`font_size_text`, pero no presenta esos parámetros como tamaños independientes que MangoHud no
puede garantizar. Ningún editor de elemento promete un tamaño individual.

## Elementos dependientes

GPU, CPU y Batería necesitan su métrica padre para que MangoHud renderice las demás métricas del
bloque.

- La métrica padre aparece marcada, no enfocable y con la explicación «Necesaria para mostrar el
  grupo».
- Los subitems restantes continúan siendo opcionales.
- Añadir cualquier subitem de un grupo inserta también su padre si falta.
- La normalización frontend y backend repara modelos antiguos o externos que contengan hijos sin
  padre.

## Composición QAM

- Cada pista de slider tiene 8 px de espacio lateral y `box-sizing: border-box`.
- Los controles mantienen una sola columna y no dependen de escalado CSS para caber.
- Los textos distinguen la escala global de la opción que elimina la jerarquía de fuente pequeña.

## Aplicación y rendimiento

- Las métricas nativas siguen siendo responsabilidad de MangoHud y no generan polling del plugin.
- Los estados propios se refrescan inmediatamente cuando una acción de Panel de Control los cambia.
- TDP dinámico, consumo y RPM se comprueban como máximo cada dos segundos; solo un valor diferente
  provoca escritura y hot reload.
- Los valores lentos reutilizan los eventos del subsistema y no añaden otro bucle.
- Sin métricas `pdc_*` activas, el tick periódico sale antes de usar el executor.
- Un tick produce como máximo una configuración y un hot reload, aunque cambien varias métricas.
- El editor abierto mantiene su polling de estado; al desmontarse no deja timers ni llamadas
  repetidas.

## Evidencia

- Pruebas frontend para cola latest-only, cierre, recarga, jerarquía tipográfica, padding y filas
  obligatorias.
- Pruebas de modelo TypeScript y Python para inserción y conservación de padres.
- Pruebas RPC para coalescencia y aplicación honesta.
- Suite frontend y backend completas, typecheck, Ruff y build.
- En Legion Go S `83N6`: artefacto idéntico, carga sin errores, respuesta del editor, ausencia de
  cola de estados intermedios y medición proporcional de CPU antes y durante el uso.
