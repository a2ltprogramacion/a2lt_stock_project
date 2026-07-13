# Plan Maestro de Tickets de Desarrollo (Unified Technical Roadmap) - A2LT Stock

Este documento constituye la única hoja de ruta oficial y el plano de construcción del sistema. Cada ticket define requerimientos funcionales, firmas de servicios, restricciones lógicas y criterios de aceptación específicos. Los agentes de programación deben procesar estos bloques de forma estrictamente secuencial, prohibiéndose el uso de atajos de código o comentarios evasivos.

---

## TICKET #1: Inicialización del Proyecto y Modelos de Datos Core (Esquema Completo)

### Descripción
Configurar el entorno inicial de Django aislado en un entorno virtual con SQLite y mapear la totalidad de la arquitectura de datos relacional para evitar migraciones destructivas en fases avanzadas del proyecto.

### Especificaciones Técnicas
1. **Aislamiento del Entorno:**
   * Inicializar el entorno virtual `.venv` en la raíz del proyecto.
   * Configurar el archivo `.gitignore` excluyendo `.venv/`, `db.sqlite3` y carpetas `__pycache__/`.
2. **Modelado de Datos (`inventory/models.py`):**
   * `ConfiguracionSistema`: Patrón Singleton (bloqueo en método `save` forzando `pk=1`). Campos para metadatos del negocio (nombre comercial, RIF, dirección, teléfono, correo) y parámetros cambiarios globales.
   * `Almacen`: Identificador de sucursal física y bandera `es_principal`.
   * `Articulo`: SKU (Clave Primaria), código de proveedor, nombre, categoría, tipo (FISICO/COMBO), costo, precio_divisa, parámetros individuales y campo de borrado lógico (`activo = BooleanField(default=True)`).
   * `InventarioAlmacen`: Tabla intermedia de stock por ubicación física. Restricción compuesta `unique_together = ('articulo', 'almacen')`. Campos de cantidad en formato `DecimalField`.
   * `RecetaCombo`: Estructura que vincula un artículo tipo Combo Virtual con sus componentes físicos y cantidades requeridas.
   * `Contacto`: Entidad unificada para Clientes y Proveedores, con campos extendidos opcionales (`rif`, `nombre_asesor`) para la gestión con proveedores.
   * `MovimientoKardex`: Registro inalterable de transacciones contables del inventario, con llaves foráneas a artículo, almacén, nota de entrega y UUID de lote de carga masiva.
   * `AuditoriaTasa`: Historial cronológico de fluctuaciones de tasas cambiarias oficiales y paralelas.
   * `NotaEntrega` y `DetalleNotaEntrega`: Estructura para el asentamiento de documentos internos de venta con snapshots inmutables de precios.
3. **Control de Capa Administrativa (`inventory/admin.py`):**
   * Registrar todos los modelos core. Bloquear permisos de creación, modificación y eliminación directa en `InventarioAlmacen` y `MovimientoKardex` mediante las propiedades del `ModelAdmin` para blindar la inalterabilidad manual del stock.

### Criterios de Aceptación (DoD)
- [ ] Comprobación del sistema limpia (`python manage.py check`) con 0 advertencias o errores.
- [ ] Migraciones ejecutadas en SQLite sin dependencias circulares o fallos de claves foráneas.

---

## TICKET #2: Lógica del Kárdex, Transacciones y Combos Dinámicos

### Descripción
Implementar el motor lógico interno del inventario en la capa de servicios, garantizando la atomicidad transaccional pura y el cálculo en tiempo real de las existencias de combos virtuales.

### Especificaciones Técnicas
1. **Motor Transaccional (`inventory/services.py`):**
   * Desarrollar la función `registrar_movimiento(articulo, almacen, tipo, cantidad, concepto, **kwargs)`. Agregar obligatoriamente el decorador `@transaction.atomic`.
   * Implementar bloqueo pesimista con `select_for_update()` al evaluar las existencias físicas.
   * Si el movimiento es una `'SALIDA'`, validar que el stock sea suficiente; en caso contrario, levantar una excepción de tipo `ValueError` para forzar un Rollback inmediato de la base de datos.
2. **Cálculo Dinámico de Combos (`inventory/models.py` -> `Articulo`):**
   * Desarrollar el método `get_stock_disponible(almacen=None)`. Si el artículo es `'FISICO'`, suma sus existencias; si es `'COMBO'`, ejecuta una importación lazy del servicio encargado de evaluar la receta bajo la fórmula matemática:
     $$\text{Stock Combo} = \min_{i} \left( \left\lfloor \frac{S(a_i)}{q_i} \right\rfloor \right)$$
3. **Desagregación de Combos en Venta:**
   * Desarrollar la función `procesar_salida_combo(combo, almacen, cantidad_combos, nota_entrega)`. Debe descontar de forma atómica cada componente físico de la receta de manera proporcional a las unidades vendidas del combo.

### Criterios de Aceptación (DoD)
- [ ] Suite de pruebas unitarias (`TransactionTestCase`) con 14 tests automatizados pasando exitosamente en verde.
- [ ] Verificación de Rollback completo si un componente físico se queda sin stock durante la desagregación de un combo.

---

## TICKET #3: Carga Masiva Tolerante a Fallos y Gestión de Colisiones

### Descripción
Desarrollar el procesador de archivos Excel `.xlsx` para la importación masiva de inventario y catálogo, implementando aislamiento de errores por fila y persistencia intermedia de conflictos mediante sesiones HTTP.

### Especificaciones Técnicas
1. **Validación de Formato (`services.py`):**
   * Función `validar_formato_excel(archivo)`. Validar extensión `.xlsx` pre-parseo. Procesar únicamente la primera hoja activa (`workbook.active`).
2. **Procesamiento de Filas (`procesar_carga_masiva`):**
   * Mapear columnas fijas: SKU, Nombre, Costo, Cantidad (opcional), Precio_Divisa, Almacen.
   * Envolver cada iteración en un bloque `try-except`. Si el SKU no existe, se crea el artículo en caliente; si el nombre está duplicado con otro SKU, inyecta una advertencia en el log de incidencias sin detener el lote.
   * Si Cantidad viene vacía o es 0, actualizar datos base del catálogo de forma silenciosa sin generar movimientos de stock.
3. **Manejo de Colisiones de Stock en Sesión:**
   * Si el SKU existe y Cantidad > 0, aislar los metadatos del conflicto en `request.session` bajo un `lote_id` (UUID4). Los registros limpios del Excel se persisten de inmediato en la base de datos.
4. **Resolución de Conflictos (`resolver_colision`):**
   * `SUMAR`: Ejecuta `registrar_movimiento` de ENTRADA por la cantidad del Excel.
   * `SUSTITUIR`: Ejecuta una SALIDA para vaciar el stock anterior a 0, y acto seguido una ENTRADA con el valor del Excel.
   * `CANCELAR`: Descarta la fila en conflicto.

### Criterios de Aceptación (DoD)
- [ ] Suite de 10 tests unitarios verificando aislamiento de errores y flujos de colisión contables en verde (Total acumulado: 26 tests).
- [ ] Generación automática del archivo de auditoría `.txt` descargable con el log de incidencias por fila.

---

## TICKET #4: El Acoplamiento de la Piel (Templates Modulares de Django) — ✅ COMPLETADO

### Descripción
Traducir la interfaz gráfica de la maqueta interactiva al motor de plantillas de Django, configurando la ergonomía visual del tema oscuro neutro y llamadas asíncronas para el manejo de modales.

### Especificaciones Técnicas
1. **Layout Base (`inventory/templates/inventory/base.html`):**
   * Configurar barra lateral estática y área `<main>` dinámica bajo Tailwind CSS.
   * Inyectar script bloqueante en el `<head>` para evaluar `localStorage.getItem('a2lt_theme')` antes de pintar el DOM, neutralizando el parpadeo blanco (FOUC).
   * Paleta oscura forzada: `dark:bg-zinc-900` para el fondo general, `dark:bg-zinc-800` para paneles, componentes y tablas, y `dark:text-zinc-100` para textos. Quedan prohibidos los tonos violetas.
2. **Interfaz de Carga (`carga.html`):**
   * Acoplar zona Drag & Drop. Mapear botones `[Sumar]`, `[Sustituir]`, `[Cancelar]` en el modal de colisión. Al hacer clic, desactivar inmediatamente todos los botones del contenedor (`disabled = true`) para neutralizar ráfagas de clics (Race Conditions) y disparar Fetch API hacia el backend.
3. **Catálogo y Redes (`catalogo.html`):**
   * Iterar el catálogo de artículos. Alinear etiquetas `<textarea>` al extremo izquierdo absoluto del archivo HTML para eliminar sangrías físicas del DOM. Aplicar `.trim()` en la lectura de JavaScript para asegurar copias al portapapeles perfectas para WhatsApp e Instagram.

### Criterios de Aceptación (DoD)
- [ ] Verificación en navegador del cambio de tema de Zinc persistente sin parpadeo blanco intermedio.
- [ ] Copia al portapapeles de fichas técnicas y textos comerciales libres de tabulaciones o espacios en blanco accidentales.

---

## TICKET #5: Módulo de Ventas, Conversión Cambiaria y Notas de Entrega

### Descripción
Implementar el ciclo transaccional de facturación interna, congelando la matemática cambiaria en el momento exacto del asentamiento y construyendo el formato de impresión física.

### Especificaciones Técnicas
1. **Servicio Core (`services.py` -> `procesar_venta`):**
   * Firma: `procesar_venta(cliente_id, lista_items, almacen_id, usuario='')` bajo `@transaction.atomic`.
   * Margen de Seguridad: Validar que `ConfiguracionSistema.tasa_bcv > 0` para blindar el flujo contra excepciones de división por cero.
   * Capturar `tasa_bcv` y el factor relacional de cobertura (`factor_cobertura = T_mercado / T_bcv`) del Singleton y grabarlos de forma inmutable en la cabecera de la `NotaEntrega`.
2. **Persistencia de Líneas de Detalle:**
   * Por cada ítem, evaluar stock real vía `get_stock_disponible()`. Si falla, disparar excepción.
   * Calcular el precio en Bolívares inmutable en el bucle: 
     $$\text{precio\_unitario\_bs} = \text{precio\_unitario\_usd} \times \text{factor\_cobertura\_aplicado} \times \text{tasa\_bcv\_aplicada}$$
   * Grabar físicamente el resultado en `DetalleNotaEntrega`. Disparar las salidas del Kárdex asociadas al ID de la nota (desagregando componentes si el ítem es un combo).
