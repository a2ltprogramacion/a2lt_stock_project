"""
inventory/views.py
==================
Vistas del sistema A2LT Stock.

Ticket #3: Vista de Carga Masiva y resolución de colisiones via sesión Django (ADR-09).
Las vistas actúan como adaptadores HTTP → servicios, sin lógica de negocio propia.
Retornan JSON para compatibilidad con AJAX/fetch desde el frontend.
"""

import json
import logging

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt  # Temporal hasta implementar tokens CSRF en JS
from django.db import models as db_models

from . import services as svc
from .models import Almacen

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 0. AUTENTICACIÓN
# ─────────────────────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated and request.session.get('empresa_id'):
        return redirect('inventory:dashboard')
        
    if request.method == 'POST':
        u = request.POST.get('username')
        p = request.POST.get('password')
        user = authenticate(request, username=u, password=p)
        if user is not None:
            login(request, user)
            from .models import Empresa
            
            if user.is_superuser:
                empresa = Empresa.objects.filter(activa=True).first()
                if empresa:
                    request.session['empresa_id'] = empresa.id
                    return redirect('inventory:dashboard')
                else:
                    messages.error(request, 'No hay ninguna empresa activa en el sistema.')
                    logout(request)
            else:
                perfil = getattr(user, 'perfil', None)
                if not perfil or not perfil.empresas_permitidas.exists():
                    messages.error(request, 'Tu usuario no tiene ninguna sucursal asignada.')
                    logout(request)
                else:
                    if perfil.empresa_activa and perfil.empresa_activa in perfil.empresas_permitidas.all():
                        request.session['empresa_id'] = perfil.empresa_activa.id
                    else:
                        primera = perfil.empresas_permitidas.first()
                        perfil.empresa_activa = primera
                        perfil.save()
                        request.session['empresa_id'] = primera.id
                    return redirect('inventory:dashboard')
        else:
            messages.error(request, 'Credenciales inválidas.')
            
    return render(request, 'inventory/login.html')

def logout_view(request):
    logout(request)
    return redirect('inventory:login')

@require_http_methods(["POST"])
def cambiar_empresa_view(request):
    empresa_id = request.POST.get('empresa_id')
    user = request.user
    
    if not user.is_authenticated:
        return redirect('inventory:login')
        
    if user.is_superuser:
        from .models import Empresa
        empresa = Empresa.objects.filter(id=empresa_id, activa=True).first()
        if empresa:
            request.session['empresa_id'] = empresa.id
    else:
        perfil = getattr(user, 'perfil', None)
        if perfil:
            empresa = perfil.empresas_permitidas.filter(id=empresa_id).first()
            if empresa:
                perfil.empresa_activa = empresa
                perfil.save()
                request.session['empresa_id'] = empresa.id
                
    return redirect('inventory:dashboard')


# ─────────────────────────────────────────────────────────────────────────────
# VISTAS GENERALES (Placeholders - se implementarán en tickets posteriores)
# ─────────────────────────────────────────────────────────────────────────────

def dashboard(request):
    """
    Panel de Control Analítico (Ticket #10).
    Métricas ejecutadas directamente en el motor de base de datos (0 loops en Python).
    """
    from django.db.models import Sum, F
    from django.utils import timezone
    from decimal import Decimal
    from .models import InventarioAlmacen, DetalleNotaEntrega
    from .managers import get_current_empresa

    empresa_id = get_current_empresa()

    # METRICA 1 (Valoración del Inventario)
    # Sum(InventarioAlmacen.cantidad_disponible * Articulo.costo)
    valoracion = InventarioAlmacen.objects.aggregate(
        valor_total=Sum(F('cantidad_disponible') * F('articulo__costo'))
    )['valor_total'] or Decimal('0.00')

    # METRICA 2 (Volumen de Ventas)
    now = timezone.now()
    ventas_mes = DetalleNotaEntrega.objects.filter(
        nota_entrega__fecha__year=now.year,
        nota_entrega__fecha__month=now.month,
        nota_entrega__empresa_id=empresa_id
    ).aggregate(
        volumen_usd=Sum(F('precio_unitario_usd') * F('cantidad')),
        volumen_bs=Sum(F('precio_unitario_bs') * F('cantidad'))
    )
    
    volumen_usd = ventas_mes['volumen_usd'] or Decimal('0.00')
    volumen_bs = ventas_mes['volumen_bs'] or Decimal('0.00')

    # Motor de Alertas Preventivas de Punto de Reorden
    # Incluye artículos con stock_minimo > 0 que cayeron en o por debajo del mínimo
    alertas = InventarioAlmacen.objects.select_related('articulo', 'almacen').filter(
        cantidad_disponible__lte=F('stock_minimo'),
        stock_minimo__gt=0
    ).order_by('cantidad_disponible')

    context = {
        'valoracion_total': valoracion,
        'volumen_usd': volumen_usd,
        'volumen_bs': volumen_bs,
        'alertas': alertas,
    }
    return render(request, 'inventory/dashboard.html', context)


