"""
EST-04 — Usuario forense: FK a ``User`` + snapshot ``usuario_nombre``.

Contexto
--------
``MovimientoKardex.usuario`` y ``NotaCredito.usuario`` eran CharField(150):
la trazabilidad forense dependía de un string libre que cualquier POST
podía falsificar y que ningún constraint vinculaba con ``auth_user``.

Este módulo fija el contrato del esquema migrado (REQ-EST04-01/02) y del
backfill de la migración ``0029`` (REQ-EST04-03):

* La FK ``usuario`` se resuelve por match exacto ``username -> auth_user``.
* Sin match, la FK queda ``NULL`` y el snapshot ``usuario_nombre`` se
  preserva intacto — el snapshot ES la trazabilidad ('seed_db', 'Sistema',
  literales de tests no matchean por diseño).
* ``on_delete=SET_NULL``: la baja del usuario real nunca borra el histórico
  (Gherkin EST04-05).
"""

import importlib
from decimal import Decimal
from unittest.mock import patch

import django.apps
from django.contrib.auth.models import User
from django.db import models
from django.test import TestCase
from django.urls import reverse

from inventory.models import AuditoriaTasa, MovimientoKardex, NotaCredito

MIGRACION_0029 = 'inventory.migrations.0029_usuario_fk_kardex_nc'


def _crear_empresa():
    """Empresa activa + ContextVar de tenant (patrón test_calculos.py:35-146)."""
    from inventory.models import Empresa
    from inventory.managers import set_current_empresa

    empresa = Empresa.objects.create(
        nombre='EST04 Corp', rif='J-EST04-001', activa=True,
    )
    set_current_empresa(empresa.id)
    return empresa


class TestBackfillUsuarioFK(TestCase):
    """Esquema renombrado + backfill por match de username (migración 0029)."""

    def setUp(self):
        from inventory.models import Almacen, Articulo

        self.empresa = _crear_empresa()
        self.almacen = Almacen.objects.create(
            empresa=self.empresa, nombre='Almacén EST-04', es_principal=True,
        )
        self.articulo = Articulo.objects.create(
            empresa=self.empresa, sku='EST04-001', nombre='Artículo EST-04',
            tipo='FISICO', categoria='OTROS',
            costo=Decimal('5.00'), precio_divisa=Decimal('10.00'),
            iva_porcentaje=Decimal('16.00'),
        )

    def _crear_kardex(self, usuario_nombre, cantidad=Decimal('1')):
        """Fixture directo (no pasa por services): fila histórica pre-migración."""
        return MovimientoKardex.objects.create(
            empresa=self.empresa,
            articulo=self.articulo,
            almacen=self.almacen,
            tipo='ENTRADA',
            cantidad=cantidad,
            saldo_resultante=cantidad,
            concepto='AJUSTE_ENTRADA',
            usuario_nombre=usuario_nombre,
            usuario=None,
        )

    # ── 1. REQ-EST04-01/02: esquema FK usuario + snapshot usuario_nombre ──

    def test_esquema_fk_y_snapshot(self):
        """`usuario` es FK SET_NULL a User; `usuario_nombre` conserva 150 chars."""
        campo_fk = MovimientoKardex._meta.get_field('usuario')
        self.assertIsInstance(campo_fk, models.ForeignKey)
        self.assertEqual(campo_fk.remote_field.on_delete, models.SET_NULL)
        self.assertTrue(campo_fk.null)
        # related_name sin colisión con Empresa.movimientos_kardex (models.py:1336)
        self.assertEqual(campo_fk.remote_field.related_name, 'kardex_registrado_por')
        self.assertTrue(hasattr(User, 'kardex_registrado_por'))

        snapshot = MovimientoKardex._meta.get_field('usuario_nombre')
        self.assertEqual(snapshot.max_length, 150)

        nc_fk = NotaCredito._meta.get_field('usuario')
        self.assertIsInstance(nc_fk, models.ForeignKey)
        self.assertEqual(nc_fk.remote_field.on_delete, models.SET_NULL)
        self.assertTrue(nc_fk.null)
        self.assertEqual(nc_fk.remote_field.related_name, 'notas_credito_emitidas')
        self.assertTrue(hasattr(User, 'notas_credito_emitidas'))

        # REQ-EST04-02: el default 'Sistema' pasa al snapshot.
        nc_snapshot = NotaCredito._meta.get_field('usuario_nombre')
        self.assertEqual(nc_snapshot.max_length, 150)
        self.assertEqual(nc_snapshot.default, 'Sistema')

    # ── 2. REQ-EST04-03: match de username → FK resuelta ──────────────────

    def test_backfill_match_de_username(self):
        user = User.objects.create_user('op_backfill', password='pw')
        mov = self._crear_kardex('op_backfill')

        mod = importlib.import_module(MIGRACION_0029)
        mod.backfill_usuario_fk(django.apps.apps, None)

        mov.refresh_from_db()
        self.assertEqual(mov.usuario_id, user.pk)
        self.assertEqual(mov.usuario_nombre, 'op_backfill')

    # ── 3. REQ-EST04-03: sin match → FK NULL + snapshot; idempotente ──────

    def test_backfill_sin_match_preserva_snapshot_y_es_idempotente(self):
        filas = [
            self._crear_kardex('seed_db'),
            self._crear_kardex('Sistema', Decimal('2')),
        ]

        mod = importlib.import_module(MIGRACION_0029)
        mod.backfill_usuario_fk(django.apps.apps, None)

        pares = []
        for fila in filas:
            fila.refresh_from_db()
            self.assertIsNone(fila.usuario_id, 'sin match la FK queda NULL')
            pares.append((fila.usuario_id, fila.usuario_nombre))
        self.assertEqual(pares, [(None, 'seed_db'), (None, 'Sistema')])

        # Segunda pasada → no-op (backfill idempotente, REQ-EST04-03).
        mod.backfill_usuario_fk(django.apps.apps, None)
        for fila, par in zip(filas, pares):
            fila.refresh_from_db()
            self.assertEqual((fila.usuario_id, fila.usuario_nombre), par)


