"""
inventory/admin.py
==================
Registro de todos los modelos en el panel de administración de Django.
Configura list_display, search_fields y filtros para facilitar la
gestión operativa directa desde /admin/.
"""

import re
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import (
    Empresa,
    ConfiguracionEmpresa,
    PerfilUsuario,
    Almacen,
    Articulo,
    InventarioAlmacen,
    RecetaCombo,
    Contacto,
    Cliente,
    Proveedor,
    MovimientoKardex,
    AuditoriaTasa,
    NotaEntrega,
    DetalleNotaEntrega,
    SerialArticulo,
    DocumentoCompra,
)
from .forms import ArticuloAdminForm

# ─────────────────────────────────────────────────────────────────────────────
# MIXINS GLOBALES
# ─────────────────────────────────────────────────────────────────────────────

class TenantGlobalAdminMixin:
    """
    Mixin para evadir el EmpresaManager estricto en el Django Admin.
    Permite a los superusuarios ver todos los registros usando global_objects.
    """
    def get_queryset(self, request):
        if hasattr(self.model, 'global_objects'):
            return self.model.global_objects.all()
        return super().get_queryset(request)


# ─────────────────────────────────────────────────────────────────────────────
# 0. CONTROL DE USUARIOS Y PERFILES (RBAC)
# ─────────────────────────────────────────────────────────────────────────────

class PerfilUsuarioInline(admin.StackedInline):
    model = PerfilUsuario
    can_delete = False
    verbose_name_plural = 'Perfil de Acceso Multi-Tenant'
    fk_name = 'user'
    filter_horizontal = ('empresas_permitidas',)

class CustomUserAdmin(UserAdmin):
    inlines = (PerfilUsuarioInline, )
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_empresas')
    
    def get_empresas(self, instance):
        if hasattr(instance, 'perfil'):
            count = instance.perfil.empresas_permitidas.count()
            return f"{count} asignadas"
        return "Sin perfil"
    get_empresas.short_description = 'Empresas Permitidas'

# Re-registrar UserAdmin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


# ─────────────────────────────────────────────────────────────────────────────
# EMPRESA Y CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'rif', 'telefono', 'correo', 'activa', 'fecha_registro')
    search_fields = ('nombre', 'rif', 'correo')
    list_filter = ('activa',)
    fieldsets = (
        ('Datos Principales', {
            'fields': ('nombre', 'rif', 'activa')
        }),
        ('Información de Contacto', {
            'fields': ('direccion', 'telefono', 'correo')
        })
    )

@admin.register(ConfiguracionEmpresa)
class ConfiguracionEmpresaAdmin(TenantGlobalAdminMixin, admin.ModelAdmin):
    list_display = ('empresa', 'tasa_bcv', 'tasa_mercado')
    search_fields = ('empresa__nombre', 'empresa__rif')
    fieldsets = (
        ('Parámetros Financieros Globales', {
            'fields': (
                'tasa_bcv', 'tasa_mercado', 'factor_cobertura',
                'margen_global', 'descuento_global',
            ),
        }),
        ('Motor de API de Tasas', {
            'classes': ('collapse',),
            'fields': ('api_url', 'http_method', 'response_selector'),
        }),
    )

    def has_add_permission(self, request):
        """Bloquea la creación manual de configuración para evitar IntegrityError (TICKET #17)."""
        return False


# ─────────────────────────────────────────────────────────────────────────────
# ALMACENES
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Almacen)
class AlmacenAdmin(TenantGlobalAdminMixin, admin.ModelAdmin):
    list_display = ('nombre', 'es_principal', 'activo')
    list_filter = ('es_principal', 'activo')
    search_fields = ('nombre',)


# ─────────────────────────────────────────────────────────────────────────────
# ARTÍCULOS
# ─────────────────────────────────────────────────────────────────────────────

class RecetaComboInline(admin.TabularInline):
    """Inline de componentes visibles desde la ficha del artículo COMBO."""
    model = RecetaCombo
    fk_name = 'combo'
    extra = 1
    autocomplete_fields = ['componente']

class SerialArticuloInline(admin.TabularInline):
    """Inline para cargar seriales directamente en el artículo físico."""
    model = SerialArticulo
    fk_name = 'articulo'
    extra = 1
    fields = ('serial', 'almacen', 'estado', 'detalle_nota')
    autocomplete_fields = ['almacen', 'detalle_nota']