def catalogo(request):
    from decimal import Decimal
    from .models import Articulo, ConfiguracionEmpresa
    from .managers import get_current_empresa

    empresa_id = get_current_empresa()
    config = ConfiguracionEmpresa.objects.get(empresa_id=empresa_id)
    articulos = Articulo.objects.filter(activo=True).order_by('nombre')
    factor = config.factor_cobertura if config else Decimal('1.0000')
    tasa_bcv = config.tasa_bcv if config else Decimal('0.0000')

    articulos_con_precios = []
    for a in articulos:
        precio_usd = a.precio_divisa
        precio_usd_ajustado = (precio_usd * factor).quantize(Decimal('0.01'))
        precio_bs_bcv = (precio_usd_ajustado * tasa_bcv).quantize(Decimal('0.01'))
        articulos_con_precios.append({
            'articulo': a,
            'precio_divisa': a.precio_divisa,
            'precio_usd_ajustado': precio_usd_ajustado,
            'precio_bs_bcv': precio_bs_bcv,
        })

    return render(request, 'inventory/catalogo.html', {
        'articulos_con_precios': articulos_con_precios,
        'articulos': articulos,
    })


def ventas(request):
    from .models import Articulo, Almacen, Contacto, ConfiguracionEmpresa
    from .managers import get_current_empresa

    articulos = Articulo.objects.filter(activo=True).order_by('nombre')
    almacenes = Almacen.objects.filter(activo=True).order_by('-es_principal', 'nombre')
    clientes = Contacto.objects.filter(tipo='CLIENTE').order_by('nombre')

    empresa_id = get_current_empresa()
    try:
        config = ConfiguracionEmpresa.objects.get(empresa_id=empresa_id)
    except ConfiguracionEmpresa.DoesNotExist:
        config = None

    context = {
        'articulos': articulos,
        'almacenes': almacenes,
        'clientes': clientes,
        'config': config,
    }
    return render(request, 'inventory/ventas.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# TICKET #3: Vista de Carga Masiva
# ─────────────────────────────────────────────────────────────────────────────

@require_http_methods(['GET', 'POST'])
def vista_descargar_plantilla(request):
    """
    Descarga la plantilla Excel (.xlsx) para carga masiva de inventario.
    Columnas: SKU, Nombre, Costo, Cantidad, Precio_Divisa, Almacen.
    """
    import openpyxl
    from django.http import HttpResponse

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Plantilla Inventario"

    headers = ['SKU', 'Nombre', 'Costo', 'Cantidad', 'Precio_Divisa', 'Almacen']
    ws.append(headers)

    # Fila de ejemplo (opcional)
    ws.append(['EJEMPLO-001', 'Producto de ejemplo', 10.00, 5, 25.00, 'Almacén Principal'])

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="plantilla_inventario_a2lt.xlsx"'
    wb.save(response)
    return response


def vista_carga_masiva(request):
    """
    GET  → Renderiza el formulario de carga masiva con la lista de almacenes.
    POST → Procesa el archivo Excel subido y retorna JSON con el resultado.

    Respuesta JSON (POST):
    {
        "ok": true,
        "lote_id": "uuid",
        "filas_procesadas": 10,
        "articulos_creados": 3,
        "articulos_actualizados": 5,
        "filas_error": 2,
        "hay_colisiones": true,
        "colisiones": [...],
        "log_errores": [...],
        "log_advertencias": [...],
        "reporte_txt": "..."
    }
    """
    if request.method == 'GET':
        almacenes = Almacen.objects.filter(activo=True).order_by('-es_principal', 'nombre')
        return render(request, 'inventory/carga.html', {'almacenes': almacenes})

    # ── POST: Procesar archivo ───────────────────────────────────────────────
    archivo = request.FILES.get('archivo_excel')
    almacen_id = request.POST.get('almacen_id')
    usuario = request.POST.get('usuario', '')

    if not archivo:
        return JsonResponse({'ok': False, 'error': 'No se recibió ningún archivo.'}, status=400)

    if not almacen_id:
        return JsonResponse({'ok': False, 'error': 'Debe seleccionar un almacén destino.'}, status=400)

    try:
        almacen_id = int(almacen_id)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'ID de almacén inválido.'}, status=400)

    try:
        resultado = svc.procesar_carga_masiva(
            archivo_excel=archivo,
            almacen_id=almacen_id,
            usuario=usuario or request.user.username if request.user.is_authenticated else 'anónimo',
        )
    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=422)
    except Exception as e:
        logger.exception('[CARGA MASIVA] Error inesperado en vista_carga_masiva.')
        return JsonResponse(
            {'ok': False, 'error': f'Error interno del servidor: {e}'},
            status=500,
        )

    # ── Persistir colisiones en sesión (ADR-09) ──────────────────────────────
    lote_id = resultado['lote_id']
    if resultado['colisiones']:
        request.session[f'carga_{lote_id}'] = {
            'colisiones': resultado['colisiones'],
            'lote_id': lote_id,
        }
        request.session.modified = True
        logger.info(
            '[CARGA MASIVA] %s colisión(es) persistidas en sesión. Lote: %s',
            len(resultado['colisiones']), lote_id,
        )

    return JsonResponse({
        'ok': True,
        'lote_id': lote_id,
        'filas_procesadas': resultado['filas_procesadas'],
        'articulos_creados': resultado['articulos_creados'],
        'articulos_actualizados': resultado['articulos_actualizados'],
        'filas_error': resultado['filas_error'],
        'hay_colisiones': bool(resultado['colisiones']),
        'colisiones': resultado['colisiones'],
        'log_errores': resultado['log_errores'],
        'log_advertencias': resultado['log_advertencias'],
        'reporte_txt': resultado['reporte_txt'],
    })


