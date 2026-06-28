# Plan de Tickets de Desarrollo de Software (Master Implementation Plan) - A2LT Stock

Este documento contiene las especificaciones técnicas rigurosas, arquitectura de datos y criterios de aceptación para la implementación completa del sistema. Los agentes de programación deben ejecutar estos tickets de forma estrictamente secuencial, manteniendo la inmutabilidad contable, el aislamiento de entornos y la actualización obligatoria del backlog al inicio y cierre de cada tarea.

---

## TICKET #1: Inicialización del Proyecto y Modelos de Datos Core (Esquema Completo)

### Descripción
Configurar el entorno inicial de Django aislado en un entorno virtual con SQLite y mapear la totalidad de la arquitectura de datos relacional para evitar migraciones destructivas en fases avanzadas.

### Especificaciones Técnicas
1. **Aislamiento del Entorno:**
   * Crear un entorno virtual de Python llamado `.venv` en la raíz: `python -m venv .venv`.
   * Configurar el archivo `.gitignore` excluyendo `.venv/`, `db.sqlite3` y carpetas `__pycache__/`.
2. **Instalación Base:**
   * Instalar Django, openpyxl y requests dentro del entorno virtual. Generar `requirements.txt`.
3. **Modelado de Datos (`inventory/models.py`):**
   * `ConfiguracionSistema`: Modelo Singleton (fuerza `pk=1`). Campos: `nombre_comercial`, `rif_negocio`, `direccion_fisica`, `telefono_contacto`, `correo_contacto`, `tasa_bcv`, `factor_cobertura`, `margen_global`, `descuento_global`, `api_url`, `http_method`, `response_selector`.
   * `Almacen`: `id`, `nombre`, `es_principal` (BooleanField).
   * `Articulo`: `sku` (PK), `codigo_proveedor`, `nombre`, `categoria` (Choices), `tipo` (FISICO/COMBO), `costo` (DecimalField), `precio_divisa` (DecimalField), `margen_ind`, `descuento_ind`, `cobertura_ind`, `descripcion`, `ficha_tecnica`, `social_quick`, `social_cross`, `activo` (BooleanField, default=True para soft-delete).
   * `InventarioAlmacen`: `articulo` (FK), `almacen` (FK), `cantidad_disponible` (DecimalField, default=0.00). Restricción `unique_together = ('articulo', 'almacen')`.
   * `RecetaCombo`: `combo` (FK a Articulo de tipo COMBO), `componente` (FK a Articulo de tipo FISICO), `cantidad_requerida` (DecimalField).
   * `Contacto`: `identificacion` (PK), `nombre`, `tipo` (CLIENTE/PROVEEDOR), `telefono`, `correo`, `red_social`, `direccion`, `rif` (null=True), `nombre_asesor` (null=True).
   * `MovimientoKardex`: `id`, `fecha_hora`, `articulo` (FK), `almacen` (FK), `tipo` (ENTRADA/SALIDA), `cantidad` (DecimalField), `concepto` (TextField), `lote_carga` (UUID, null=True), `nota_entrega` (FK, null=True).
   * `AuditoriaTasa`: `id`, `fecha_hora`, `tasa_bcv`, `tasa_mercado`, `factor_cobertura`, `fuente` (MANUAL/API).
   * `NotaEntrega`: `id` (Autoincremental), `correlativo` (CharField, único), `fecha_emision`, `cliente` (FK a Contacto), `tasa_bcv_aplicada`, `factor_cobertura_applied`.
   * `DetalleNotaEntrega`: `id`, `nota_entrega` (FK), `articulo` (FK), `cantidad`, `precio_unitario_usd`, `precio_bs_final`.
4. **Capa de Control Administrativo (`inventory/admin.py`):**
   * Registrar todos los modelos. Bloquear inserción/edición manual en `InventarioAlmacen` y `MovimientoKardex` mediante `has_add_permission=False` y `has_change_permission=False`.

### Criterios de Aceptación (DoD)
- [ ] Entorno virtual activo e instalaciones verificadas en `requirements.txt`.
- [ ] Ejecución limpia de `makemigrations` y `migrate` sin errores de claves foráneas o circulares.
- [ ] Django Admin operativo protegiendo el Kárdex en modo lectura exclusiva.

---

## TICKET #2: Lógica del Kárdex, Transacciones y Combos Dinámicos

### Descripción
Implementar el motor lógico de inventario en la capa de servicios garantizando atomicidad transaccional pura y el cálculo en tiempo real de combos virtuales mediante la receta física.

### Especificaciones Técnicas
1. **Motor Transaccional (`inventory/services.py`):**
   * Desarrollar `registrar_movimiento(articulo, almacen, tipo, cantidad, concepto, **kwargs)`. Agregar decorador `@transaction.atomic`.
   * Implementar bloqueo pesimista con `select_for_update()` al evaluar el stock.
   * Si `tipo == 'SALIDA'`, verificar que `cantidad_disponible >= cantidad`. Si es insuficiente, levantar `ValueError` para forzar Rollback inmediato. No permitir saldos negativos.
