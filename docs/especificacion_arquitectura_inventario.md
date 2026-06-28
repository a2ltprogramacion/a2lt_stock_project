# Documento de Especificación Funcional y Arquitectura de Software (SRS)
## Sistema Ligero de Gestión de Inventario, Control Cambiario y Social Selling (V1.0)

---

## 1. Introducción y Filosofía de Diseño

### 1.1. Visión del Producto
El sistema está concebido como una herramienta web ágil, precisa y de alto rendimiento, diseñada específicamente para comerciantes y emprendedores que operan en ecosistemas dinámicos de comercio digital y redes sociales (Instagram, WhatsApp, TikTok). 

El diseño se inspira en la robustez y lógica de transacciones de ERPs tradicionales como *Profit Plus 2K12 Administrativo*, pero elimina su complejidad burocrática e interfaces pesadas, reemplazándolas por un flujo de trabajo optimizado para la velocidad y el social selling.

### 1.2. Principios de Arquitectura
*   **Desacoplamiento Estricto:** La capa de datos (persistencia) no se conecta de manera directa o rígida con la interfaz de usuario. Todo cambio de stock pasa por un validador de transacciones.
*   **Sin Modificación Directa de Stock:** Queda estrictamente prohibido alterar el campo `cantidad_disponible` de un artículo mediante operaciones de base de datos directas (`UPDATE` sin auditoría). Cada incremento o decremento debe estar respaldado por un registro en el historial de movimientos (Kárdex).
*   **Diseño Monolítico Limpio:** Desarrollado sobre el framework Python/Django, utilizando inicialmente SQLite para facilitar el despliegue rápido en fase de pruebas locales, con un esquema de base de datos totalmente compatible para migrar sin fricciones a PostgreSQL en fase de producción.

---

## 2. Reglas Cambiarias y Matemática de Costos/Precios

### 2.1. Métodos de Ganancia
El sistema soportará dos metodologías independientes para calcular el precio de venta sugerido a partir del costo del artículo. Ambas variables se configurarán a nivel global y se podrán sobrescribir a nivel individual por artículo:

#### Método Directo (Markup o Margen sobre el Costo)
Aplica un porcentaje multiplicador directo sobre el costo del artículo.
$$P_v = C \times (1 + M_{up})$$
Donde:
*   $P_v$: Precio de Venta
*   $C$: Costo de Adquisición
*   $M_{up}$: Porcentaje de Markup configurado (ej: `0.30` para un 30%).

#### Método Real (Margen de Utilidad Bruta o Margin)
Asegura que el porcentaje de ganancia real se calcule sobre el precio final de venta.
$$P_v = \frac{C}{1 - M_{argin}}$$
Donde:
*   $P_v$: Precio de Venta
*   $C$: Costo de Adquisición
*   $M_{argin}$: Margen de ganancia real deseado (ej: `0.30` para un 30% del precio final).

### 2.2. Manejo de Descuentos
*   **Descuento Global e Individual:** Se definirá un porcentaje de descuento global por defecto. Al crear un artículo, este heredará el descuento global, pero el administrador tendrá la facultad de modificar este valor de forma manual e individual en la ficha técnica del producto.

### 2.3. Dinámica Cambiaria (Caso de Uso: Venezuela)
Para proteger el valor de reposición de la mercancía ante fluctuaciones cambiarias rápidas entre la tasa oficial del Banco Central de Venezuela (BCV) y tasas de referencia del mercado paralelo (ej: Binance P2P), se implementa un **Factor de Cobertura Cambiaria**.

#### Fórmulas de Conversión
1.  **Factor de Cobertura Cambiaria ($F_c$):**
    $$F_c = \frac{T_{mercado}}{T_{bcv}}$$
    Donde:
    *   $T_{mercado}$ es la tasa de referencia informal o de reposición (ej. Binance P2P = `840` Bs/$).
    *   $T_{bcv}$ es la tasa oficial del Banco Central de Venezuela (ej. `600` Bs/$).
    
    *Ejemplo:*
    $$F_c = \frac{840}{600} = 1.4$$

2.  **Precio de Venta Ajustado en USD ($P_{usd\_ajustado}$):**
    Es el precio de venta final en dólares que se le aplicará al cliente si decide pagar utilizando moneda de curso nacional (Bolívares) bajo tasa oficial.
    $$P_{usd\_ajustado} = P_{usd\_divisa} \times F_c$$
    
    *Ejemplo para un artículo con precio en divisas efectivo de $25:*
    $$P_{usd\_ajustado} = \$25 \times 1.4 = \$35$$