# ── Vista de Carga Masiva Atómica (Ticket #27) ──────────────────────────

def vista_carga_masiva_excel(request):
    """
    Endpoint estrictamente atómico para carga masiva Excel (Ticket #27).

    POST: Recibe archivo .xlsx, lo procesa con procesar_carga_masiva_excel().
          Cualquier error de validación → rollback total.
    """
    from .managers import get_current_empresa

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Solo se acepta método POST.'}, status=405)

    empresa_id = get_current_empresa()
    if not empresa_id:
        return JsonResponse({'ok': False, 'error': 'Sesión de empresa no detectada.'}, status=400)

    archivo = request.FILES.get('archivo_excel')
    if not archivo:
        return JsonResponse({'ok': False, 'error': 'No se recibió ningún archivo.'}, status=400)

    usuario = request.user.username if request.user.is_authenticated else 'anónimo'

    try:
        resultado = svc.procesar_carga_masiva_excel(
            file_io=archivo,
            empresa_id=empresa_id,
            usuario=usuario,
        )
    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=422)
    except Exception as e:
        logger.exception('[CARGA MASIVA EXCEL] Error inesperado.')
        return JsonResponse({'ok': False, 'error': f'Error interno: {e}'}, status=500)

    return JsonResponse({'ok': True, **resultado})


# ─────────────────────────────────────────────────────────────────────────────
# TICKET #3: Vista de Resolución de Colisiones (Los 3 Botones del Modal)
# ─────────────────────────────────────────────────────────────────────────────

