"""
DATA-04 — ``Contacto`` tipo PROVEEDOR exige ``rif`` y ``nombre_asesor``.

Contexto
--------
La vista ``contactos_view`` ya validaba RIF/Asesor para proveedores en el
formulario, pero ``Model.save()``, el admin, el shell y los scripts podían
saltarse esa validación: un PROVEEDOR sin RIF era persistible. El docstring
de ``Contacto`` dice que la PK (``identificacion``) ES la identificación
fiscal, así que un proveedor sin ``rif`` es un dato contradictorio.

Diagnóstico previo (BD real, pre-migración): 22 contactos, 5 PROVEEDORES,
los 5 con ``rif=None`` y ``nombre_asesor=None`` (sembrados por una versión
anterior de ``seed_db``). Por eso la migración 0023 ejecuta un ``RunPython``
de backfill ANTES de los ``AddConstraint``:
``rif`` vacío → copiar ``identificacion`` (la PK es la identificación
fiscal); ``nombre_asesor`` vacío → ``'PENDIENTE'``.

Niveles auditados
-----------------
1. Modelo: ``Contacto.clean()`` exige rif/asesor para PROVEEDOR (con
   ``strip()``: ``'   '`` también es inválido). Para CLIENTE ambos siguen
   opcionales (regresión de contrato, ADR-05).
2. BD: ``CheckConstraint`` condicionales ``proveedor_requiere_rif`` y
   ``proveedor_requiere_asesor``. El ``IS NULL`` explícito es CRÍTICO en
   SQLite: un CHECK que evalúa a NULL pasa; con
   ``(rif IS NULL OR rif = '')`` el resultado es FALSE, no NULL.
   Los proxies ``Cliente``/``Proveedor`` heredan ``clean()`` y comparten la
   tabla, así que quedan cubiertos automáticamente.
3. Migración: la 0023 debe añadir AMBOS constraints, con el backfill de
   datos ANTES (si no, SQLite rechaza el ``AddConstraint`` con filas
   ofensoras ya presentes).

Nota sobre los tests de BD
--------------------------
``bulk_create()`` no pasa por ``save()`` ni por validación del modelo: si la
BD rechaza al proveedor incompleto, el constraint es real. El patrón
``assertRaises`` + ``transaction.atomic()`` es el mismo que
``test_models_detalle_almacen.py`` (DATA-03).
"""

import importlib
import pkgutil

from django.apps import apps as global_apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.migrations.operations import AddConstraint, RunPython
from django.db.models import Q
from django.test import TestCase

from inventory.managers import reset_current_empresa, set_current_empresa
from inventory.models import Contacto, Empresa


def _migracion_0023():
    """Devuelve el módulo de la migración 0023 (o None si aún no existe)."""
    from inventory import migrations as mig_pkg

    for info in pkgutil.iter_modules(mig_pkg.__path__):
        if info.name.startswith('0023_'):
            return importlib.import_module(f'inventory.migrations.{info.name}')
    return None


