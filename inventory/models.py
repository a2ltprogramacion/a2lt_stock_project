"""
inventory/models.py
===================
Motor de datos core del sistema A2LT Stock.

Contiene todos los modelos de base de datos definidos en el Ticket #1
según las decisiones arquitectónicas aprobadas (ADR-01 a ADR-06):

  - ConfiguracionSistema  (Singleton global, ADR-04)
  - Almacen
  - Articulo              (con soft-delete, ADR-03)
  - InventarioAlmacen     (tabla intermedia M2M con DecimalField, ADR-02)
  - RecetaCombo
  - Contacto              (clientes + proveedores unificados, ADR-05)
  - MovimientoKardex      (registro inalterable, Regla Sagrada)
  - AuditoriaTasa
  - NotaEntrega
  - DetalleNotaEntrega

REGLA SAGRADA: Ningún campo de stock se modifica directamente.
Todo cambio de existencias debe originarse desde MovimientoKardex
dentro de un bloque @transaction.atomic (implementado en services.py).
"""

import math
from decimal import Decimal

from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from .managers import EmpresaManager


# ─────────────────────────────────────────────────────────────────────────────
# 1. EMPRESA Y CONFIGURACIÓN (SaaS Multi-Tenant)
# ─────────────────────────────────────────────────────────────────────────────

class Empresa(models.Model):
    """
    Entidad raíz del modelo SaaS. Cada empresa tiene su propio esquema lógico aislado.
    """
    nombre = models.CharField(max_length=150, verbose_name="Nombre de la Empresa")
    rif = models.CharField(max_length=20, unique=True, verbose_name="RIF / Identificación")
    direccion = models.TextField(blank=True, verbose_name="Dirección Física")
    telefono = models.CharField(max_length=30, blank=True, verbose_name="Teléfono de Contacto")
    correo = models.EmailField(blank=True, verbose_name="Correo de Contacto")
    activa = models.BooleanField(default=True, verbose_name="Activa")
    fecha_registro = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Registro")

    class Meta:
        verbose_name = 'Empresa'
        verbose_name_plural = '01. Empresas'

    def __str__(self):
        return f"[{self.rif}] {self.nombre}"

class ConfiguracionEmpresa(models.Model):
    """
    Configuración individual por inquilino. Reemplaza el antiguo patrón Singleton.
    """
    empresa = models.OneToOneField(
        Empresa, 
        on_delete=models.CASCADE, 
        related_name='configuracion',
        verbose_name='Empresa'
    )

    # -- Parámetros Financieros Globales --
    tasa_bcv = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0.0000,
        verbose_name='Tasa BCV (Bs/$)',
        help_text='Tasa oficial del Banco Central de Venezuela.',
    )
    tasa_mercado = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0.0000,
        verbose_name='Tasa Mercado / Referencia (Bs/$)',
        help_text='Tasa de referencia informal (ej. Binance P2P).',
    )
    factor_cobertura = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=1.0000,
        verbose_name='Factor de Cobertura Cambiaria (Fc)',
        help_text='Calculado como: Tasa Mercado / Tasa BCV.',
    )
    margen_global = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=30.00,
        verbose_name='Margen de Ganancia Global (%)',
    )
    descuento_global = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=5.00,
        verbose_name='Descuento Global (%)',
    )
    prefijo_nota_entrega = models.CharField(
        max_length=20,
        default='NE',
        verbose_name='Prefijo Nota de Entrega',
        help_text='Prefijo alfanumérico fijo para el correlativo. Ej: NE, A2LT-B17.',
    )
    correlativo_inicial_nota = models.PositiveIntegerField(
        default=1,
        verbose_name='Correlativo Inicial Nota',
        help_text='Número inicial del correlativo. Para migraciones puede arrancar desde N.',
    )
    ivas_disponibles = models.JSONField(
        default=list,
        blank=True,
        verbose_name='IVAs Disponibles (%)',
        help_text='Lista de hasta 5 tasas de IVA configurables. Ej: [0, 8, 16].',
    )

    # -- Configuración del Motor de API de Tasas --
    api_url = models.CharField(
        max_length=500,
        blank=True,
        verbose_name='URL de la API de Tasas',
        help_text='Endpoint externo para sincronización automática de tasas.',
    )
    http_method = models.CharField(
        max_length=4,
        choices=[('GET', 'GET'), ('POST', 'POST')],
        default='GET',
        verbose_name='Método HTTP',
    )
    response_selector = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Selector JSON Path',
        help_text='Ruta dentro del JSON de respuesta (ej: data.prices.USDT).',
    )

    # -- Calibración de Impresión por Coordenadas (Ticket #12) --
    print_offset_x = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        verbose_name='Offset X Impresión (mm)',
        help_text='Desplazamiento horizontal global en milímetros.',
    )
    print_offset_y = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        verbose_name='Offset Y Impresión (mm)',
        help_text='Desplazamiento vertical global en milímetros.',
    )
    print_row_spacing = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=5.00,
        verbose_name='Espaciado de Filas (mm)',
        help_text='Distancia vertical entre renglones de productos impresos.',
    )

    # -- Configuración de Devoluciones (Ticket #15-SAAS) --
    usa_almacen_cuarentena = models.BooleanField(
        default=False,
        verbose_name='Usar Almacén de Cuarentena',
        help_text='Desvía las devoluciones a un almacén de Servicio Técnico en lugar de reingresarlas al origen.',
    )

    # -- Textos editables para Social Selling (Cross-Selling) --
    cross_selling_header = models.TextField(
        default='🔥 *SUPER OFERTA CONSOLIDADA A2LT* 🔥\n\nTenemos estos productos listos para ti:\n\n',
        verbose_name='Encabezado Oferta Consolidada',
        help_text='Texto que encabeza el mensaje de oferta consolidada en el Panel de Social Selling.',
    )
    cross_selling_footer = models.TextField(
        default='¡Envíame un mensaje para coordinar tu pedido ahora mismo! 🚀',
        verbose_name='Pie de Oferta Consolidada',
        help_text='Texto que cierra el mensaje de oferta consolidada en el Panel de Social Selling.',
    )

    objects = EmpresaManager()
    global_objects = models.Manager()

    class Meta:
        verbose_name = 'Configuración de la Empresa'
        verbose_name_plural = '02. Configuraciones de la Empresa'

    def __str__(self):
        return f'Configuración: {self.empresa.nombre}'

    def save(self, *args, **kwargs):
        from decimal import Decimal
        
        # Primero asegurar que todo sea Decimal para cálculos limpios
        self.tasa_bcv = Decimal(str(self.tasa_bcv)) if self.tasa_bcv else Decimal('0.0000')
        self.tasa_mercado = Decimal(str(self.tasa_mercado)) if self.tasa_mercado else Decimal('0.0000')
        self.factor_cobertura = Decimal(str(self.factor_cobertura)) if self.factor_cobertura else Decimal('1.0000')

        if self.pk:
            try:
                orig = ConfiguracionEmpresa.global_objects.get(pk=self.pk)
                orig_tasa_bcv = Decimal(str(orig.tasa_bcv))
                orig_tasa_mercado = Decimal(str(orig.tasa_mercado))
                orig_factor_cobertura = Decimal(str(orig.factor_cobertura))
            except ConfiguracionEmpresa.DoesNotExist:
                orig = None
                orig_tasa_bcv = Decimal('0.0000')
                orig_tasa_mercado = Decimal('0.0000')
                orig_factor_cobertura = Decimal('1.0000')
        else:
            orig = None
            orig_tasa_bcv = Decimal('0.0000')
            orig_tasa_mercado = Decimal('0.0000')
            orig_factor_cobertura = Decimal('1.0000')

        if self.tasa_bcv > 0:
            cambio_mercado = (self.tasa_mercado != orig_tasa_mercado)
            cambio_factor = (self.factor_cobertura != orig_factor_cobertura)
            cambio_bcv = (self.tasa_bcv != orig_tasa_bcv)

            if cambio_mercado and not cambio_factor:
                # Modificó solo mercado -> recalcula factor
                self.factor_cobertura = self.tasa_mercado / self.tasa_bcv
            elif cambio_factor and not cambio_mercado:
                # Modificó solo factor -> recalcula mercado
                self.tasa_mercado = self.tasa_bcv * self.factor_cobertura
            elif cambio_bcv:
                # Modificó BCV -> se mantiene el factor, se recalcula mercado
                self.tasa_mercado = self.tasa_bcv * self.factor_cobertura
            else:
                # Si cambió mercado y factor al mismo tiempo o viene inconsistente
                if self.tasa_mercado > 0 and self.tasa_mercado != (self.tasa_bcv * self.factor_cobertura):
                    self.factor_cobertura = self.tasa_mercado / self.tasa_bcv
                elif self.factor_cobertura > 0 and self.tasa_mercado == 0:
                    self.tasa_mercado = self.tasa_bcv * self.factor_cobertura
        else:
            # Prevent ZeroDivisionError and maintain logical state
            self.factor_cobertura = Decimal("1.0000")
            self.tasa_mercado = Decimal("0.0000")

        # Ensure values are rounded properly
        self.tasa_bcv = round(self.tasa_bcv, 4)
        self.tasa_mercado = round(self.tasa_mercado, 4)
        self.factor_cobertura = round(self.factor_cobertura, 4)

        super().save(*args, **kwargs)