@require_http_methods(['POST'])
def vista_resolver_colision(request):
    """
    POST → Aplica la decisión del usuario (SUMAR/SUSTITUIR/CANCELAR) sobre
           un SKU en colisión. Elimina la colisión resuelta de la sesión.

    Body JSON esperado:
    {
        "lote_id": "uuid",
        "sku": "ART-001",
        "decision": "SUMAR",           // o "SUSTITUIR" o "CANCELAR"
        "cantidad_excel": "10",
        "almacen_id": 1,
        "costo": "25.50",              // opcional
        "precio_divisa": "35.00",      // opcional
        "nombre_excel": "Nombre Nuevo" // opcional
    }

    Respuesta JSON:
    {
        "ok": true,
        "decision": "SUMAR",
        "sku": "ART-001",
        "movimientos": [12, 13],
        "mensaje": "...",
        "colisiones_pendientes": 2
    }
    """
    try:
        datos = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Body inválido. Se esperaba JSON.'}, status=400)

    lote_id = datos.get('lote_id', '')
    sku = datos.get('sku', '').strip()
    decision = datos.get('decision', '').strip().upper()
    cantidad_excel = datos.get('cantidad_excel', '0')
    almacen_id = datos.get('almacen_id')
    costo = datos.get('costo')
    precio_divisa = datos.get('precio_divisa')
    nombre_excel = datos.get('nombre_excel', '')
    usuario = datos.get('usuario', '')

    # Validaciones básicas
    if not lote_id:
        return JsonResponse({'ok': False, 'error': 'lote_id es obligatorio.'}, status=400)
    if not sku:
        return JsonResponse({'ok': False, 'error': 'sku es obligatorio.'}, status=400)
    if not decision:
        return JsonResponse({'ok': False, 'error': 'decision es obligatoria.'}, status=400)
    if almacen_id is None:
        return JsonResponse({'ok': False, 'error': 'almacen_id es obligatorio.'}, status=400)

    try:
        resultado = svc.resolver_colision(
            sku=sku,
            almacen_id=int(almacen_id),
            decision=decision,
            cantidad_excel=cantidad_excel,
            lote_id=lote_id,
            usuario=usuario or (request.user.username if request.user.is_authenticated else 'anónimo'),
            costo=costo if costo else None,
            precio_divisa=precio_divisa if precio_divisa else None,
            nombre_excel=nombre_excel,
        )
    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=422)
    except Exception as e:
        logger.exception('[COLISIÓN] Error inesperado resolviendo SKU %s.', sku)
        return JsonResponse({'ok': False, 'error': f'Error interno: {e}'}, status=500)

    # ── Actualizar sesión: eliminar la colisión resuelta ──────────────────────
    session_key = f'carga_{lote_id}'
    session_data = request.session.get(session_key, {})
    colisiones = session_data.get('colisiones', [])
    colisiones_restantes = [c for c in colisiones if c['sku'] != sku]

    if colisiones_restantes:
        request.session[session_key] = {
            'colisiones': colisiones_restantes,
            'lote_id': lote_id,
        }
    else:
        # Todas las colisiones resueltas → limpiar entrada de sesión
        request.session.pop(session_key, None)

    request.session.modified = True

    return JsonResponse({
        'ok': True,
        'decision': resultado['decision'],
        'sku': resultado['sku'],
        'movimientos': resultado['movimientos'],
        'mensaje': resultado['mensaje'],
        'colisiones_pendientes': len(colisiones_restantes),
    })


# ═══════════════════════════════════════════════════════════════════════
# TICKET #5: MÓDULO DE VENTAS
# ═══════════════════════════════════════════════════════════════════════

from django.views.decorators.http import require_GET


@require_GET
def api_buscar_articulos(request):
    from .models import Articulo, ConfiguracionEmpresa
    from .managers import get_current_empresa
    from decimal import Decimal

    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    articulos = Articulo.objects.filter(activo=True).filter(
        db_models.Q(sku__icontains=q) | db_models.Q(nombre__icontains=q)
    ).order_by('nombre')[:20]

    empresa_id = get_current_empresa()
    try:
        config = ConfiguracionEmpresa.objects.get(empresa_id=empresa_id)
        factor = config.factor_cobertura if config else Decimal('1.0000')
    except ConfiguracionEmpresa.DoesNotExist:
        factor = Decimal('1.0000')

    results = []
    for a in articulos:
        precio_ajustado = (a.precio_divisa * factor).quantize(Decimal('0.01'))
        results.append({
            'sku': a.sku,
            'nombre': a.nombre,
            'precio': str(precio_ajustado),
            'tipo': a.tipo,
            'usa_serial': a.usa_serial,
        })
    return JsonResponse({'results': results})


@require_GET
def api_validar_stock(request, sku, almacen_id):
    from .models import Articulo, Almacen

    try:
        articulo = Articulo.objects.get(sku=sku, activo=True)
    except Articulo.DoesNotExist:
        return JsonResponse({'stock_disponible': 0}, status=404)

    try:
        almacen = Almacen.objects.get(pk=almacen_id, activo=True)
    except Almacen.DoesNotExist:
        return JsonResponse({'stock_disponible': 0}, status=404)

    stock = articulo.get_stock_disponible(almacen=almacen)
    return JsonResponse({'stock_disponible': stock})


import json
from django.http import JsonResponse

@require_http_methods(["POST"])
@csrf_exempt
def vista_crear_venta(request):
    """Endpoint AJAX para procesar el carrito de compras y generar Nota de Entrega."""
    try:
        data = json.loads(request.body)
        empresa_id = data.get('empresa_id')
        cliente_id = data.get('cliente_id')
        almacen_id = data.get('almacen_id')
        lista_items = data.get('items', [])
        observaciones = data.get('observaciones', '')
        
        if not almacen_id or not lista_items:
            return JsonResponse({'ok': False, 'error': 'Faltan datos obligatorios (almacen_id o items).'}, status=400)

        for item in lista_items:
            if 'sku' in item and 'articulo_sku' not in item:
                item['articulo_sku'] = item.pop('sku')

        nota = svc.procesar_venta(
            empresa_id=empresa_id,
            cliente_id=cliente_id,
            lista_items=lista_items,
            almacen_id=almacen_id,
            usuario=request.user.username if request.user.is_authenticated else 'API',
            observaciones=observaciones
        )
        
        return JsonResponse({
            'ok': True,
            'nota_id': nota.pk,
            'correlativo': nota.numero
        })
    except ValueError as e:
        # Error de negocio (ej. falta de stock) -> Rollback automático en procesar_venta
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)
    except Exception as e:
        logger.exception("Error procesando venta")
        return JsonResponse({'ok': False, 'error': 'Error interno del servidor.'}, status=500)