class TestData04ContactoRif(TestCase):
    """DATA-04: proveedores con RIF y asesor en modelo, BD y migración."""

    def setUp(self):
        sufijo = abs(hash(self._testMethodName)) % (10 ** 8)
        self.empresa = Empresa.objects.create(
            nombre=f'DATA04 {self._testMethodName[:28]}',
            rif=f'J-DATA04-{sufijo:08d}',
            activa=True,
        )
        token = set_current_empresa(self.empresa.id)
        self.addCleanup(reset_current_empresa, token)
        self.sufijo = sufijo

    def _contacto(self, **overrides):
        """Arrange: proveedor válido; cada test sobrescribe lo que audita."""
        datos = {
            'empresa': self.empresa,
            'identificacion': f'J-DATA04-{self.sufijo:08d}',
            'nombre': 'Proveedor DATA04',
            'tipo': 'PROVEEDOR',
            'rif': f'J-DATA04-{self.sufijo:08d}',
            'nombre_asesor': 'Asesor DATA04',
        }
        datos.update(overrides)
        return Contacto(**datos)

    # -- 1. clean(): PROVEEDOR sin rif es inválido --------------------------
    def test_data04_proveedor_sin_rif_es_invalido(self):
        contacto = self._contacto(rif=None)

        with self.assertRaises(ValidationError) as ctx:
            contacto.full_clean()

        self.assertIn(
            'rif', ctx.exception.error_dict,
            msg='El error debe reportarse bajo la clave de campo "rif".',
        )

    # -- 2. clean(): PROVEEDOR sin asesor es inválido ------------------------
    def test_data04_proveedor_sin_asesor_es_invalido(self):
        contacto = self._contacto(nombre_asesor=None)

        with self.assertRaises(ValidationError) as ctx:
            contacto.full_clean()

        self.assertIn(
            'nombre_asesor', ctx.exception.error_dict,
            msg='El error debe reportarse bajo la clave de campo "nombre_asesor".',
        )

    # -- 3. Contrato positivo: proveedor completo es válido ------------------
    def test_data04_proveedor_con_rif_y_asesor_es_valido(self):
        self._contacto().full_clean()  # No debe lanzar ValidationError.

    # -- 4. Regresión: CLIENTE sigue sin exigir rif/asesor (ADR-05) ----------
    def test_data04_cliente_sin_rif_es_valido(self):
        self._contacto(
            tipo='CLIENTE', rif=None, nombre_asesor=None,
        ).full_clean()  # No debe lanzar ValidationError.

    # -- 5. clean() hace strip(): solo espacios también es vacío ------------
    def test_data04_rif_con_espacios_se_rechaza(self):
        contacto = self._contacto(rif='   ')

        with self.assertRaises(ValidationError) as ctx:
            contacto.full_clean()

        self.assertIn(
            'rif', ctx.exception.error_dict,
            msg='Un rif de solo espacios debe considerarse vacío (strip).',
        )

    # -- 6. BD rechaza PROVEEDOR sin rif (bulk_create salta save()) ----------
    def test_data04_bd_rechaza_proveedor_sin_rif(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Contacto.objects.bulk_create([self._contacto(rif=None)])

        self.assertEqual(
            Contacto.objects.filter(
                tipo='PROVEEDOR'
            ).filter(Q(rif__isnull=True) | Q(rif='')).count(),
            0,
            msg='La transacción debe revertirse sin dejar proveedores sin rif.',
        )

    # -- 7. BD rechaza PROVEEDOR sin asesor ----------------------------------
    def test_data04_bd_rechaza_proveedor_sin_asesor(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Contacto.objects.bulk_create(
                    [self._contacto(nombre_asesor=None)]
                )

        self.assertEqual(
            Contacto.objects.filter(
                tipo='PROVEEDOR'
            ).filter(
                Q(nombre_asesor__isnull=True) | Q(nombre_asesor='')
            ).count(),
            0,
            msg='La transacción debe revertirse sin dejar proveedores sin asesor.',
        )

    # -- 8. BD acepta CLIENTE sin rif: constraint CONDICIONAL ----------------
    def test_data04_bd_acepta_cliente_sin_rif(self):
        # Para CLIENTE la condición debe evaluar TRUE explícito (no NULL):
        # ``NOT (CLIENTE = PROVEEDOR AND ...)`` → NOT (FALSE AND ...) → TRUE.
        try:
            Contacto.objects.bulk_create([
                self._contacto(tipo='CLIENTE', rif=None, nombre_asesor=None)
            ])
        except IntegrityError as exc:
            self.fail(
                f'El constraint debe ser condicional (solo PROVEEDOR): {exc}'
            )

        # El signal create_tenant_defaults siembra un "Cliente Genérico"
        # por empresa, así que se verifica el registro NUEVO por su PK.
        guardado = Contacto.objects.filter(
            identificacion=f'J-DATA04-{self.sufijo:08d}', tipo='CLIENTE'
        ).first()
        self.assertIsNotNone(
            guardado,
            msg='El CLIENTE sin rif debe persistir (ADR-05: campos de '
                'proveedor son opcionales para clientes).',
        )
        self.assertIsNone(
            guardado.rif,
            msg='El rif debe persistir como NULL, no como cadena vacía.',
        )

    # -- 9. La migración 0023: backfill ANTES de los AddConstraint -----------
    def test_data04_migracion_anade_constraints(self):
        migracion = _migracion_0023()
        self.assertIsNotNone(
            migracion,
            msg='No existe ninguna migración inventory/migrations/0023_*',
        )

        operaciones = list(migracion.Migration.operations)

        # (a) El RunPython de backfill existe y va ANTES de los constraints
        # (el diagnóstico previo halló 5 proveedores sin rif/asesor).
        idx_backfill = next(
            (
                i for i, op in enumerate(operaciones)
                if isinstance(op, RunPython)
                and op.code is not None
                and 'rellenar_rif_asesor_proveedores' in getattr(
                    op.code, '__name__', ''
                )
            ),
            None,
        )
        self.assertIsNotNone(
            idx_backfill,
            msg='La 0023 debe incluir un RunPython llamado '
                '"*_rellenar_rif_asesor_proveedores" (backfill de los 5 '
                'proveedores ofensores hallados en el diagnóstico).',
        )

        # (b) Exactamente un AddConstraint por cada constraint documentado.
        for nombre_constraint in (
            'proveedor_requiere_rif', 'proveedor_requiere_asesor'
        ):
            indices = [
                i for i, op in enumerate(operaciones)
                if isinstance(op, AddConstraint)
                and getattr(op.constraint, 'name', None) == nombre_constraint
            ]
            self.assertEqual(
                len(indices), 1,
                msg=f'Debe existir exactamente un AddConstraint para '
                    f'"{nombre_constraint}" (encontrados: {len(indices)}).',
            )
            self.assertLess(
                idx_backfill, indices[0],
                msg=f'El RunPython de backfill debe ir ANTES del '
                    f'AddConstraint "{nombre_constraint}".',
            )

        # (c) La función de backfill existe, es idempotente y su SQL es
        # válido sobre los apps reales (mismo patrón que DATA-03/0022).
        self.assertIsNotNone(
            getattr(migracion, '_rellenar_rif_asesor_proveedores', None)
        )
        migracion._rellenar_rif_asesor_proveedores(global_apps, None)
        migracion._rellenar_rif_asesor_proveedores(global_apps, None)
        self.assertFalse(
            Contacto.global_objects.filter(tipo='PROVEEDOR').filter(
                Q(rif__isnull=True) | Q(rif='')
            ).exists(),
            msg='Tras el backfill no debe quedar ningún proveedor sin rif.',
        )
