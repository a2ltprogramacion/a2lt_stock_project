"""
EST-02 — Documentos emitidos inmutables: matriz de campos + señales + admin.

Contexto
--------
El audit de EST-02 (spec §2.2) encontró que las cabeceras de los documentos
emitidos (``NotaEntrega``, ``DocumentoCompra``, ``NotaCredito``) y sus líneas
(``Detalle*``) eran mutables con un simple ``save()``/``delete()`` desde
cualquier punto del código: se podía "anular" una venta editando ``estado``
en el admin sin reversar stock, borrar una NC con sus trazas, o retocar
precios snapshot de una línea histórica.

Este módulo fija el contrato del guard (REQ-EST02-01..10):

* **Matriz**: tras emisión, una cabecera solo muta ``estado`` (con transición
  única PROCESADO→ANULADO) + ``motivo_anulacion`` en el MISMO save de esa
  transición. Las líneas (``Detalle*``) tienen matriz VACÍA: solo se permite
  el re-save idempotente con valores idénticos.
* **Documento cerrado**: un documento ANULADO es histórico — toda mutación
  posterior se bloquea (REQ-EST02-02).
* **Borrados**: ``pre_delete`` bloquea instancia, queryset bulk y cascada
  (REQ-EST02-04). El bypass reutilizado es el MISMO ``kardex_bypass`` de
  EST-01 (mecanismo compartido, REQ-EST02-07).
* **Dead code**: el ``nc.delete()`` dentro de los ``except`` de
  ``procesar_devolucion_*`` era un no-op dentro de ``@transaction.atomic``
  cuyo ``pre_delete`` enmascaría la excepción original (REQ-EST02-05).

Divergencia reportada y aprobada por el coordinador (2026-10-24, opción A)
------------------------------------------------------------------------
El plan conecta ``pre_save`` de NE/DC en TASK-01 asumiendo que los únicos
writers ilegales son los 4 sitios auditados (spec §1.5). La auditoría real
encontró 6: los 4 del plan MÁS dos tails de CREACIÓN que el plan no cubría —

* ``procesar_venta`` (services.py:1598):
  ``nota_entrega.save(update_fields=['iva_total', 'iva_check'])`` sobre la
  NE ya insertada (create en 1416).
* ``registrar_compra_proveedor`` (services.py:2291):
  ``documento.save(update_fields=['monto_total_usd', 'iva_total',
  'monto_total_bs_snapshot'])`` sobre la DC ya insertada.

El handler del capítulo bloquea ``update_fields`` ajenos a la matriz aunque
el valor no cambie → TASK-01 según la letra del plan rompía ambos flujos
críticos de creación. Resolución aprobada: extender el patrón pre-create del
§5 (el mismo que el capítulo aplica a la NC) a NE/DC — los totales se
computan ANTES del ``create`` (la cabecera nace completa) y los dos tails
desaparecen. Misma justificación forense que §5: "una NE/DC PROCESADO existe
100ms con iva_total/monto mentido".
"""

from decimal import Decimal

from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from inventory import services as svc
from inventory.admin import DetalleNotaEntregaInline
from inventory.models import (
    Articulo,
    ConfiguracionEmpresa,
    Contacto,
    DetalleNotaCredito,
    DetalleNotaEntrega,
    DocumentoCompra,
    DocumentoInmutableError,
    NotaCredito,
    NotaEntrega,
)
from inventory.tests import crear_almacen, crear_articulo_fisico, crear_empresa