@admin.register(Articulo)
class ArticuloAdmin(TenantGlobalAdminMixin, admin.ModelAdmin):
    form = ArticuloAdminForm
    list_display = ('sku', 'nombre', 'categoria', 'tipo', 'precio_divisa', 'activo')
    list_filter = ('categoria', 'tipo', 'activo', 'metodo_ganancia')
    search_fields = ('sku', 'nombre', 'codigo_proveedor')
    list_editable = ('activo',)
    inlines = [RecetaComboInline, SerialArticuloInline]
    fieldsets = (
        ('Identificación', {
            'fields': ('sku', 'codigo_proveedor', 'nombre', 'categoria', 'tipo', 'usa_serial'),
        }),
        ('Operaciones de Carga Masiva (Opcional)', {
            'classes': ('collapse', 'seriales-masivo-group'),
            'fields': ('almacen_ingreso_seriales', 'carga_masiva_seriales'),
            'description': 'Inserte seriales múltiples separados por saltos de línea o comas.',
        }),
        ('Precios y Márgenes', {
            'fields': (
                'costo', 'precio_divisa', 'metodo_ganancia',
                'margen_ind', 'descuento_ind', 'cobertura_ind',
            ),
        }),
        ('Contenido y Social Selling', {
            'fields': ('descripcion', 'ficha_tecnica', 'social_quick', 'social_cross'),
        }),
        ('Estado', {
            'fields': ('activo',),
        }),
    )
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        
        carga_masiva = form.cleaned_data.get('carga_masiva_seriales')
        almacen_destino = form.cleaned_data.get('almacen_ingreso_seriales')
        
        if carga_masiva and almacen_destino and obj.usa_serial:
            raw_seriales = re.split(r'[\n,\s]+', carga_masiva.strip())
            seriales_limpios = list(set([s.strip() for s in raw_seriales if s.strip()]))
            
            if seriales_limpios:
                seriales_a_crear = [
                    SerialArticulo(
                        empresa=obj.empresa,
                        articulo=obj,
                        serial=serial,
                        almacen=almacen_destino,
                        estado='DISPONIBLE'
                    )
                    for serial in seriales_limpios
                ]
                SerialArticulo.objects.bulk_create(seriales_a_crear)

    def get_inlines(self, request, obj=None):
        inlines = list(super().get_inlines(request, obj))
        if obj:
            if obj.tipo == 'FISICO' and RecetaComboInline in inlines:
                inlines.remove(RecetaComboInline)
            if not getattr(obj, 'usa_serial', False) and SerialArticuloInline in inlines:
                inlines.remove(SerialArticuloInline)
        return tuple(inlines)

    class Media:
        js = ('inventory/js/admin_articulo.js',)

@admin.register(SerialArticulo)
class SerialArticuloAdmin(TenantGlobalAdminMixin, admin.ModelAdmin):
    list_display = ('serial', 'articulo', 'almacen', 'estado', 'detalle_nota')
    list_filter = ('estado', 'almacen')
    search_fields = ('serial', 'articulo__nombre', 'articulo__sku')
    autocomplete_fields = ['articulo', 'almacen', 'detalle_nota']


# ─────────────────────────────────────────────────────────────────────────────
# INVENTARIO POR ALMACÉN
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(InventarioAlmacen)
class InventarioAlmacenAdmin(TenantGlobalAdminMixin, admin.ModelAdmin):
    list_display = (
        'articulo', 'almacen', 'cantidad_disponible',
        'ubicacion_estante', 'fecha_ultima_actualizacion',
    )
    list_filter = ('almacen',)
    search_fields = ('articulo__sku', 'articulo__nombre', 'almacen__nombre')
    readonly_fields = ('fecha_ultima_actualizacion',)

    def has_add_permission(self, request):
        """
        Deshabilita la creación manual desde el admin.
        El inventario solo se puede crear via carga masiva o servicios.
        """
        return False

    def has_change_permission(self, request, obj=None):
        """
        Deshabilita la edición directa del stock desde el admin.
        Todo cambio debe pasar por MovimientoKardex.
        """
        return False


# ─────────────────────────────────────────────────────────────────────────────
# RECETA DE COMBOS
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(RecetaCombo)
class RecetaComboAdmin(TenantGlobalAdminMixin, admin.ModelAdmin):
    list_display = ('combo', 'componente', 'cantidad_requerida')
    search_fields = ('combo__nombre', 'componente__nombre')
    autocomplete_fields = ['combo', 'componente']


