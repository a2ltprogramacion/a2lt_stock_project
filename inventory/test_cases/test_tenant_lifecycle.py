"""
Ciclo de vida del tenant: siembra por señal y teardown con ``.delete()``.

Contexto
--------
Hallazgo (verificado por 2 agentes independientes): al crear una ``Empresa``,
la señal ``create_tenant_defaults`` siembra el paquete del tenant —
``ConfiguracionEmpresa``, ``Almacen``, ``Contacto``, 2 ``Moneda`` (USD/VES)
y 1 ``TasaCambio`` (USD→VES) — pero ``empresa.delete()`` lanzaba
``ProtectedError`` porque ``TasaCambio.moneda_origen`` y ``moneda_destino``
eran ``PROTECT``: el collector de Django con PROTECT bloquea la cascada de
las monedas AUNQUE las filas de TasaCambio que las referencian también se
eliminen en la misma operación (via ``TasaCambio.empresa`` CASCADE).

La corrección cambia ambas FK a ``RESTRICT`` (Django ≥ 2.2):
``RESTRICT`` = ``PROTECT`` **salvo** cuando las filas que referencian
también caen en la misma operación del collector.

Semántica resultante que esta suite garantiza
---------------------------------------------
1. ``empresa.delete()`` de un tenant recién sembrado **funciona**: la tasa
   inicial cae por el CASCADE de ``TasaCambio.empresa`` en la misma
   operación, por lo que ya nada protege a las monedas sembradas.
2. ``moneda.delete()`` directo con historial de tasas **sigue bloqueado**:
   lanza ``RestrictedError``. NOTA verificada en runtime: en Django 6.0
   ``RestrictedError`` YA NO es subclase de ``ProtectedError`` (jerarquía
   histórica de Django ≤ 5.0); ambos son subclases directas de
   ``IntegrityError`` (ver test 2). En este repo el impacto es nulo: no
   existe ningún uso de ``ProtectedError`` que dependiera de la
   subclasificación.
3. Las introspección de ``on_delete`` queda fijada a ``models.RESTRICT``
   para evitar regresiones silenciosas a PROTECT o CASCADE.
"""

from django.db import models
from django.db.models.deletion import RestrictedError
from django.db.utils import IntegrityError
from django.test import TestCase

from inventory.models import (
    Almacen, ConfiguracionEmpresa, Contacto, Empresa, Moneda, TasaCambio,
)


class TestTenantLifecycle(TestCase):
    """Siembra y teardown completo de un tenant recién creado."""

    def _crear_empresa(self):
        """
        Crea una Empresa con RIF único por test (el pk puede reciclarse
        entre corridas si la BD conserva filas; el RIF es lo único).
        """
        sufijo = abs(hash(self._testMethodName)) % (10 ** 8)
        return Empresa.objects.create(
            nombre=f'TENANT {self._testMethodName[:24]}',
            rif=f'J-TENANT-{sufijo:08d}',
            activa=True,
        )

    def _contar_paquete_sembrado(self, empresa_id):
        """
        Cuenta el paquete sembrado SIN filtro de tenant (global_objects):
        1 config, 1 almacén, 1 contacto, 2 monedas, 1 tasa.
        """
        return {
            'config': ConfiguracionEmpresa.global_objects.filter(
                empresa_id=empresa_id,
            ).count(),
            'almacen': Almacen.global_objects.filter(
                empresa_id=empresa_id,
            ).count(),
            'contacto': Contacto.global_objects.filter(
                empresa_id=empresa_id,
            ).count(),
            'monedas': Moneda.global_objects.filter(
                empresa_id=empresa_id,
            ).count(),
            'tasas': TasaCambio.global_objects.filter(
                empresa_id=empresa_id,
            ).count(),
        }

    # -- 1. Teardown completo de un tenant recién sembrado ------------------
    def test_tenant_recien_sembrado_se_elimina_completo(self):
        # Arrange: la señal siembra el paquete completo del tenant.
        empresa = self._crear_empresa()
        empresa_id = empresa.pk

        paquete = self._contar_paquete_sembrado(empresa_id)
        self.assertEqual(paquete, {
            'config': 1, 'almacen': 1, 'contacto': 1,
            'monedas': 2, 'tasas': 1,
        }, msg=f'El seed del tenant {empresa.rif} no coincide con lo esperado')

        # Act: el delete del tenant recién sembrado NO debe lanzar
        # ProtectedError (con PROTECT en TasaCambio→Moneda fallaba aunque
        # la tasa también cayera en la misma operación del collector).
        empresa.delete()

        # Assert: TODO el paquete sembrado cae a 0, consultado sin filtro
        # de tenant para no depender del estado de EmpresaManager.
        paquete_tras_delete = self._contar_paquete_sembrado(empresa_id)
        self.assertEqual(
            paquete_tras_delete,
            {'config': 0, 'almacen': 0, 'contacto': 0,
             'monedas': 0, 'tasas': 0},
            msg=(
                'Tras empresa.delete() del tenant sembrado deben quedar 0 '
                f'filas de cada modelo (quedó: {paquete_tras_delete})'
            ),
        )

    # -- 2. Moneda con historial de tasas sigue protegida -------------------
    def test_moneda_con_historial_de_tasas_no_se_borra_directamente(self):
        # Arrange: tenant sembrado; la señal crea una tasa USD→VES que
        # referencia a VES como moneda_destino.
        empresa = self._crear_empresa()
        ves = Moneda.global_objects.get(empresa=empresa, codigo='VES')

        # Act + Assert: el borrado directo de la moneda (sin que la tasa
        # caiga en la misma operación) lanza RestrictedError.
        with self.assertRaises(RestrictedError) as ctx:
            ves.delete()

        # Documenta la jerarquía real de excepciones (verificada en
        # runtime, Django 6.0): RestrictedError y ProtectedError son
        # hermanas, ambas subclases directas de IntegrityError. Un
        # ``except IntegrityError`` cubre ambas semánticas (bloqueo de
        # borrado directo de monedas con historial).
        self.assertIsInstance(
            ctx.exception, IntegrityError,
            msg='RestrictedError debe ser subclase de IntegrityError',
        )

        # La moneda sigue viva: RESTRICT bloqueó el borrado directo.
        self.assertTrue(
            Moneda.global_objects.filter(pk=ves.pk).exists(),
            msg='La moneda con historial de tasas no debe haberse borrado',
        )

    # -- 3. Las FK de TasaCambio hacia Moneda usan RESTRICT -----------------
    def test_fk_de_tasacambio_usa_restrict(self):
        for campo in ('moneda_origen', 'moneda_destino'):
            campo_fk = TasaCambio._meta.get_field(campo)
            self.assertIs(
                campo_fk.remote_field.on_delete, models.RESTRICT,
                msg=(
                    f'TasaCambio.{campo} debe usar on_delete=RESTRICT '
                    '(permite el teardown del tenant sembrado pero sigue '
                    'bloqueando el borrado directo de monedas con historial)'
                ),
            )