@require_http_methods(["GET"])
def vista_imprimir_nota(request, nota_id):
    """Renderiza el layout minimalista de la Nota de Entrega para impresión."""
    from .models import NotaEntrega, ConfiguracionEmpresa
    nota = get_object_or_404(NotaEntrega.objects.select_related('cliente', 'almacen'), pk=nota_id)
    detalles = nota.detalles.select_related('articulo').all()
    config = ConfiguracionEmpresa.objects.get(empresa=nota.empresa)
    
    total_usd = sum(d.cantidad * d.precio_unitario_usd for d in detalles)
    total_bs = sum(d.cantidad * d.precio_unitario_bs for d in detalles)
    
    context = {
        'nota': nota,
        'detalles': detalles,
        'config': config,
        'total_usd': total_usd,
        'total_bs': total_bs
    }
    return render(request, 'inventory/nota_entrega_print.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 6. TASAS DE CAMBIO
# ─────────────────────────────────────────────────────────────────────────────

def vista_sincronizar_tasa(request):
    """
    Endpoint para sincronizar la tasa de cambio.
    Solo admite POST. Retorna JSON.
    """
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)
    
    from .services import sincronizar_tasa_cambio
    resultado = sincronizar_tasa_cambio()
    return JsonResponse(resultado)


# ─────────────────────────────────────────────────────────────────────────────
# 7. AUDITORÍA Y KÁRDEX
# ─────────────────────────────────────────────────────────────────────────────

def vista_movimientos(request):
    """
    Renderiza la tabla histórica de MovimientoKardex con filtros avanzados.
    Aplica select_related para evitar el problema N+1 queries.
    """
    from .models import MovimientoKardex, Almacen

    movimientos = MovimientoKardex.objects.select_related('articulo', 'almacen', 'nota_entrega', 'documento_compra').all().order_by('-fecha_hora')

    almacen_id = request.GET.get('almacen_id')
    sku = request.GET.get('sku')
    tipo = request.GET.get('tipo')
    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')

    if almacen_id:
        movimientos = movimientos.filter(almacen_id=almacen_id)
    if sku:
        movimientos = movimientos.filter(articulo__sku__icontains=sku)
    if tipo in ['ENTRADA', 'SALIDA']:
        movimientos = movimientos.filter(tipo=tipo)
    if fecha_desde:
        movimientos = movimientos.filter(fecha_hora__date__gte=fecha_desde)
    if fecha_hasta:
        movimientos = movimientos.filter(fecha_hora__date__lte=fecha_hasta)

    almacenes = Almacen.objects.filter(activo=True)

    context = {
        'movimientos': movimientos,
        'almacenes': almacenes,
        'filtros': {
            'almacen_id': almacen_id or '',
            'sku': sku or '',
            'tipo': tipo or '',
            'fecha_desde': fecha_desde or '',
            'fecha_hasta': fecha_hasta or '',
        }
    }
    return render(request, 'inventory/movimientos.html', context)

# ─────────────────────────────────────────────────────────────────────────────
# 8. CONTACTOS Y COMPRAS (TICKET #9)
# ─────────────────────────────────────────────────────────────────────────────