class CabecerasInmutablesBase(TestCase):
    """Fixture común (patrón tests.py TestVentaExitosa): tenant en sesión,
    artículo FISICO con stock, una venta (NE PROCESADO) y una compra
    (DC PROCESADO) — todo por los caminos legítimos de services."""

    def setUp(self):
        self.empresa = crear_empresa(nombre='EST02 Cabeceras', rif='J-EST02-CAB')
        self.config = ConfiguracionEmpresa.objects.get(empresa=self.empresa)
        self.config.tasa_bcv = Decimal('40.00')
        self.config.factor_cobertura = Decimal('1.05')
        self.config.save()

        self.almacen = crear_almacen(self.empresa, 'Almacén EST-02')
        self.cliente = Contacto.objects.create(
            empresa=self.empresa, nombre='Cliente EST-02', tipo='CLIENTE',
            identificacion='V-EST02-CAB',
        )
        self.proveedor = Contacto.objects.create(
            empresa=self.empresa, nombre='Proveedor EST-02', tipo='PROVEEDOR',
            identificacion='J-EST02-PRV', rif='J-EST02-PRV',
            nombre_asesor='Asesor EST-02',
        )
        self.articulo = crear_articulo_fisico(
            self.empresa, sku='EST02-001', nombre='Artículo EST-02',
        )
        svc.registrar_movimiento(
            self.articulo, self.almacen, 'ENTRADA', Decimal('10'),
            'Inventario Inicial',
        )

        # NE PROCESADO vía el camino legítimo (nace completa: iva incluido).
        self.nota = svc.procesar_venta(
            self.cliente.pk,
            [{'articulo_sku': 'EST02-001', 'cantidad': '2',
              'precio_unitario_usd': '20.00'}],
            self.almacen.pk,
        )

        # DC PROCESADO vía el camino legítimo (nace completa: totales incluidos).
        resp_compra = svc.registrar_compra_proveedor(
            empresa_id=self.empresa.pk,
            proveedor_id=self.proveedor.pk,
            tipo_documento='FACTURA_COMPRA',
            numero_factura='F-EST02-001',
            lista_items=[{'sku': 'EST02-001', 'cantidad': 3,
                          'costo_factura': Decimal('9.50')}],
            almacen_id=self.almacen.pk,
        )
        self.compra = DocumentoCompra.objects.get(
            pk=resp_compra['documento_id'],
        )


class TestCabecerasInmutables(CabecerasInmutablesBase):
    """TASK-EST02-01 — REQ-EST02-01/02/04/05/07.

    La matriz de cabeceras es exactamente {estado, motivo_anulacion} con
    transición única PROCESADO→ANULADO (REQ-EST02-02); el resto de campos
    son inmutables tras emisión (Gherkin EST02-05).
    """

    def test_ne_y_dc_campo_fuera_de_matriz_bloqueado(self):
        """Gherkin EST02-05: mutar un campo ajeno a la matriz lanza
        DocumentoInmutableError y la fila queda intacta."""
        # NE: campo ajeno
        self.nota.moneda_pago = 'BS_EFECTIVO'
        with self.assertRaises(DocumentoInmutableError):
            self.nota.save()
        self.nota.refresh_from_db()
        self.assertEqual(self.nota.moneda_pago, 'USD')

        # DC: campo ajeno
        self.compra.observaciones = 'edición manual'
        with self.assertRaises(DocumentoInmutableError):
            self.compra.save()
        self.compra.refresh_from_db()
        self.assertEqual(self.compra.observaciones, '')

    def test_anulado_es_documento_cerrado(self):
        """Gherkin EST02-04: la anulación legítima funciona; después el
        documento está CERRADO — ni reabrir estado ni retocar el motivo."""
        svc.reversar_nota_entrega(
            self.empresa.pk, self.nota.pk, 'anulación de prueba',
        )
        self.nota.refresh_from_db()
        self.assertEqual(self.nota.estado, 'ANULADO')

        # Reabrir: bloqueado (transición ANULADO→PROCESADO no existe).
        self.nota.estado = 'PROCESADO'
        with self.assertRaises(DocumentoInmutableError):
            self.nota.save()

        # Motivo fuera de la transición: bloqueado (documento cerrado).
        self.nota.refresh_from_db()
        self.nota.motivo_anulacion = 'otro motivo'
        with self.assertRaises(DocumentoInmutableError):
            self.nota.save(update_fields=['motivo_anulacion'])

    def test_resave_idempotente_ok_y_update_fields_ajenos_bloqueados(self):
        """Gherkin EST02-06: re-save sin cambios pasa; update_fields ajeno
        a la matriz se bloquea AUNQUE el valor no cambie."""
        # Re-save idempotente de NE y DC: sin cambios → permitido.
        self.nota.save()
        self.compra.save()

        # update_fields ajeno con valor idéntico: bloqueado.
        with self.assertRaises(DocumentoInmutableError):
            self.nota.save(update_fields=['observaciones'])

    def test_devolucion_fallida_rollback_limpio_sin_guard(self):
        """REQ-EST02-05 (RED net del dead code): la devolución fallida lanza
        la excepción ORIGINAL (ValueError) — no DocumentoInmutableError del
        nc.delete() muerto — y el rollback atómico no deja NC huérfanas."""
        det = self.nota.detalles.first()
        with self.assertRaises(ValueError) as ctx:
            svc.procesar_devolucion_venta(
                self.empresa.pk,
                self.nota.pk,
                [{'detalle_id': det.pk, 'cantidad_devolver': Decimal('99')}],
                motivo='excede pendiente',
            )
        # El mensaje de la excepción original sobrevive (no hay masking).
        self.assertIn('No se pueden devolver', str(ctx.exception))

        # Rollback atómico: 0 NC y 0 detalles NC huérfanos.
        self.assertEqual(NotaCredito.global_objects.count(), 0)
        self.assertEqual(DetalleNotaCredito.objects.count(), 0)


