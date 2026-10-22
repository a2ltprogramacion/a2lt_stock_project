"""
DATA-06 — Índice compuesto del kárdex: (articulo, almacen, fecha_hora).

Contexto
--------
Los reportes de kárdex filtran por artículo + almacén + rango de fecha.
Antes de DATA-06, ``MovimientoKardex`` solo tenía los índices implícitos de
las FK (una columna cada uno): el optimizador de SQLite buscaba por
``almacen_id`` y luego filtraba ``articulo_id``/``fecha_hora`` fila a fila
(plan constatado con EXPLAIN QUERY PLAN sobre la BD de desarrollo:

    SEARCH inventory_movimientokardex
    USING INDEX inventory_movimientokardex_almacen_id_37907772 (almacen_id=?)

DATA-06 añade un índice compuesto que cubre el patrón de consulta del
reporte:

    Index(fields=['articulo', 'almacen', 'fecha_hora'],
          name='idx_kardex_fecha_art_alm')

Nota sobre el ORDEN de las columnas (desviación documentada del snippet
de docs/AUDIT_REPORT.md, que proponia fecha_hora primero)
---------------------------------------------------------------------
SQLite solo puede "seek" un prefijo de igualdades seguido de un rango.
Con ``fecha_hora`` liderando, el rango anula el seek de ``articulo``/
``almacen`` y el optimizador SIEMPRE prefiere el equality-seek de los
índices FK implicitos de 1 columna (db_index=True) — el compuesto queda
muerto (constatado con EXPLAIN QUERY PLAN en BD aislada). Con las
igualdades primero, el plan busca con las 3 condiciones:

    SEARCH ... USING COVERING INDEX idx_kardex_fecha_art_alm
    (articulo_id=? AND almacen_id=? AND fecha_hora>? AND fecha_hora<?)

La garantía vive en tres niveles:
1. El modelo lo declara (``MovimientoKardex._meta.indexes``).
2. La migración 0027 lo crea en la BD (operación ``AddIndex``).
3. El optimizador de SQLite lo usa en la consulta patrón del reporte
   (``EXPLAIN QUERY PLAN`` — el optimizador trabaja sin datos: no se
   necesitan filas de kárdex para validar el plan).
"""

import importlib
import pkgutil

from django.db import connection
from django.db.models import Index
from django.test import TestCase

from inventory.models import MovimientoKardex

INDEX_NAME = 'idx_kardex_fecha_art_alm'
# Igualdades (articulo, almacen) primero y rango (fecha_hora) al final:
# es el único orden que el optimizador de SQLite usa para el patrón del
# reporte (con fecha_hora primero prefiere los índices FK de 1 columna).
INDEX_FIELDS = ['articulo', 'almacen', 'fecha_hora']
TABLA = MovimientoKardex._meta.db_table

CONSULTA_REPORTE = (
    f'EXPLAIN QUERY PLAN SELECT id FROM {TABLA} '
    'WHERE articulo_id=1 AND almacen_id=1 '
    "AND fecha_hora BETWEEN '2026-01-01' AND '2026-12-31'"
)


def _migracion_0027():
    """Devuelve el módulo de la migración 0027 (o None si aún no existe)."""
    from inventory import migrations as mig_pkg

    for info in pkgutil.iter_modules(mig_pkg.__path__):
        if info.name.startswith('0027_'):
            return importlib.import_module(f'inventory.migrations.{info.name}')
    return None


class TestData06IndiceKardex(TestCase):
    """DATA-06: índice compuesto (articulo, almacen, fecha_hora) del kárdex."""

    def _explain_query_plan(self, sql):
        """Ejecuta EXPLAIN QUERY PLAN y devuelve la columna detail del plan."""
        with connection.cursor() as cursor:
            cursor.execute(sql)
            return [row[3] for row in cursor.fetchall()]

    # -- 1. (DATA-06) El modelo declara el índice compuesto ---------------
    def test_data06_indice_compuesto_definido(self):
        # Arrange: índices declarados en el Meta del modelo.
        por_nombre = {idx.name: idx for idx in MovimientoKardex._meta.indexes}

        # Assert: existe el índice DATA-06, con sus campos exactos y orden.
        self.assertIn(
            INDEX_NAME, por_nombre,
            msg=f"Falta el índice '{INDEX_NAME}' en MovimientoKardex.Meta.indexes",
        )
        self.assertIsInstance(por_nombre[INDEX_NAME], Index)
        self.assertEqual(list(por_nombre[INDEX_NAME].fields), INDEX_FIELDS)

    # -- 2. (DATA-06) La migración 0027 crea el índice con AddIndex --------
    def test_data06_migracion_crea_indice(self):
        from django.db.migrations.operations import AddIndex

        # Arrange: localizar la migración 0027 por importlib.
        migracion = _migracion_0027()
        self.assertIsNotNone(
            migracion,
            msg='La migración 0027_* (AddIndex de DATA-06) aún no existe',
        )

        # Assert: contiene exactamente un AddIndex con el índice exacto.
        addindexes = [
            op for op in migracion.Migration.operations
            if isinstance(op, AddIndex) and op.index.name == INDEX_NAME
        ]
        self.assertEqual(
            len(addindexes), 1,
            msg=(
                f"Se esperaba exactamente un AddIndex '{INDEX_NAME}' en la "
                f'migración 0027; operaciones encontradas: '
                f'{[type(op).__name__ for op in migracion.Migration.operations]}'
            ),
        )
        self.assertEqual(list(addindexes[0].index.fields), INDEX_FIELDS)

    # -- 3. (DATA-06) El optimizador usa el índice en la consulta patrón --
    def test_data06_sqlite_usa_el_indice_en_consulta_de_reporte(self):
        # Arrange: el proyecto es SQLite (settings.DATABASES); EXPLAIN QUERY
        # PLAN es del optimizador, no requiere filas de kárdex.
        # Nota: connection.vendor reporta 'sqlite' para el backend sqlite3.
        self.assertEqual(connection.vendor, 'sqlite')

        # Act: plan del optimizador para la consulta patrón del reporte.
        plan = self._explain_query_plan(CONSULTA_REPORTE)
        plan_texto = ' | '.join(plan)

        # Assert: el plan resuelve la consulta CON el índice DATA-06
        # (SQLite lo reporta como USING INDEX o USING COVERING INDEX).
        self.assertRegex(
            plan_texto,
            rf'USING (?:COVERING )?INDEX {INDEX_NAME}',
            msg=f'El optimizador NO usó {INDEX_NAME}. Plan: {plan_texto}',
        )
