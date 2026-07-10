"""
inventory/urls.py
=================
Mapa de URLs de la app inventory — A2LT Stock.
"""

from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    # ── Vistas generales ─────────────────────────────────────────────────────
    path('', views.login_view, name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
    path('cambiar-empresa/', views.cambiar_empresa_view, name='cambiar_empresa'),
    path('catalogo/', views.catalogo, name='catalogo'),
    path('ventas/', views.ventas, name='ventas'),
    path('compras/', views.compras_view, name='compras'),
    path('compras/registrar/', views.registrar_compra_api, name='registrar_compra_api'),
    path('movimientos/', views.vista_movimientos, name='movimientos'),
    path('movimientos/registrar/', views.vista_registrar_asiento_manual, name='registrar_asiento_manual'),
    path('contactos/', views.contactos, name='contactos'),
    path('articulos/', views.articulos_view, name='articulos'),
    path('configuracion/', views.configuracion_view, name='configuracion'),
    path('reversos/', views.reversos_view, name='reversos'),
    path('api/reversar-venta/', views.api_reversar_venta, name='api_reversar_venta'),
    path('api/reversar-compra/', views.api_reversar_compra, name='api_reversar_compra'),
    # ── Ticket #3: Carga Masiva ───────────────────────────────────────────────
    path('carga/', views.vista_carga_masiva, name='carga_masiva'),
    path('carga/excel/', views.vista_carga_masiva_excel, name='carga_masiva_excel'),
    path('carga/resolver/', views.vista_resolver_colision, name='resolver_colision'),
    path('carga/plantilla/', views.vista_descargar_plantilla, name='descargar_plantilla'),

    # ── Ticket #5: Ventas ─────────────────────────────────────────────────────
    path('catalogo/buscar/', views.api_buscar_articulos, name='buscar_articulos'),
    path('ventas/validar_stock/<str:sku>/<int:almacen_id>/', views.api_validar_stock, name='validar_stock'),
    path('ventas/crear/', views.vista_crear_venta, name='crear_venta'),
    path('ventas/seriales/<str:articulo_sku>/<int:almacen_id>/', views.vista_buscar_seriales_articulo, name='buscar_seriales'),
    path('ventas/<int:nota_id>/imprimir/', views.vista_imprimir_nota, name='imprimir_nota'),
    path('ventas/<int:nota_id>/imprimir-coordenadas/', views.vista_imprimir_coordenadas, name='imprimir_coordenadas'),

    # Tasas
    path('tasas/sincronizar/', views.vista_sincronizar_tasa, name='sincronizar_tasa'),

    # ── Ticket #13: Exportación ───────────────────────────────────────────────
    path('respaldo/', views.vista_exportar_respaldo, name='exportar_respaldo'),

    # ── Fase 4: Reportes ───────────────────────────────────────────────────────
    path('reportes/', views.vista_reportes, name='reportes'),
    path('reportes/<str:nombre>/', views.vista_reporte_detalle, name='reporte_detalle'),
]