class TestDetallesInmutables(CabecerasInmutablesBase):
    """TASK-EST02-02 — REQ-EST02-03/04/10.

    La matriz de líneas es VACÍA: precio_base y snapshots no mutan tras
    emisión (Gherkin EST02-02); los borrados de cabecera/línea quedan
    bloqueados vía pre_delete (Gherkin EST02-03); el re-save idempotente
    pasa (Gherkin EST02-08); y la devolución NO muta la línea origen —
    el "writer" de ``cantidad_devuelta_acumulada`` es el INSERT de
    DetalleNotaCredito, no un update de la fila (REQ-EST02-10).

    Nota TDD: esta clase certifica el wiring cableado en TASK-EST02-01
    (pre_save de los 3 Detalle* + pre_delete de los 6) — nace verde por
    diseño, como TestKardexCaminoLegitimo en EST-01.
    """

    def setUp(self):
        super().setUp()
        det = self.nota.detalles.first()
        self.resp_devolucion = svc.procesar_devolucion_venta(
            self.empresa.pk,
            self.nota.pk,
            [{'detalle_id': det.pk, 'cantidad_devolver': Decimal('1')}],
            motivo='devolución parcial de prueba',
        )
        self.nc = NotaCredito.objects.get(pk=self.resp_devolucion['nc_id'])
        self.det_nc = DetalleNotaCredito.objects.get(
            pk=self.resp_devolucion['detalles_ids'][0],
        )
        self.detalle = DetalleNotaEntrega.objects.get(pk=det.pk)

    def test_detalle_precio_y_snapshot_bloqueados(self):
        """Gherkin EST02-02: mutar precio/snapshot de una línea emitida
        lanza DocumentoInmutableError y la fila queda intacta."""
        # Línea de venta: precio snapshot
        self.detalle.precio_base = Decimal('999')
        with self.assertRaises(DocumentoInmutableError):
            self.detalle.save()
        self.detalle.refresh_from_db()
        self.assertEqual(self.detalle.precio_base, Decimal('20.0000'))

        # Línea de NC: snapshot negociado
        self.det_nc.precio_unitario_snapshot = Decimal('1')
        with self.assertRaises(DocumentoInmutableError):
            self.det_nc.save()
        self.det_nc.refresh_from_db()
        self.assertEqual(
            self.det_nc.precio_unitario_snapshot, Decimal('20.0000'),
        )

    def test_deletes_de_cabecera_y_detalles_bloqueados(self):
        """Gherkin EST02-03: borrado de línea, cabecera, NC y bulk — todos
        bloqueados; nada se pierde (pre_delete por instancia en bulk/cascada).

        Orden real de Django (precedente EST-01, test_kardex_inmutable): el
        collector valida los FK PROTECT preexistentes durante collect(),
        ANTES de enviar pre_delete — sobre un documento con devolución el
        ProtectedError de DetalleNotaCredito.detalle_origen_venta aborta
        primero y el guard queda como backstop. Sobre un documento LIMPIO
        (sin NC) collect() completa y el pre_delete del guard es quien
        aborta: ese es el camino de certificación directa del wiring.

        Patrón savepoint (test_kardex_inmutable): el raise dentro del
        atomic del collector marca needs_rollback de la transacción
        exterior — lo aislamos con transaction.atomic() propio.
        """
        # (a) Documento LIMPIO (sin devoluciones): el guard aborta en pre_delete.
        nota_limpia = svc.procesar_venta(
            self.cliente.pk,
            [{'articulo_sku': 'EST02-001', 'cantidad': '1',
              'precio_unitario_usd': '20.00'}],
            self.almacen.pk,
        )
        with self.assertRaises(DocumentoInmutableError):
            with transaction.atomic():
                nota_limpia.detalles.all().delete()
        self.assertEqual(
            nota_limpia.detalles.count(), 1, 'las líneas del doc limpio persisten',
        )

        with self.assertRaises(DocumentoInmutableError):
            with transaction.atomic():
                nota_limpia.delete()
        self.assertTrue(
            NotaEntrega.objects.filter(pk=nota_limpia.pk).exists(),
            'la cabecera del doc limpio persiste',
        )

        # (b) Documento CON devolución (el del setUp): ProtectedError (FK
        # preexistente) o DocumentoInmutableError (backstop) — ambos
        # abortan completo sin tocar filas.
        with self.assertRaises((ProtectedError, DocumentoInmutableError)):
            with transaction.atomic():
                self.nota.detalles.all().delete()
        self.assertEqual(self.nota.detalles.count(), 1, 'las líneas persisten')

        with self.assertRaises((ProtectedError, DocumentoInmutableError)):
            with transaction.atomic():
                self.nota.delete()
        self.assertTrue(
            NotaEntrega.objects.filter(pk=self.nota.pk).exists(),
            'la cabecera persiste',
        )

        # NC: pre_delete conectado desde TASK-01 (su pre_save llega en TASK-04).
        # Su cascada no arrastra filas PROTECT-adas → el guard aborta directo.
        with self.assertRaises(DocumentoInmutableError):
            with transaction.atomic():
                self.nc.delete()
        self.assertTrue(NotaCredito.objects.filter(pk=self.nc.pk).exists())

        # Bulk de cabeceras: idéntico abort (guard o PROTECT según el camino).
        with self.assertRaises((ProtectedError, DocumentoInmutableError)):
            with transaction.atomic():
                NotaEntrega.objects.all().delete()
        self.assertEqual(
            NotaEntrega.objects.count(), 2, 'el bulk aborta completo',
        )

    def test_resave_idempotente_detalle_nc_y_origen_intacto(self):
        """Gherkin EST02-08 + REQ-EST02-10: re-save idempotente de la línea
        NC (sus derivados se recalculan de entradas idénticas → diff vacío)
        y de la línea origen tras la devolución (que NO la mutó)."""
        # DetalleNotaCredito: save() recalcula derivados deterministas → OK.
        det_nc_fresco = DetalleNotaCredito.objects.get(pk=self.det_nc.pk)
        det_nc_fresco.save()

        # DetalleNotaEntrega origen: la devolución insertó una fila NC nueva,
        # no tocó esta → re-save idempotente OK.
        detalle_origen_fresco = DetalleNotaEntrega.objects.get(
            pk=self.detalle.pk,
        )
        detalle_origen_fresco.save()

        # La propiedad acumula lo devuelto SIN columna y SIN mutación:
        # 1 unidad devuelta sobre 2 vendidas.
        self.assertEqual(
            detalle_origen_fresco.cantidad_devuelta_acumulada, Decimal('1.0000'),
        )
        self.assertEqual(
            detalle_origen_fresco.cantidad_pendiente_devolver, Decimal('1'),
        )


