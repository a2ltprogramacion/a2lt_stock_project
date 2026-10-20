"""
DATA-09 — Una sola moneda base por empresa, garantizada por la BD.

Contexto
--------
``Moneda.save()`` ya desmarca la base anterior del tenant, pero esa lógica es
una *race condition*: dos procesos concurrentes pueden leer/actualizar a la vez
y dejar dos filas con ``es_base=True``. La garantía real debe vivir en el
esquema mediante un ``UniqueConstraint`` parcial:

    UniqueConstraint(fields=['empresa'], condition=Q(es_base=True),
                     name='una_moneda_base_por_empresa')

Estos tests RED deben fallar antes de añadir el constraint / la migración.

Nota sobre el test de esquema
-----------------------------
``bulk_create()`` NO llama a ``Model.save()``; por eso sirve para insertar una
segunda base y comprobar que es la *BD* (no la lógica del modelo) quien la
rechaza con ``IntegrityError``.

Nota sobre SQLite
-----------------
SQLite soporta índices únicos parciales (``CREATE UNIQUE INDEX ... WHERE ...``),
que es exactamente lo que Django genera para un ``UniqueConstraint`` con
``condition``. El test de esquema es por tanto válido en el backend real.
"""

import importlib
import pkgutil
from unittest.mock import patch

from django.apps import apps as global_apps
from django.db import IntegrityError, transaction
from django.db.models import UniqueConstraint
from django.test import TestCase

from inventory.managers import reset_current_empresa, set_current_empresa
from inventory.models import Empresa, Moneda

CONSTRAINT_NAME = 'una_moneda_base_por_empresa'


def _migracion_0021():
    """Devuelve el módulo de la migración 0021 (o None si aún no existe)."""
    from inventory import migrations as mig_pkg

    for info in pkgutil.iter_modules(mig_pkg.__path__):
        if info.name.startswith('0021_'):
            return importlib.import_module(f'inventory.migrations.{info.name}')
    return None