2. **Cálculo Dinámico de Combos (`inventory/models.py` -> `Articulo`):**
   * Desarrollar el método `get_stock_disponible(almacen=None)`. 
   * Si el tipo es `FISICO`, sumar los registros en `InventarioAlmacen`.
   * Si el tipo es `COMBO`, ejecutar importación lazy de `services.calcular_stock_combo` evaluando la fórmula:
     $$\text{Stock Combo} = \min_{i} \left( \left\lfloor \frac{S(a_i)}{q_i} \right\rfloor \right)$$
3. **Desagregación de Combos:**
   * Desarrollar `procesar_salida_combo(combo, almacen, cantidad_combos, nota_entrega)`. Debe descontar de forma atómica cada componente físico de la receta multiplicando `cantidad_combos * cantidad_requerida`.

### Criterios de Aceptación (DoD)
- [ ] Suite de pruebas unitarias (`TransactionTestCase`) con 14 tests en verde.
- [ ] Verificación de Rollback completo si un componente de la receta se queda sin stock durante la salida del combo.

---

## TICKET #3: Carga Masiva Tolerante a Fallos y Gestión de Colisiones

### Descripción
Desarrollar el procesador de archivos Excel `.xlsx` para la importación masiva de inventario y catálogo, implementando tolerancia a fallos por fila y persistencia intermedia de conflictos mediante sesiones.

### Especificaciones Técnicas
1. **Validación de Formato:**
   * Función `validar_formato_excel(archivo)`. Rechazar extensiones diferentes a `.xlsx` levantando un `ValueError`. Leer únicamente la hoja activa (`workbook.active`).
2. **Procesamiento de Filas (`services.py` -> `procesar_carga_masiva`):**
   * Columnas fijas: A (SKU), B (Nombre), C (Costo), D (Cantidad), E (Precio_Divisa), F (Almacen).
   * Envolver cada fila en un bloque `try-except`. Si el SKU no existe, crear el artículo. Si el nombre está duplicado con otro SKU, procesar e inyectar advertencia en el log.
   * Si Cantidad es 0 o vacía, actualizar datos base de forma silenciosa sin alterar stock ni generar Kárdex.
3. **Manejo de Colisiones en Sesión HTTP:**
   * Si el SKU existe y Cantidad > 0, aislar el registro en la sesión Django (`request.session`) bajo un `lote_id` (UUID4) y frenar la persistencia de stock de esa fila. Los registros limpios se persisten de inmediato.
4. **Resolución de Conflictos:**
   * `resolver_colision(sku, almacen_id, decision, cantidad_excel, lote_id)`:
     * `SUMAR`: Ejecuta `registrar_movimiento` de ENTRADA.
     * `SUSTITUIR`: Ejecuta SALIDA por el stock actual para dejarlo en 0, y acto seguido una ENTRADA por el valor del Excel.
     * `CANCELAR`: Descarta la fila.

### Criterios de Aceptación (DoD)
- [ ] Suite de 10 tests unitarios verificando aislamiento de errores y flujos de colisión contables en verde.
- [ ] Generación automática del archivo de auditoría `.txt` descargable con el log de incidencias por fila.

---

## TICKET #4: El Acoplamiento de la Piel (Templates Modulares de Django)

### Descripción
Traducir la interfaz gráfica de la maqueta interactiva al motor de plantillas de Django, configurando la ergonomía visual del tema oscuro neutro y llamadas asíncronas para el manejo de modales.

### Especificaciones Técnicas
1. **Layout Base (`inventory/templates/inventory/base.html`):**
   * Configurar barra lateral estática y área `<main>` dinámica bajo Tailwind CSS.
   * Inyectar script bloqueante en el `<head>` para evaluar `localStorage.getItem('a2lt_theme')` antes de pintar el DOM, neutralizando el parpadeo blanco (FOUC).
   * Paleta oscura forzada: `dark:bg-zinc-900` para el lienzo, `dark:bg-zinc-800` para paneles, componentes y tablas. Quedan prohibidos los tonos violetas.
2. **Interfaz de Carga (`carga.html`):**
   * Acoplar zona Drag & Drop con Javascript. Mapear botones `[Sumar]`, `[Sustituir]`, `[Cancelar]` en el modal de colisión. Al hacer clic, desactivar inmediatamente todos los botones del contenedor (`disabled = true`) para neutralizar ráfagas de clics (Race Conditions) y disparar Fetch API hacia el backend.
3. **Catálogo y Redes (`catalogo.html`):**
   * Iterar el catálogo de artículos. Alinear etiquetas `<textarea>` al extremo izquierdo absoluto del archivo HTML para eliminar sangrías físicas del DOM. Aplicar `.trim()` en la lectura de JavaScript para asegurar copias al portapapeles perfectas para redes sociales.

