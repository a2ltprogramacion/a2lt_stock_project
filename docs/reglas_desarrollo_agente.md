# Reglas de Oro de Desarrollo (Development System Constitution)

Este documento contiene las reglas de ingeniería de software, arquitectura de datos y control de flujos que los agentes autónomos de programación deben cumplir de forma obligatoria y estricta al desarrollar A2LT Stock.

---

## 1. Reglas de Integridad del Kárdex (La Regla Sagrada)

*   **Prohibición de Modificación Directa:** Queda estrictamente prohibido realizar operaciones de actualización directa (`UPDATE` o reasignación manual) sobre el campo `cantidad_disponible` de la relación `InventarioAlmacen` sin un respaldo transaccional.
*   **Trazabilidad Obligatoria:** Todo incremento o decremento en las existencias físicas de cualquier almacén debe estar originado por un registro inalterable en `MovimientoKardex`.
*   **Atomicidad en Base de Datos:** Todo movimiento de inventario, nota de entrega, compra o ajuste debe ejecutarse dentro de un bloque transaccional atómico utilizando el decorador de Django:

```python
from django.db import transaction

@transaction.atomic
def registrar_movimiento(...):
    # Lógica transaccional
```

> [!IMPORTANT]
> Si el registro en el Kárdex falla, el inventario físico no debe ser alterado bajo ninguna circunstancia.

---

## 2. Lógica Dinámica de Combos (Bundles)

*   **No Almacenamiento de Existencias:** Los productos marcados como `tipo = "COMBO"` no poseen un campo de stock estático en la base de datos.
*   **Cálculo Dinámico:** El stock disponible de un combo debe calcularse en tiempo real mediante una consulta que evalúe la disponibilidad de sus componentes en la receta para el almacén seleccionado:

$$\text{Stock del Combo} = \min_{i} \left( \left\lfloor \frac{S(a_i)}{q_i} \right\rfloor \right)$$

Donde:
*   $S(a_i)$ es el stock disponible del componente $a_i$.
*   $q_i$ es la cantidad requerida de dicho componente en la receta.

*   **Desagregación en Venta:** Al emitir una Nota de Entrega que incluya un Combo Virtual, el sistema debe restar automáticamente del stock físico de cada componente las cantidades proporcionales a las unidades vendidas del combo.

---

## 3. Dinámica Cambiaria y Redondeo (Venezuela)

*   **Factor de Cobertura Global e Individual:** El precio de venta ajustado para operaciones en moneda nacional (Bolívares) bajo tasa oficial debe calcularse de manera dinámica utilizando el Factor de Cobertura Cambiaria ($F_c$), priorizando el valor individual del artículo sobre el global configurado en el sistema:

$$P_{usd\_ajustado} = P_{usd\_divisa} \times F_c$$
$$P_{bs\_bcv} = P_{usd\_ajustado} \times T_{bcv}$$

*   **Sincronización API Segura:** El módulo de sincronización automática de tasas de cambio no debe ejecutar código Python crudo desde la interfaz (prohibido el uso de `exec()` o similares). Debe interactuar exclusivamente a través de parámetros seguros de API configurados en el modelo (URL, Método HTTP y Selector JSON Path).

---

## 4. Tolerancia a Fallos en Carga Masiva

*   **Procesamiento Parcial:** La carga masiva desde archivos Excel no debe abortar el lote completo ante errores de formato o SKU inexistentes. Debe guardar todos los registros limpios y aislar las filas defectuosas.
*   **Salida de Auditoría Explicativa:** El sistema debe compilar un reporte detallado (log de incidencias) que identifique la fila del archivo y el error exacto (ej: `Fila 14: SKU inexistente`). Este log debe ser descargable como archivo `.txt` y copiable al portapapeles.
*   **Flujo de Colisiones:** Cuando se cargue un stock de un SKU que ya existe en el almacén de destino, el sistema debe levantar una interrupción de estado y forzar al usuario a decidir entre tres alternativas:
    *   **Sumar:** El nuevo stock se añade de forma aditiva:
        $$Stock_{final} = Stock_{actual} + Stock_{Excel}$$
    *   **Sustituir:** Se elimina el stock previo registrando una salida de ajuste, y se asienta el nuevo valor ingresado en el Excel:
        $$Stock_{final} = Stock_{Excel}$$
    *   **Cancelar:** Aborta el guardado del lote completo sin alterar las bases de datos.

---

## 5. Pruebas Unitarias Obligatorias (Unit Testing)

El agente de programación tiene la obligación de escribir pruebas unitarias automatizadas (`tests.py`) para los siguientes flujos críticos antes de entregar cualquier desarrollo:

1.  Cálculo dinámico del stock de combos virtuales basados en recetas.
2.  Comportamiento transaccional atómico del Kárdex en ventas e inventarios.
3.  Validación de consistencia en el cálculo dinámico de precios ajustados y conversión de tasas oficiales.

---

## 6. Aislamiento del Entorno (Virtual Environments)

*   **Uso Obligatorio de venv:** Queda estrictamente prohibido que el agente de programación instale librerías Python a nivel global del sistema. Todo el desarrollo, pruebas y ejecución local deben ejecutarse estrictamente con el entorno virtual activo (`.venv`).
*   **Sincronización de Dependencias:** Cualquier nueva librería instalada debe registrarse en el archivo `requirements.txt` de inmediato, asegurando que el comando `pip freeze` se ejecute exclusivamente dentro del entorno virtual activo.