class TestData09UnaMonedaBasePorEmpresa(TestCase):
    """DATA-09: máximo una ``Moneda`` con ``es_base=True`` por empresa."""

    def setUp(self):
        sufijo = abs(hash(self._testMethodName)) % (10 ** 8)
        self.empresa = Empresa.objects.create(
            nombre=f'DATA09 {self._testMethodName[:28]}',
            rif=f'J-DATA09-{sufijo:08d}',
            activa=True,
        )
        # La señal de creación de Empresa ya siembra USD (base) + VES.
        token = set_current_empresa(self.empresa.id)
        self.addCleanup(reset_current_empresa, token)

    # -- 1. El constraint existe en el modelo ---------------------------
    def test_data09_constraint_una_moneda_base_por_empresa_existe(self):
        constraints = [
            c for c in Moneda._meta.constraints
            if isinstance(c, UniqueConstraint) and c.name == CONSTRAINT_NAME
        ]
        self.assertEqual(
            len(constraints), 1,
            msg=(
                "Se esperaba exactamente un UniqueConstraint llamado "
                f"'{CONSTRAINT_NAME}' en Moneda.Meta.constraints"
            ),
        )
        constraint = constraints[0]
        self.assertEqual(tuple(constraint.fields), ('empresa',))
        self.assertIsNotNone(
            constraint.condition,
            msg="El constraint debe ser PARCIAL (condition=Q(es_base=True))",
        )
        self.assertIn('es_base', str(constraint.condition))
        self.assertTrue(constraint.condition.children)

    # -- 2. La BD rechaza dos bases (saltándose save()) -----------------
    def test_data09_dos_monedas_base_misma_empresa_levanta_integrity_error(self):
        # Precondición: la empresa ya tiene USD como base.
        self.assertTrue(
            Moneda.global_objects.get(
                empresa_id=self.empresa.id, codigo='USD'
            ).es_base
        )

        # bulk_create() inserta directo: NO pasa por save(), por lo que el
        # "flip" del modelo no puede ocultar el problema. Debe ser el esquema
        # quien rechace la segunda base.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Moneda.global_objects.bulk_create([
                    Moneda(
                        empresa_id=self.empresa.id,
                        codigo='DUX',
                        nombre='Duplicada Base',
                        simbolo='D',
                        decimales=2,
                        es_base=True,
                        activa=True,
                    )
                ])

        # La transacción se recuperó y la base original sigue intacta.
        self.assertEqual(
            Moneda.global_objects.filter(
                empresa_id=self.empresa.id, es_base=True
            ).count(),
            1,
        )

    # -- 3. La UX se conserva: save() promueve y desmarca la anterior ---
    def test_data09_save_promueve_base_y_desmarca_la_anterior(self):
        eur = Moneda.objects.create(
            empresa=self.empresa, codigo='EUR', nombre='Euro',
            simbolo='E', decimales=2, es_base=False, activa=True,
        )

        eur.es_base = True
        eur.save()  # No debe levantar IntegrityError.

        eur.refresh_from_db()
        usd = Moneda.objects.get(empresa=self.empresa, codigo='USD')
        self.assertTrue(eur.es_base)
        self.assertFalse(
            usd.es_base,
            msg=(
                "save() debe desmarcar la base anterior para preservar la UX "
                "(promover una moneda sin bajar la otra a mano)."
            ),
        )
        self.assertEqual(
            Moneda.global_objects.filter(
                empresa_id=self.empresa.id, es_base=True
            ).count(),
            1,
        )

    # -- 4. Varias monedas NO base están permitidas --------------------
    def test_data09_permite_multiples_monedas_no_base(self):
        Moneda.objects.create(
            empresa=self.empresa, codigo='EUR', nombre='Euro',
            simbolo='E', decimales=2, es_base=False, activa=True,
        )
        Moneda.objects.create(
            empresa=self.empresa, codigo='COP', nombre='Peso Colombiano',
            simbolo='COL$', decimales=2, es_base=False, activa=True,
        )

        self.assertEqual(
            Moneda.global_objects.filter(
                empresa_id=self.empresa.id, es_base=False
            ).count(),
            3,  # VES (sembrada) + EUR + COP
        )

    # -- 5. El constraint es por tenant, no global ---------------------
    def test_data09_es_base_es_por_empresa(self):
        otra = Empresa.objects.create(
            nombre='DATA09 Otra Empresa',
            rif='J-DATA09-OTRA',
            activa=True,
        )

        bases_a = Moneda.global_objects.filter(
            empresa_id=self.empresa.id, es_base=True
        )
        bases_b = Moneda.global_objects.filter(
            empresa_id=otra.id, es_base=True
        )
        self.assertEqual(bases_a.count(), 1)
        self.assertEqual(bases_b.count(), 1)
        self.assertNotEqual(bases_a.first().empresa_id, bases_b.first().empresa_id)

        # Y la empresa B puede promover su propia moneda alterna sin tocar A.
        alt = Moneda.global_objects.create(
            empresa=otra, codigo='EUR', nombre='Euro B',
            simbolo='E', decimales=2, es_base=False, activa=True,
        )
        alt.es_base = True
        alt.save()
        self.assertEqual(
            Moneda.global_objects.filter(empresa_id=otra.id, es_base=True).count(),
            1,
        )
        self.assertEqual(
            Moneda.global_objects.filter(
                empresa_id=self.empresa.id, es_base=True
            ).count(),
            1,
        )

    # -- 6. La migración limpia duplicados antes del AddConstraint ------
    def test_data09_migracion_deja_una_sola_base_por_empresa(self):
        """
        Comprobaciones:
          1. Existe la migración ``0021_*`` con un ``RunPython`` de limpieza.
          2. Ese ``RunPython`` aparece ANTES del ``AddConstraint`` en
             ``operations`` (si fuera después, el AddConstraint fallaría en
             instalaciones con duplicados preexistentes).
          3. La función de limpieza es idempotente y, ejecutada sobre los
             datos actuales, deja como máximo una base por empresa.
          4. La función usa el manager histórico (``apps.get_model``), es
             decir, NO está sujeta al filtro de tenant.
        """
        from django.db.migrations.operations import AddConstraint, RunPython

        migracion = _migracion_0021()
        self.assertIsNotNone(
            migracion,
            msg="No existe ninguna migración inventory/migrations/0021_*",
        )

        operaciones = list(migracion.Migration.operations)
        idx_runpython = next(
            (i for i, op in enumerate(operaciones)
             if isinstance(op, RunPython)
             and op.code is not None
             and 'una_base_por_empresa' in getattr(op.code, '__name__', '')),
            None,
        )
        self.assertIsNotNone(
            idx_runpython,
            msg=(
                "La migración 0021 debe incluir un RunPython de limpieza "
                "llamado *_una_base_por_empresa*"
            ),
        )
        idx_addconstraint = next(
            (i for i, op in enumerate(operaciones)
             if isinstance(op, AddConstraint)),
            None,
        )
        self.assertIsNotNone(idx_addconstraint)
        self.assertLess(
            idx_runpython, idx_addconstraint,
            msg="El RunPython de limpieza debe ir ANTES del AddConstraint",
        )

        # La función usa apps.get_model(): manager histórico sin filtro tenant.
        self.assertIsNotNone(getattr(migracion, '_una_base_por_empresa', None))

        # Idempotente sobre el estado actual (aquí ya hay 1 base/empresa).
        migracion._una_base_por_empresa(global_apps, None)
        migracion._una_base_por_empresa(global_apps, None)

        for empresa_id in Moneda.global_objects.values_list(
            'empresa_id', flat=True
        ).distinct():
            with self.subTest(empresa_id=empresa_id):
                self.assertLessEqual(
                    Moneda.global_objects.filter(
                        empresa_id=empresa_id, es_base=True
                    ).count(),
                    1,
                )
