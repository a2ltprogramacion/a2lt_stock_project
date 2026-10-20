"""
DATA-10 — Una tasa de cambio vigente por (empresa, par, día), garantizada por la BD.

Contexto
--------
Decisión de producto ratificada (spec P1, 2026-10-20): ``TasaCambio`` guarda
UNA tasa vigente por (empresa, moneda_origen, moneda_destino, fecha). Corregir
la tasa de un día es un UPDATE del registro del día; la trazabilidad de cada
actualización intradía vive en ``AuditoriaTasa`` (donde ya escribe la
sincronización). Antes de este cambio solo existía un índice de consulta
(NO único), por lo que dos procesos podían insertar tasas duplicadas del
mismo par y día.

La garantía vive en el esquema:

    UniqueConstraint(
        fields=['empresa', 'moneda_origen', 'moneda_destino', 'fecha'],
        name='unique_tasa_par_fecha',
    )

El índice de consulta ``Index(fields=['empresa', 'moneda_origen',
'moneda_destino', '-fecha'])`` se CONSERVA (REQ-DATA10-02): el constraint
cubre integridad, el índice cubre performance de las consultas por fecha
descendente (``obtener_tasa``).

Nota sobre el test de esquema
-----------------------------
``bulk_create()`` NO llama a ``Model.save()``; por eso sirve para comprobar
que es la *BD* (no la lógica del modelo) quien rechaza la segunda tasa con
``IntegrityError``.

Nota sobre SQLite
-----------------
En SQLite el mensaje de violación de UNIQUE NO incluye el nombre del índice
(limitación del backend, constatada en EST-11). Por eso este archivo NO hace
asserts sobre el texto del error: solo ``assertRaises(IntegrityError)`` +
verificación de que no quedó fila duplicada.

Nota sobre el seed de la señal
------------------------------
La señal de creación de ``Empresa`` (signals.py) siembra USD (base) + VES y
UNA tasa inicial USD→VES con ``fecha=hoy``. Los tests leen esa fecha del
estado en lugar de asumir "hoy", y el escenario cross-empresa usa una fecha
distinta de la del seed para no colisionar con el seed propio de la otra
empresa (que también es "hoy").
"""

import importlib
import pkgutil
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import UniqueConstraint
from django.test import TestCase

from inventory.managers import reset_current_empresa, set_current_empresa
from inventory.models import Empresa, Moneda, TasaCambio

CONSTRAINT_NAME = 'unique_tasa_par_fecha'
INDEX_DE_CONSULTA = ['empresa', 'moneda_origen', 'moneda_destino', '-fecha']


def _migracion_0026():
    """Devuelve el módulo de la migración 0026 (o None si aún no existe)."""
    from inventory import migrations as mig_pkg

    for info in pkgutil.iter_modules(mig_pkg.__path__):
        if info.name.startswith('0026_'):
            return importlib.import_module(f'inventory.migrations.{info.name}')
    return None