3. **Formato de Impresión (`nota_entrega_print.html`):**
   * Desarrollar la vista de impresión inyectando estilos CSS `@media print`. Al activarse el comando de impresión del navegador, ocultar la barra lateral, botones y fondos, formateando el canvas exclusivamente en blanco y negro sobre dimensiones de ticket.

### Criterios de Aceptación (DoD)
- [ ] Suite total de 29 tests unitarios pasando exitosamente en verde.
- [ ] Test unitario que demuestre que una variación posterior en la tasa cambiaria global del Singleton no altera los totales en Bolívares de las Notas de Entrega emitidas en el pasado.

---

   * Crear la ruta `/tasas/sincronizar/` mapeada a una vista que responda un JSON con el estado de la operación. Vincularla mediante un botón de refresco asíncrono en la interfaz del panel de control.

### Criterios de Aceptación (DoD)
- [ ] Prueba unitaria utilizando `unittest.mock` para simular una respuesta de API JSON externa exitosa, validando la mutación del Singleton y el registro en el histórico de auditoría.
- [ ] Control de excepciones implementado: si la API externa experimenta timeout o retorna un error 500, el sistema intercepta el fallo de forma limpia, no altera las tasas actuales y emite una alerta visual en el frontend.

---

## TICKET #7: Motor de Reverso Atómico de Lotes de Carga Masiva

### Descripción
Desarrollar el motor de desinstalación de inventario para deshacer cargas masivas completas basándose en su identificador único de lote, garantizando la integridad histórica del Kárdex.

### Especificaciones Técnicas
1. **Validación de Integridad Temporal (`services.py` -> `revertir_carga_masiva`):**
   * Recibir el `lote_id` (UUID4).
   * Rastrear todos los `MovimientoKardex` asociados a dicho lote.
   * **Filtro de Seguridad Contable:** Por cada artículo involucrado en el lote, realizar una consulta en la base de datos buscando si existen movimientos en el Kárdex con una marca de tiempo (`fecha_hora`) *posterior* a la creación del lote y que correspondan a operaciones de Salida por Venta (Notas de Entrega), Ajustes Manuales o Consumos de Receta.
   * Si se detecta un solo movimiento posterior que afecte el stock de cualquiera de los productos del lote, disparar una excepción `ValidationError` y abortar el proceso.
2. **Ejecución Atómica del Reverso:**
   * Si la validación es exitosa, abrir un bloque `@transaction.atomic`.
   * Por cada artículo del lote, calcular la cantidad originalmente ingresada y ejecutar una llamada a `registrar_movimiento` de tipo `'SALIDA'` bajo el concepto estricto: `"Reverso automático de Carga Masiva - Lote [UUID]"`.
   * Descontar las existencias físicas del modelo `InventarioAlmacen` para el almacén correspondiente.

### Criterios de Aceptación (DoD)
- [ ] Test unitario que certifique que el reverso de un lote limpio devuelve el inventario de las sucursales a su valor numérico exacto anterior.
- [ ] Test de bloqueo verificado: si un artículo incluido en el lote simula una venta posterior de una sola unidad, el sistema bloquea el reverso del lote completo y emite un mensaje de error explícito detallando los SKU comprometidos.

---

## TICKET #8: Módulo de Movimientos entre Almacenes y Ajustes Manuales

### Descripción
Construir las funciones de servicio y la interfaz analítica para gestionar la transferencia física de mercancía entre sucursales y la ejecución de inventarios físicos de ajuste auditados.

### Especificaciones Técnicas
1. **Lógica de Transferencia (`services.py` -> `transferir_mercancia`):**
   * Firma: `transferir_mercancia(articulo_sku, almacen_origen_id, almacen_destino_id, cantidad, usuario='')`.
   * Envolver en `@transaction.atomic` con bloqueo pesimista `select_for_update()`.
   * Validar existencias en el origen. Si es menor a la cantidad a transferir, levantar excepción de stock insuficiente.
   * Registrar una transacción de `'SALIDA'` vinculada al almacén de origen (Concepto: `"Transferencia de salida hacia Almacén [Destino]"`).
   * Registrar una transacción de `'ENTRADA'` vinculada al almacén de destino (Concepto: `"Transferencia de entrada desde Almacén [Origen]"`). Ambos registros deben compartir la misma estampa de tiempo y transacción.
2. **Lógica de Ajuste Manual (Inventario Físico):**
   * Desarrollar `ejecutar_ajuste_manual(articulo_sku, almacen_id, nueva_cantidad_fisica, motivo, usuario='')`.
   * Calcular la diferencia: $\Delta = \text{nueva\_cantidad\_fisica} - \text{stock\_actual}$.
   * Si $\Delta > 0$, disparar entrada por el valor absoluto de la diferencia. Si $\Delta < 0$, disparar salida. Concepto obligatorio: `"Ajuste manual de inventario: [Motivo]"`.
3. **Pestaña Analítica (`inventory/templates/inventory/movimientos.html`):**
   * Maquetar una tabla de auditoría avanzada que consuma los registros de `MovimientoKardex`. Implementar filtros del lado del servidor usando Django Querysets para segmentar por Almacén, SKU, Tipo de movimiento y rango de fechas.

### Criterios de Aceptación (DoD)
- [ ] Al ejecutar una transferencia de 50 unidades entre dos almacenes, el stock del origen disminuye, el del destino aumenta y el Kárdex registra las dos filas inalterables de auditoría.
- [ ] Filtros de la tabla de movimientos operativos y libres de fugas de memoria o queries duplicadas (N+1 queries eliminadas mediante `select_related`).

---

## TICKET #9: Fichas de Contacto Avanzadas y Registro de Compras (Control de Costos)

### Descripción
Implementar los paneles de gestión para el alta segmentada de la base de datos de contactos y el flujo lógico de ingreso de mercancía por Factura de Compra para la actualización automática de costos base.

### Especificaciones Técnicas
1. **Lógica de Ingreso por Compra (`services.py` -> `registrar_compra_proveedor`):**
   * Firma: `registrar_compra_proveedor(proveedor_id, articulo_sku, cantidad, costo_factura, almacen_id, usuario='')`.
   * Envolver en un bloque transaccional atómico.
   * Actualizar de forma directa el campo `costo` del modelo `Articulo` con el nuevo valor `costo_factura`.
   * **Recálculo Automático de Precios:** Invocar una rutina interna que lea el método de ganancia configurado (Markup o Margin) y actualice inmediatamente el campo `precio_divisa` del artículo para asegurar que el precio de venta sugerido mantenga la rentabilidad real frente al nuevo costo.
   * Generar un movimiento de `'ENTRADA'` en el Kárdex vinculado al almacén seleccionado bajo el concepto: `"Ingreso por Factura de Compra Proveedor ID [Identificación]"`.
2. **Interfaz de Gestión (`contactos.html`):**
   * Reestructurar la pantalla para dividir visualmente a los Clientes de los Proveedores en pestañas independientes utilizando la misma tabla unificada de `Contacto`.
   * Forzar que al dar de alta un Proveedor, los campos `rif` y `nombre_asesor` de la base de datos de Django sean obligatorios de forma estricta en el formulario web, manteniéndolos opcionales únicamente para Clientes.

### Criterios de Aceptación (DoD)
- [ ] Al registrar una compra con un costo mayor al anterior, la ficha del artículo muta su costo y su precio en divisas en la base de datos de forma automática.
- [ ] Intentar guardar un contacto de tipo Proveedor con el campo RIF vacío bloquea la persistencia en el frontend y backend emitiendo una excepción de validación.

---

## TICKET #10: Panel de Control Analítico, KPIs y Alertas de Stock Mínimo

### Descripción
Construir el motor de agregación de datos comerciales y financieros en tiempo real para poblar los indicadores clave de rendimiento (KPIs) del Dashboard principal.

### Especificaciones Técnicas
1. **Consultas de Agregación de Datos (`inventory/views.py` -> `dashboard.html`):**
   * **Métrica de Valoración Contable:** Desarrollar una consulta utilizando funciones de agregación de Django (`Sum` y expresiones `F`) para calcular el valor total del inventario en custodia del negocio mediante la fórmula matemática:
     $$\text{Valor Total} = \sum (\text{InventarioAlmacen.cantidad\_disponible} \times \text{Articulo.costo})$$
   * **Métrica de Rendimiento de Ventas:** Calcular el volumen bruto facturado en dólares y su equivalencia en Bolívares mediante la agregación de las líneas de `DetalleNotaEntrega` emitidas en el día en curso y el acumulado mensual.
2. **Motor de Alertas de Ruptura de Stock:**
   * Desarrollar un Queryset optimizado que identifique todos los artículos de tipo `'FISICO'` cuya sumatoria de existencias en todos los almacenes sea exactamente igual a 0.
   * Pintar estos artículos en una sección prioritaria del Dashboard bajo una tarjeta de alerta de color carmín (`dark:bg-red-950`, `text-red-200`) denominada "Rupturas de Stock Críticas - Requiere Reposición".

### Criterios de Aceptación (DoD)
- [ ] La pantalla del Dashboard renderiza y procesa los datos en un tiempo inferior a 300ms en el entorno local.
- [ ] Queda estrictamente prohibido realizar bucles `for` en memoria de Python para calcular los totales; todo el procesamiento matemático debe ser delegado a la base de datos mediante queries consolidadas (`.aggregate()`).

---

## 🚀 PASOS MÁS ALLÁ (FUTURE-PROOF STABILITY & TELEMETRY)

## TICKET #11: Indexación Avanzada y Optimización de Concurrencia de Redes

### Descripción
Implementar índices compuestos y optimizaciones en la capa de persistencia para soportar ráfagas concurrentes de solicitudes de copiado de stock y consultas masivas desde múltiples terminales de social selling.

### Especificaciones Técnicas
1. **Optimización de Base de Datos (`inventory/models.py`):**
   * Añadir una declaración de índices explícitos en el modelo `Articulo` dentro de la clase `Meta`:
     ```python
     indexes = [
         models.Index(fields=['sku', 'activo']),
         models.Index(fields=['nombre']),
     ]
     ```
   * Modificar el modelo `InventarioAlmacen` incorporando un índice compuesto sobre `('articulo', 'almacen')` para acelerar las operaciones del motor transaccional de salidas rápidas del Kárdex.