class TestAdminDocumentosReadonly(CabecerasInmutablesBase):
    """TASK-EST02-03 — REQ-EST02-08.

    El admin de documentos emitidos es SOLO LECTURA total: add/change/delete
    prohibidos, view conservado para quien ya lo tenía, todos los campos
    readonly en el detalle. Cierra el vector "anular sin reversar stock"
    que hoy permite editar ``estado`` a mano desde /admin/ (el guard de
    TASK-01 queda como backstop del ORM, no como UX).
    """

    @staticmethod
    def _superuser():
        from django.contrib.auth.models import User

        return User.objects.create_superuser(
            'est02admin', 'est02@example.com', 'pw-est02',
        )

    def test_admins_documentos_permisos_readonly_totales(self):
        from django.contrib import admin as dj_admin
        from django.test import RequestFactory

        request = RequestFactory().get('/admin/')
        request.user = self._superuser()

        casos = [
            (NotaEntrega, self.nota),
            (DetalleNotaEntrega, self.nota.detalles.first()),
            (DocumentoCompra, self.compra),
        ]
        for modelo, obj in casos:
            model_admin = dj_admin.site._registry[modelo]
            with self.subTest(admin=model_admin.__class__.__name__):
                self.assertFalse(
                    model_admin.has_add_permission(request),
                    'add prohibido: el documento nace vía services',
                )
                self.assertFalse(
                    model_admin.has_change_permission(request, obj),
                    'change prohibido: registro histórico',
                )
                self.assertFalse(
                    model_admin.has_delete_permission(request, obj),
                    'delete prohibido: REQ-EST02-04',
                )
                self.assertTrue(
                    model_admin.has_view_permission(request, obj),
                    'view conservado para quien ya lo tenía',
                )
                readonly = model_admin.get_readonly_fields(request, obj)
                nombres_concretos = {
                    f.name for f in modelo._meta.concrete_fields
                }
                self.assertTrue(
                    nombres_concretos.issubset(set(readonly)),
                    'todos los campos concretos deben ser readonly',
                )
        # El vector crítico, explícito:
        ne_admin = dj_admin.site._registry[NotaEntrega]
        self.assertIn('estado', ne_admin.get_readonly_fields(request, self.nota))
        self.assertIn('motivo_anulacion', ne_admin.get_readonly_fields(request, self.nota))

        # El inline de detalles no ofrece checkbox de borrado.
        self.assertFalse(DetalleNotaEntregaInline.can_delete)

    def test_admin_post_no_anula_sin_reversar_stock(self):
        """Gherkin EST02-10: un POST forzado al change view de una NE no
        cambia el estado ni toca el stock — la anulación pasa por
        services.reversar_nota_entrega o no ocurre."""
        from django.contrib.auth.models import User

        superuser = User.objects.create_superuser(
            'est02post', 'post@example.com', 'pw-est02',
        )
        self.client.force_login(superuser)
        url = f'/admin/inventory/notaentrega/{self.nota.pk}/change/'
        stock_antes = self.articulo.get_stock_disponible(self.almacen)

        # Smoke del plan (TASK-03) — ADAPTADO POR BLOQUEO PREEXISTENTE (A/B):
        # el changelist/detalle GET NO se aserta aquí. Todo changelist del
        # admin 500-ea en este entorno por un bug AJENO a EST-02:
        # AttributeError 'RequestContext' object has no attribute 'template'
        # (django/template/base.py:171 vía inclusion tags del admin) con
        # Django 6.0.6 + Python 3.14.8. Evidencia A/B 2026-10-24: falla IGUAL
        # en el árbol limpio 7fe7905 (admin VIEJO, sin documentos, con
        # superuser recién creado) y también en el changelist stock de
        # /admin/auth/user/; /admin/ (dashboard) da 200. La suite base 512
        # no lo detectó porque NINGÚN test existente hace GET a un
        # changelist. El vector que EST-02 cierra (POST de anulación sin
        # reversar stock) no requiere render: el POST con change=False
        # responde 403 SIN tocar plantillas ni el ORM — verificado.

        response = self.client.post(url, {
            'estado': 'ANULADO',
            'motivo_anulacion': 'anulación por panel',
        })

        # Sin change permission el admin responde 403 (PermissionDenied),
        # nunca llega al form ni al ORM.
        self.assertEqual(response.status_code, 403)

        # La fila sigue PROCESADO y el stock queda INTACTO (antes == después
        # del POST: ni reverso ni mutación alguna).
        self.nota.refresh_from_db()
        self.assertEqual(self.nota.estado, 'PROCESADO')
        self.assertEqual(
            self.articulo.get_stock_disponible(self.almacen), stock_antes,
            'el stock no se reversa: no hubo anulación real',
        )