class TestResolucionUsuario(TestCase):
    """Helper único de resolución str|User en los 3 sitios de persistencia.

    REQ-EST04-05: instancia User → FK + snapshot; string existente → FK
    resuelta + snapshot; string sin match → FK NULL + snapshot preservado
    (los ~60 literales de tests quedan aquí, intactos). REQ-EST04-07: los
    `reversar_*` dejan de hardcodear 'Sistema' y registran quién anuló.
    """

    def setUp(self):
        from inventory.models import Almacen, Articulo, ConfiguracionEmpresa

        self.empresa = _crear_empresa()
        self.config = ConfiguracionEmpresa.objects.get(empresa=self.empresa)
        self.config.tasa_bcv = Decimal('40.0000')
        self.config.factor_cobertura = Decimal('1.0500')
        self.config.save()
        self.almacen = Almacen.objects.create(
            empresa=self.empresa, nombre='Almacén EST-04 Res', es_principal=True,
        )
        self.articulo = Articulo.objects.create(
            empresa=self.empresa, sku='EST04-RES', nombre='Artículo EST-04 Res',
            tipo='FISICO', categoria='OTROS',
            costo=Decimal('5.00'), precio_divisa=Decimal('10.00'),
            iva_porcentaje=Decimal('16.00'),
        )
        self.user = User.objects.create_user('op_resolucion', password='pw')

    def _registrar(self, usuario, cantidad=Decimal('1')):
        from inventory.services import registrar_movimiento

        return registrar_movimiento(
            self.articulo, self.almacen, 'ENTRADA', cantidad,
            'AJUSTE_ENTRADA', usuario=usuario,
        )

    # ── 1. Gherkin EST04-01: instancia User → FK + snapshot ────────────────

    def test_user_instancia_llena_fk_y_snapshot(self):
        mov = self._registrar(self.user)

        self.assertEqual(mov.usuario_id, self.user.pk)
        self.assertEqual(mov.usuario_nombre, self.user.username)

    # ── 2. Gherkin EST04-02/03: str con match y sin match ─────────────────

    def test_str_match_resuelve_fk_y_no_match_deja_null(self):
        user_match = User.objects.create_user('op_resolver', password='pw')

        mov_match = self._registrar('op_resolver', Decimal('2'))
        self.assertEqual(mov_match.usuario_id, user_match.pk)
        self.assertEqual(mov_match.usuario_nombre, 'op_resolver')

        mov_sin_match = self._registrar('data03', Decimal('3'))
        self.assertIsNone(mov_sin_match.usuario_id)
        self.assertEqual(mov_sin_match.usuario_nombre, 'data03')

    # ── 3. Gherkin EST04-08: reversos registran quién anuló ────────────────

    def test_reversar_registran_usuario(self):
        from inventory.models import Contacto
        from inventory.services import (
            procesar_venta, registrar_compra_proveedor,
            reversar_documento_compra, reversar_nota_entrega,
        )

        # Stock para la venta.
        self._registrar(self.user, Decimal('10'))

        nota = procesar_venta(
            None,
            [{'articulo_sku': 'EST04-RES', 'cantidad': 2,
              'precio_unitario_usd': '20.00'}],
            self.almacen.pk,
            usuario=self.user,
        )
        proveedor = Contacto.objects.create(
            empresa=self.empresa, identificacion='J-EST04-PROV',
            tipo='PROVEEDOR', nombre='Proveedor EST-04',
            rif='J-EST04-PROV', nombre_asesor='Asesor Test',
        )
        res_compra = registrar_compra_proveedor(
            proveedor_id=str(proveedor.pk),
            numero_factura='FACT-EST04',
            fecha_compra='2026-01-15',
            almacen_id=self.almacen.pk,
            lista_items=[{'sku': 'EST04-RES', 'cantidad': Decimal('5.00'),
                          'costo_factura': Decimal('10.00')}],
            usuario=self.user,
        )

        admin = User.objects.create_user('admin', password='pw')
        reversar_nota_entrega(
            self.empresa.pk, nota.pk, 'error de prueba', usuario=admin,
        )
        reversar_documento_compra(
            self.empresa.pk, res_compra['documento_id'],
            'error de prueba', usuario=admin,
        )

        reverso_venta = MovimientoKardex.objects.filter(
            concepto='DEVOLUCION_VENTA',
        ).order_by('-pk').first()
        self.assertEqual(reverso_venta.usuario_id, admin.pk)
        self.assertEqual(reverso_venta.usuario_nombre, 'admin')

        reverso_compra = MovimientoKardex.objects.filter(
            concepto='ANULACION_COMPRA',
        ).order_by('-pk').first()
        self.assertEqual(reverso_compra.usuario_id, admin.pk)
        self.assertEqual(reverso_compra.usuario_nombre, 'admin')

        # Backward-compat (REQ-EST04-07): sin el arg → snapshot 'Sistema'
        # y FK NULL ('Sistema' no existe como auth_user por diseño).
        self._registrar(self.user, Decimal('10'))
        nota2 = procesar_venta(
            None,
            [{'articulo_sku': 'EST04-RES', 'cantidad': 1,
              'precio_unitario_usd': '20.00'}],
            self.almacen.pk,
            usuario=self.user,
        )
        reversar_nota_entrega(self.empresa.pk, nota2.pk, 'sin usuario')
        default_venta = MovimientoKardex.objects.filter(
            concepto='DEVOLUCION_VENTA',
        ).order_by('-pk').first()
        self.assertIsNone(default_venta.usuario_id)
        self.assertEqual(default_venta.usuario_nombre, 'Sistema')


