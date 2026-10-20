"""
EST-11 — Un solo almacén principal por empresa, garantizado por la BD.

Contexto
--------
El flag ``Almacen.es_principal`` solo se usaba para ordering en vistas, como
default de importaciones masivas y en la siembra (``signals.py`` crea 1
principal por empresa nueva); el admin podía promover un segundo principal y
corromper la invariante "uno solo", sin que nada lo impidiera (``Almacen``
no tenía ``save()`` propio ni constraints en ``Meta``).

La garantía real debe vivir en el esquema (mismo patrón aprobado en DATA-09
para ``Moneda.es_base``):

    UniqueConstraint(fields=['empresa'], condition=Q(es_principal=True),
                     name='un_almacen_principal_por_empresa')

...más un ``save()`` con flip atómico que degrada al principal anterior de
la misma empresa (conserva la UX de "promover" sin reventar con un
``IntegrityError`` crudo).

Diagnóstico de datos reales (2026-10-20) y decisión de producto
---------------------------------------------------------------
La BD de desarrollo tenía UNA empresa ofensora (id=34, "Empresa Demo A2LT")
con dos principales: id=55 'Almacén Principal' (menor pk) e id=56
'Almacen Principal'. Producto decidió conservar id=56 —el principal
*efectivo*: el que ``.first()`` del ordering ``['-es_principal', 'nombre']``
entrega hoy a los defaults de importación— y degradar id=55. Por eso la
migración ``0025_*`` incluye un ``RunPython`` de backfill ANTES del
``AddConstraint``: sin limpieza previa, el constraint reventaría al aplicarse
sobre datos duplicados.

Nota sobre el test de esquema
-----------------------------
``bulk_create()`` NO llama a ``Model.save()``; sirve para comprobar que es la
*BD* (no la lógica del modelo) quien rechaza el segundo principal con
``IntegrityError``.

Nota sobre SQLite
-----------------
SQLite soporta índices únicos parciales (``CREATE UNIQUE INDEX ... WHERE ...``),
que es exactamente lo que Django genera para un ``UniqueConstraint`` con
``condition``. El test de esquema es por tanto válido en el backend real.
"""

import importlib
import pkgutil

from django.apps import apps as global_apps
from django.db import IntegrityError, transaction
from django.db.models import UniqueConstraint
from django.test import TestCase

from inventory.managers import reset_current_empresa, set_current_empresa
from inventory.models import Almacen, Empresa

CONSTRAINT_NAME = 'un_almacen_principal_por_empresa'


def _migracion_0025():
    """Devuelve el módulo de la migración 0025 (o None si aún no existe)."""
    from inventory import migrations as mig_pkg

    for info in pkgutil.iter_modules(mig_pkg.__path__):
        if info.name.startswith('0025_'):
            return importlib.import_module(f'inventory.migrations.{info.name}')
    return None