3.  **Precio Final en Bolívares Oficiales ($P_{bs\_bcv}$):**
    Monto final que transferirá el comprador al cambio oficial.
    $$P_{bs\_bcv} = P_{usd\_ajustado} \times T_{bcv}$$
    
    *Ejemplo:*
    $$P_{bs\_bcv} = \$35 \times 600 = 21,000 \text{ Bs.}$$

### 2.4. Automatización Cambiaria Futuro-Segura
Para evitar la inyección de código malicioso en tiempo de ejecución, se descarta el uso de scripts directos en base de datos. En su lugar, el sistema contará con un **Motor de Integración API Configurable**:
*   **Estructura de Configuración:** El administrador definirá en el panel de control:
    *   `api_url`: URL del Endpoint de consulta (soporta servicios de terceros, Google Apps Scripts de control personal, o integraciones locales basadas en la lógica de `binance-bcv.py`).
    *   `http_method`: `GET` / `POST`.
    *   `response_selector`: Ruta del formato JSON de respuesta (JSON Path) para extraer el valor numérico exacto de manera dinámica (ej: `data.prices.USDT`).

---

## 3. Control Multi-Almacén y Arquitectura de Datos

### 3.1. Relación Muchos a Muchos
Para garantizar la escalabilidad del sistema desde el día uno, el inventario físico no se registrará de manera directa en la entidad del artículo. Se implementa una tabla intermedia de relaciones:

```
[Artículos] (1) <----> (Milos) [InventarioAlmacen] (Muchos) <----> (1) [Almacenes]
                                       |
                            - cantidad_disponible
                            - ubicacion_estante
```

### 3.2. Reglas de Operación Multi-Almacén
*   **Almacén Principal (Default):** El sistema contará con un almacén base asignado por defecto para agilizar la creación manual de artículos y las importaciones masivas simplificadas.
*   **Trazabilidad Transaccional:** Cada movimiento de inventario (Kárdex) debe estar obligatoriamente vinculado a un ID de Almacén. No se permiten transacciones sin la asignación de un origen o destino físico válido.

---

## 4. Gestión de Combos Virtuales (Bundles)

### 4.1. Filosofía de No Compromiso de Stock
Para evitar congelar inventario que podría venderse de forma separada, los Combos no poseen un stock estático. El stock de un combo es virtual y se calcula dinámicamente según la disponibilidad de sus componentes individuales.

### 4.2. Fórmula de Disponibilidad Dinámica
Dado un combo compuesto por un conjunto de artículos $A = \{a_1, a_2, \dots, a_n\}$, donde cada componente $a_i$ requiere una cantidad específica $q_i$ en la receta, y posee un stock disponible actual $S(a_i)$ en un almacén específico:

$$\text{Stock Disponible del Combo} = \min_{i} \left( \left\lfloor \frac{S(a_i)}{q_i} \right\rfloor \right)$$

#### Ejemplo: Combo "Bomba Solar + Panel Solar"
*   **Bomba Solar** (Componente 1): Stock disponible = `10`, Cantidad requerida en receta = `1`.
*   **Panel Solar** (Componente 2): Stock disponible = `4`, Cantidad requerida en receta = `2`.

*Cálculo de disponibilidad del combo:*
$$\text{Stock Combo} = \min \left( \left\lfloor \frac{10}{1} \right\rfloor, \left\lfloor \frac{4}{2} \right\rfloor \right) = \min(10, 2) = 2 \text{ Combos disponibles}$$

### 4.3. Lógica de Descuento en Venta
Al confirmarse la venta de un combo, el sistema inicia un bloque transaccional atómico (`transaction.atomic` en Django) que descuenta de forma automática e individual las cantidades de cada componente en la receta física. Si la transacción falla en cualquiera de los componentes, todo el proceso de venta se revierte para evitar inconsistencias numéricas.

---

## 5. Motor de Carga Masiva y Gestión de Colisiones

### 5.1. Importación Tolerante a Fallos
El sistema procesará la importación de archivos de Excel de manera parcial. No cancelará la subida completa del lote ante un error puntual en alguna de las filas, sino que procesará las transacciones limpias y aislará los registros inválidos.
*   **Reporte de Errores Descargable:** Al concluir la importación, el sistema proveerá una alerta visible con botones rápidos de:
    *   *Copiar Errores al Portapapeles* (formato plano).
    *   *Descargar Reporte (.txt)* con desglose detallado (ej. `Fila 14: SKU inexistente, Fila 32: El Costo debe ser numérico`).

### 5.2. Flujo de Colisiones de SKU (Lógica Quirúrgica)
Al cargar un archivo masivo con artículos que ya existen en un almacén destino seleccionado, el sistema suspenderá la persistencia y presentará tres opciones de resolución de conflicto:

```
                  [ Conflicto Detectado: SKU Existente ]
                                     |
            +-----------------------+-----------------------+
            |                       |                       |
        [ SUMAR ]              [ SUSTITUIR ]            [ CANCELAR ]
            |                       |                       |
(Incrementa el stock)     (Sustituye stock actual)   (Aborta operación)
            |                       |
     (Registra en Kárdex)     (Kárdex: Salida anterior
                              + Entrada de nuevo valor)
```

#### Reglas de Auditoría en la Base de Datos para Colisiones:
*   **Si el usuario selecciona [Sumar]:** El sistema incrementa el stock actual y genera un registro de movimiento en el Kárdex de tipo "Entrada por Carga Masiva (Suma)" detallando el ID de lote de la carga.
*   **Si el usuario selecciona [Sustituir]:** El sistema realiza un proceso en dos pasos dentro de una sola transacción:
    1.  Genera una transacción de **Salida** para vaciar el stock anterior registrado (ej: "Ajuste de Salida por Sustitución Carga Masiva" por $-X$ unidades).
    2.  Genera una transacción de **Entrada** por el nuevo valor ingresado en el Excel (ej: "Entrada por Sustitución Carga Masiva" por $+Y$ unidades). Esto garantiza que la curva histórica del Kárdex sea matemáticamente exacta y no se salte pasos temporales.

### 5.3. Política de Reversos de Carga Masiva
El sistema permitirá revertir un proceso de carga masiva completo bajo una estricta validación de integridad:
*   **Reversibilidad Permitida:** Solo se podrá ejecutar el reverso de una carga masiva si ninguno de los artículos incluidos en ese lote ha sido afectado por transacciones de venta o ajustes manuales posteriores.
*   **Reversibilidad Bloqueada:** Si un artículo de la carga ya fue afectado por una venta (Nota de Entrega) o un movimiento posterior, el sistema deshabilitará el botón de reverso automático para este lote. El usuario será notificado de que, para proceder, deberá revertir de forma manual los documentos generados posteriormente o, en su defecto, ejecutar un ajuste manual de inventario para corregir las existencias.

---

## 6. Módulo de Social Selling e Interfaz de Usuario

### 6.1. Gestión de Contenido Multi-Propósito por Artículo
Cada artículo contará con tres campos de texto multilínea enriquecidos en su base de datos para interactuar con canales de comunicación rápidos:
1.  **Ficha Técnica Tradicional:** Detalles de especificaciones físicas del artículo.
2.  **Respuesta Rápida de Redes:** Mensaje comercial preformateado que incluye variables de sustitución dinámica como `[Precio_USD]`, `[Precio_BCV]`, `[Nombre_Articulo]`.
3.  **Mensaje de Cross-Selling:** Un extracto comercial corto optimizado para anexarse en bloques consolidados de ofertas masivas.

> [!NOTE]
> Cada uno de estos tres campos contará con un icono de acción rápida para *Copiar al Portapapeles* mediante llamadas directas a la API del navegador.

### 6.2. Generador de Mensajes Consolidados (Cross-Selling)
En la interfaz de usuario se dispondrá de un panel de búsqueda avanzada y filtrado de catálogo.
*   **Mecánica de Uso:** El operador filtra los artículos por categoría o palabras clave, selecciona mediante checkboxes los productos que desea ofertar y presiona el botón maestro "Generar Oferta Consolidada".
*   **Salida de Datos:** El sistema concatena los mensajes de *Cross-Selling* de todos los artículos seleccionados en un único bloque de texto con formato comercial, agregando el encabezado de oferta global y las aclaratorias cambiarias del día preconfiguradas, copiándolo directamente en el portapapeles del dispositivo del operador sin almacenar estructuras adicionales en la base de datos.

---

## 7. Documentos de Salida y Entidades de Soporte

### 7.1. Notas de Entrega (Sin Valor Fiscal)
Para el control interno diario, el sistema generará correlativos numéricos de Notas de Entrega.
*   **Diseño Físico Flexible:** El sistema permitirá la impresión de este documento en formatos limpios y minimalistas, configurando un lienzo libre con coordenadas adaptables para que el usuario pueda imprimir directamente sobre formatos de factura preimpresos que maneje en su negocio físico.
*   **Asignación de Clientes:** Por defecto, el sistema asignará las transacciones a un registro de "Cliente Genérico" mediante un acceso rápido de un solo clic. Sin embargo, mantendrá abierta la opción de registrar la ficha del cliente (Nombre, Teléfono, Correo, Red Social) para consolidar una base de datos destinada a futuras estrategias de marketing directo.

### 7.2. Registro de Proveedores
Se implementará una entidad de base de datos para Proveedores:
*   **Campos:** Nombre de la Empresa, RIF / ID Fiscal, Teléfono de Contacto, Nombre del Asesor de Ventas, Correo Electrónico y registro histórico de Facturas de Compra asociadas a dicho proveedor para control de costos.