class TestVistasUsuarioForense(TestCase):
    """REQ-EST04-06: las vistas pasan `request.user`; POST `usuario` deprecado.

    El operador autenticado es la fuente de verdad forense: el valor de
    `usuario` por POST/JSON se ignora con `logger.warning` (Gherkin
    EST04-07) y la FK/snapshot salen SIEMPRE del `request.user`.
    """

    def setUp(self):
        import json  # noqa: F401 — se usa en los tests
        from inventory.models import Almacen, Articulo
        from inventory.tests import seed_inventario

        self.empresa = _crear_empresa()
        self.almacen = Almacen.objects.create(
            empresa=self.empresa, nombre='Almacén EST-04 Vista', es_principal=True,
        )
        self.articulo_colision = Articulo.objects.create(
            empresa=self.empresa, sku='EST04-COL', nombre='Artículo Colisión',
            tipo='FISICO', categoria='OTROS',
            costo=Decimal('5.00'), precio_divisa=Decimal('10.00'),
        )
        seed_inventario(self.articulo_colision, self.almacen, cantidad=20)

        # Login multi-tenant (patrón tests.py:4302).
        self.user = User.objects.create_user('op_carga', password='pw1234')
        perfil = self.user.perfil
        perfil.empresas_permitidas.add(self.empresa)
        perfil.empresa_activa = self.empresa
        perfil.save()
        self.client.login(username='op_carga', password='pw1234')
        session = self.client.session
        session['empresa_id'] = self.empresa.id
        session.save()

    def test_post_usuario_deprecado_carga_y_colision(self):
        import json

        from django.core.files.uploadedfile import SimpleUploadedFile
        from inventory.tests import _crear_excel_bytes

        # (a) Carga masiva por POST con `usuario='farsante'` en el form.
        excel = _crear_excel_bytes([
            ('EST04-POST-1', 'Artículo POST', '5.00', '10', '9.99', ''),
        ])
        with self.assertLogs('inventory.views', level='WARNING') as captura:
            resp = self.client.post('/carga/', {
                'archivo_excel': SimpleUploadedFile(
                    'carga.xlsx', excel.getvalue(),
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                ),
                'almacen_id': self.almacen.pk,
                'usuario': 'farsante',
            })
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertIn('deprecado', ' '.join(captura.output))

        lote_id = resp.json()['lote_id']
        movs_lote = list(MovimientoKardex.objects.filter(lote_carga=lote_id))
        self.assertTrue(movs_lote, 'la carga masiva debe registrar kárdex')
        for mov in movs_lote:
            self.assertEqual(mov.usuario_id, self.user.pk)
            self.assertEqual(mov.usuario_nombre, 'op_carga')

        # (b) Resolución de colisión por JSON con `usuario='farsante'`.
        with self.assertLogs('inventory.views', level='WARNING') as captura:
            resp_col = self.client.post(
                '/carga/resolver/',
                data=json.dumps({
                    'sku': 'EST04-COL',
                    'decision': 'SUMAR',
                    'cantidad_excel': '8',
                    'lote_id': 'lote-est04-vista',
                    'almacen_id': self.almacen.pk,
                    'usuario': 'farsante',
                }),
                content_type='application/json',
            )
        self.assertEqual(resp_col.status_code, 200, resp_col.content[:300])
        self.assertIn('deprecado', ' '.join(captura.output))

        mov_decision = MovimientoKardex.objects.filter(
            concepto='CARGA_MASIVA_SUMA',
        ).order_by('-pk').first()
        self.assertIsNotNone(mov_decision)
        self.assertEqual(mov_decision.usuario_id, self.user.pk)
        self.assertEqual(mov_decision.usuario_nombre, 'op_carga')