2. **Ejecución y Despliegue Secuencial:**
   * Generar el archivo de migración correspondiente utilizando `python manage.py makemigrations inventory --name index_opt`.
   * Ejecutar la migración localmente y certificar mediante el comando `EXPLAIN QUERY PLAN` de SQLite que las búsquedas del catálogo pasaron de realizar escaneos completos de tabla (*Table Scan*) a búsquedas indexadas directas (*Index Scan*).

### Criterios de Aceptación (DoD)
- [ ] Las consultas de filtrado del catálogo utilizan los índices creados, verificado mediante logs de SQL de Django.
- [ ] Migración aplicada de forma limpia en el entorno local sin pérdida de registros existentes.

---

## TICKET #12: Generador de Impresión Parametrizada por Coordenadas Libres

### Descripción
Desarrollar el motor de renderizado de impresión flexible que permita mapear los campos de la Nota de Entrega sobre formatos de factura físicos preimpresos mediante una matriz de coordenadas espaciales.

### Especificaciones Técnicas
1. **Configuración de Coordenadas en la Base de Datos:**
   * Añadir campos de calibración dimensional al modelo `ConfiguracionSistema`: `print_offset_x` (DecimalField, para sangría izquierda en mm), `print_offset_y` (DecimalField, para sangría superior en mm), `print_row_spacing` (DecimalField, espaciado entre líneas de ítems en mm).
2. **Capa Visual y CSS Dinámico (`inventory/templates/inventory/impresion_coordenadas.html`):**
   * Crear un template de impresión especial donde cada elemento informativo de la Nota de Entrega (Nombre del Cliente, RIF, Fecha, Total) se renderice dentro de contenedores HTML posicionados de forma absoluta (`position: absolute`).
   * Utilizar variables inline de estilos CSS alimentadas directamente desde las variables del Singleton: 
     ```html
     <div style="position: absolute; left: {{ config.print_offset_x }}mm; top: {{ config.print_offset_y }}mm;">
         {{ nota.cliente.nombre }}
     </div>
     ```
   * Esto permite al comerciante calibrar el sistema desde el panel de control para que el texto coincida exactamente con los recuadros de sus talonarios físicos preimpresos.

### Criterios de Aceptación (DoD)
- [ ] La interfaz permite modificar las coordenadas en milímetros desde el panel de control y el layout de impresión HTML desplaza los bloques de texto de forma milimétrica en consecuencia.

---

## TICKET #13: Sistema de Telemetría Local y Respaldos Atómicos en Frío de SQLite

### Descripción
Implementar el script de mantenimiento operativo automatizado del sistema local para ejecutar copias de seguridad consistentes en frío de la base de datos SQLite y monitorear la salud del almacenamiento.

### Especificaciones Técnicas
1. **Script de Respaldo Consistente (`inventory/cron_backup.py`):**
   * Desarrollar un script ejecutable de Python nativo independiente del servidor web.
   * Para garantizar un respaldo 100% libre de corrupción, el script debe invocar comandos de la API de SQLite de bajo nivel para forzar un vaciado de páginas en disco mediante una conexión en modo lectura exclusiva utilizando el comando de control: `VACUUM INTO 'backups/backup_a2lt_[timestamp].sqlite3'`.
2. **Rotación de Logs e Indicador de Desgaste:**
   * El script creará un log local detallando el tamaño del archivo resultante, el espacio libre en el disco duro del procesador local y emitirá una advertencia crítica en consola si el almacenamiento de la máquina anfitriona cae por debajo del 15% de su capacidad total.
3. **Punto de Entrada en Django:**
   * Registrar un comando personalizado de Django (`python manage.py ejecutar_backup_frio`) en la carpeta `inventory/management/commands/` para permitir que el operador pueda disparar el respaldo de forma manual desde la terminal con un solo comando.

### Criterios de Aceptación (DoD)
- [ ] Al ejecutar `python manage.py ejecutar_backup_frio`, se genera un archivo de base de datos SQLite clonado e independiente dentro de la carpeta `backups/`, totalmente funcional y libre de bloqueos de escritura.
- [ ] El comando finaliza su ejecución de forma limpia reportando las métricas de espacio consumido en la terminal.

---

## REGISTRO DE DECISIONES DE ARQUITECTURA (ADRs) Y ESTADO DE TICKETS

(El histórico de ADR-01 a ADR-13 se encuentra preservado en versiones anteriores. A partir de aquí continuamos la bitácora de ejecución).

**ADR-14**: Aislamiento lógico multi-tenant mediante EmpresaManager y Middleware de Contexto.
**ADR-15**: Mutación de ConfiguracionSistema Singleton a una relación directa 'ConfiguracionEmpresa' vinculada a la entidad Empresa.
**ADR-16**: Adopción de 'contextvars' (en lugar de threading.local) en managers.py para garantizar un scope seguro y compatible con ejecuciones síncronas/asíncronas en Django.

### TICKET #1-SAAS: Refactorización e Inyección de la Capa Multi-Tenant — ✅ COMPLETADO
*   **Alcance:**
    *   Aislamiento con EmpresaManager y contextvars.
    *   Migración de DB a SaaS Verde (drop de DB actual).
    *   Modificación masiva de FK en todos los modelos.
*   **Estado:** ✅ Completado.


### TICKET #6: Motor de Automatización e Integración de Tasas de Cambio (API Sync) — ✅ COMPLETADO (2026-06-25)
*   **Iniciado:** 2026-06-25
*   **Alcance:**
    *   Cliente HTTP robusto usando `requests` con timeout de 5 segundos.
    *   Procesamiento seguro de la respuesta iterando por llaves (cero uso de `eval()` o `exec()`).
    *   Cálculo del Factor de Cobertura y mutación atómica del Singleton.
    *   Histórico en `AuditoriaTasa` con fuente "API".
    *   Endpoint asíncrono para su consumo desde el frontend.
    *   Tests con `unittest.mock` para simulación de escenarios de éxito y fallo (500, timeout).
*   **Estado:** ✅ Completado.

---

### TICKET #7: Motor de Reverso Atómico de Lotes de Carga Masiva — ✅ COMPLETADO
*   **Iniciado:** 2026-06-25
*   **Alcance:**
    *   `revertir_carga_masiva(lote_id, usuario)` en `services.py`.
    *   Validación de integridad temporal: buscar movimientos de salida posteriores a la carga.
    *   Reverso atómico mediante llamadas inversas de `SALIDA` en Kárdex.
    *   Tests de rollback limpio y de bloqueo defensivo.
*   **Estado:** ✅ Completado.

---

### TICKET #8: Módulo de Movimientos entre Almacenes y Ajustes Manuales — ✅ COMPLETADO
*   **Iniciado:** 2026-06-25
*   **Alcance:**
    *   `transferir_mercancia` para envíos entre sucursales.
    *   `ejecutar_ajuste_manual` para cuadres de inventario físico.
    *   Pestaña analítica de auditoría en `movimientos.html` con N+1 optimizations.
    *   Tests de TransactionTestCase.
*   **Estado:** ✅ Completado.

---

### TICKET #9: Fichas de Contacto Avanzadas y Registro de Compras (Control de Costos) — ✅ COMPLETADO
*   **Iniciado:** 2026-06-25
*   **Alcance:**
    *   `registrar_compra_proveedor` con recálculo automático de precio (protección de margen).
    *   Fichas de contacto segmentadas en la UI (Clientes / Proveedores).
    *   Validación estricta de formulario (RIF y Asesor obligatorios para Proveedores).
    *   Tests de TransactionTestCase (compras y validación backend).
*   **Estado:** ✅ Completado.

---

### TICKET #10: Panel de Control Analítico, KPIs y Alertas de Stock Mínimo — ✅ COMPLETADO
*   **Iniciado:** 2026-06-25
*   **Alcance:**
    *   `vista_dashboard` con métricas financieras nativas en base de datos.
    *   Cálculo de Valoración del Inventario vía `Sum(F() * F())`.
    *   Cálculo de Volumen de Ventas (Mensual en USD y Bs) desde `DetalleNotaEntrega`.
    *   Motor de Alertas Preventivas de Punto de Reorden (`cantidad_disponible <= stock_minimo`).
    *   Pruebas unitarias de agregación y filtros.
*   **Estado:** ✅ Completado.

---

### TICKET #11: Indexación Avanzada y Optimización de Concurrencia de Redes — ✅ COMPLETADO
*   **Iniciado:** 2026-06-25
*   **Alcance:**
    *   Optimización física del catálogo web con índice compuesto sobre `['sku', 'activo']`.
    *   Índice de texto sobre `['nombre']` en `Articulo` para el autocompletado.
    *   Índice compuesto sobre `['articulo', 'almacen']` en `InventarioAlmacen` para acelerar el `select_for_update()`.
    *   Pruebas unitarias para certificar la existencia estructural de los índices en el ORM.
*   **Estado:** ✅ Completado.

---

### TICKET #12: Generador de Impresión Parametrizada por Coordenadas Libres — ✅ COMPLETADO
*   **Iniciado:** 2026-06-25
*   **Alcance:**
    *   Campos dimensionales en `ConfiguracionEmpresa` (`print_offset_x`, `print_offset_y`, `print_row_spacing`).
    *   Plantilla HTML modular en `@media print` con posicionamiento absoluto y bucles.
    *   Vista conectada al contexto Multi-Tenant.
    *   Tests de persistencia y renderizado.
*   **Estado:** ✅ Completado.

---

### TICKET #13: Sistema de Exportación Lógica y Respaldos Aislados por Tenant (Cierre de Proyecto) — ✅ COMPLETADO
*   **Iniciado:** 2026-06-25
*   **Alcance:**
    *   `exportar_datos_tenant` en `services.py` con aislamiento lógico (solo datos del tenant).
    *   Mitigación de timeout truncando historial a N meses.
    *   Controlador de descarga directa en `views.py`.
    *   Comando `ejecutar_backup_SaaS.py` con telemetría de disco (`shutil.disk_usage`).
    *   Tests unitarios de aislamiento y truncamiento cronológico.
*   **Estado:** ✅ Completado.

---

### TICKET #14-SAAS: Módulo de Trazabilidad de Garantías y Control de Seriales en Mostrador — ✅ COMPLETADO — ✅ COMPLETADO
*   **Iniciado:** 2026-06-25
*   **Alcance:**
    *   Añadir `usa_serial` en `Articulo` y crear modelo `SerialArticulo`.
    *   Validación y quema atómica de seriales en `procesar_venta` con `select_for_update()`.
    *   UI Modal / Wizard paso a paso para la selección FIFO de seriales en el carrito.
    *   Endpoint AJAX `vista_buscar_seriales_articulo` filtrado por almacén.
    *   Pruebas unitarias de bloqueo Race Condition y consistencia de cantidad.