def contactos(request):
    """
    Gestión segmentada de Clientes y Proveedores.
    Fuerza RIF y Asesor para Proveedores vía POST.
    """
    from .models import Contacto
    from django.core.exceptions import ValidationError
    from django.contrib import messages
    from .managers import get_current_empresa
    from django.http import HttpResponseForbidden

    # Resolver empresa activa del ContextVar (TenantMiddleware lo setea).
    # Esto reemplaza getattr(request, 'empresa', None) que NUNCA se setea
    # (el middleware solo setea el ContextVar, no request.empresa).
    empresa_id = get_current_empresa()
    if not empresa_id:
        return HttpResponseForbidden("Sesión de empresa no detectada.")

    if request.method == 'POST':
        tipo = request.POST.get('tipo', 'CLIENTE')
        nombre = request.POST.get('nombre', '').strip()
        telefono = request.POST.get('telefono', '').strip()
        correo = request.POST.get('correo', '').strip()
        rif = request.POST.get('rif', '').strip()
        nombre_asesor = request.POST.get('nombre_asesor', '').strip()
        red_social = request.POST.get('red_social', '').strip()
        direccion = request.POST.get('direccion', '').strip()
        observaciones = request.POST.get('observaciones', '').strip()

        try:
            if not nombre:
                raise ValidationError("El nombre del contacto es obligatorio.")

            if tipo == 'PROVEEDOR':
                if not rif:
                    raise ValidationError("El RIF es obligatorio para proveedores.")
                if not nombre_asesor:
                    raise ValidationError("El nombre del asesor es obligatorio para proveedores.")

            # Buscar si existe (update) o crear nuevo
            import uuid
            Contacto.objects.create(
                empresa_id=empresa_id,
                identificacion=rif if rif else str(uuid.uuid4())[:20],
                tipo=tipo,
                nombre=nombre,
                telefono=telefono,
                correo=correo,
                rif=rif,
                nombre_asesor=nombre_asesor,
                red_social=red_social,
                direccion=direccion,
                observaciones=observaciones
            )
            messages.success(request, f"{tipo.capitalize()} registrado exitosamente.")
        except ValidationError as e:
            messages.error(request, e.message)

    # Listados para las pestañas
    clientes = Contacto.objects.filter(empresa_id=empresa_id, tipo='CLIENTE').order_by('nombre')
    proveedores = Contacto.objects.filter(empresa_id=empresa_id, tipo='PROVEEDOR').order_by('nombre')

    return render(request, 'inventory/contactos.html', {
        'clientes': clientes,
        'proveedores': proveedores
    })

# ─────────────────────────────────────────────────────────────────────────────
# 9. IMPRESIÓN PARAMETRIZADA POR COORDENADAS (TICKET #12)
# ─────────────────────────────────────────────────────────────────────────────