class TestAuditoriaTasaUsuario(TestCase):
    """EST-05 (REQ-EST05-A1): FK ``usuario`` + snapshot en ``AuditoriaTasa``.

    Mismo patrón EST-04 aplicado al histórico de tasas: los 2 writers
    (``views.configuracion_view`` fuente='MANUAL' y
    ``services.sincronizar_tasa_cambio`` fuente='API') resuelven con el
    helper único ``resolver_usuario`` — la FK y el snapshot salen del
    usuario autenticado. ``on_delete=SET_NULL``: la baja del usuario real
    nunca borra la auditoría de tasas; el snapshot preserva el nombre.
    """

    def setUp(self):
        from inventory.models import ConfiguracionEmpresa

        self.empresa = _crear_empresa()
        self.config = ConfiguracionEmpresa.objects.get(empresa=self.empresa)
        self.config.tasa_bcv = Decimal('40.0000')
        self.config.factor_cobertura = Decimal('1.0000')
        self.config.tasa_mercado = Decimal('40.0000')
        self.config.api_url = 'https://198.51.100.10/tasa'
        self.config.http_method = 'GET'
        self.config.response_selector = 'data.tasa_paralela'
        self.config.save()

        # Login multi-tenant con staff (patrón tests.py:8912: solo
        # is_staff/is_superuser puede mutar la configuración global).
        self.user = User.objects.create_user('op_tasas', password='pw1234')
        self.user.is_staff = True
        self.user.save()
        perfil = self.user.perfil
        perfil.empresas_permitidas.add(self.empresa)
        perfil.empresa_activa = self.empresa
        perfil.save()
        self.client.login(username='op_tasas', password='pw1234')
        session = self.client.session
        session['empresa_id'] = self.empresa.id
        session.save()

    # ── 1. Writer MANUAL: POST a configuración con tasa cambiada ──────────

    def test_configuracion_manual_registra_usuario_fk(self):
        """POST con tasa cambiada → última AuditoriaTasa lleva FK + snapshot."""
        r = self.client.post(reverse('inventory:configuracion'), {
            'tasa_bcv': '45.5000',
            'tasa_mercado': '55.0000',
            'factor_cobertura': '1.3000',
        })
        self.assertRedirects(r, reverse('inventory:configuracion'))

        auditoria = AuditoriaTasa.objects.last()
        self.assertIsNotNone(auditoria, 'la tasa cambió: debe auditarse')
        self.assertEqual(auditoria.fuente, 'MANUAL')
        self.assertEqual(auditoria.usuario_id, self.user.pk)
        self.assertEqual(auditoria.usuario_nombre, 'op_tasas')

    # ── 2. Writer API: sincronización con usuario resuelto ────────────────

    @patch('requests.request')
    def test_sincronizar_api_registra_usuario(self, mock_request):
        """sincronizar_tasa_cambio(usuario=User) → AuditoriaTasa 'API' con FK."""
        mock_response = mock_request.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': {'tasa_paralela': 50.00}}

        from inventory.services import sincronizar_tasa_cambio
        resultado = sincronizar_tasa_cambio(usuario=self.user)

        self.assertTrue(resultado['ok'])
        auditoria = AuditoriaTasa.objects.last()
        self.assertIsNotNone(auditoria, 'la sync exitosa debe auditarse')
        self.assertEqual(auditoria.fuente, 'API')
        self.assertEqual(auditoria.usuario_id, self.user.pk)
        self.assertEqual(auditoria.usuario_nombre, 'op_tasas')

    # ── 3. Gherkin EST04-05 aplicado a tasas: SET_NULL preserva histórico ──

    def test_baja_usuario_preserva_snapshot_auditoria(self):
        """La baja del usuario real deja la FK en NULL y el snapshot intacto."""
        auditoria = AuditoriaTasa.objects.create(
            empresa=self.empresa,
            tasa_bcv=Decimal('40.0000'),
            tasa_mercado=Decimal('42.0000'),
            factor_cobertura=Decimal('1.0500'),
            fuente='MANUAL',
            notas='Fixture directo EST-05',
            usuario=self.user,
            usuario_nombre='op_tasas',
        )

        self.user.delete()

        auditoria.refresh_from_db()
        self.assertEqual(AuditoriaTasa.objects.count(), 1)
        self.assertIsNone(auditoria.usuario_id)
        self.assertEqual(auditoria.usuario_nombre, 'op_tasas')