*   **Estado:** ✅ Completado.

---

### TICKET #15-SAAS: Módulo de Devoluciones Parciales, Notas de Crédito y Almacén de Cuarentena — ✅ COMPLETADO
*   **Iniciado:** 2026-06-25
*   **Alcance:**
    *   Añadir `usa_almacen_cuarentena` a `ConfiguracionEmpresa`.
    *   Modelos `NotaCredito` y `DetalleNotaCredito`.
    *   Servicio `procesar_devolucion_venta` con soporte de reingreso a cuarentena vs origen y matriz de costo (Histórico vs Actual).
    *   Gestión de ítems dañados/defectuosos para merma automática.
    *   Reverso atómico de seriales vendidos a estado `DISPONIBLE`.
    *   Tests transaccionales.
*   **Estado:** ✅ Completado.

---

**ADR-17**: Seguridad Hermética del Manager Multi-Tenant — El `EmpresaManager` retorna un queryset vacío (`none()`) cuando el `ContextVar` no tiene empresa activa, en lugar de retornar toda la tabla sin filtrar. Esto blinda contra fugas de datos cross-tenant accidentales.
**ADR-18**: Snapshot de Costo Inmutable en Detalle de Venta — Se añade el campo `costo_unitario_snapshot` a `DetalleNotaEntrega` para congelar el costo de adquisición al momento exacto de la venta, habilitando devoluciones a costo histórico real sin distorsión contable.