class TestNotaCreditoPreCreate(CabecerasInmutablesBase):
    """TASK-EST02-04 — REQ-EST02-06/07 (cierre del capítulo §5).

    La NC nace COMPLETA: ``monto_total_reembolso`` definitivo en el
    ``create`` (doble pasada: validar+calcular → persistir), sin el tail
    ``nc.save(update_fields=...)`` que mutaba una NC ya emitida — campo
    fuera de la matriz EST-02 — y sin el dead code ``nc.delete()``.

    El gate de fuente (patrón test_calculos.py) es la RED neta del §5:
    obliga a que los montos se computen ANTES del create vía el helper
    compartido ``calculos.calcular_linea_devolucion`` (fuente única con
    ``DetalleNotaCredito.save()``, DATA-01). Los esperados se computan A
    MANO (fórmula del modelo, cuantizada a 4 decimales) para no acoplarse
    al helper que el propio gate exige.
    """

    _Q = Decimal('0.0001')

    def setUp(self):
        super().setUp()
        # Segundo artículo para una venta multi-línea (el override de
        # precio/iva se negocia en la devolución, no en la venta).
        self.articulo_b = crear_articulo_fisico(
            self.empresa, sku='EST02-002', nombre='Artículo EST-02 B',
        )
        svc.registrar_movimiento(
            self.articulo_b, self.almacen, 'ENTRADA', Decimal('10'),
            'Inventario Inicial',
        )
        self.nota_2items = svc.procesar_venta(
            self.cliente.pk,
            [
                {'articulo_sku': 'EST02-001', 'cantidad': '2',
                 'precio_unitario_usd': '20.00'},
                {'articulo_sku': 'EST02-002', 'cantidad': '3',
                 'precio_unitario_usd': '10.00'},
            ],
            self.almacen.pk,
        )

    def test_nc_nace_con_monto_definitivo_sin_segundo_save(self):
        """La NC de venta y de compra nacen con el monto definitivo; no hay
        nc.save() posterior al create ni nc.delete(); y la NC emitida
        re-salva idempotente con su pre_save YA conectado (§2, matriz
        {estado, motivo_anulacion})."""
        import inspect

        # Arrange: devolución de 2 líneas — la 2ª con override de precio+iva.
        dets = list(self.nota_2items.detalles.all().order_by('id'))
        det_a, det_b = dets

        # Act: la NC de venta.
        resp = svc.procesar_devolucion_venta(
            self.empresa.pk,
            self.nota_2items.pk,
            [
                {'detalle_id': det_a.pk, 'cantidad_devolver': '1'},
                {'detalle_id': det_b.pk, 'cantidad_devolver': '2',
                 'precio_unitario': '12.50', 'iva_porcentaje': '8'},
            ],
            motivo='NC pre-create venta',
        )
        nc = NotaCredito.objects.get(pk=resp['nc_id'])

        # Esperado a mano — MISMA fórmula que DetalleNotaCredito.save():
        # línea A con los snapshots del detalle; línea B con el override.
        sub_a = (Decimal('1') * det_a.precio_base).quantize(self._Q)
        iva_a = (sub_a * (det_a.iva_porcentaje or 0) / Decimal('100')).quantize(self._Q)
        sub_b = (Decimal('2') * Decimal('12.50')).quantize(self._Q)
        iva_b = (sub_b * Decimal('8') / Decimal('100')).quantize(self._Q)
        esperado_venta = (sub_a + iva_a).quantize(self._Q) + (sub_b + iva_b).quantize(self._Q)

        # Assert: el monto nació definitivo y cuadra por partida doble.
        self.assertEqual(nc.monto_total_reembolso, esperado_venta)
        self.assertEqual(
            nc.monto_total_reembolso,
            sum(d.linea_total_usd for d in nc.detalles.all()),
            'monto de cabecera == Σ linea_total_usd de sus detalles',
        )

        # Act: la NC de compra (1 línea, snapshots del detalle de compra).
        det_compra = self.compra.detalles.first()
        resp_c = svc.procesar_devolucion_compra(
            self.empresa.pk,
            self.compra.pk,
            [{'detalle_id': det_compra.pk, 'cantidad_devolver': '1'}],
            motivo='NC pre-create compra',
        )
        nc_c = NotaCredito.objects.get(pk=resp_c['nc_id'])

        sub_c = (Decimal('1') * det_compra.costo_base).quantize(self._Q)
        iva_c = (sub_c * (det_compra.iva_porcentaje or 0) / Decimal('100')).quantize(self._Q)
        esperado_compra = (sub_c + iva_c).quantize(self._Q)

        self.assertEqual(nc_c.monto_total_reembolso, esperado_compra)
        self.assertEqual(
            nc_c.monto_total_reembolso,
            sum(d.linea_total_usd for d in nc_c.detalles.all()),
        )

        # Gate de fuente (§5): el create lleva el monto; NO hay segundo
        # save ni dead code; el helper compartido es quien computa.
        for funcion in (svc.procesar_devolucion_venta, svc.procesar_devolucion_compra):
            fuente = inspect.getsource(funcion)
            with self.subTest(gate=funcion.__name__):
                self.assertIn('monto_total_reembolso=', fuente,
                              'la NC nace con monto en el create')
                self.assertIn('calcular_linea_devolucion(', fuente,
                              'montos pre-create vía helper único (DATA-01)')
                self.assertNotIn('nc.save(', fuente,
                                 'tail nc.save(update_fields=...) eliminado')
                self.assertNotIn('nc.delete()', fuente,
                                 'dead code nc.delete() eliminado')

        # La NC emitida re-salva idempotente con pre_save CONECTADO (§2):
        # matriz {estado, motivo_anulacion} — sin cambios → diff vacío.
        nc_fresca = NotaCredito.objects.get(pk=nc.pk)
        nc_fresca.save()
        nc_fresca.refresh_from_db()
        self.assertEqual(nc_fresca.monto_total_reembolso, esperado_venta)