class TestEst11UnAlmacenPrincipalPorEmpresa(TestCase):
    """EST-11: máximo un ``Almacen`` con ``es_principal=True`` por empresa."""

    def setUp(self):
        sufijo = abs(hash(self._testMethodName)) % (10 ** 8)
        self.empresa = Empresa.objects.create(
            nombre=f'EST11 {self._testMethodName[:28]}',
            rif=f'J-EST11-{sufijo:08d}',
            activa=True,
        )
        # La señal de creación de Empresa ya siembra 1 almacén principal.
        token = set_current_empresa(self.empresa.id)
        self.addCleanup(reset_current_empresa, token)

    def _demover_principales(self):
        """Arrange: degrada por BD el principal sembrado (sin pasar por save())."""
        Almacen.global_objects.filter(
            empresa_id=self.empresa.id, es_principal=True
        ).update(es_principal=False)

    # -- 1. La BD rechaza dos principales (saltándose save()) -------------
    def test_est11_bd_rechaza_dos_principales_por_empresa(self):
        self._demover_principales()

        # bulk_create() inserta directo: NO pasa por save(), por lo que el
        # flip del modelo no puede ocultar el problema. Debe ser el esquema
        # quien rechaze dos principales de la MISMA empresa.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Almacen.global_objects.bulk_create([
                    Almacen(
                        empresa_id=self.empresa.id,
                        nombre='Principal Uno',
                        es_principal=True,
                    ),
                    Almacen(
                        empresa_id=self.empresa.id,
                        nombre='Principal Dos',
                        es_principal=True,
                    ),
                ])

        # La transacción se recuperó y no quedó ningún principal.
        self.assertEqual(
            Almacen.global_objects.filter(
                empresa_id=self.empresa.id, es_principal=True
            ).count(),
            0,
        )

    # -- 2. El constraint es por empresa, no global -----------------------
    def test_est11_bd_acepta_dos_principales_en_empresas_distintas(self):
        otra = Empresa.objects.create(
            nombre='EST11 Otra Empresa',
            rif='J-EST11-OTRA',
            activa=True,
        )

        # La señal siembra 1 principal por empresa: dos empresas distintas
        # pueden tener su principal simultáneamente, sin IntegrityError.
        for empresa_id in (self.empresa.id, otra.id):
            with self.subTest(empresa_id=empresa_id):
                self.assertEqual(
                    Almacen.global_objects.filter(
                        empresa_id=empresa_id, es_principal=True
                    ).count(),
                    1,
                    msg=(
                        "Cada empresa debe poder tener su propio principal: "
                        "el constraint es por empresa, no global."
                    ),
                )

    # -- 3. La UX se conserva: save() promueve y degrada la anterior ------
    def test_est11_promover_degrada_al_anterior(self):
        self._demover_principales()
        almacen_a = Almacen.objects.create(
            empresa=self.empresa, nombre='Almacén A', es_principal=True,
        )
        self.assertTrue(almacen_a.es_principal)

        # Promover B vía save() (objects.create) NO debe reventar con
        # IntegrityError: degrada a A en la misma transacción.
        almacen_b = Almacen.objects.create(
            empresa=self.empresa, nombre='Almacén B', es_principal=True,
        )

        almacen_a.refresh_from_db()
        almacen_b.refresh_from_db()
        self.assertFalse(
            almacen_a.es_principal,
            msg=(
                "save() debe degradar al principal anterior para preservar la "
                "UX (promover un almacén sin bajar el otro a mano)."
            ),
        )
        self.assertTrue(almacen_b.es_principal)
        self.assertEqual(
            Almacen.global_objects.filter(
                empresa_id=self.empresa.id, es_principal=True
            ).count(),
            1,
        )

    # -- 4. El flip es por tenant: no toca otras empresas ------------------
    def test_est11_flip_no_toca_otras_empresas(self):
        empresa_b = Empresa.objects.create(
            nombre='EST11 Empresa B',
            rif='J-EST11-EMPB',
            activa=True,
        )
        principal_b = Almacen.global_objects.get(
            empresa_id=empresa_b.id, es_principal=True
        )
        self.assertTrue(principal_b.es_principal)

        # Promover un almacén en A no debe degradar el principal de B.
        Almacen.objects.create(
            empresa=self.empresa,
            nombre='Almacén Promovido',
            es_principal=True,
        )

        principal_b.refresh_from_db()
        self.assertTrue(
            principal_b.es_principal,
            msg="El flip en A no debe tocar el principal de B.",
        )
        self.assertEqual(
            Almacen.global_objects.filter(
                empresa_id=empresa_b.id, es_principal=True
            ).count(),
            1,
        )

    # -- 5. Cero principales es válido -------------------------------------
    def test_est11_cero_principales_es_valido(self):
        # El constraint es parcial sobre es_principal=True: no obliga a que
        # exista uno. Demover al único principal debe estar permitido.
        principal = Almacen.global_objects.get(
            empresa_id=self.empresa.id, es_principal=True
        )
        self.assertTrue(principal.es_principal)

        principal.es_principal = False
        principal.save()  # No debe levantar IntegrityError.

        principal.refresh_from_db()
        self.assertFalse(principal.es_principal)
        self.assertEqual(
            Almacen.global_objects.filter(
                empresa_id=self.empresa.id, es_principal=True
            ).count(),
            0,
        )

    # -- 6. La migración 0025 añade el constraint (backfill ANTES) ----------
    def test_est11_migracion_anade_constraint(self):
        """
        Comprobaciones:
          1. Existe la migración ``0025_*`` con un ``AddConstraint`` del
             ``UniqueConstraint`` parcial ``un_almacen_principal_por_empresa``
             (fields=['empresa'], condition=Q(es_principal=True)).
          2. Hubo ofensores reales (empresa 34 con id=55 e id=56), así que la
             migración DEBE incluir un ``RunPython`` de backfill que aparece
             ANTES del ``AddConstraint`` (si fuera después, el AddConstraint
             fallaría en instalaciones con duplicados preexistentes).
          3. La función de backfill existe en el módulo (usa el manager
             histórico ``apps.get_model``: NO está sujeta al filtro de
             tenant) y es idempotente sobre el estado actual.
        """
        from django.db.migrations.operations import AddConstraint, RunPython

        migracion = _migracion_0025()
        self.assertIsNotNone(
            migracion,
            msg="No existe ninguna migración inventory/migrations/0025_*",
        )

        operaciones = list(migracion.Migration.operations)

        idx_runpython = next(
            (i for i, op in enumerate(operaciones)
             if isinstance(op, RunPython)
             and op.code is not None
             and 'un_principal_por_empresa' in getattr(op.code, '__name__', '')),
            None,
        )
        self.assertIsNotNone(
            idx_runpython,
            msg=(
                "La migración 0025 debe incluir un RunPython de backfill "
                "llamado *_un_principal_por_empresa* (la BD de desarrollo "
                "arrastraba una empresa con dos principales)."
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
            msg="El RunPython de backfill debe ir ANTES del AddConstraint",
        )

        # El AddConstraint es exactamente el UniqueConstraint parcial.
        constraint = operaciones[idx_addconstraint].constraint
        self.assertEqual(constraint.name, CONSTRAINT_NAME)
        self.assertEqual(tuple(constraint.fields), ('empresa',))
        self.assertIsNotNone(
            constraint.condition,
            msg="El constraint debe ser PARCIAL (condition=Q(es_principal=True))",
        )
        self.assertIn('es_principal', str(constraint.condition))

        # La función de backfill vive en el módulo (manager histórico).
        self.assertIsNotNone(getattr(migracion, '_un_principal_por_empresa', None))

        # Idempotente sobre el estado actual (aquí ya hay 1 principal/empresa).
        migracion._un_principal_por_empresa(global_apps, None)
        migracion._un_principal_por_empresa(global_apps, None)

        for empresa_id in Almacen.global_objects.values_list(
            'empresa_id', flat=True
        ).distinct():
            with self.subTest(empresa_id=empresa_id):
                self.assertLessEqual(
                    Almacen.global_objects.filter(
                        empresa_id=empresa_id, es_principal=True
                    ).count(),
                    1,
                )