### Criterios de Aceptación (DoD)
- [ ] Verificación en navegador del cambio de tema persistente sin parpadeo blanco intermedio.
- [ ] Copia al portapapeles de fichas técnicas y textos comerciales con alineación de caracteres limpia, libre de tabulaciones basura.

---

## TICKET #5: Módulo de Ventas, Conversión Cambiaria y Notas de Entrega

### Descripción
Implementar el ciclo transaccional de facturación interna, congelando la matemática cambiaria en el momento exacto del asentamiento y construyendo el formato de impresión física.

### Especificaciones Técnicas
1. **Servicio Core (`services.py` -> `procesar_venta`):**
   * Firma: `procesar_venta(cliente_id, lista_items, almacen_id, usuario='')` bajo `@transaction.atomic`.
   * Margen de Seguridad: Validar que `ConfiguracionSistema.tasa_bcv > 0` para blindar el flujo contra excepciones de división por cero.
   * Capturar `tasa_bcv` y `factor_cobertura` (T_mercado / T_bcv) del Singleton y grabarlos directamente en la cabecera del registro `NotaEntrega`.
   * Forzar la asignación a "Cliente Genérico" si no se provee un `cliente_id`.
2. **Persistencia de Líneas de Detalle:**
   * Por cada ítem, evaluar stock real vía `get_stock_disponible()`. Si falla, disparar excepción.
   * Calcular el precio en Bolívares inmutable en el bucle: 
     $$\text{precio\_bs\_final} = \text{precio\_unitario\_usd} \times \text{factor\_cobertura\_aplicado} \times \text{tasa\_bcv\_aplicada}$$
   * Grabar físicamente el resultado en `DetalleNotaEntrega`. Disparar las salidas del Kárdex asociadas al ID de la nota.
3. **Formato de Impresión (`inventory/templates/inventory/ventas.html`):**
   * Desarrollar la vista de impresión inyectando estilos CSS `@media print`. Al activarse el comando de impresión del navegador, ocultar el Sidebar, cabeceras del sistema y fondos, formateando el canvas exclusivamente en blanco y negro sobre dimensiones A4 u 80mm térmico.

### Criterios de Aceptación (DoD)
- [ ] Test unitario que demuestre que una variación posterior en la tasa cambiaria global del Singleton no altera los totales en Bolívares de las Notas de Entrega emitidas en el pasado.
- [ ] Bloqueo y Rollback total si un artículo del carrito de ventas excede las existencias físicas del almacén de origen.

---

## TICKET #6: Motor de Automatización e Integración de Tasas de Cambio (API Sync)

### Descripción
Desarrollar el cliente de integración HTTP y el procesador dinámico de estructuras JSON para actualizar de forma automatizada y segura las variables cambiarias del sistema.

### Especificaciones Técnicas
1. **Lógica del Cliente API (`services.py` -> `sincronizar_tasa_cambio`):**
   * Extraer `api_url`, `http_method` y `response_selector` de la configuración Singleton.
   * Invocar la petición mediante la librería `requests` con un timeout estricto de 5 segundos.
   * **Procesamiento Seguro:** Queda estrictamente prohibido usar `eval()` o `exec()` para resolver el `response_selector`. Implementar un extractor iterativo de llaves basado en notación de puntos (split por `.`) para navegar de forma nativa por el diccionario JSON recuperado.
2. **Asentamiento Cambiario:**
   * Al aislar el valor numérico flotante de la tasa de mercado, abrir un bloque `@transaction.atomic`.
   * Calcular el nuevo Factor de Cobertura ($F_c = T_{mercado} / T_{bcv}$).
   * Actualizar el Singleton e insertar un registro de auditoría inalterable en la tabla `AuditoriaTasa` marcando la fuente como `'API'`.
3. **Controlador Visual:**
   * Crear la ruta `/tasas/sincronizar/` mapeada a una vista que responda un JSON con el estado de la operación. Vincularla mediante un botón de refresco asíncrono en la interfaz del panel de control.

### Criterios de Aceptación (DoD)
- [ ] Prueba unitaria utilizando `unittest.mock` para simular una respuesta de API JSON externa exitosa, validando la mutación del Singleton y el registro en el histórico de auditoría.
- [ ] Control de excepciones implementado: si la API externa experimenta timeout o retorna un error 500, el sistema intercepta el fallo de forma limpia, no altera las tasas actuales y emite una alerta visual en el frontend.

---

## TICKET #7: Motor de Reverso Atómico de Lotes de Carga Masiva

### Descripción
Desarrollar el motor lógico de desinstalación de inventario para deshacer cargas masivas completas basándose en su identificador único de lote, garantizando la integridad histórica del Kárdex.

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