def vista_imprimir_coordenadas(request, nota_id):
    """
    Recupera una Nota de Entrega y la renderiza usando un lienzo de impresión libre.
    Las coordenadas y el espaciado provienen del perfil Multi-Tenant de la empresa.
    """
    from .models import NotaEntrega, ConfiguracionEmpresa
    from django.shortcuts import get_object_or_404
    
    nota = get_object_or_404(
        NotaEntrega.objects.select_related('cliente', 'empresa').prefetch_related('detalles__articulo'), 
        pk=nota_id
    )
    
    # Asumimos que request.empresa fue inyectada por el middleware, 
    # pero por seguridad podemos sacar la config de la misma nota.
    config = ConfiguracionEmpresa.objects.get(empresa=nota.empresa)

    # Calculamos totales para el documento
    total_usd = sum(d.precio_unitario_usd * d.cantidad for d in nota.detalles.all())
    total_bs = sum(d.precio_unitario_bs * d.cantidad for d in nota.detalles.all())

    context = {
        'nota': nota,
        'detalles': nota.detalles.all(),
        'config': config,
        'total_usd': total_usd,
        'total_bs': total_bs
    }

    return render(request, 'inventory/impresion_coordenadas.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 10. EXPORTACIÓN Y TELEMETRÍA (TICKET #13)
# ─────────────────────────────────────────────────────────────────────────────

def vista_exportar_respaldo(request):
    """
    Controlador para descargar el snapshot lógico en JSON del Tenant activo.
    """
    import json
    from django.http import HttpResponse
    from django.core.serializers.json import DjangoJSONEncoder
    from django.utils.text import slugify
    import time
    from .services import exportar_datos_tenant

    from .managers import get_current_empresa
    empresa_id = get_current_empresa()
    if not empresa_id:
        return JsonResponse({'ok': False, 'error': 'Sesión de empresa no detectada.'}, status=403)
    payload = exportar_datos_tenant(empresa_id=empresa_id, meses_historico=6)
    
    json_data = json.dumps(payload, cls=DjangoJSONEncoder, indent=2)
    
    rif_slug = slugify(payload['metadata']['empresa_rif'])
    timestamp = int(time.time())
    filename = f"respaldo_a2lt_{rif_slug}_{timestamp}.json"
    
    response = HttpResponse(json_data, content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


# ─────────────────────────────────────────────────────────────────────────────
# 11. TRAZABILIDAD Y CONTROL DE SERIALES (TICKET #14-SAAS)
# ─────────────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def vista_buscar_seriales_articulo(request, articulo_sku, almacen_id):
    """
    Endpoint AJAX para obtener los seriales disponibles de un artículo específico
    dentro de un almacén seleccionado.
    Filtra obligatoriamente por estado='DISPONIBLE'.
    """
    from .models import SerialArticulo
    # Obtenemos el listado de seriales
    seriales = SerialArticulo.objects.filter(
        articulo__sku=articulo_sku,
        almacen_id=almacen_id,
        estado='DISPONIBLE'
    ).order_by('id') # FIFO base

    # Construimos el payload de respuesta
    data = [
        {
            'id': s.pk,
            'serial': s.serial
        }
        for s in seriales
    ]
    
    return JsonResponse({'ok': True, 'data': data})


@login_required
def articulos_view(request):
    """
    Vista para administrar artículos (GET=listar, POST=crear/actualizar).
    Multi-tenant: opera sobre la empresa activa del ContextVar.

    Requiere @login_required + CSRF token en el fetch (articulos.html).
    """
    from django.http import JsonResponse
    from decimal import Decimal
    from .models import Articulo
    from .managers import get_current_empresa

    if request.method == 'POST':
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST

        sku = data.get('sku', '').strip()
        nombre = data.get('nombre', '').strip()
        if not sku or not nombre:
            return JsonResponse({'ok': False, 'error': 'SKU y Nombre son obligatorios.'}, status=400)

        empresa_id = get_current_empresa()
        if not empresa_id:
            return JsonResponse({'ok': False, 'error': 'No hay empresa activa.'}, status=400)

        defaults = {
            'nombre': nombre,
            'categoria': data.get('categoria', 'OTROS'),
            'tipo': data.get('tipo', 'FISICO'),
            'costo': Decimal(str(data.get('costo', '0'))),
            'precio_divisa': Decimal(str(data.get('precio_divisa', '0'))),
            'descripcion': data.get('descripcion', ''),
            'ficha_tecnica': data.get('ficha_tecnica', ''),
            'social_quick': data.get('social_quick', ''),
            'social_cross': data.get('social_cross', ''),
        }

        articulo, created = Articulo.objects.update_or_create(
            sku=sku,
            empresa_id=empresa_id,
            defaults=defaults,
        )

        return JsonResponse({'ok': True, 'created': created, 'sku': articulo.sku})

    articulos = Articulo.objects.filter(activo=True).order_by('nombre')
    articulos_json = json.dumps(list(articulos.values(
        'sku', 'nombre', 'categoria', 'tipo',
        'costo', 'precio_divisa', 'descripcion',
        'ficha_tecnica', 'social_quick', 'social_cross',
    )), default=str)
    return render(request, 'inventory/articulos.html', {
        'articulos': articulos,
        'articulos_json': articulos_json,
    })


def configuracion_view(request):
    """
    Vista para ver y guardar la configuración global de la empresa inquilina.
    """
    from decimal import Decimal
    from .models import ConfiguracionEmpresa, AuditoriaTasa
    
    config = ConfiguracionEmpresa.objects.first()
    
    if request.method == 'POST':
        try:
            bcv_old = config.tasa_bcv
            mercado_old = config.tasa_mercado
            factor_old = config.factor_cobertura
            
            config.tasa_bcv = Decimal(request.POST.get('tasa_bcv', '0.0000'))
            config.tasa_mercado = Decimal(request.POST.get('tasa_mercado', '0.0000'))
            config.factor_cobertura = Decimal(request.POST.get('factor_cobertura', '1.0000'))
            config.margen_global = Decimal(request.POST.get('margen_global', '0.00'))
            config.descuento_global = Decimal(request.POST.get('descuento_global', '0.00'))
            
            # Parametros de impresión
            config.print_offset_x = Decimal(request.POST.get('print_offset_x', '0.00'))
            config.print_offset_y = Decimal(request.POST.get('print_offset_y', '0.00'))
            config.print_row_spacing = Decimal(request.POST.get('print_row_spacing', '5.00'))
            
            # Cuarentena
            config.usa_almacen_cuarentena = 'usa_almacen_cuarentena' in request.POST
            
            # API
            config.api_url = request.POST.get('api_url', '').strip()
            config.response_selector = request.POST.get('response_selector', '').strip()

            # Social Selling (Cross-Selling)
            config.cross_selling_header = request.POST.get('cross_selling_header', '').strip()
            config.cross_selling_footer = request.POST.get('cross_selling_footer', '').strip()

            config.save()
            
            if (config.tasa_bcv != bcv_old or config.tasa_mercado != mercado_old or config.factor_cobertura != factor_old):
                AuditoriaTasa.objects.create(
                    empresa=config.empresa,
                    tasa_bcv=config.tasa_bcv,
                    tasa_mercado=config.tasa_mercado,
                    factor_cobertura=config.factor_cobertura,
                    fuente='MANUAL',
                    notas='Actualización desde Configuración Global'
                )
                
            messages.success(request, 'Configuración global actualizada de manera exitosa.')
            return redirect('inventory:configuracion')
        except Exception as e:
            messages.error(request, f'Error al guardar la configuración: {str(e)}')

    auditorias = AuditoriaTasa.objects.all().order_by('-fecha_hora')[:30]
    
    context = {
        'config': config,
        'auditorias': auditorias,
    }
    return render(request, 'inventory/configuracion.html', context)



# ─────────────────────────────────────────────────────────────────────────────
# TICKET #19: POS Inverso (Compras)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def compras_view(request):
    """
    Renderiza la terminal de mostrador para ingreso de facturas de compra.
    """
    from .models import Contacto, Almacen, ConfiguracionEmpresa
    from .managers import get_current_empresa
    
    proveedores = Contacto.objects.filter(tipo='PROVEEDOR').order_by('nombre')
    almacenes = Almacen.objects.filter(activo=True).order_by('-es_principal', 'nombre')

    empresa_id = get_current_empresa()
    try:
        config = ConfiguracionEmpresa.objects.get(empresa_id=empresa_id)
    except ConfiguracionEmpresa.DoesNotExist:
        config = None

    context = {
        'proveedores': proveedores,
        'almacenes': almacenes,
        'config': config,
    }
    return render(request, 'inventory/compras.html', context)

import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from decimal import Decimal
from .services import registrar_compra_proveedor

@login_required
@require_POST
def registrar_compra_api(request):
    """
    Recibe el payload JSON del POS Inverso, valida e invoca al motor transaccional.
    """
    try:
        data = json.loads(request.body)
        empresa_id = data.get('empresa_id')
        proveedor_id = data.get('proveedor_id')
        numero_factura = data.get('numero_factura')
        fecha_compra = data.get('fecha_compra')
        monto_total_usd = Decimal(str(data.get('monto_total_usd', '0.00')))
        almacen_id = data.get('almacen_id')
        lista_items = data.get('lista_items', [])
        observaciones = data.get('observaciones', '')

        if not proveedor_id:
            return JsonResponse({'ok': False, 'error': 'Seleccione un proveedor.'}, status=400)

        for item in lista_items:
            if 'sku' in item and 'articulo_sku' not in item:
                item['articulo_sku'] = item.pop('sku')
            item['cantidad'] = Decimal(str(item['cantidad']))
            item['costo_factura'] = Decimal(str(item['costo_factura']))
            # Los seriales ya vienen como lista de strings en item.get('seriales')

        registrar_compra_proveedor(
            empresa_id=empresa_id,
            proveedor_id=proveedor_id,
            numero_factura=numero_factura,
            fecha_compra=fecha_compra,
            monto_total_usd=monto_total_usd,
            almacen_id=almacen_id,
            lista_items=lista_items,
            usuario=request.user.username,
            observaciones=observaciones
        )

        return JsonResponse({'ok': True, 'mensaje': 'Compra registrada exitosamente.'})

    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


# ─────────────────────────────────────────────────────────────────────────────
# TICKET #20: MÓDULO DE REVERSOS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def reversos_view(request):
    from .models import NotaEntrega, DocumentoCompra
    
    empresa_id = request.session.get('empresa_id')
    
    if empresa_id:
        ventas = NotaEntrega.objects.filter(empresa_id=empresa_id).order_by('-fecha', '-id')
        compras = DocumentoCompra.objects.filter(empresa_id=empresa_id).order_by('-fecha_compra', '-id')
    else:
        # Fallback
        ventas = NotaEntrega.objects.none()
        compras = DocumentoCompra.objects.none()
        
    context = {
        'ventas': ventas,
        'compras': compras,
    }
    return render(request, 'inventory/reversos.html', context)

@require_http_methods(["POST"])
@login_required
def api_reversar_venta(request):
    import json
    from . import services as svc
    
    try:
        data = json.loads(request.body)
        nota_id = data.get('id')
        motivo = data.get('motivo')
        empresa_id = request.session.get('empresa_id')
        
        if not nota_id or not motivo:
            return JsonResponse({'ok': False, 'error': 'ID y motivo son obligatorios.'}, status=400)
            
        resultado = svc.reversar_nota_entrega(empresa_id, nota_id, motivo)
        return JsonResponse(resultado)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)

@require_http_methods(["POST"])
@login_required
def api_reversar_compra(request):
    import json
    from . import services as svc
    
    try:
        data = json.loads(request.body)
        compra_id = data.get('id')
        motivo = data.get('motivo')
        empresa_id = request.session.get('empresa_id')
        
        if not compra_id or not motivo:
            return JsonResponse({'ok': False, 'error': 'ID y motivo son obligatorios.'}, status=400)
            
        resultado = svc.reversar_documento_compra(empresa_id, compra_id, motivo)
        return JsonResponse(resultado)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)