class TestData10TasaCambioUnicaPorDia(TestCase):
    """DATA-10: máximo una ``TasaCambio`` por (empresa, par, día)."""

    def setUp(self):
        sufijo = abs(hash(self._testMethodName)) % (10 ** 8)
        self.empresa = Empresa.objects.create(
            nombre=f'DATA10 {self._testMethodName[:28]}',
            rif=f'J-DATA10-{sufijo:08d}',
            activa=True,
        )
        # La señal de creación de Empresa ya siembra USD (base) + VES y la
        # tasa inicial USD→VES con fecha=hoy (signals.py).
        token = set_current_empresa(self.empresa.id)
        self.addCleanup(reset_current_empresa, token)

        self.usd = Moneda.objects.get(empresa=self.empresa, codigo='USD')
        self.ves = Moneda.objects.get(empresa=self.empresa, codigo='VES')
        self.tasa_seed = TasaCambio.objects.get(
            moneda_origen=self.usd, moneda_destino=self.ves
        )

    # -- 1. (DATA10-01) La BD rechaza la 2a tasa del mismo par y día ------
    def test_data10_bd_rechaza_segunda_tasa_mismo_par_y_fecha(self):
        # Arrange (REQ-DATA10-01): el modelo declara el constraint con sus
        # campos exactos.
        constraints = [
            c for c in TasaCambio._meta.constraints
            if isinstance(c, UniqueConstraint) and c.name == CONSTRAINT_NAME
        ]
        self.assertEqual(
            len(constraints), 1,
            msg=(
                "Se esperaba exactamente un UniqueConstraint llamado "
                f"'{CONSTRAINT_NAME}' en TasaCambio.Meta.constraints"
            ),
        )
        self.assertEqual(
            tuple(constraints[0].fields),
            ('empresa', 'moneda_origen', 'moneda_destino', 'fecha'),
        )

        fecha = self.tasa_seed.fecha

        # Act: bulk_create inserta directo, sin pasar por save(). Si el
        # modelo tuviera lógica de "upsert", no podría ocultar el problema:
        # debe ser el esquema quien rechace la segunda tasa del mismo día.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TasaCambio.global_objects.bulk_create([
                    TasaCambio(
                        empresa=self.empresa,
                        moneda_origen=self.usd,
                        moneda_destino=self.ves,
                        tasa=Decimal('999.000000'),
                        fecha=fecha,
                    )
                ])

        # Assert: no quedó fila duplicada y la original sigue intacta.
        filas = TasaCambio.global_objects.filter(
            empresa_id=self.empresa.id,
            moneda_origen_id=self.usd.id,
            moneda_destino_id=self.ves.id,
            fecha=fecha,
        )
        self.assertEqual(filas.count(), 1)
        self.assertEqual(filas.get().pk, self.tasa_seed.pk)

    # -- 2. (DATA10-02) Fecha distinta sí se permite ----------------------
    def test_data10_fecha_distinta_se_permite(self):
        fecha_distinta = self.tasa_seed.fecha + timedelta(days=1)

        TasaCambio.objects.create(
            empresa=self.empresa,
            moneda_origen=self.usd,
            moneda_destino=self.ves,
            tasa=Decimal('37.000000'),
            fecha=fecha_distinta,
        )

        self.assertEqual(
            TasaCambio.objects.filter(
                moneda_origen=self.usd, moneda_destino=self.ves
            ).count(),
            2,  # seed (hoy) + nueva (mañana)
        )
        self.assertTrue(
            TasaCambio.objects.filter(fecha=fecha_distinta).exists()
        )

    # -- 3. (DATA10-03) Par distinto sí se permite -----------------------
    def test_data10_par_distinto_se_permite(self):
        eur = Moneda.objects.create(
            empresa=self.empresa, codigo='EUR', nombre='Euro',
            simbolo='E', decimales=2, es_base=False, activa=True,
        )

        # MISMA fecha que el seed, par DISTINTO (EUR→VES).
        TasaCambio.objects.create(
            empresa=self.empresa,
            moneda_origen=eur,
            moneda_destino=self.ves,
            tasa=Decimal('40.000000'),
            fecha=self.tasa_seed.fecha,
        )

        self.assertEqual(
            TasaCambio.objects.filter(moneda_origen=eur).count(), 1
        )
        # El seed del par USD→VES sigue intacto.
        self.assertEqual(
            TasaCambio.objects.filter(
                moneda_origen=self.usd, moneda_destino=self.ves
            ).count(),
            1,
        )

    # -- 4. (DATA10-04) Empresa distinta sí se permite --------------------
    def test_data10_empresa_distinta_se_permite(self):
        otra = Empresa.objects.create(
            nombre='DATA10 Otra Empresa',
            rif='J-DATA10-OTRA',
            activa=True,
        )
        # Cada empresa tiene su propia tasa sembrada con fecha=hoy; para
        # probar el MISMO (par, fecha) en dos empresas sin chocar con los
        # seeds propios usamos una fecha distinta de "hoy".
        fecha_compartida = self.tasa_seed.fecha - timedelta(days=1)

        # Empresa A tiene una tasa (USD→VES, fecha_compartida)...
        TasaCambio.objects.create(
            empresa=self.empresa,
            moneda_origen=self.usd,
            moneda_destino=self.ves,
            tasa=Decimal('36.500000'),
            fecha=fecha_compartida,
        )

        # ...y la empresa B puede tener la MISMA tasa del MISMO día.
        usd_b = Moneda.global_objects.get(empresa_id=otra.id, codigo='USD')
        ves_b = Moneda.global_objects.get(empresa_id=otra.id, codigo='VES')
        TasaCambio.global_objects.create(
            empresa=otra,
            moneda_origen=usd_b,
            moneda_destino=ves_b,
            tasa=Decimal('37.000000'),
            fecha=fecha_compartida,
        )

        self.assertEqual(
            TasaCambio.global_objects.filter(
                empresa_id=otra.id,
                moneda_origen_id=usd_b.id,
                moneda_destino_id=ves_b.id,
                fecha=fecha_compartida,
            ).count(),
            1,
        )
        # La fila de A con el mismo (par, fecha) sigue existiendo.
        self.assertTrue(
            TasaCambio.global_objects.filter(
                empresa_id=self.empresa.id, fecha=fecha_compartida
            ).exists()
        )

    # -- 5. (DATA10-05) El índice de consulta se conserva ------------------
    def test_data10_index_de_consulta_se_conserva(self):
        indexes = [
            idx for idx in TasaCambio._meta.indexes
            if list(idx.fields) == INDEX_DE_CONSULTA
        ]
        self.assertEqual(
            len(indexes), 1,
            msg=(
                "REQ-DATA10-02: debe existir exactamente un Index con campos "
                f"{INDEX_DE_CONSULTA} en TasaCambio.Meta.indexes (el "
                "constraint es ADICIONAL, no sustituye el índice de consulta)"
            ),
        )

    # -- 6. La migración añade el constraint -------------------------------
    def test_data10_migracion_anade_constraint(self):
        from django.db.migrations.operations import AddConstraint

        migracion = _migracion_0026()
        self.assertIsNotNone(
            migracion,
            msg="No existe ninguna migración inventory/migrations/0026_*",
        )

        add_constraints = [
            op for op in migracion.Migration.operations
            if isinstance(op, AddConstraint)
        ]
        self.assertEqual(
            len(add_constraints), 1,
            msg="La migración 0026 debe contener exactamente un AddConstraint",
        )
        constraint = add_constraints[0].constraint
        self.assertIsInstance(constraint, UniqueConstraint)
        self.assertEqual(constraint.name, CONSTRAINT_NAME)
        self.assertEqual(
            tuple(constraint.fields),
            ('empresa', 'moneda_origen', 'moneda_destino', 'fecha'),
        )