# ─────────────────────────────────────────────────────────────────────────────
# CONTACTOS
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Cliente)
class ClienteAdmin(TenantGlobalAdminMixin, admin.ModelAdmin):
    list_display = ('identificacion', 'nombre', 'telefono', 'correo')
    search_fields = ('identificacion', 'nombre', 'telefono', 'correo', 'red_social')
    fieldsets = (
        ('Datos Principales', {
            'fields': ('identificacion', 'nombre'),
        }),
        ('Información de Contacto', {
            'fields': ('telefono', 'correo', 'red_social', 'direccion'),
        }),
        ('Observaciones', {
            'fields': ('observaciones',),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(tipo='CLIENTE')


@admin.register(Proveedor)
class ProveedorAdmin(TenantGlobalAdminMixin, admin.ModelAdmin):
    list_display = ('identificacion', 'nombre', 'rif', 'nombre_asesor', 'telefono', 'correo')
    search_fields = ('identificacion', 'nombre', 'telefono', 'correo', 'rif')
    list_filter = ('rif',)
    fieldsets = (
        ('Datos Principales', {
            'fields': ('identificacion', 'nombre'),
        }),
        ('Datos Fiscales del Proveedor', {
            'fields': ('rif', 'nombre_asesor'),
        }),
        ('Información de Contacto', {
            'fields': ('telefono', 'correo', 'red_social', 'direccion'),
        }),
        ('Observaciones', {
            'fields': ('observaciones',),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(tipo='PROVEEDOR')


@admin.register(Contacto)
class ContactoAdmin(TenantGlobalAdminMixin, admin.ModelAdmin):
    list_display = ('identificacion', 'nombre', 'tipo', 'telefono', 'correo')
    list_filter = ('tipo',)
    search_fields = ('identificacion', 'nombre', 'telefono', 'correo', 'red_social')

    def has_module_permission(self, request):
        return False


# ─────────────────────────────────────────────────────────────────────────────
# KÁRDEX (Solo lectura — registro inalterable)
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(MovimientoKardex)
class MovimientoKardexAdmin(TenantGlobalAdminMixin, admin.ModelAdmin):
    list_display = (
        'fecha_hora', 'articulo', 'almacen', 'tipo',
        'concepto', 'cantidad', 'saldo_resultante',
    )
    list_filter = ('tipo', 'concepto', 'almacen')
    search_fields = ('articulo__sku', 'articulo__nombre', 'lote_carga')
    readonly_fields = (
        'fecha_hora', 'articulo', 'almacen', 'tipo', 'concepto',
        'cantidad', 'saldo_resultante', 'nota_entrega',
        'lote_carga', 'detalle_adicional', 'usuario',
    )
    date_hierarchy = 'fecha_hora'

    def has_add_permission(self, request):
        """El Kárdex es de solo lectura — Regla Sagrada."""
        return False

    def has_change_permission(self, request, obj=None):
        """El Kárdex es inalterable — Regla Sagrada."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Los registros del Kárdex no pueden eliminarse."""
        return False


# ─────────────────────────────────────────────────────────────────────────────
# AUDITORÍA DE TASAS
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(AuditoriaTasa)
class AuditoriaTasaAdmin(TenantGlobalAdminMixin, admin.ModelAdmin):
    list_display = ('fecha_hora', 'tasa_bcv', 'tasa_mercado', 'factor_cobertura', 'fuente')
    list_filter = ('fuente',)
    readonly_fields = ('fecha_hora',)
    date_hierarchy = 'fecha_hora'


# ─────────────────────────────────────────────────────────────────────────────
# NOTAS DE ENTREGA
# ─────────────────────────────────────────────────────────────────────────────

class DetalleNotaEntregaInline(admin.TabularInline):
    model = DetalleNotaEntrega
    extra = 0
    readonly_fields = ('subtotal_usd', 'subtotal_bs')


@admin.register(NotaEntrega)
class NotaEntregaAdmin(TenantGlobalAdminMixin, admin.ModelAdmin):
    list_display = ('numero', 'fecha', 'cliente', 'almacen', 'estado', 'moneda_pago')
    list_filter = ('estado', 'moneda_pago', 'almacen')
    search_fields = ('numero', 'cliente__nombre', 'cliente__identificacion')
    readonly_fields = ('numero', 'fecha', 'tasa_bcv_aplicada', 'factor_cobertura_aplicado')
    inlines = [DetalleNotaEntregaInline]
    date_hierarchy = 'fecha'


@admin.register(DetalleNotaEntrega)
class DetalleNotaEntregaAdmin(TenantGlobalAdminMixin, admin.ModelAdmin):
    list_display = (
        'nota_entrega', 'articulo', 'cantidad',
        'precio_unitario_usd', 'descuento_aplicado',
    )
    search_fields = ('nota_entrega__numero', 'articulo__nombre', 'articulo__sku')


# ─────────────────────────────────────────────────────────────────────────────
# 12. DOCUMENTO DE COMPRA (TICKET #19)
# ─────────────────────────────────────────────────────────────────────────────

class MovimientoKardexCompraInline(admin.TabularInline):
    model = MovimientoKardex
    fk_name = 'documento_compra'
    extra = 0
    can_delete = False
    fields = ('articulo', 'almacen', 'cantidad', 'saldo_resultante', 'fecha_hora')
    readonly_fields = fields

    def has_add_permission(self, request, obj):
        return False

@admin.register(DocumentoCompra)
class DocumentoCompraAdmin(TenantGlobalAdminMixin, admin.ModelAdmin):
    list_display = ('numero_factura', 'proveedor', 'fecha_compra', 'monto_total_usd')
    list_filter = ('fecha_compra', 'proveedor')
    search_fields = ('numero_factura', 'proveedor__nombre', 'proveedor__rif')
    autocomplete_fields = ['proveedor']
    inlines = [MovimientoKardexCompraInline]
    readonly_fields = ('fecha_registro',)