# ─────────────────────────────────────────────────────────────────────────────
# 1B. PERFIL DE USUARIO Y CONTROL DE ACCESO (RBAC)
# ─────────────────────────────────────────────────────────────────────────────

class PerfilUsuario(models.Model):
    """
    Extensión del modelo User para control de acceso Multi-Tenant.
    Define a qué empresas tiene acceso el usuario y cuál es la empresa activa.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil', verbose_name='Usuario')
    empresas_permitidas = models.ManyToManyField(Empresa, blank=True, related_name='usuarios_permitidos', verbose_name='Empresas Permitidas')
    empresa_activa = models.ForeignKey(Empresa, on_delete=models.SET_NULL, null=True, blank=True, related_name='usuarios_activos', verbose_name='Empresa Activa')

    class Meta:
        verbose_name = 'Perfil de Usuario'
        verbose_name_plural = '02B. Perfiles de Usuario'

    def __str__(self):
        return f'Perfil de {self.user.username}'

    def clean(self):
        super().clean()
        if self.empresa_activa and self.id:  # self.id ensures ManyToMany is accessible
            # We must be careful because ManyToMany needs an ID before querying
            # To avoid errors during creation, we check if id exists
            if not self.empresas_permitidas.filter(id=self.empresa_activa.id).exists():
                raise ValidationError({
                    'empresa_activa': 'La empresa activa debe estar dentro de las empresas permitidas para este usuario.'
                })

@receiver(post_save, sender=User)
def crear_perfil_usuario(sender, instance, created, **kwargs):
    if created:
        PerfilUsuario.objects.create(user=instance)

@receiver(post_save, sender=User)
def guardar_perfil_usuario(sender, instance, **kwargs):
    if hasattr(instance, 'perfil'):
        instance.perfil.save()


# ─────────────────────────────────────────────────────────────────────────────
# 2. ALMACÉN
# ─────────────────────────────────────────────────────────────────────────────

class Almacen(models.Model):
    """
    Representa una ubicación física de almacenamiento (sucursal, bodega, etc.).
    Cada movimiento de Kárdex debe estar vinculado a un almacén válido.
    """
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='almacenes')
    nombre = models.CharField(
        max_length=100,
        verbose_name='Nombre del Almacén',
        help_text='Identificador corto (ej: Principal, Sucursal Norte).',
    )
    es_principal = models.BooleanField(
        default=False,
        verbose_name='¿Es el Almacén Principal?',
        help_text='El almacén principal se asigna por defecto en importaciones masivas.',
    )
    activo = models.BooleanField(default=True, verbose_name='Activo')

    objects = EmpresaManager()
    global_objects = models.Manager()

    class Meta:
        verbose_name = 'Almacén'
        verbose_name_plural = '03. Almacenes'
        ordering = ['-es_principal', 'nombre']

    def __str__(self):
        sufijo = ' ★' if self.es_principal else ''
        return f'{self.nombre}{sufijo}'


# ─────────────────────────────────────────────────────────────────────────────
# 3. ARTÍCULO
# ─────────────────────────────────────────────────────────────────────────────

class Articulo(models.Model):
    """
    Entidad principal del catálogo de productos.
    Puede ser FISICO (con stock real en almacén) o COMBO (stock calculado dinámicamente).
    Incluye soft-delete (ADR-03) para preservar integridad histórica del Kárdex.
    """

    TIPO_CHOICES = [
        ('FISICO', 'Físico'),
        ('COMBO', 'Combo Virtual'),
    ]
    CATEGORIA_CHOICES = [
        ('HOGAR', 'Hogar'),
        ('HERRAMIENTAS', 'Herramientas'),
        ('SOLARES', 'Solares'),
        ('OTROS', 'Otros'),
    ]
    METODO_GANANCIA_CHOICES = [
        ('MARKUP', 'Markup (sobre el costo)'),
        ('MARGIN', 'Margen Real (sobre el precio de venta)'),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='articulos')

    # -- Identificación --
    sku = models.CharField(
        max_length=50,
        primary_key=True,
        verbose_name='SKU',
        help_text='Código único interno de identificación del artículo.',
    )
    codigo_proveedor = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Código de Proveedor',
    )
    nombre = models.CharField(
        max_length=200,
        verbose_name='Nombre del Artículo',
    )
    categoria = models.CharField(
        max_length=20,
        choices=CATEGORIA_CHOICES,
        default='OTROS',
        verbose_name='Categoría',
    )
    tipo = models.CharField(
        max_length=10,
        choices=TIPO_CHOICES,
        default='FISICO',
        verbose_name='Tipo de Artículo',
    )
    usa_serial = models.BooleanField(
        default=False,
        verbose_name='Usa Serial de Garantía',
        help_text='Indica si este artículo requiere la selección obligatoria de seriales al facturar.',
    )

    # -- Financiero (ADR-02: DecimalField para precisión) --
    costo = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0.0000,
        verbose_name='Costo de Adquisición (USD)',
    )
    precio_divisa = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0.0000,
        verbose_name='Precio en Divisas / Efectivo (USD)',
    )
    metodo_ganancia = models.CharField(
        max_length=10,
        choices=METODO_GANANCIA_CHOICES,
        default='MARKUP',
        verbose_name='Método de Cálculo de Ganancia',
    )
    margen_ind = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=30.00,
        verbose_name='Margen / Markup Individual (%)',
        help_text='Sobrescribe el margen global para este artículo.',
    )
    descuento_ind = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=5.00,
        verbose_name='Descuento Individual (%)',
    )
    cobertura_ind = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='Factor de Cobertura Individual (Fc)',
        help_text='Si se configura, sobrescribe el Fc global del sistema.',
    )
    iva_porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=16.00,
        verbose_name='IVA del Artículo (%)',
        help_text='Editable sólo por usuarios superiores en la Ficha. '
                  'Snapshot inmutable al facturar.',
    )

    # -- Textos de Contenido y Social Selling --
    descripcion = models.TextField(
        blank=True,
        verbose_name='Descripción General',
    )
    ficha_tecnica = models.TextField(
        null=True,
        blank=True,
        verbose_name='Ficha Técnica',
        help_text='Especificaciones físicas y técnicas detalladas del artículo.',
    )
    social_quick = models.TextField(
        null=True,
        blank=True,
        verbose_name='Respuesta Rápida de Redes',
        help_text='Mensaje comercial preformateado para Instagram/WhatsApp. '
                  'Usar variables: [Precio_USD], [Precio_BCV], [Nombre_Articulo].',
    )
    social_cross = models.TextField(
        null=True,
        blank=True,
        verbose_name='Mensaje de Cross-Selling',
        help_text='Extracto corto para bloques de ofertas consolidadas.',
    )

    # -- Control de Estado (ADR-03: Soft Delete) --
    activo = models.BooleanField(
        default=True,
        verbose_name='Activo',
        help_text='Desactiva el artículo sin eliminarlo para preservar el historial del Kárdex.',
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de Creación',
    )
    fecha_actualizacion = models.DateTimeField(
        auto_now=True,
        verbose_name='Última Actualización',
    )

    objects = EmpresaManager()
    global_objects = models.Manager()

    class Meta:
        verbose_name = 'Artículo'
        verbose_name_plural = '05. Artículos'
        ordering = ['nombre']
        indexes = [
            models.Index(fields=['sku', 'activo'], name='idx_articulo_sku_activo'),
            models.Index(fields=['nombre'], name='idx_articulo_nombre'),
        ]

    def __str__(self):
        return f'[{self.sku}] {self.nombre}'

    def clean(self):
        """Validación: los combos no pueden tener costo ni precio_divisa positivos propios."""
        if self.tipo == 'COMBO' and self.costo > 0:
            raise ValidationError(
                {'costo': 'Un artículo tipo COMBO no debería tener costo propio. '
                          'El costo se deriva de sus componentes.'}
            )

    def get_stock_disponible(self, almacen=None):
        """
        Retorna el stock disponible de este artículo.

        - FISICO: suma de cantidad_disponible en InventarioAlmacen.
          Si se pasa `almacen`, filtra sólo ese almacén.
        - COMBO: calcula dinámicamente con la fórmula:
              Stock_Combo = min( floor(S(a_i) / q_i) )
          evaluando cada componente de la RecetaCombo en el almacén
          especificado. Si no se especifica almacén, retorna 0 para
          COMBO (el almacén es obligatorio para calcular existencias reales).

        Importa services de forma lazy para evitar la dependencia circular
        models → services → models.
        """
        if self.tipo == 'FISICO':
            qs = InventarioAlmacen.objects.filter(articulo=self)
            if almacen is not None:
                qs = qs.filter(almacen=almacen)
            resultado = qs.aggregate(
                total=models.Sum('cantidad_disponible')
            )['total']
            return resultado or 0

        elif self.tipo == 'COMBO':
            if almacen is None:
                return 0
            from . import services as svc  # lazy import: evita ciclo models↔services
            return svc.calcular_stock_combo(self, almacen)

        return 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. INVENTARIO POR ALMACÉN (Tabla Intermedia M2M)
# ─────────────────────────────────────────────────────────────────────────────

class InventarioAlmacen(models.Model):
    """
    Tabla intermedia que registra el stock físico de un artículo en un almacén.
    REGLA SAGRADA: El campo cantidad_disponible NUNCA se modifica directamente.
    Toda actualización debe pasar por MovimientoKardex + services.registrar_movimiento().
    ADR-02: Usa DecimalField para soporte de unidades fraccionables.
    """
    articulo = models.ForeignKey(
        Articulo,
        on_delete=models.PROTECT,
        related_name='inventarios',
        verbose_name='Artículo',
        limit_choices_to={'tipo': 'FISICO'},
    )
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='inventarios')
    almacen = models.ForeignKey(
        Almacen,
        on_delete=models.PROTECT,
        related_name='inventarios',
        verbose_name='Almacén',
    )
    cantidad_disponible = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        verbose_name='Cantidad Disponible',
    )
    stock_minimo = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        verbose_name='Stock Mínimo (Punto de Reorden)',
    )
    ubicacion_estante = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='Ubicación / Estante',
        help_text='Referencia física dentro del almacén (ej: Pasillo A, Estante 3).',
    )
    fecha_ultima_actualizacion = models.DateTimeField(
        auto_now=True,
        verbose_name='Última Actualización de Stock',
    )

    objects = EmpresaManager()
    global_objects = models.Manager()

    class Meta:
        verbose_name = 'Inventario por Almacén'
        verbose_name_plural = '09. Inventarios por Almacén'
        unique_together = ('articulo', 'almacen')
        ordering = ['almacen', 'articulo']
        indexes = [
            models.Index(fields=['articulo', 'almacen'], name='idx_inv_articulo_almacen'),
        ]

    def __str__(self):
        return f'{self.articulo.nombre} @ {self.almacen.nombre}: {self.cantidad_disponible}'


# ─────────────────────────────────────────────────────────────────────────────
# 5. RECETA DE COMBO VIRTUAL
# ─────────────────────────────────────────────────────────────────────────────

class RecetaCombo(models.Model):
    """
    Define la composición de un artículo tipo COMBO.
    Un combo requiere una cantidad específica de cada componente físico.
    El stock disponible del combo se calcula dinámicamente en services.py:
      Stock_Combo = min( floor(S(a_i) / q_i) ) para todos los componentes.
    ADR-02: cantidad_requerida es DecimalField para soportar fracciones.
    """
    combo = models.ForeignKey(
        Articulo,
        on_delete=models.CASCADE,
        related_name='receta_combo',
        verbose_name='Combo',
        limit_choices_to={'tipo': 'COMBO'},
    )
    componente = models.ForeignKey(
        Articulo,
        on_delete=models.PROTECT,
        related_name='usado_en_combos',
        verbose_name='Componente Físico',
        limit_choices_to={'tipo': 'FISICO'},
    )
    cantidad_requerida = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Cantidad Requerida por Unidad de Combo',
    )

    class Meta:
        verbose_name = 'Receta de Combo'
        verbose_name_plural = '06. Recetas de Combos'
        unique_together = ('combo', 'componente')

    def __str__(self):
        return f'{self.combo.nombre} ← {self.cantidad_requerida} × {self.componente.nombre}'

    def clean(self):
        if self.cantidad_requerida <= 0:
            raise ValidationError(
                {'cantidad_requerida': 'La cantidad requerida debe ser mayor a cero.'}
            )
        if self.combo == self.componente:
            raise ValidationError('Un combo no puede ser componente de sí mismo.')


# ─────────────────────────────────────────────────────────────────────────────
# 6. CONTACTO (Clientes y Proveedores Unificados — ADR-05)
# ─────────────────────────────────────────────────────────────────────────────

class Contacto(models.Model):
    """
    Directorio unificado de clientes y proveedores (ADR-05).
    Los campos exclusivos de proveedores son opcionales (null/blank).
    La pk es la identificación fiscal/personal para evitar duplicados.
    """

    TIPO_CHOICES = [
        ('CLIENTE', 'Cliente'),
        ('PROVEEDOR', 'Proveedor'),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='contactos')

    identificacion = models.CharField(
        max_length=20,
        primary_key=True,
        verbose_name='RIF / Cédula',
        help_text='Identificación fiscal o personal. Debe ser única.',
    )
    nombre = models.CharField(
        max_length=200,
        verbose_name='Nombre Completo / Razón Social',
    )
    tipo = models.CharField(
        max_length=10,
        choices=TIPO_CHOICES,
        default='CLIENTE',
        verbose_name='Tipo de Contacto',
    )
    telefono = models.CharField(
        max_length=30,
        blank=True,
        verbose_name='Teléfono',
    )
    correo = models.EmailField(
        blank=True,
        verbose_name='Correo Electrónico',
    )
    red_social = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Usuario de Red Social',
        help_text='Ej: @usuario_instagram, +58... WhatsApp.',
    )
    direccion = models.TextField(
        blank=True,
        verbose_name='Dirección',
    )
    observaciones = models.TextField(
        blank=True,
        verbose_name='Observaciones',
    )

    # -- Campos específicos de Proveedor (ADR-05) --
    rif = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name='RIF Proveedor',
        help_text='Solo requerido para contactos de tipo Proveedor.',
    )
    nombre_asesor = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        verbose_name='Nombre del Asesor de Ventas',
        help_text='Contacto comercial directo del proveedor.',
    )

    fecha_registro = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de Registro',
    )

    objects = EmpresaManager()
    global_objects = models.Manager()

    class Meta:
        verbose_name = 'Contacto'
        verbose_name_plural = '04. Contactos (Clientes y Proveedores)'
        ordering = ['tipo', 'nombre']

    def __str__(self):
        return f'[{self.get_tipo_display()}] {self.nombre} ({self.identificacion})'


class ClienteManager(EmpresaManager):
    def get_queryset(self):
        return super().get_queryset().filter(tipo='CLIENTE')

class ProveedorManager(EmpresaManager):
    def get_queryset(self):
        return super().get_queryset().filter(tipo='PROVEEDOR')


class Cliente(Contacto):
    objects = ClienteManager()
    global_objects = models.Manager()

    class Meta:
        proxy = True
        verbose_name = 'Cliente'
        verbose_name_plural = '04a. Clientes'

    def save(self, *args, **kwargs):
        self.tipo = 'CLIENTE'
        super().save(*args, **kwargs)


class Proveedor(Contacto):
    objects = ProveedorManager()
    global_objects = models.Manager()

    class Meta:
        proxy = True
        verbose_name = 'Proveedor'
        verbose_name_plural = '04b. Proveedores'

    def save(self, *args, **kwargs):
        self.tipo = 'PROVEEDOR'
        super().save(*args, **kwargs)

# ─────────────────────────────────────────────────────────────────────────────
# 7.5. DOCUMENTO DE COMPRA (TICKET #19)
# ─────────────────────────────────────────────────────────────────────────────

class DocumentoCompra(models.Model):
    """
    Cabecera ligera de importación que agrupa compras a proveedores.
    """
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='documentos_compra')
    proveedor = models.ForeignKey(
        Contacto,
        on_delete=models.PROTECT,
        limit_choices_to={'tipo': 'PROVEEDOR'},
        related_name='documentos_compra',
        verbose_name='Proveedor'
    )
    numero_factura = models.CharField(max_length=100, blank=True, default='', verbose_name='Número de Factura')
    fecha_compra = models.DateField(blank=True, null=True, default=None, verbose_name='Fecha de Compra')
    monto_total_usd = models.DecimalField(max_digits=14, decimal_places=4, verbose_name='Monto Total (USD)')

    # FASE 3 — Snapshot de tasa al momento de la compra (regla contable)
    tasa_bcv_aplicada = models.DecimalField(
        max_digits=12, decimal_places=4, default=0.0000, null=True, blank=True,
        verbose_name='Tasa BCV aplicada (snapshot)'
    )
    tasa_mercado_aplicada = models.DecimalField(
        max_digits=12, decimal_places=4, default=0.0000, null=True, blank=True,
        verbose_name='Tasa mercado aplicada (snapshot)'
    )
    factor_cobertura_aplicado = models.DecimalField(
        max_digits=8, decimal_places=4, default=1.0000, null=True, blank=True,
        verbose_name='Factor cobertura aplicada (snapshot)'
    )
    fuente_tasa = models.CharField(
        max_length=20, blank=True, default='',
        verbose_name='Fuente de la tasa (BCV/MANUAL/BINANCE)'
    )
    monto_total_bs_snapshot = models.DecimalField(
        max_digits=18, decimal_places=2, default=0.00, null=True, blank=True,
        verbose_name='Monto total en Bs (snapshot)'
    )

    fecha_registro = models.DateTimeField(auto_now_add=True)
    
    ESTADO_CHOICES = [
        ('PROCESADO', 'Procesado'),
        ('ANULADO', 'Anulado'),
    ]
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PROCESADO', verbose_name='Estado')
    motivo_anulacion = models.TextField(null=True, blank=True, verbose_name='Motivo de Anulación')
    observaciones = models.TextField(blank=True, default='', verbose_name='Observaciones')

    objects = EmpresaManager()
    global_objects = models.Manager()

    class Meta:
        verbose_name = 'Documento de Compra'
        verbose_name_plural = '12. Documentos de Compra'
        ordering = ['-fecha_compra', '-id']

    def __str__(self):
        return f"Factura {self.numero_factura} - {self.proveedor.nombre}"

# ─────────────────────────────────────────────────────────────────────────────
# 8. MOVIMIENTO KÁRDEX (Registro Inalterable — Regla Sagrada)
# ─────────────────────────────────────────────────────────────────────────────

class MovimientoKardex(models.Model):
    """
    Registro histórico e inalterable de todas las entradas y salidas de stock.
    REGLA SAGRADA: Es el ÚNICO origen válido para modificar cantidad_disponible
    en InventarioAlmacen. Siempre se ejecuta dentro de @transaction.atomic.
    ADR-02: cantidad es DecimalField.
    """

    TIPO_CHOICES = [
        ('ENTRADA', 'Entrada'),
        ('SALIDA', 'Salida'),
    ]
    CONCEPTO_CHOICES = [
        # Entradas
        ('COMPRA', 'Compra a Proveedor'),
        ('CARGA_MASIVA_SUMA', 'Carga Masiva — Suma'),
        ('CARGA_MASIVA_SUSTITUCION_ENTRADA', 'Carga Masiva — Entrada por Sustitución'),
        ('AJUSTE_ENTRADA', 'Ajuste Manual de Entrada'),
        ('TRANSFERENCIA_ENTRADA', 'Transferencia — Entrada'),
        ('DEVOLUCION_ENTRADA', 'Devolución — Reingreso'),
        ('DEVOLUCION_VENTA', 'Devolución de Venta'),
        ('ANULACION_COMPRA', 'Anulación de Compra'),
        ('REVERSO_ENTRADA', 'Reverso de Carga Masiva — Entrada'),
        # Salidas
        ('VENTA', 'Venta (Nota de Entrega)'),
        ('CARGA_MASIVA_SUSTITUCION_SALIDA', 'Carga Masiva — Salida por Sustitución'),
        ('AJUSTE_SALIDA', 'Ajuste Manual de Salida'),
        ('TRANSFERENCIA_SALIDA', 'Transferencia — Salida'),
        ('MERMA_DEFECTUOSO', 'Merma por Artículo Defectuoso'),
        ('REVERSO_SALIDA', 'Reverso de Carga Masiva — Salida'),
    ]

    fecha_hora = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha y Hora',
    )
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='movimientos_kardex')
    articulo = models.ForeignKey(
        Articulo,
        on_delete=models.PROTECT,
        related_name='movimientos',
        verbose_name='Artículo',
    )
    almacen = models.ForeignKey(
        Almacen,
        on_delete=models.PROTECT,
        related_name='movimientos',
        verbose_name='Almacén',
    )
    tipo = models.CharField(
        max_length=7,
        choices=TIPO_CHOICES,
        verbose_name='Tipo de Movimiento',
    )
    concepto = models.CharField(
        max_length=60,
        choices=CONCEPTO_CHOICES,
        verbose_name='Concepto',
    )
    cantidad = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Cantidad',
    )
    saldo_resultante = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Saldo Resultante',
        help_text='Stock de este artículo en este almacén después del movimiento.',
    )
    nota_entrega = models.ForeignKey(
        'NotaEntrega',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimientos_kardex',
        verbose_name='Nota de Entrega Asociada',
    )
    documento_compra = models.ForeignKey(
        DocumentoCompra,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimientos',
        verbose_name='Documento de Compra Asociado',
    )
    lote_carga = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='ID de Lote de Carga Masiva',
        help_text='Referencia al batch de carga masiva que originó este movimiento.',
    )
    detalle_adicional = models.TextField(
        blank=True,
        verbose_name='Detalle Adicional',
        help_text='Información de auditoría extra (ej: factura de compra, referencia externa).',
    )
    usuario = models.CharField(
        max_length=150,
        blank=True,
        verbose_name='Usuario que Realizó el Movimiento',
    )

    objects = EmpresaManager()
    global_objects = models.Manager()

    class Meta:
        verbose_name = 'Movimiento del Kárdex'
        verbose_name_plural = '10. Movimientos del Kárdex'
        ordering = ['-fecha_hora']

    def __str__(self):
        return (
            f'[{self.fecha_hora:%Y-%m-%d %H:%M}] '
            f'{self.get_tipo_display()} — {self.articulo.nombre} '
            f'@ {self.almacen.nombre}: {self.cantidad:+}'
        )


# ─────────────────────────────────────────────────────────────────────────────
# 8. AUDITORÍA DE TASAS DE CAMBIO
# ─────────────────────────────────────────────────────────────────────────────

class AuditoriaTasa(models.Model):
    """
    Historial de variación de tasas de cambio y factor de cobertura.
    Permite reconstruir el precio histórico de cualquier transacción.
    """

    FUENTE_CHOICES = [
        ('MANUAL', 'Ingreso Manual'),
        ('API', 'Sincronización por API'),
    ]

    fecha_hora = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha y Hora del Registro',
    )
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='auditoria_tasas')
    tasa_bcv = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name='Tasa BCV (Bs/$)',
    )
    tasa_mercado = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name='Tasa Mercado / Referencia (Bs/$)',
    )
    factor_cobertura = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        verbose_name='Factor de Cobertura Cambiaria (Fc)',
        help_text='Fc = Tasa Mercado / Tasa BCV',
    )
    fuente = models.CharField(
        max_length=10,
        choices=FUENTE_CHOICES,
        default='MANUAL',
        verbose_name='Fuente de la Tasa',
    )
    notas = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Notas',
    )

    objects = EmpresaManager()
    global_objects = models.Manager()

    class Meta:
        verbose_name = 'Auditoría de Tasa de Cambio'
        verbose_name_plural = '08. Auditoría de Tasas de Cambio'
        ordering = ['-fecha_hora']

    def __str__(self):
        return (
            f'[{self.fecha_hora:%Y-%m-%d %H:%M}] '
            f'BCV: {self.tasa_bcv} | Mercado: {self.tasa_mercado} | Fc: {self.factor_cobertura}'
        )


# ─────────────────────────────────────────────────────────────────────────────
# 9. NOTA DE ENTREGA (ADR-01: esquema definido en Ticket #1)
# ─────────────────────────────────────────────────────────────────────────────

class NotaEntrega(models.Model):
    """
    Documento de salida que registra una venta o despacho.
    Genera correlativo numérico automático.
    La lógica transaccional de desagregación de stock se implementa en Ticket #2.
    """

    ESTADO_CHOICES = [
        ('PROCESADO', 'Procesado'),
        ('ANULADO', 'Anulado'),
    ]
    TIPO_DOCUMENTO_CHOICES = [
        ('NOTA_ENTREGA', 'Nota de Entrega'),
        ('FACTURA', 'Factura'),
    ]
    MONEDA_CHOICES = [
        ('USD', 'Dólares (USD)'),
        ('BS_BCV', 'Bolívares a Tasa BCV'),
        ('BS_EFECTIVO', 'Bolívares en Efectivo'),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='notas_entrega')
    numero = models.PositiveIntegerField(
        verbose_name='Nº de Nota de Entrega',
        help_text='Correlativo numérico único por empresa, generado automáticamente.',
    )
    tipo_documento = models.CharField(
        max_length=15,
        choices=TIPO_DOCUMENTO_CHOICES,
        default='NOTA_ENTREGA',
        verbose_name='Tipo de Documento',
    )
    numero_nota = models.CharField(
        max_length=30,
        blank=True,
        verbose_name='N° Nota Interna',
        help_text='Correlativo alfanumérico configurable. Ej: NE-00000008.',
    )
    numero_factura = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name='N° Factura Física',
        help_text='Manual. Sólo si tipo_documento=FACTURA. Único por empresa.',
    )
    fecha = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de Emisión',
    )
    cliente = models.ForeignKey(
        Contacto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notas_entrega',
        limit_choices_to={'tipo': 'CLIENTE'},
        verbose_name='Cliente',
        help_text='Si está vacío, se asigna al cliente genérico.',
    )
    almacen = models.ForeignKey(
        Almacen,
        on_delete=models.PROTECT,
        related_name='notas_entrega',
        verbose_name='Almacén de Despacho',
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='PROCESADO',
        verbose_name='Estado',
    )
    motivo_anulacion = models.TextField(null=True, blank=True, verbose_name='Motivo de Anulación')
    moneda_pago = models.CharField(
        max_length=12,
        choices=MONEDA_CHOICES,
        default='USD',
        verbose_name='Moneda de Pago',
    )
    tasa_bcv_aplicada = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0.0000,
        verbose_name='Tasa BCV al Momento de la Venta',
        help_text='Snapshot de la tasa BCV aplicada en el momento exacto de la venta.',
    )
    factor_cobertura_aplicado = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=1.0000,
        verbose_name='Factor de Cobertura Aplicado',
    )
    tasa_mercado_aplicada = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0.0000,
        verbose_name='Tasa Mercado al Momento de la Venta (Snapshot)',
    )
    iva_check = models.BooleanField(
        default=False,
        verbose_name='IVA Aplicado',
        help_text='Indica si el documento procesa el cálculo impositivo.',
    )
    iva_total = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0.0000,
        verbose_name='IVA Total (Snapshot)',
        help_text='Snapshot del IVA totalizado al momento de la venta.',
    )
    descuento_global = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        verbose_name='Descuento Global del Documento (%)',
    )
    observaciones = models.TextField(
        blank=True,
        verbose_name='Observaciones',
    )

    objects = EmpresaManager()
    global_objects = models.Manager()

    class Meta:
        verbose_name = 'Nota de Entrega'
        verbose_name_plural = '11. Notas de Entrega'
        ordering = ['-numero']
        unique_together = (
            ('empresa', 'numero'),
        )
        constraints = [
            models.UniqueConstraint(
                fields=['empresa', 'numero_nota'],
                name='unique_numero_nota_por_empresa',
                condition=~models.Q(numero_nota=''),
            ),
            models.UniqueConstraint(
                fields=['empresa', 'numero_factura'],
                name='unique_numero_factura_por_empresa',
                condition=~models.Q(numero_factura=''),
            ),
        ]

    def __str__(self):
        cliente_nombre = self.cliente.nombre if self.cliente else 'Cliente Genérico'
        ident = self.numero_nota or f'NE-{self.numero:08d}'
        return f'{ident} | {cliente_nombre} | {self.get_estado_display()}'

    def save(self, *args, **kwargs):
        """
        Auto-genera:
          - numero: correlativo entero por empresa (respetando correlativo_inicial_nota)
          - numero_nota: formato {prefijo}-{numero:08d} (ej: NE-00000008)
        Sólo si no vienen ya poblados (permite override para casos especiales).
        """
        if not self.numero:
            from django.db.models import Max
            max_num = NotaEntrega.global_objects.filter(
                empresa=self.empresa
            ).aggregate(max_num=Max('numero'))['max_num']
            # Arrancar desde correlativo_inicial_nota configurado, o 1 si no hay config
            try:
                inicial = ConfiguracionEmpresa.objects.get(
                    empresa_id=self.empresa_id
                ).correlativo_inicial_nota
            except ConfiguracionEmpresa.DoesNotExist:
                inicial = 1
            if max_num:
                self.numero = max_num + 1
            else:
                self.numero = max(inicial, 1)
        if not self.numero_nota:
            try:
                prefijo = ConfiguracionEmpresa.objects.get(
                    empresa_id=self.empresa_id
                ).prefijo_nota_entrega
            except ConfiguracionEmpresa.DoesNotExist:
                prefijo = 'NE'
            self.numero_nota = f'{prefijo}-{self.numero:08d}'
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# 10. DETALLE DE NOTA DE ENTREGA
# ─────────────────────────────────────────────────────────────────────────────

class DetalleNotaEntrega(models.Model):
    """
    Línea de detalle de una Nota de Entrega.
    Almacena el snapshot del precio al momento de la venta para
    que los reportes históricos sean inmutables e independientes
    de futuros cambios en la ficha del artículo.
    ADR-02: cantidades y precios como DecimalField.
    """
    nota_entrega = models.ForeignKey(
        NotaEntrega,
        on_delete=models.CASCADE,
        related_name='detalles',
        verbose_name='Nota de Entrega',
    )
    articulo = models.ForeignKey(
        Articulo,
        on_delete=models.PROTECT,
        related_name='detalles_nota_entrega',
        verbose_name='Artículo',
    )
    almacen = models.ForeignKey(
        Almacen,
        on_delete=models.PROTECT,
        related_name='detalles_nota_entrega',
        null=True,
        blank=True,
        verbose_name='Almacén de Origen',
        help_text='Almacén desde donde se ejecuta la rebaja real de stock.',
    )
    cantidad = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Cantidad',
    )
    # Snapshot de los 4 precios al momento de la venta (inmutables — ADR-18)
    precio_base = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0.0000,
        verbose_name='Precio Base (USD, Snapshot)',
        help_text='Precio en divisas del catálogo al momento de facturar.',
    )
    precio_ajustado = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0.0000,
        verbose_name='Precio Ajustado (USD, Snapshot)',
        help_text='precio_base × factor_cobertura. Protección cambiaria.',
    )
    precio_directo_bcv = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=0.00,
        verbose_name='Precio Bs. BCV (Snapshot)',
        help_text='precio_base × tasa_bcv. Sin factor de cobertura.',
    )
    precio_ajustado_bcv = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=0.00,
        verbose_name='Precio Bs. Ajustado (Snapshot)',
        help_text='precio_base × factor_cobertura × tasa_bcv. Mayor protección.',
    )
    costo_unitario_snapshot = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0.0000,
        verbose_name='Costo Unitario al Momento de la Venta (Snapshot)',
        help_text='Costo de adquisición del artículo grabado inmutablemente al facturar (ADR-18).',
    )
    descuento_aplicado = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Descuento Individual (%)',
    )
    iva_porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        verbose_name='IVA del Artículo (%) (Snapshot)',
        help_text='Snapshot del IVA tomado de la ficha del artículo al facturar.',
    )

    class Meta:
        verbose_name = 'Detalle de Nota de Entrega'
        verbose_name_plural = '12. Detalles de Notas de Entrega'

    def __str__(self):
        return f'{self.nota_entrega} | {self.articulo.nombre} × {self.cantidad}'

    @property
    def subtotal_usd(self):
        """Subtotal en USD (precio_base) aplicando descuento individual."""
        from decimal import Decimal
        factor_descuento = Decimal('1') - (self.descuento_aplicado / Decimal('100'))
        return self.precio_base * self.cantidad * factor_descuento

    @property
    def subtotal_ajustado_usd(self):
        """Subtotal en USD ajustado (× factor_cobertura) aplicando descuento."""
        from decimal import Decimal
        factor_descuento = Decimal('1') - (self.descuento_aplicado / Decimal('100'))
        return self.precio_ajustado * self.cantidad * factor_descuento

    @property
    def subtotal_bs_bcv(self):
        """Subtotal en Bs. BCV (sin factor) aplicando descuento."""
        from decimal import Decimal
        factor_descuento = Decimal('1') - (self.descuento_aplicado / Decimal('100'))
        return self.precio_directo_bcv * self.cantidad * factor_descuento

    @property
    def subtotal_bs(self):
        """Subtotal en Bs. ajustado (con factor) aplicando descuento."""
        from decimal import Decimal
        factor_descuento = Decimal('1') - (self.descuento_aplicado / Decimal('100'))
        return self.precio_ajustado_bcv * self.cantidad * factor_descuento

    @property
    def iva_usd(self):
        """IVA en USD sobre el subtotal ajustado (precio_ajustado)."""
        from decimal import Decimal
        return self.subtotal_ajustado_usd * (self.iva_porcentaje / Decimal('100'))

    @property
    def iva_bs(self):
        """IVA en Bs. sobre el subtotal ajustado (precio_ajustado_bcv)."""
        from decimal import Decimal
        return self.subtotal_bs * (self.iva_porcentaje / Decimal('100'))


# ─────────────────────────────────────────────────────────────────────────────
# 11. TRAZABILIDAD Y CONTROL DE SERIALES (TICKET #14-SAAS)
# ─────────────────────────────────────────────────────────────────────────────

class SerialArticulo(models.Model):
    """
    Registro físico y unitario de un artículo en stock que requiere trazabilidad de garantía.
    Un serial es un identificador único por unidad de producto.
    """
    ESTADO_CHOICES = [
        ('DISPONIBLE', 'Disponible en Mostrador'),
        ('VENDIDO', 'Vendido / Consumido'),
        ('ANULADO_COMPRA', 'Anulado por Reverso de Compra'),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='seriales')
    articulo = models.ForeignKey(
        Articulo,
        on_delete=models.CASCADE,
        related_name='seriales',
        verbose_name='Artículo',
    )
    serial = models.CharField(
        max_length=100,
        verbose_name='Serial / IMEI',
        help_text='Identificador de garantía único para esta unidad.',
    )
    compra_origen = models.ForeignKey('DocumentoCompra', on_delete=models.SET_NULL, null=True, blank=True, related_name='seriales_ingresados')
    almacen = models.ForeignKey(
        Almacen,
        on_delete=models.PROTECT,
        related_name='seriales_almacenados',
        verbose_name='Almacén Actual',
    )
    estado = models.CharField(
        max_length=15,
        choices=ESTADO_CHOICES,
        default='DISPONIBLE',
        verbose_name='Estado Operativo',
    )
    detalle_nota = models.ForeignKey(
        DetalleNotaEntrega,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='seriales_asignados',
        verbose_name='Nota de Venta Asociada',
    )

    objects = EmpresaManager()
    global_objects = models.Manager()

    class Meta:
        verbose_name = 'Serial de Artículo'
        verbose_name_plural = '07. Seriales de Artículos'
        unique_together = ('empresa', 'serial')

    def __str__(self):
        return f"{self.serial} ({self.get_estado_display()})"


class NotaCredito(models.Model):
    """
    Cabecera de Nota de Crédito para gestionar devoluciones.
    """
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='notas_credito')
    nota_entrega = models.ForeignKey(
        NotaEntrega, 
        on_delete=models.PROTECT, 
        related_name='notas_credito',
        verbose_name='Nota de Entrega Original'
    )
    numero_control = models.CharField(
        max_length=50, 
        verbose_name='Número de Control',
        help_text='Identificador único de la Nota de Crédito.'
    )
    motivo = models.TextField(
        verbose_name='Motivo de Devolución',
        blank=True
    )
    monto_total_reembolso = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        default=0.00,
        verbose_name='Monto Total de Reembolso (USD)'
    )
    fecha = models.DateTimeField(auto_now_add=True)

    objects = EmpresaManager()
    global_objects = models.Manager()

    class Meta:
        verbose_name = 'Nota de Crédito'
        verbose_name_plural = '13. Notas de Crédito'

    def __str__(self):
        return f"NC-{self.numero_control} (Ref: {self.nota_entrega.numero})"


class DetalleNotaCredito(models.Model):
    """
    Línea de detalle para artículos devueltos en una Nota de Crédito.
    """
    nota_credito = models.ForeignKey(
        NotaCredito,
        on_delete=models.CASCADE,
        related_name='detalles'
    )
    articulo = models.ForeignKey(
        Articulo,
        on_delete=models.PROTECT,
        related_name='devoluciones'
    )
    cantidad = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    costo_aplicado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Costo Aplicado al Reingreso'
    )

    class Meta:
        verbose_name = 'Detalle de Nota de Crédito'
        verbose_name_plural = '14. Detalles de Notas de Crédito'

    def __str__(self):
        return f"{self.articulo.nombre} × {self.cantidad} (NC: {self.nota_credito.numero_control})"


# ─────────────────────────────────────────────────────────────────────────────
# FASE 3 — MULTIMODEDA: MODELOS DE MONEDA Y TASAS
# ─────────────────────────────────────────────────────────────────────────────

class Moneda(models.Model):
    """
    Catalogo de monedas que soporta el sistema. Por defecto USD y VES
    (bolivar venezolano). La moneda base del tenant esta marcada con
    es_base=True; las demas son monedas alternas para conversion.
    """
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='monedas'
    )
    codigo = models.CharField(
        max_length=3,
        verbose_name='Codigo ISO 4217',
        help_text='Por ejemplo: USD, VES, EUR, COP, ARS'
    )
    nombre = models.CharField(max_length=50)
    simbolo = models.CharField(max_length=5, default='$')
    decimales = models.PositiveSmallIntegerField(default=2)
    es_base = models.BooleanField(
        default=False,
        verbose_name='Moneda base del tenant',
        help_text='Si True, todos los precios se almacenan en esta moneda.'
    )
    activa = models.BooleanField(default=True)

    objects = EmpresaManager()
    global_objects = models.Manager()

    class Meta:
        verbose_name = 'Moneda'
        verbose_name_plural = 'Monedas'
        unique_together = [('empresa', 'codigo')]
        ordering = ['es_base', 'codigo']

    def __str__(self):
        return f"{self.codigo} ({self.simbolo})"

    def save(self, *args, **kwargs):
        # Garantizar que solo haya UNA moneda es_base=True por tenant.
        if self.es_base:
            qs = Moneda.objects.filter(
                empresa=self.empresa, es_base=True
            ).exclude(pk=self.pk)
            qs.update(es_base=False)
        super().save(*args, **kwargs)


class TasaCambio(models.Model):
    """
    Historico inmutable de tasas de cambio por par de monedas y fecha.
    Cada snapshot de AuditoriaTasa o sincronizacion guarda un registro
    aqui para conservar trazabilidad historica.
    """
    Fuente = [
        ('BCV', 'Banco Central de Venezuela (oficial)'),
        ('MANUAL', 'Ingreso manual del operador'),
        ('API', 'API externa (e.g. Binance P2P)'),
        ('INFLATION', 'Tasa calculada por inflacion interna'),
    ]

    empresa = models.ForeignKey(
        Empresa, on_delete=models.CASCADE, related_name='tasas_cambio'
    )
    moneda_origen = models.ForeignKey(
        Moneda, on_delete=models.PROTECT, related_name='tasas_origen'
    )
    moneda_destino = models.ForeignKey(
        Moneda, on_delete=models.PROTECT, related_name='tasas_destino'
    )
    tasa = models.DecimalField(
        max_digits=18, decimal_places=6,
        verbose_name='Tasa (1 origen = N destino)'
    )
    fecha = models.DateField(verbose_name='Fecha de la tasa')
    fuente = models.CharField(max_length=20, choices=Fuente, default='MANUAL')
    usuario = models.CharField(max_length=150, blank=True, default='')
    notas = models.CharField(max_length=255, blank=True, default='')
    creada_en = models.DateTimeField(auto_now_add=True)

    objects = EmpresaManager()
    global_objects = models.Manager()

    class Meta:
        verbose_name = 'Tasa de Cambio'
        verbose_name_plural = 'Tasas de Cambio'
        indexes = [
            models.Index(fields=['empresa', 'moneda_origen', 'moneda_destino', '-fecha']),
        ]
        ordering = ['-fecha', '-creada_en']

    def __str__(self):
        return f"1 {self.moneda_origen.codigo} = {self.tasa} {self.moneda_destino.codigo} ({self.fecha})"

    @classmethod
    def obtener_tasa(cls, origen_codigo, destino_codigo, empresa_id, fecha=None):
        """
        Retorna la tasa mas reciente del par origen->destino <= fecha.
        Si no existe, lanza ValueError operacional.
        """
        from django.utils import timezone
        empresa_id_int = int(empresa_id)
        fecha = fecha or timezone.localdate()
        # Usar Moneda.manager por tenant para resolver origen/destino
        monedas = Moneda.objects.filter(empresa_id=empresa_id_int)
        try:
            origen = monedas.get(codigo=origen_codigo.upper())
            destino = monedas.get(codigo=destino_codigo.upper())
        except Moneda.DoesNotExist:
            raise ValueError(
                f"Moneda origen o destino no configurada en el tenant."
            )
        # Buscar la tasa mas reciente via global_objects (no filtrar
        # por ContextVar aunque sirva de hint).
        tasa = cls.global_objects.filter(
            empresa_id=empresa_id_int,
            moneda_origen=origen,
            moneda_destino=destino,
            fecha__lte=fecha
        ).order_by('-fecha', '-creada_en').first()
        if not tasa:
            raise ValueError(
                f"No hay tasa {origen_codigo}->{destino_codigo} al {fecha}"
            )
        return tasa