### TICKET #16-REFFACTOR: Saneamiento Crítico de Seguridad e Integridad SaaS — ✅ COMPLETADO (2026-06-25)
*   **Iniciado:** 2026-06-25
*   **Alcance:**
    *   C-01: `EmpresaManager` retorna `.none()` sin tenant activo (ADR-17).
    *   C-02: ENTRADA atómica con expresiones `F()` contra race conditions concurrentes.
    *   C-03: Correlativo de `NotaEntrega` aislado por empresa con `unique_together` + `save()` con `Max('numero')` filtrado por `empresa`.
    *   C-04: Campo `costo_unitario_snapshot` en `DetalleNotaEntrega` y reparación de la matriz de costeo histórico en devoluciones (ADR-18).
    *   C-05: Ampliación de `CONCEPTO_CHOICES` y estandarización semántica de conceptos del Kárdex.
    *   C-06: Remoción de singletons ciegos (`ConfiguracionEmpresa.objects.first()`).
    *   C-07 (Ticket #16-BACKEND-SHIELD): SALIDA con `F()` expression en `registrar_movimiento()` delegando la resta al motor de BD para blindaje anti-race-condition. Correlativo de `NotaEntrega.save()` aislado por empresa (confirmado pre-existente). `costo_unitario_snapshot` confirmado en modelo y `procesar_venta()`.
    *   Tests defensivos de aislamiento cross-tenant y diferenciación de costo histórico vs actual.
*   **Estado:** ✅ Completado.

---

### TICKET #17-FRONT-FIX: Restauración UI Slate e Integridad Matemática — ✅ COMPLETADO (2026-06-25)
*   **Iniciado:** 2026-06-25
*   **Alcance:**
    *   Fijación matemática en `models.py` asegurando que los campos operen en tipo de dato `Decimal` con precedencia de `tasa_mercado` sobre `factor_cobertura`.
    *   Filtrado Multi-Tenant riguroso en la vista de `contactos`.
    *   Sincronización del toggle de cambio de tema y resolución del bug "descuadrado" de 4px del sidebar en `base.html`.
    *   Portabilidad 100% íntegra desde la maqueta del tab-contactos con soporte a los modales de contacto hacia `contactos.html`.
    *   Inyección de funciones JavaScript nativas (`openContactModal`, `closeContactModal`, `viewContactDetails`) para habilitar los botones de Registrar Cliente/Proveedor y Ver Detalles.
    *   Aprobación de la suite de pruebas unitarias al 100%.
*   **Estado:** ✅ Completado.

---

### CORRECCIONES DE INTERFAZ, RUTAS FALTANTES & AUTO-CÁLCULO DE TASAS — ✅ COMPLETADO (2026-06-25)
*   **Iniciado:** 2026-06-25
*   **Alcance:**
    *   Saneamiento del header en `base.html` (reparada etiqueta malformada que descuadraba el menú lateral).
    *   Inyección de script de inicio de tema (Light/Dark) en el `<head>` y persistencia robusta vía `localStorage` en `toggleTheme()` para evitar parpadeos visuales al cambiar de página.
    *   Conversión de botones estáticos a enlaces dinámicos Django en el sidebar (`articulos`, `configuracion`) con resaltado CSS activo condicionado al enrutamiento del servidor.
    *   Páginas y plantillas completas para los módulos anteriormente vacíos: `articulos.html` (lista dinámica de fichas) y `configuracion.html` (formulario interactivo completo).
    *   Auto-cálculo interactivo en frontend (Vanilla JS) y validación transaccional en backend (`ConfiguracionEmpresa.save()`) entre la Tasa BCV, el Factor de Cobertura y la Tasa Ajustada (Mercado).
    *   Histórico auditor en tiempo real alimentado desde el guardado del formulario hacia `AuditoriaTasa` sin duplicidad en la sincronización automática por API.
*   **Estado:** ✅ Completado.

---

### TICKET #18-RBAC: Perfiles de Acceso y Control Multi-Tenant — ✅ COMPLETADO
*   **Iniciado:** 2026-06-25
*   **Alcance:**
    *   Arquitectura de perfiles y permisos basada en roles.
*   **Estado:** ✅ Completado.

---

### TICKET #19: Estructura de Compras y Control Logístico (Backend & Frontend) — ✅ COMPLETADO
*   **Iniciado:** 2026-06-25
*   **Alcance:**
    *   Ingreso de `DocumentoCompra` y vista `compras.html`.
*   **Estado:** ✅ Completado.

---

### TICKET #20-REVERSOS: Módulo de Contrapartidas y Devoluciones — ✅ COMPLETADO (2026-06-25)
*   **Iniciado:** 2026-06-25
*   **Alcance:**
    *   `NotaEntrega` y `DocumentoCompra`: campos `estado` (PROCESADO/ANULADO) + `motivo_anulacion` sin sobreescribir observaciones originales.
    *   `SerialArticulo`: campo `compra_origen` FK a `DocumentoCompra` + estado `ANULADO_COMPRA`.
    *   `registrar_compra_proveedor`: estampa `compra_origen=documento` en cada serial creado.
    *   `reversar_nota_entrega()`: `@transaction.atomic`, `select_for_update()`, valida estado no-ANULADO, cambia a ANULADO, inyecta ENTRADA por `DEVOLUCION_VENTA` vía F(), libera seriales (VENDIDO → DISPONIBLE, desliga `detalle_nota`).
    *   `reversar_documento_compra()`: `@transaction.atomic`, `select_for_update()`, valida estado no-ANULADO, cambia a ANULADO, inyecta SALIDA por `ANULACION_COMPRA` vía F(), seriales → `ANULADO_COMPRA`.
    *   UI `reversos.html`: diseño Slate-950, dos pestañas (Ventas/Compras), tabla con badges de estado, modal de motivo, Fetch API asíncrono con repintado de badge + remoción del botón.
    *   Sidebar: botón "Reversos y Anulaciones" con icono rojo.
    *   Endpoints: `reversos/` (GET), `api/reversar-venta/` (POST), `api/reversar-compra/` (POST).
*   **Estado:** ✅ Completado.

---

### TICKET #21-FORENSIC-FIX: Reparación de Puntos Ciegos de la Auditoría Forense — ✅ COMPLETADO (2026-06-25)
*   **Iniciado:** 2026-06-25
*   **Alcance:**
    *   **compras.html**: `processPurchase()` reescrita — fetch apunta a `/inventory/compras/registrar/`, payload JSON estructurado como `{ proveedor_id, numero_factura, fecha_compra, monto_total_usd, almacen_id, lista_items }`.
    *   **compras.html modal**: `name="red_social"`, `name="direccion"`, `name="observaciones"`, `name="nombre_asesor"` (condicional para PROVEEDOR).
    *   **ventas.html**: `processSale()` movió `almacen_id` a raíz del payload, eliminó `almacen_id` de cada item, agregó campo Observaciones inyectado al backend.
    *   **contactos.html**: Tabla corregida — `{{ c.red_social }}` en columna Red Social, `viewContactDetails()` recibe `direccion` y `observaciones` reales, modal con `name` attributes completos.
    *   **views.py contacto POST**: Lee `red_social`, `direccion`, `observaciones` y los persiste en `Contacto.objects.create()`.
    *   **views.py vista_crear_venta**: Captura `observaciones` del payload y lo pasa a `procesar_venta()`.
    *   **services.py procesar_venta**: Acepta parámetro `observaciones` y lo persiste en `NotaEntrega.observaciones`.
*   **Estado:** ✅ Completado. 58/58 tests pasando.

---

### TICKET #22-COVERAGE: Expansión de Cobertura de Pruebas (Tests Críticos) — ✅ COMPLETADO (2026-06-26)
*   **Iniciado:** 2026-06-26
*   **Alcance:**
    *   Auditoría topológica identificó 3 lagunas: reversos documentales, F() en SALIDA, correlativo aislado por empresa.
    *   `TestCoberturaCritica(TransactionTestCase)` con 4 tests anexados a `inventory/tests.py`:
        1. `test_reversar_nota_entrega_valida_kardex` — certifica ENTRADA DEVOLUCION_VENTA, stock restaurado, serial DISPONIBLE.
        2. `test_reversar_documento_compra_valida_kardex` — certifica SALIDA ANULACION_COMPRA, stock 0, serial ANULADO_COMPRA.
        3. `test_salida_kardex_ejecuta_expresion_f_correctamente` — F() en BD (no memoria) verificado vía refresh_from_db().
        4. `test_correlativo_nota_entrega_aislado_por_empresa` — 2 empresas con NotaEntrega #1 sin violar unique_together.
    *   Suite total: 58 → 62 tests en verde.
*   **Estado:** ✅ Completado.

---

### TICKET #23-CROSS-SELLING-CONFIG: Textos Editables de Social Selling — ✅ COMPLETADO (2026-06-26)
*   **Iniciado:** 2026-06-26
*   **Alcance:**
    *   Agregados campos `cross_selling_header` y `cross_selling_footer` (TextField) a `ConfiguracionEmpresa` con valores por defecto de los textos hardcodeados anteriormente.
    *   Migración `0005_configuracionempresa_cross_selling_footer_and_more`.
    *   Vista `configuracion_view` modificada para leer y persistir los nuevos campos vía POST.
    *   Template `configuracion.html`: nueva sección "Mensajes de Social Selling (Cross-Selling)" con dos textareas.
    *   Template `catalogo.html`: `updateCrossSellingOutput()` ahora lee `data-cross-header` y `data-cross-footer` del panel, poblados desde `{{ config.cross_selling_header }}` y `{{ config.cross_selling_footer }}`.
    *   62/62 tests en verde.

### TICKET #24-ANTI-HARDCODING-SOCIAL-SELLING: Saneamiento Arquitectónico (Anti-Hardcoding en Social Selling) — ✅ COMPLETADO (2026-06-26)
*   **Iniciado:** 2026-06-26
*   **Alcance:**
    *   **FASE 1 (Modelo):** Verificados los 3 campos TextField en `Articulo`: `ficha_tecnica` (Ficha Técnica), `social_quick` (Respuesta Rápida de Redes), `social_cross` (Mensaje de Cross-Selling). Ya existentes desde migration `0001`.
    *   **FASE 2 (CRUD):** `articulos_view` modificada para manejar POST (crear/actualizar artículos vía AJAX). Template `articulos.html` reescrito: modal completo con los 3 textareas de marketing (Ficha Técnica, Cross-Selling, Respuesta Rápida) + campos de identificación, precios y descripción. Los datos se persisten vía `fetch()` a `POST /articulos/`.
    *   **FASE 3 (Frontend):** `catalogo.html` saneado: los 3 textareas por tarjeta ahora leen `{{ articulo.social_quick }}`, `{{ articulo.social_cross }}`, `{{ articulo.ficha_tecnica }}` en lugar de strings hardcodeados. Cero indentación dentro de etiquetas textarea.
    *   **FASE 4 (Certificación):** `makemigrations` = No changes detected (los campos ya existían). Tests: 62/62 OK en 2.16s.
    *   **Seed:** Modificado `seed_db.py` con mensajes realistas para los 20 artículos usando placeholders `[Precio_USD]` y `[Precio_BCV]`. Ejecutado `seed_db --clear`: 20 artículos poblados, 29 facturas, 3 reversos, 88 movs. Kárdex.
    *   **Sustitución dinámica:** `catalogo.html` inyecta `TASA_MERCADO` y `ARTICULOS_PRECIOS` como JS global. `copyToClipboard()` sustituye placeholders al copiar. `updateCrossSellingOutput()` sustituye al generar el texto consolidado.
*   **Estado:** ✅ Completado.

---

### TICKET #23-TENANT-INIT: Automatización de Inicialización de Parámetros y Resolución de Bloques Comerciales — ✅ COMPLETADO (2026-06-26)
*   **Iniciado:** 2026-06-26
*   **Alcance:**
    *   **C-01 (Backend):** ✅ Señal `post_save` en `Empresa` → auto-crea `ConfiguracionEmpresa` con tasa_bcv=60.00, factor_cobertura=1.40, margen_global=30.00. `signals.py` + `apps.py` (ready ya importaba señales).
    *   **C-02 (Backend):** ✅ Migración `0006_inicializar_configuraciones_existentes` con `RunPython` que pobla retroactivamente empresas sin configuración vía `get_or_create()`.
    *   **C-03 (Backend):** ✅ Saneamiento contable: `catalogo` view calcula `precio_usd_ajustado = precio_divisa * factor_cobertura` y `precio_bs_bcv = precio_usd_ajustado * tasa_bcv` con `Decimal.quantize(0.01)`. Fix Multi-Tenant: reemplazado `.first()` por `get(empresa_id=get_current_empresa())`.
    *   **C-04 (Frontend/Templates):** ✅ Grid 2/1 con tarjetas de artículos + panel sticky de Oferta Consolidada. Textareas `quick-`, `cross-`, `ficha-` enlazados a `social_quick`, `social_cross`, `ficha_tecnica`. Precios calculados mostrados en cabecera.
    *   **C-05 (Frontend/JS):** ✅ `filterProducts()`, `toggleSelectProduct()`, `updateCrossSellingOutput()`, `copyToClipboard()` con sustitución de `[Precio_USD]` y `[Precio_BCV]`. Botones `fa-copy` por textarea + botón masivo en panel.
    *   **C-06 (Data):** ✅ Vista `vista_descargar_plantilla` en `views.py` + URL `carga/plantilla/` + botón "Descargar Plantilla Excel" en `carga.html`. Genera `.xlsx` con columnas: SKU, Nombre, Costo, Cantidad, Precio_Divisa, Almacen.

### TICKET #24-TENANT-SWITCH: Auditoría de Conmutación de Contexto de Sesión — ✅ COMPLETADO (v2.0)
*   **Iniciado:** 2026-06-26
*   **Alcance:** Validar que el cambio de empresa en el navbar ejecute una petición POST/GET controlada, mutando el `empresa_id` en la sesión de Django, limpiando los carritos draft activos y redirigiendo al usuario al Dashboard limpio del nuevo Tenant.
*   **Alcance Real (v1.0):**
    *   **Auditoría:** Detectado que `draftNoteItems` es volátil (JS en memoria) y se destruye al recargar página, pero existe riesgo **Cross-Tab Session Pollution**: si el operador cambia empresa en Pestaña 2, la Pestaña 1 inyecta datos en el Tenant equivocado.
    *   **Blindaje Frontend:** `ventas.html` y `compras.html` ahora envían `empresa_id: {{ request.session.empresa_id }}` en el payload JSON.
    *   **Blindaje Backend:** `procesar_venta()` y `registrar_compra_proveedor()` en `services.py` validan que `payload.empresa_id == get_current_empresa()`. Si difieren, lanzan `ValueError`.
    *   **Test de seguridad:** `test_prevencion_contaminacion_multi_pestana` en `TestSaneamientoYVulnerabilidadesSaaS`.
*   **Refactor v2.0 (2026-06-26) — RECHAZO ARQUITECTURA + CORRECCIÓN:**
    *   **Fallo #1 — NoneType Bypass:** El condicional `_ctx_empresa is not None` permitía que transacciones sin contexto de Tenant procedieran sin aislamiento.
    *   **Fallo #2 — Casteo Inseguro:** `int(empresa_id)` directo exponía a error 500 no controlado.
    *   **Fallo #3 — Auto-captura del raise:** El `raise ValueError("contexto ha cambiado")` estaba dentro del `try`, siendo capturado por su propio `except (ValueError, TypeError)`, resultando siempre en "inválido o ha sido alterado" aunque la discrepancia fuera real.
    *   **Correcciones aplicadas:**
        1. Separación del casteo seguro (`try: int()`) del `if` de discrepancia (fuera del `try`).
        2. Validación estricta: `_ctx_empresa is None` → `ValueError` inmediato.
        3. `empresa_id=None` (llamadas internas) → fallback a `_ctx_empresa`.
        4. Test expandido: contexto nulo, empresa_id vacío, no-casteable, discrepante, correcto, y fallback None.
*   **Estado:** ✅ Completado (v2.0). 63/63 tests OK.

### TICKET #25-SOCIAL-INTEGRATION: Cableado de Header/Footer Global y Data Seeding Real — ✅ COMPLETADO
*   **Iniciado:** 2026-06-26
*   **Alcance:** Modificar `seed_db.py` para inyectar textos comerciales reales (Ubiquiti, antenas). Cablear en `catalogo.html` las variables globales del Tenant `cross_selling_header` y `cross_selling_footer` en la concatenación de JavaScript.
*   **Cambios realizados:**
    *   **seed_db.py:** Actualizados los mensajes `SOCIAL_MESSAGES` para `A2LT-TEL-005` (Access Point Ubiquiti U6) y `A2LT-TEL-011` (Antena 5GHz 30dBi) con textos comerciales reales usando tokens `$[PRECIO_USD]` / `$[PRECIO_BCV]`.
    *   **catalogo.html:**
        *   Variables JS `msgHeaderTemplate` y `msgFooterTemplate` inicializadas desde `{{ config.cross_selling_header|escapejs }}` / `{{ config.cross_selling_footer|escapejs }}`.
        *   `updateCrossSellingOutput()` refactorizada: usa las variables globales en lugar de leer `dataset` del panel.
        *   `.replaceAll('$[PRECIO_USD]', ...)` y `.replaceAll('$[PRECIO_BCV]', ...)` agregados en `updateCrossSellingOutput()` y `copyToClipboard()` para soportar ambos formatos de tokens (`[Precio_USD]` legado + `$[PRECIO_USD]` nuevo).
*   **Estado:** ✅ Completado. 63/63 tests OK.

### TICKET #27-EXCEL-BULK-LOAD: Parser de Importación Masiva y Consistencia Contable — ✅ COMPLETADO
*   **Iniciado:** 2026-06-26
*   **Alcance:** Implementar el procesamiento de `plantilla_inventario_a2lt.xlsx` vía openpyxl. Validar SKU, mapear precios/costos en Decimal y forzar a que toda carga de stock genere un documento de movimiento en el Kárdex del Tenant, garantizando transaccionalidad atómica.
*   **Cambios realizados:**
    *   **services.py:** Nueva función `procesar_carga_masiva_excel(file_io, empresa_id, usuario)`. Valida cabeceras exactas (SKU, Nombre, Costo, Cantidad, Precio_Divisa, Almacen), casteo seguro a Decimal, rechaza almacenes ajenos al Tenant. Envuelta en `transaction.atomic()` — cualquier error → rollback total.
    *   **views.py:** Nueva vista `vista_carga_masiva_excel` — endpoint POST que recibe el archivo y empresa_id del contexto, retorna JSON con `lote_id`, `filas_procesadas`, `articulos_creados`, `kardex_entradas`.
    *   **urls.py:** Nueva ruta `carga/excel/` con name `carga_masiva_excel`.
    *   **tests.py:** `TestCargaMasivaExcelAtomica` con 3 tests:
        *   `test_carga_masiva_atomica_y_kardex` — 1 artículo nuevo + 1 existente; verifica stock, Kárdex, nombres/costos.
        *   `test_carga_masiva_rollback_por_error` — fila con costo negativo: el `transaction.atomic()` revierte todo.
        *   `test_carga_masiva_rechaza_almacen_ajeno` — almacén inexistente en el Tenant es rechazado.
*   **Estado:** ✅ Completado. 66/66 tests OK.

### TICKET #26-JS-DOM-FIX: Remoción de Variables Huérfanas y Saneamiento del Catálogo — ✅ COMPLETADO
*   **Iniciado:** 2026-06-26
*   **Alcance:** Erradicar diccionarios JS externos. Modificar `catalogo.html` para extraer tasas y precios directamente de los `data-attributes` del HTML generados por Django, garantizando que `updateCrossSellingOutput()` ensamble el mensaje sin reventar el hilo de ejecución.
*   **Cambios realizados:**
    *   Eliminado el bloque `<script>` huérfano que declaraba `TASA_MERCADO` y `ARTICULOS_PRECIOS` — causaban `ReferenceError` al no estar definidos.
    *   Cada `.articulo-card` ahora lleva `data-precio-usd` y `data-precio-bcv` con los valores precalculados por el backend (`precio_usd_ajustado` / `precio_bs_bcv`).
    *   `data-sku` ahora usa el SKU exacto (sin `|lower`) para que `querySelector` coincida con `toggleSelectProduct`.
    *   `updateCrossSellingOutput()` reescrita: lee `pUsd`/`pBcv` desde `card.dataset` en lugar de variables globales.
    *   `copyToClipboard()` reescrita: lee ambos precios desde `btn.dataset` en lugar de computar con `TASA_MERCADO`.
    *   Botones de copia actualizados con `data-precio-usd` y `data-precio-bcv` precalculados.
*   **Estado:** ✅ Completado. 63/63 tests OK.

### TICKET #28-CATEGORIA-REFACTOR: Normalización de Clasificación en Carga Masiva — ✅ COMPLETADO
*   **Iniciado:** 2026-06-26
*   **Alcance:** Inspeccionar el campo `categoria` en `Articulo`. Eliminar el string `'OTROS'` en línea dentro de `procesar_carga_masiva_excel()` e implementar un mecanismo de resolución segura que soporte la evolución del modelo hacia ForeignKey sin romper el motor atómico.
*   **Diagnóstico:** `categoria` es `CharField(max_length=20, choices=CATEGORIA_CHOICES, default='OTROS')` en `models.py:357`. El modelo ya tiene `default='OTROS'`, por lo que la resolución segura consiste en delegar al default del modelo.
*   **Cambios realizados:**
    *   Eliminado `categoria='OTROS'` (literal hardcodeado) de los dos `Articulo.objects.create()` en `services.py` — línea 676 (`procesar_carga_masiva`) y línea 914 (`procesar_carga_masiva_excel`). Ahora el campo se resuelve vía el `default='OTROS'` del modelo.
    *   Agregada aserción `self.assertEqual(nuevo.categoria, 'OTROS')` en `test_carga_masiva_atomica_y_kardex` para certificar que la categoría default se asigna correctamente.
*   **Estado:** ✅ Completado. 66/66 tests OK.

### TICKET #30-HOTFIX: Reparación de Buscadores de Artículos y Endpoints Faltantes — ✅ COMPLETADO (2026-06-26)
*   **Inicialado:** 2026-06-26
*   **Bug:** Buscador de artículos no funcionaba en `ventas.html` ni `compras.html`. Buscador de clientes no funcionaba en `ventas.html`. Solo funcionaba el buscador de proveedores en `compras.html`.
*   **Causas raíz identificadas:**
    1. **Endpoint `/inventory/catalogo/buscar/` inexistente:** Los templates hacen `fetch('/inventory/catalogo/buscar/?q=...')` pero no había URL ni vista para este endpoint. El artículos buscador 404-silenciosamente.
    2. **Endpoint `/inventory/ventas/validar_stock/<sku>/<almacen>/` inexistente:** `addItemToNote()` y `addItemToPurchase()` validan stock contra este endpoint antes de agregar al carrito. No existía → 404 → bloqueo silencioso.
    3. **Contexto `config` ausente en vistas:** `ventas.html` referencia `{{ config.factor_cobertura }}` y `{{ config.tasa_bcv }}` pero la vista `ventas()` no pasaba `config` al contexto. `compras_view()` tampoco. Sin config, `globalFactor` y `globalBCV` serían undefined.
    4. **Prefijo de URL inconsistente:** Root URL conf montaba inventory en `path('', include(...))` (sin prefijo), pero todos los `fetch()` en templates usaban `/inventory/...` como prefijo. Las URLs resolvían a `/catalogo/buscar/` pero JS llamaba a `/inventory/catalogo/buscar/`.
*   **Cambios realizados:**
    *   **views.py:** Nueva vista `api_buscar_articulos()` (GET, `/catalogo/buscar/?q=`) — busca artículos por SKU o nombre (case-insensitive, `Q(sku__icontains) | Q(nombre__icontains)`) con paginación de 20 resultados. Retorna JSON `{results: [{sku, nombre, precio, tipo, usa_serial}]}`. Precio calculado con `factor_cobertura` del Tenant.
    *   **views.py:** Nueva vista `api_validar_stock()` (GET, `/ventas/validar_stock/<sku>/<almacen_id>/`) — retorna JSON `{stock_disponible: N}` vía `Articulo.get_stock_disponible(almacen)`.
    *   **views.py:** `ventas()` ahora inyecta `config` (`ConfiguracionEmpresa`) en el contexto.
    *   **views.py:** `compras_view()` ahora inyecta `config` en el contexto.
    *   **urls.py:** Añadidas rutas `catalogo/buscar/` y `ventas/validar_stock/<str:sku>/<int:almacen_id>/`.
    *   **Root urls.py:** Cambiado `path('', include(...))` → `path('inventory/', include(...))` para que las URLs resuelvan con prefijo `/inventory/`, coincidiendo con todos los `fetch()` existentes en templates.
    *   **views.py:** Import `from django.db import models as db_models` para `Q` en la búsqueda.
*   **Estado:** ✅ Completado. 71/71 tests OK.

### TICKET #30-POS-INTEGRATION: Saneamiento Transaccional y de Interfaz en Ventas/Compras — ✅ COMPLETADO (2026-06-26)
*   **Iniciado:** 2026-06-26
*   **Alcance:**
    *   **C-01 (Buscadores case-insensitive):** ✅ Ya implementado — `ventas.html` y `compras.html` usan `fetch('/inventory/catalogo/buscar/?q=')` con `.toLowerCase()` en el query (patrón Ticket #29).
    *   **C-02 (Almacenes dinámicos por Tenant):** ✅ `ventas()`, `compras_view()`, `vista_carga_masiva()` y `movimientos_view` en `views.py` ahora filtran `Almacen.objects.filter(empresa=request.empresa, activo=True)`. Eliminado riesgo de mostrar almacenes de otros Tenants en los selectores.
    *   **C-03 (Buscador de contactos + tarjeta resumen):** ✅ Reemplazado `<select>` plano por input buscador + dropdown flotante en `ventas.html` (clientes) y `compras.html` (proveedores). `data-identificacion`, `data-telefono`, `data-direccion` inyectados vía `clientDataset`/`providerDataset` JS arrays. Tarjeta resumen dinámica con nombre, RIF, teléfono y dirección al seleccionar contacto.
    *   **C-04 (Proxy Models Cliente/Proveedor):** ✅ `ClienteManager(EmpresaManager)` y `ProveedorManager(EmpresaManager)` con `get_queryset().filter(tipo=)` automático. Proxy models `Cliente`/`Proveedor` en `models.py` con `save()` que fuerza tipo. Admin segregado: `ClienteAdmin` y `ProveedorAdmin` con `get_queryset().filter(tipo=)`. `ContactoAdmin` registrado con `has_module_permission=False` (oculto del índice, disponible para autocomplete).
    *   **C-05 (Observaciones en compras):** ✅ Campo `observaciones` añadido a `DocumentoCompra`. Textarea en `compras.html`. API `registrar_compra_api` captura y pasa `observaciones`. Servicio `registrar_compra_proveedor()` acepta y persiste parámetro. `NotaEntrega.observaciones` ya persistía desde Ticket #21.
    *   **Migración:** `0007_add_observaciones_to_documento_compra` (proxy models + campo observaciones).
    *   **Tests:** `TestProxyModelsYObservaciones(TransactionTestCase)` — 5 tests:
        1. `test_cliente_proxy_filtro_tipo` — Cliente.objects solo retorna CLIENTE, Proveedor.objects solo retorna PROVEEDOR.
        2. `test_cliente_proxy_save_autoset_tipo` — `Cliente.save()` fuerza `tipo='CLIENTE'`.
        3. `test_proveedor_proxy_save_autoset_tipo` — `Proveedor.save()` fuerza `tipo='PROVEEDOR'`.
        4. `test_observaciones_nota_entrega_persiste` — `procesar_venta(observaciones='...')` persiste en `NotaEntrega`.
        5. `test_observaciones_documento_compra_persiste` — `registrar_compra_proveedor(observaciones='...')` persiste en `DocumentoCompra`.
*   **Estado:** ✅ Completado. 71/71 tests OK.

### TICKET #29-CATALOG-BUGFIX: Saneamiento de Buscador Case-Insensitive y Triple Token Cambiario — ✅ COMPLETADO
*   **Iniciado:** 2026-06-26
*   **Alcance:** Forzar `.toLowerCase()` en el DOM del buscador. Reestructurar `views.py` y `catalogo.html` para inyectar tres atributos `data-precio` independientes, permitiendo el desglose exacto de `$[PRECIO_USD]`, `$[PRECIO_BCV]` y `$[PRECIO_BS]`.
*   **Bug 1 (Búsqueda):** `filterProducts()` convertía el query a minúsculas pero no el SKU del dataset → "a2lt" no encontraba "A2LT-TEL-005".
*   **Bug 2 (Tokens):** Solo 2 capas (`data-precio-usd` = ajustado, `data-precio-bcv` = bolívares). Falta la capa base (`precio_divisa`) para `$[PRECIO_USD]`.
*   **Cambios realizados:**
    *   **views.py:** Agregado `'precio_divisa': a.precio_divisa` al contexto de `catalogo()`.
    *   **catalogo.html (data-attributes):** 3 capas en card y 3 botones de copia:
        *   `data-precio-base` = `precio_divisa` (catálogo puro, sin factor)
        *   `data-precio-ajustado` = `precio_usd_ajustado` (con factor_cobertura)
        *   `data-precio-bs` = `precio_bs_bcv` (bolívares)
    *   **catalogo.html (`data-nombre`):** Removido `|lower` del template — la normalización ahora es exclusivamente en JS.
    *   **catalogo.html (JS filterProducts):** `(card.dataset.sku || '').toLowerCase()` y `(card.dataset.nombre || '').toLowerCase()` antes del `.includes()`.
    *   **catalogo.html (JS tokens):** `updateCrossSellingOutput()` y `copyToClipboard()` reemplazan 6 tokens:
        *   `$[PRECIO_USD]` → base, `$[PRECIO_BCV]` → ajustado, `$[PRECIO_BS]` → bolívares (nuevos)
        *   `[Precio_USD]` → base, `[Precio_BCV]` → ajustado, `[Precio_Bs]` → bolívares (legacy)
*   **Mapeo de tokens:**
    | Token | Capa | Valor |
    |---|---|---|
     | `$[PRECIO_USD]` | Base | `precio_divisa` (sin factor) |
     | `$[PRECIO_BCV]` | Ajustado | `precio_usd_ajustado` (× factor_cobertura) |
     | `$[PRECIO_BS]` | Bolívares | `precio_bs_bcv` (ajustado × tasa_bcv) |
 *   **Estado:** ✅ Completado. 66/66 tests OK.

---

### ITERACIÓN 1.1.0 — Emisión NE/Factura, Compras Avanzadas, Fichas de Artículos (2026-07-10 → 2026-07-13)

*   **Iniciado:** 2026-07-10
*   **Commits:** `66e3aba`, `712ba8c`, `08e8ada`, `487a525`, `c470093`
*   **Tests:** 157 (1.0.0) → 234 (1.1.0). +77 tests.

### TICKET #14-EMISION-NE: Emisión de Notas de Entrega / Facturas con Snapshots de 4 Precios (Fases N1-N5) — ✅ COMPLETADO
*   **Iniciado:** 2026-07-10
*   **Alcance:**
    *   **N1 (Modelos):** `NotaEntrega` ampliado con `tipo_documento` (`NOTA_ENTREGA` | `FACTURA`), `numero_factura` (opcional para NE, obligatorio para FACTURA, único por empresa), `iva_check` (auto), `iva_total`, `descuento_global` (0-100 %), `numero_nota` con formato `{prefijo}-{numero:08d}`. `DetalleNotaEntrega` con **4 snapshots** de precio: `precio_base`, `precio_ajustado`, `precio_directo_bcv`, `precio_ajustado_bcv` + `iva_porcentaje` + `descuento_aplicado` individual.
    *   **N1 (Config):** `ConfiguracionEmpresa` añade `prefijo_nota_entrega` ('NE' default), `correlativo_inicial_nota` (1), `ivas_disponibles` (JSONField lista: [16, 8, 0]).
    *   **N2 (Service):** `procesar_venta` ampliado con `tipo_documento` y `numero_factura`. Snapshot de `tasa_mercado_aplicada` adicionado. Validación: FACTURA sin `numero_factura` → ValueError. `descuento_global` fuera de rango 0-100 → ValueError.
    *   **N3 (UI):** `ventas.html` con radio NOTA_ENTREGA/FACTURA, input `numero_factura` condicional, input `note-discount-percent`, sección de totales con label "IVA:".
    *   **N4 (Interlock):** `confirm-sale-btn` deshabilitado si FACTURA y `#invoice-ref` vacío. Handler `enableConfirmIfFacturaReady()` con `oninput`.
    *   **N5 (PDF):** `vista_detalle_nota` muestra totales + IVA + descuento condicional. `generar_pdf_nota` (reportlab A4 portrait) con encabezado: SKU, nombre, cantidad, 4 precios, IVA, descuento. URLs `/ventas/<id>/` (detalle) y `/ventas/<id>/pdf/` (descarga).
    *   **Migración:** `0010_alter_notaentrega_unique_together_and_more`.
*   **Tests:** 17 nuevos (`TestModelosNotaEntregaFaseN1` 8 + `TestProcesarVentaN2` 9). Suite 200 → 217.
*   **Estado:** ✅ Completado.

### TICKET #15-COMPRAS-AVANZADAS: Compras con 4 Snapshots de Costo + IVA + Descuento + Seriales (Fases C1-C3) — ✅ COMPLETADO
*   **Iniciado:** 2026-07-11
*   **Alcance:**
    *   **C1 (Modelos):** `DocumentoCompra` con correlativo automático por empresa via signal `create_tenant_defaults` (`Max('numero')+1`). `DetalleDocumentoCompra` con **4 snapshots** de costo: `costo_directo`, `costo_ajustado`, `costo_directo_bcv`, `costo_ajustado_bcv` + `iva_porcentaje` + `descuento_aplicado`. Soporte `seriales` (lista de IMEI/serial traceables).
    *   **C1 (Service):** `registrar_compra_proveedor` extendido con 2do parámetro `lista_items=[{articulo_sku, cantidad, costo, iva_porcentaje, descuento, seriales}]`. Validación multi-tenant de FKs (almacen, proveedor, artículo, seriales). Snapshot de tasas al crear documento.
    *   **C3 (UI):** `compras.html` con UI completa: tabla de items + IVA row + descuento row + totales con descuento condicional. Handler `processPurchase()` con `escapeHtml()`. Botones款项 del proveedor dropdown + tarjet residumen.
    *   **C3 (Vistas):** `vista_detalle_compra` muestra totales + bloque de descuento condicional. `generar_pdf_compra` (reportlab A4 portrait). URLs `/compras/<id>/` (detalle) + `/compras/<id>/pdf/` (descarga).
    *   **Migraciones:** `0011_detallecompra_iva_porcentaje_descuento_and_more`, `0012_documento_compra_serials_and_more`.
*   **Tests:** 18 nuevos (TestRegistrarCompraProveedorMultiTenant + snapshots). Suite 213 → 231.
*   **Estado:** ✅ Completado.

### TICKET #16-AUDITORIA-VC: Auditoría Ventas/Compras — Corrección de Críticos, Medios y Bajos — ✅ COMPLETADO
*   **Iniciado:** 2026-07-12
*   **Alcance:** Auditoría forense completa de los módulos N1-C3. 11 hallazgos (4 críticos, 5 medios, 2 bajos) corregidos.
*   **Hallazgos críticos corregidos:**
    *   **C1 (Bug correlativo):** `Max('id')` en cálculo de correlativo de `DocumentoCompra` (generaba saltos). Eliminado; `DocumentoCompra.save()` usa `Max('numero')+1` filtrado por empresa.
    *   **C2 (Leak multi-tenant):** 4 vistas (`vista_detalle_nota`, `generar_pdf_nota`, `vista_detalle_compra`, `generar_pdf_compra`) usaban `get_object_or_404(Modelo, pk=id)` sin filtrar `empresa_id`. Corregido con `get_object_or_404(Modelo, pk=id, empresa_id=request.session.get('empresa_id'))`.
    *   **C3 (XSS en JS):** 26 sinks de `innerHTML` sin escape en `ventas.html` (13) y `compras.html` (13). Añadido helper JS `escapeHtml()` en ambos templates. Sinks escapados: `renderClientDropdown`/`renderProviderDropdown`, `filterSaleItem`/`filterPurchaseItem`, `renderNoteItems`/`renderPurchaseItems`, `renderSerialsPanel`/`renderPurchaseSerialsPanel`.
    *   **C4 (HTML roto):** Tag `<h-sm">` malformado en `nota_detalle.html` (línea 139 original) eliminado.
*   **Hallazgos medios corregidos:**
    *   **M1 (Descuento no aplicado):** `descuento_global` se persistía pero no se reflejaba en los totales mostrados en las 4 vistas/PDFs y 2 templates de detalle. Añadido bloque condicional `{% if monto_descuento_usd and monto_descuento_usd > 0 %}` en los 6 lugares.
    *   **M2 (Label IVA incorrecto):** Labels "IVA (16%)" en `ventas.html:233` y `compras.html:256` (el IVA ahora es configurable portenant y por artículo). Cambiado a "IVA:".
    *   **M5 (Doble submit posible):** Botones `confirm-*-btn` permitían doble submit durante fetch asíncrono. Añadido disable + spinner con restore en `.then()`/`.catch()`.
    *   **M7 (Variable muerta):** `iva_total_bs` en `services.py` calculaba descuento doble sobre IVA en Bs pero nunca se persistía. Eliminado.
    *   **M8 (Total Bs. descuadrado):** `total_bs_neto` en `vista_detalle_nota` y `vista_detalle_compra` usaban fórmula simplificada sin tomar en cuenta snapshots individuales de cada detalle (`factor_desc`, `cobertura`, `tasa_bcv`). Alineado con fórmula `((total_bs * factor_desc) + total_iva_bs_neto)`.
*   **Hallazgos bajos corregidos:**
    *   **B1 (Código muerto + HTML):** Eliminados `note-discount-usd`, `purchase-discount-usd`, `lastCorrelative`, `iva_porcentaje` duplicado en `compras.html:503-505`. `</section>` añadido en `ventas.html` y `compras.html`. Balance HTML verificado: 50/50, 53/53, 28/28, 29/29 divs, 1/1 sections.
    *   **B4 (Error silencioso):** `processSale` y `processPurchase` sin `if (!r.ok)` guard. Añadido guard y `.catch()` mejorado con mensaje de error al usuario.
*   **Limpieza:** Eliminados 9 archivos debug temporales (`check_*.py`, `fix_*.py`, `add_tests.py`, `show_context.py`) + `__pycache__`.
*   **Tests:** 3 tests actualizados con `request.session = {'empresa_id': self.empresa.pk}` para simular sesión en llamadas directas a vistas protegidas.
*   **Estado:** ✅ Completado. Commit `c470093`.

### TICKET #17-FICHAS-ARTICULOS: Tokens de Variables de Precio + Toolbar de Inserción con Caret Tracking — ✅ COMPLETADO
*   **Iniciado:** 2026-07-13
*   **Alcance:** Resolver el problema de "no actualizar mensajes cada vez que cambien precios/tasas". 4 variables dinámicas para redactar mensajes de mercadeo en `social_quick` y `social_cross` que se sustituyen al mostrar/copiar.
*   **Tokens implementados:**
    | Token | Cálculo en el catálogo (al mostrar) |
    |---|---|
    | `$[PRECIO_USD]` | `precio_divisa` (USD base) |
    | `$[PRECIO_BCV]` | `precio_divisa × factor_cobertura` |
    | `$[PRECIO_BS_BASE]` | **`precio_divisa × tasa_bcv`** (sin factor — NUEVO) |
    | `$[PRECIO_BS]` | `precio_divisa × factor × tasa_bcv` |
*   **Cambios realizados:**
    *   **Backend (`views.py`):** `vista_catalogo` añade `precio_bs_base = (precio_usd * tasa_bcv).quantize(Decimal('0.01'))` al iterable `articulos_con_precios`. Sin migración (cálculo en vivo).
    *   **Catálogo (`catalogo.html`):** atributo `data-precio-bs-base` añadido en tarjeta del artículo (1) + 7 botones de copia (3 colapsados + 4 expandidos). La función `copyToClipboard()` y `updateCrossSellingOutput()` añaden `.replaceAll('$[PRECIO_BS_BASE]', pBsBase).replace(/\[Precio_BS_BASE\]/g, pBsBase)`. Comentarios actualizados.
    *   **Formulario Artículos (`articulos.html`):** 2 toolbars (una sobre `#form-p-cross`, otra sobre `#form-p-quick`) con 4 botones cada una:
        *   💵 USD — `$[PRECIO_USD]`
        *   🛡️ BCV — `$[PRECIO_BCV]`
        *   ⚡ Bs.Base — `$[PRECIO_BS_BASE]`
        *   🛡️ Bs.Ajust. — `$[PRECIO_BS]`
    *   **JS `injectToken(textareaId, token)`:** lee `selectionStart`/`selectionEnd` del textarea, reconstruye el valor `texto[:start] + token + texto[end:]` (sobrescribe selección si existe, si no inserta en cursor), posiciona el caret después del token con `setSelectionRange(start + token.length, ...)`, mantiene el foco, dispara `Event('input')` al final. **NO hace fetch al servidor**: el texto se persiste literal al guardar con `saveProduct()`.
    *   **Ficha Técnica (`#form-p-ficha`):** SIN toolbar (es para datos técnicos del equipo, no incluye precios).
    *   **Help text actualizado:** menciona los 4 tokens disponibles en el párrafo explicativo bajo `#form-p-quick`.
*   **Tests (21 nuevos en 4 clases):**
    *   `TestCatalogoPreciosCuadruple` (3) — verifica cálculo de los 4 precios (USD=10, ajustado=15, Bs.base=400, Bs.ajustado=600 sin solaparse; caso borde factor=1).
    *   `TestCatalogoTemplateTokens` (5) — verifica atributos `data-precio-bs-base` en tarjeta y botones + sustitución JS del 4to token + compatibilidad legacy + no-romper tokens existentes.
    *   `TestArticulosToolbarTokens` (10) — 2 toolbars, 4 botones por toolbar (8 llamadas `injectToken`), función JS definida, usa selectionStart/End, restaura foco, no hace fetch, menciona 4 tokens en help, ficha técnica sin toolbar.
    *   `TestArticulosToolbarRender` (3) — vista `/articulos/ renderiza 2 toolbars + 8 injectToken + define función + menciona PRECIO_BS_BASE.
*   **Tests suite:** 231 → 234 tests (3 nuevos del módulo + 18 ya contabilizados en C23).
*   **Documentación formal:** ADR-25 (tokens literales) + ADR-26 (toolbar caret tracking sin servidor).
*   **Estado:** ✅ Completado. Commit `c470093`.

---

### Resumen 1.1.0

*   **Commits:** `66e3aba` (N1+N2), `712ba8c` (N3+N4+N5), `08e8ada` (C1), `487a525` (C3), `c470093` (Fichas + Auditoría).
*   **Migraciones:** 0010 (NE snapshots), 0011 (DetalleDocumentoCompra extendido), 0012 (seriales PDFs).
*   **Tests:** 234 OK en ~151s.
*   **Modelos nuevos:** 1 (`DetalleDocumentoCompra`).
*   **Modelos ampliados:** `NotaEntrega` (+`tipo_documento`, `numero_factura`, `iva_check`, `iva_total`, `descuento_global`, `tasa_mercado_aplicada`), `DetalleNotaEntrega` (+4 precios +IVA +descuento), `DocumentoCompra` (+`tipo_documento`, `observaciones`), `DetalleDocumentoCompra` (+4 costos +IVA +descuento), `ConfiguracionEmpresa` (+`prefijo_nota_entrega`, `correlativo_inicial_nota`, `prefijo_nota_compra`, `correlativo_inicial_compra`, `ivas_disponibles`), `Articulo` (+`iva_porcentaje` default 16).
*   **Vistas nuevas:** `vista_detalle_nota`, `generar_pdf_nota`, `vista_detalle_compra`, `generar_pdf_compra`.
*   **Templates nuevos:** `nota_detalle.html`, `compra_detalle.html`.
*   **Templates ampliados:** `ventas.html` (radio NE/FACTURA + descuento + escapeHtml + spinners), `compras.html` (UI completa + escapeHtml + spinners), `catalogo.html` (+`data-precio-bs-base` + nuevo token), `articulos.html` (+2 toolbars + `injectToken` JS).
---

### ITERACIÓN 1.1.1 — Refinamiento O1/O2/O3 (2026-07-13)
*   **Iniciado:** 2026-07-13
*   **Commits:** (este commit).
*   **Tests:** 234 → 247 (+13). Suite corre en ~160s.
*   **Migraciones:** 0013 (tipo_documento 3-opciones en DocumentoCompra).
*   **Resumen breve:**
    *   **O1 — 3 tipos de documento de Compra:** FACTURA_COMPRA (antes predeterminada), NOTA_ENTREGA_PROVEEDOR (recibo), REGISTRO_MENOR (sin doc. físico). Elimina confusión con Nota de Crédito y Orden de Compra obsoletas.
    *   **O2 — IVA individual por línea (PDT):** cada ítem del carrito (ventas/compras) lleva su propio iva_porcentaje configurable via <select> por línea. Backend procesar_venta y egistrar_compra_proveedor respetan el override sobre Articulo.iva_porcentaje.
    *   **O3 — Notas de Crédito se separan como módulo aparte** (ver TICKET #18-NC abajo).
*   **DoD (DoR):**
    *   [x] Backend acepta las 3 nuevas opciones + rechaza choices viejos.
    *   [x] Columna IVA % <select> en grilla de entas.html y compras.html.
    *   [x] ivas_disponibles_json inyectado por vista (fallback [16, 8, 0] si config vacío).
    *   [x] Grilla factura mixta 16%/8%/0% persiste y se desglosa en vista/PDF (tests OK).
    *   [x] NOTA_CREDITO_COMPRA y ORDEN_COMPRA deprecadas (TICKET #18-NC).
    *   [x] Tests O1 + O2 (13 tests) verdes; 247 tests totales.
    *   [x] CHANGELOG 1.1.1 + OPERACION ampliado + README actualizado.

---

### TICKET #18-NC: Módulo de Notas de Crédito (Devoluciones de Mercancía) 📌 PLANIFICADO (2026-07-13)
*   **Iniciado:** 2026-07-13
*   **Origen:** Observación O3 del cliente en iteración 1.1.1 — las Notas de Crédito son devoluciones **totales o parciales** de uno o varios documentos de entrada (NotaEntrega/Factura en ventas o DocumentoCompra en compras). Requieren referenciar el documento original, listar items a devolver, generar contramovimientos de kardex y opcionalmente liberar seriales. No caben en un radio button de Compras; deben ser módulo aparte.
*   **Alcance propuesto:**
    *   **Sub A (Backend):**
        *   Modelos NotaCredito y DetalleNotaCredito (FK al documento original NotaEntrega o DocumentoCompra + 	ipo_origen string 'VENTA'/'COMPRA' + cantidades_devueltas por item).
        *   procesar_devolucion_venta(venta_id, items_a_devolver[], motivo, usuario=None, empresa_id=None) en services.py con @transaction.atomic + select_for_update.
        *   procesar_devolucion_compra(compra_id, items_a_devolver[], motivo, ...) análoga.
        *   Si aplica, liberar_serial (status: 'VENDIDO' → 'DISPONIBLE'; 'ANULADO_COMPRA' → estado original).
    *   **Sub B (Form Wizard UI):**
        *   Nueva URL /notas-credito/ + plantilla con wizard de 4 pasos:
            1. Seleccionar origen (Venta o Compra).
            2. Buscar y elegir documento (autocompleta por #doc o cliente/proveedor).
            3. Seleccionar items a devolver (grilla con checkbox por línea + cantidad slider 1..cantidad_vendida).
            4. Confirmar motivo + estado (ANULADO_TOTAL o DEVOLUCION_PARCIAL).
    *   **Sub C (Reverso + Kardex):**
        *   concepto_kardex='DEVOLUCION_VENTA' (entrada) o 'DEVOLUCION_COMPRA' (salida).
        *   Reingreso de stock al almacén original del documento.
        *   Auditoría de motivo en motivo_nota_credito de NotaCredito.
    *   **Sub D (Vista + PDF):**
        *   /notas-credito/<id>/ con detalle + /notas-credito/<id>/pdf/.
        *   Link desde /reversos/ hacia la NC resultante.
    *   **Sub E (Estado del documento original):**
        *   Cuando NC > 0 sobre NotaEntrega o DocumentoCompra, agregar campo sin_devolver_total calculado en el detalle (cantidad_vendida − cantidad_devuelta_NC) para listar devoluciones parciales consecutivas.
*   **DoR (sin implementar):**
    *   [ ] Modelos NotaCredito y DetalleNotaCredito con migración.
    *   [ ] procesar_devolucion_venta y procesar_devolucion_compra con rollback limpio.
    *   [ ] 8-10 tests (TransactionTestCase): rollback si motivo vacío, NC total vs parcial, seriales liberados, kardex DEVOLUCION_*, trazabilidad desde origen, multi-tenant.
    *   [ ] UI wizard /notas-credito/ con 4 pasos.
    *   [ ] Vista detalle + PDF A4 portrait.
    *   [ ] Conexión con /reversos/ para ver historial de NCs por documento origen.
*   **Estado:** 📌 **PLANIFICADO**. Iteración 1.1.1 anterió la elección 'NOTA_CREDITO_COMPRA' del radio de Compras; ahora hay que construir el módulo completo en una iteración futura.
