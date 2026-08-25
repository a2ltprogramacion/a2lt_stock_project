# Informe de Auditoría Integral — A2LT Stock System
**Auditor**: Antigravity Senior Full-Stack Auditor  
**Fecha**: 2026-07-15  
**Alcance**: `y:\Proyectos\a2lt_stock_project` — Django 4.x / Python / SQLite / Tailwind CSS  
**Archivos auditados**: `settings.py`, `views.py` (2132L), `services.py` (2523L), `models.py` (2101L), `middleware.py`, `managers.py`, `admin.py`, `templates/inventory/base.html`, `login.html`, `.env`

---

## 1. Calidad de Código y Arquitectura

---

### Hallazgo A-01 — [Alta]: God-File Anti-Pattern en `services.py` y `views.py`

**Componentes**: [`services.py`](file:///y:/Proyectos/a2lt_stock_project/inventory/services.py) (2 523 líneas) y [`views.py`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py) (2 132 líneas).

**Impacto**: La complejidad ciclomática acumulada en un solo módulo hace imposible la paralelización de desarrollo, eleva exponencialmente el riesgo de regresión ante cualquier modificación, y convierte cada `import` en un riesgo de importación circular latente. El propio ADR-21 en `services.py` reconoce el problema pero lo aplaza sin criterio de salida claro. Con 4 655 líneas de lógica crítica en 2 archivos, el MTTR (tiempo de resolución de incidentes) es innecesariamente alto.

**Solución Propuesta**: Migración modular por dominio funcional. El ADR-21 es válido para proteger el estado actual de tests, pero debe incluir un umbral explícito de split (ej. > 2000 líneas o cuando se añada un nuevo módulo de dominio):

```
inventory/
  services/
    __init__.py          # re-exporta la API pública manteniendo compatibilidad
    kardex.py            # registrar_movimiento, calcular_stock_combo
    ventas.py            # procesar_venta
    compras.py           # registrar_compra_proveedor
    carga_masiva.py      # procesar_carga_masiva, resolver_colision
    tasas.py             # sincronizar_tasa_cambio
    reversos.py          # reversar_nota_entrega, reversar_documento_compra
    devoluciones.py      # procesar_devolucion_venta, procesar_devolucion_compra
    exportacion.py       # exportar_datos_tenant
```

---

### Hallazgo A-02 — [Alta]: Imports Diferidos Masivos Violan el Principio de Cohesión

**Componentes**: [`views.py`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py) — prácticamente cada función de vista realiza `from .models import X`, `from decimal import Decimal`, `from django.http import JsonResponse` dentro del cuerpo de la función.

**Impacto**: Los imports diferidos no son una optimización en Django (el módulo ya está cargado en memoria). Solo añaden ruido y ocultan dependencias reales. Un linter o el analizador estático de tipos no puede inferir el grafo de dependencias del módulo de forma trivial. En ~40 vistas, esto se repite ~120 veces de forma redundante.

**Solución Propuesta**: Centralizar todos los imports al encabezado de cada módulo. Solo usar imports diferidos cuando sea estrictamente necesario para romper una dependencia circular real (que en este proyecto ya está resuelta vía `managers.py`).

```python
# Al inicio de views.py — centralizado
from decimal import Decimal
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.core.paginator import Paginator, EmptyPage
from .models import (
    Almacen, Articulo, InventarioAlmacen, MovimientoKardex,
    NotaEntrega, DetalleNotaEntrega, ConfiguracionEmpresa,
    Contacto, AuditoriaTasa, DocumentoCompra, NotaCredito, SerialArticulo
)
from .managers import get_current_empresa
```

---

### Hallazgo A-03 — [Alta]: N+1 Queries en Dashboard (Combo Loop sin `prefetch_related`)

**Componentes**: [`views.py:L171-187`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py#L171-L187) — función `dashboard()`.

**Impacto**: El bloque de cálculo de combos ejecuta hasta `10 combos × N almacenes × M componentes` consultas SQL independientes por cada petición al dashboard. Con 10 combos y 5 almacenes, puede disparar >150 queries por carga de página, degradando el rendimiento de forma exponencial a medida que crece el catálogo.

```python
# ACTUAL — N+1 crítico
for combo in combos_qs[:10]:
    for alm in almacenes_qs:  # una query por almacén × combo
        s = _svc.calcular_stock_combo(combo, alm)  # N queries internas
```

**Solución Propuesta**: Pre-cargar la receta y el inventario en memoria antes del loop, o calcular el stock máximo de combos desde una única query agregada:

```python
# Opción 1: prefetch recetas e inventario
combos_qs = Articulo.objects.filter(tipo='COMBO', activo=True).prefetch_related(
    'receta_combo__componente',
    Prefetch('receta_combo__componente__inventarios',
             queryset=InventarioAlmacen.objects.filter(almacen__activo=True))
)[:10]
```

---

### Hallazgo A-04 — [Media]: `configuracion_view` usa `ConfiguracionEmpresa.objects.first()` sin Filtro Multi-Tenant

**Componentes**: [`views.py:L1485`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py#L1485).

**Impacto**: `.first()` sobre el manager `EmpresaManager` devolverá el `ConfiguracionEmpresa` de la empresa activa en el ContextVar — correcto. Sin embargo, si por algún motivo el ContextVar es `None` (bug de inicialización o test mal configurado), el manager devuelve `QuerySet.none()` y `.first()` retorna `None`, causando `AttributeError: 'NoneType' object has no attribute 'tasa_bcv'` en la línea siguiente.

```python
# ACTUAL — falla silenciosa si config es None
config = ConfiguracionEmpresa.objects.first()
bcv_old = config.tasa_bcv  # AttributeError si config=None
```

**Solución Propuesta**:

```python
empresa_id = get_current_empresa()
if not empresa_id:
    messages.error(request, 'Sesión de empresa no detectada.')
    return redirect('inventory:dashboard')

config = get_object_or_404(ConfiguracionEmpresa, empresa_id=empresa_id)
```

---

### Hallazgo A-05 — [Media]: Lógica de Negocio Financiera en `Vista` (DRY Violation)

**Componentes**: [`views.py:L710-765`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py#L710-L765) (`vista_detalle_nota`) y [`views.py:L867-876`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py#L867-L876) (`generar_pdf_nota`) — lógica de cálculo de totales/descuentos duplicada.

**Impacto**: La lógica de aplicación de `descuento_global` al subtotal y al IVA está copiada palabra por palabra entre `vista_detalle_nota`, `generar_pdf_nota`, `vista_detalle_compra` y `generar_pdf_compra`. Cualquier corrección en la fórmula debe aplicarse en 4 lugares distintos, lo que garantiza divergencia eventualmente.

**Solución Propuesta**: Extraer a una función utilitaria en `services.py` o un módulo `utils.py`:

```python
# services/utils.py
from decimal import Decimal

def calcular_totales_documento(detalles, descuento_global: Decimal) -> dict:
    """Calcula subtotales, IVA neto y total con descuento global aplicado."""
    total_usd = sum(d.cantidad * d.precio_base for d in detalles)
    total_bs  = sum(d.cantidad * d.precio_ajustado_bcv for d in detalles)
    total_iva_usd = sum(d.iva_usd for d in detalles)
    total_iva_bs  = sum(d.iva_bs for d in detalles)

    factor = Decimal('1') - (descuento_global / Decimal('100'))
    return {
        'subtotal_usd_neto':   (total_usd * factor).quantize(Decimal('0.01')),
        'total_iva_usd_neto':  (total_iva_usd * factor).quantize(Decimal('0.01')),
        'monto_descuento_usd': (total_usd - total_usd * factor).quantize(Decimal('0.01')),
        'total_iva_bs_neto':   (total_iva_bs * factor).quantize(Decimal('0.01')),
        'total_bs_neto':       ((total_bs * factor) + (total_iva_bs * factor)).quantize(Decimal('0.01')),
    }
```

---

### Hallazgo A-06 — [Media]: Función Anidada `celda()` Definida Dentro de un Loop

**Componentes**: [`services.py:L559-564`](file:///y:/Proyectos/a2lt_stock_project/inventory/services.py#L559-L564) — `procesar_carga_masiva()`.

**Impacto**: Definir una función (`celda`) dentro de un bucle `for` hace que Python cree un nuevo objeto función en cada iteración. Para archivos con miles de filas esto produce overhead innecesario de allocación de objetos, aunque en Python el impacto es mínimo. El mayor problema es de legibilidad y testabilidad: `celda` no puede testearse de forma aislada.

**Solución Propuesta**: Mover `celda()` como función de módulo antes de `procesar_carga_masiva()`.

---

### Hallazgo A-07 — [Baja]: `logout_view` Acepta GET (CSRF Risk-Vector Latente)

**Componentes**: [`views.py:L72-74`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py#L72-L74).

**Impacto**: Cualquier `<img src="/logout/">` o enlace externo puede forzar el logout del usuario via CSRF. Aunque Django protege las sesiones, la destrucción de la misma via GET es un vector de CSRF de disponibilidad (no de confidencialidad).

**Solución Propuesta**:

```python
@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return redirect('inventory:login')
```

Y en el sidebar reemplazar el `<a href="...logout">` por un mini `<form method="POST">`.

---

## 2. Seguridad y Robustez (SecOps)

---

### Hallazgo S-01 — [Crítica]: `SECRET_KEY` de Desarrollo Hardcodeada en `.env` Commiteado

**Componentes**: [`.env:L9`](file:///y:/Proyectos/a2lt_stock_project/.env#L9) y [`settings.py:L28`](file:///y:/Proyectos/a2lt_stock_project/a2lt_stock_project/settings.py#L28).

**Impacto**: El `.env` de desarrollo con `SECRET_KEY=dev-test-key-c2lt5-f52afea-2026-07-no-production-pls` está en el repositorio (existe `.gitignore` pero históricamente pudo haber sido commiteado). Un atacante con acceso al repositorio puede forjar cookies de sesión, tokens CSRF y cualquier dato firmado por Django. El fallback en `settings.py` (`dev-insecure-key-change-in-prod`) confirma que el valor es conocido. **Esto invalida toda la seguridad de sesiones.**

**Solución Propuesta**:
1. Verificar el historial de Git con `git log --all -- .env` y purgarlo si fue commiteado (`git filter-repo`).
2. Rotar la clave **inmediatamente** en producción:
```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```
3. Eliminar el fallback inseguro de `settings.py`. Si no hay `SECRET_KEY` en entorno, el sistema debe **fallar explícitamente**:
```python
import sys
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    print("FATAL: SECRET_KEY no definida en variables de entorno.", file=sys.stderr)
    sys.exit(1)
```

---

### Hallazgo S-02 — [Alta]: SSRF (Server-Side Request Forgery) en `sincronizar_tasa_cambio()`

**Componentes**: [`services.py:L1426-1430`](file:///y:/Proyectos/a2lt_stock_project/inventory/services.py#L1426-L1430), [`views.py:L1081-1091`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py#L1081-L1091), y [`views.py:L1508`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py#L1508) (donde se guarda `api_url`).

**Impacto**: La URL de la API de tasas es configurable desde la interfaz web por cualquier usuario autenticado con acceso a Configuración. No existe ninguna validación de que la URL sea un endpoint externo legítimo. Un operador malintencionado puede configurar `api_url = http://169.254.169.254/latest/meta-data/` (AWS metadata) o `http://localhost:8080/internal-admin` para exfiltrar información de la red interna o servicios internos.

**Solución Propuesta**:

```python
import re
from urllib.parse import urlparse

ALLOWED_API_URL_PATTERN = re.compile(
    r'^https?://([\w\-]+\.)+[\w\-]+(:\d+)?(/.*)?$'
)
BLOCKED_HOSTS = {'localhost', '127.0.0.1', '0.0.0.0', '169.254.169.254', '::1'}

def validar_api_url(url: str) -> str:
    """Valida que la URL sea externa y no apunte a recursos internos."""
    if not ALLOWED_API_URL_PATTERN.match(url):
        raise ValueError(f"Formato de URL inválido: {url}")
    parsed = urlparse(url)
    hostname = parsed.hostname or ''
    if hostname in BLOCKED_HOSTS or hostname.startswith('192.168.') or hostname.startswith('10.'):
        raise ValueError(f"La URL apunta a un recurso de red privada (SSRF bloqueado): {hostname}")
    return url
```

Aplicar en `configuracion_view` antes de asignar `config.api_url`.

---

### Hallazgo S-03 — [Alta]: Exposición de Error Interno en Respuestas JSON de Producción

**Componentes**: [`views.py:L420`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py#L420), [`views.py:L487`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py#L487), [`views.py:L566`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py#L566), [`views.py:L1627-1628`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py#L1627-L1628).

**Impacto**: Múltiples handlers de excepción genérica retornan `str(e)` directamente al cliente:
```python
return JsonResponse({'ok': False, 'error': f'Error interno del servidor: {e}'}, status=500)
return JsonResponse({'ok': False, 'error': str(e)}, status=400)  # registrar_compra_api
```
En producción, esto expone stack traces, nombres de tabla de BD, rutas del sistema de ficheros y lógica interna a cualquier usuario que provoque un error inesperado. Esto cumple OWASP A05:2021 (Security Misconfiguration) y A09:2021 (Security Logging Failures).

**Solución Propuesta**:
```python
# Patrón seguro para todos los handlers genéricos
except Exception:
    logger.exception('[MÓDULO] Error inesperado en <nombre_vista>.')
    error_msg = 'Error interno del servidor.' if not settings.DEBUG else str(e)
    return JsonResponse({'ok': False, 'error': error_msg}, status=500)
```

---

### Hallazgo S-04 — [Alta]: Sin Rate Limiting en el Endpoint de Login (OWASP A07)

**Componentes**: [`views.py:L33-70`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py#L33-L70) — `login_view`.

**Impacto**: El endpoint de login no tiene ningún mecanismo de limitación de intentos (rate limiting, lockout, captcha). Un atacante puede realizar un ataque de fuerza bruta contra credenciales de forma ilimitada. Django Admin tiene protección básica, pero la vista personalizada no hereda nada de ello.

**Solución Propuesta**: Implementar `django-axes` (la solución más compatible con el stack actual):
```bash
pip install django-axes
```
```python
# settings.py
INSTALLED_APPS += ['axes']
MIDDLEWARE += ['axes.middleware.AxesMiddleware']
AUTHENTICATION_BACKENDS = ['axes.backends.AxesStandaloneBackend', 'django.contrib.auth.backends.ModelBackend']
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # 1 hora de lockout
AXES_LOCKOUT_TEMPLATE = 'inventory/lockout.html'
```

---

### Hallazgo S-05 — [Alta]: `vista_imprimir_coordenadas` sin Verificación de Ownership Multi-Tenant

**Componentes**: [`views.py:L1330-1351`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py#L1330-L1351).

**Impacto**: La vista recupera la nota por `pk=nota_id` usando `get_object_or_404` **sin filtrar por `empresa_id`**. Cualquier usuario autenticado en el sistema (perteneciente a cualquier empresa) puede acceder a la nota de entrega de otra empresa cambiando el `nota_id` en la URL. Es un IDOR (Insecure Direct Object Reference) — OWASP A01:2021.

```python
# ACTUAL — sin filtro de empresa (IDOR)
nota = get_object_or_404(
    NotaEntrega.objects.select_related(...),
    pk=nota_id   # cualquier nota del sistema es accesible
)
```

**Solución Propuesta**:
```python
empresa_id = request.session.get('empresa_id')
nota = get_object_or_404(
    NotaEntrega.objects.select_related('cliente', 'empresa').prefetch_related('detalles__articulo'),
    pk=nota_id,
    empresa_id=empresa_id  # filtro anti-IDOR obligatorio
)
```

---

### Hallazgo S-06 — [Media]: `logout_view` No Invalida Explícitamente los Datos de Sesión

**Componentes**: [`views.py:L72-74`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py#L72-L74).

**Impacto**: `logout(request)` de Django invalida la sesión, pero no limpia el `empresa_id` del ContextVar del thread. Si el servidor usa un pool de threads y hay un bug de no-reset en el middleware, el ContextVar podría quedar con datos stale. El middleware sí hace `reset_current_empresa(token)` en el `finally`, pero el logout no pasa por ese middleware post-respuesta de la misma manera. Riesgo bajo en el flujo normal pero no es cero.

**Solución Propuesta**: Limpiar explícitamente la sesión antes de `logout()`:
```python
def logout_view(request):
    request.session.flush()  # destruye la sesión y crea una nueva vacía
    logout(request)
    return redirect('inventory:login')
```

---

### Hallazgo S-07 — [Media]: `CSRF_COOKIE_HTTPONLY = False` — Justificado pero Documentado de Forma Insuficiente

**Componentes**: [`settings.py:L237`](file:///y:/Proyectos/a2lt_stock_project/a2lt_stock_project/settings.py#L237).

**Impacto**: `CSRF_COOKIE_HTTPONLY = False` permite que JavaScript lea la cookie CSRF. Esto es una práctica deliberada (documentada en el código) para que `getCookie('csrftoken')` funcione en los fetch AJAX. Sin embargo, si un atacante logra XSS, puede exfiltrar el token CSRF. La alternativa segura es usar el header `X-CSRFToken` desde un elemento del DOM (no de la cookie).

**Solución Propuesta**: Cambiar a `CSRF_COOKIE_HTTPONLY = True` y modificar el helper de JS en `base.html` para leer el token desde el elemento `{% csrf_token %}` del DOM:
```javascript
// Alternativa segura: leer desde el input oculto del DOM
function getCsrfToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value
        || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
}
```

---

### Hallazgo S-08 — [Media]: `vista_buscar_seriales_articulo` sin Validación Multi-Tenant

**Componentes**: [`views.py:L1402-1416`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py#L1402-L1416).

**Impacto**: El endpoint `/seriales/<sku>/<almacen_id>/` filtra por `articulo__sku` y `almacen_id` pero no valida que el `almacen_id` pertenezca a la empresa activa del usuario. Un usuario podría enumerar seriales de otro tenant especificando un `almacen_id` ajeno.

**Solución Propuesta**:
```python
empresa_id = get_current_empresa()
seriales = SerialArticulo.objects.filter(
    articulo__sku=articulo_sku,
    articulo__empresa_id=empresa_id,   # validación multi-tenant
    almacen_id=almacen_id,
    almacen__empresa_id=empresa_id,    # doble validación
    estado='DISPONIBLE'
).order_by('id')
```

---

### Hallazgo S-09 — [Baja]: `db.sqlite3` en el Directorio Raíz del Proyecto (Sin Protección de Acceso)

**Componentes**: [`db.sqlite3`](file:///y:/Proyectos/a2lt_stock_project/db.sqlite3) — 643 KB, accesible.

**Impacto**: Si el servidor web sirve archivos estáticos desde `BASE_DIR` (error de configuración en producción), el archivo `db.sqlite3` sería descargable directamente, exponiendo toda la base de datos. Además, está en el repositorio (fichero de 643KB), lo que expone datos reales si el repo es público.

**Solución Propuesta**: Mover la BD fuera del directorio del proyecto y añadir `db.sqlite3` al `.gitignore`. Para producción, usar PostgreSQL.

---

## 3. Estética y Consistencia Visual (UI)

---

### Hallazgo U-01 — [Media]: Tailwind CSS via CDN en Producción (Performance y Seguridad)

**Componentes**: [`base.html:L9`](file:///y:/Proyectos/a2lt_stock_project/inventory/templates/inventory/base.html#L9) y [`login.html:L7`](file:///y:/Proyectos/a2lt_stock_project/inventory/templates/inventory/login.html#L7).

**Impacto**: El CDN de Tailwind carga en modo "play" (JIT en el navegador), lo que:
1. Genera una petición HTTP externa en cada carga de página (latencia).
2. Depende de una CDN de tercero — si `cdn.tailwindcss.com` falla, la UI queda sin estilos.
3. El CDN carga **todas** las utilidades de Tailwind (~3.9 MB en desarrollo), versus un build optimizado de ~10-30 KB para el CSS real usado.
4. No hay Subresource Integrity (SRI) hash en la etiqueta `<script>`, exponiendo al usuario a un potencial ataque de supply chain si el CDN es comprometido.

**Solución Propuesta**: Configurar Tailwind como parte del build pipeline de Django con `django-tailwind` o añadir un paso `npm run build` con purge:
```html
<!-- Reemplazar el CDN por un archivo CSS compilado y optimizado -->
<link rel="stylesheet" href="{% static 'css/main.css' %}">
```

---

### Hallazgo U-02 — [Media]: Inconsistencia de `tailwind.config` Duplicado entre Templates

**Componentes**: [`base.html:L21-49`](file:///y:/Proyectos/a2lt_stock_project/inventory/templates/inventory/base.html#L21-L49) y [`login.html:L10-31`](file:///y:/Proyectos/a2lt_stock_project/inventory/templates/inventory/login.html#L10-L31).

**Impacto**: El objeto `tailwind.config` con la paleta `corporate` está definido dos veces con valores ligeramente distintos. `login.html` omite los colores `slate.850` y `slate.950`, y la familia tipográfica `sans: ['Inter']`. Si se modifica la paleta de colores en uno, el otro no se actualiza, generando inconsistencia visual entre la pantalla de login y el sistema interno.

**Solución Propuesta**: Centralizar en un archivo JS estático compartido (`/static/js/tailwind.config.js`) y referenciarlo desde ambos templates:
```html
<script src="{% static 'js/tailwind.config.js' %}"></script>
```

---

### Hallazgo U-03 — [Media]: Sidebar No Responsive — Inutilizable en Pantallas < 1024px

**Componentes**: [`base.html:L148-232`](file:///y:/Proyectos/a2lt_stock_project/inventory/templates/inventory/base.html#L148-L232).

**Impacto**: El sidebar lateral de 256px (`w-64`) es fijo y nunca colapsa en pantallas móviles o tablets. No existe ningún breakpoint `md:hidden` ni un botón hamburguesa que lo oculte. En dispositivos de 768px o menos, el contenido principal queda comprimido en un área muy reducida, haciendo el sistema inoperable en tabletas (que los operadores de almacén podrían usar).

**Solución Propuesta**: Añadir toggle responsive al sidebar:
```html
<aside id="sidebar" class="w-64 ... hidden lg:flex flex-col ... transition-transform">
<!-- contenido del sidebar -->
</aside>
<button onclick="document.getElementById('sidebar').classList.toggle('hidden')" 
        class="lg:hidden fixed bottom-4 right-4 z-50 bg-indigo-600 text-white p-3 rounded-full shadow-xl">
    <i class="fa-solid fa-bars"></i>
</button>
```

---

### Hallazgo U-04 — [Baja]: Avatar del Usuario en Sidebar es Estático (`OP`)

**Componentes**: [`base.html:L210-211`](file:///y:/Proyectos/a2lt_stock_project/inventory/templates/inventory/base.html#L210-L211).

**Impacto**: El avatar del perfil muestra siempre las letras `OP` hardcodeadas, sin importar quién esté autenticado. Esto destruye la percepción de personalización y hace que el sistema parezca no terminado o incompleto.

**Solución Propuesta**: Usar las iniciales reales del usuario:
```html
<div class="w-8 h-8 rounded-full bg-indigo-600 ...">
    {{ request.user.first_name.0|upper|default:request.user.username.0|upper }}{{ request.user.last_name.0|upper }}
</div>
```

---

### Hallazgo U-05 — [Baja]: FontAwesome y Google Fonts cargados desde CDN Externo sin SRI

**Componentes**: [`base.html:L11`](file:///y:/Proyectos/a2lt_stock_project/inventory/templates/inventory/base.html#L11) y [`base.html:L52`](file:///y:/Proyectos/a2lt_stock_project/inventory/templates/inventory/base.html#L52).

**Impacto**: Sin atributos `integrity` (SRI) y `crossorigin`, si `cdnjs.cloudflare.com` o `fonts.googleapis.com` son comprometidos, el atacante puede inyectar JavaScript arbitrario en la aplicación. Esto es especialmente grave dado que FA 6.4.0 tiene scripts activos.

**Solución Propuesta**: Añadir hashes SRI o autoalojar las fuentes/iconos:
```html
<link rel="stylesheet" 
      href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"
      integrity="sha512-iecdLmaskl7CVkqkXNQ/ZH/XLlvWZOJyj7Yy7tcenmpD1ypASozpmT/E0iPtmFIB46ZmdtAc9eNBvH0H/ZpiBw=="
      crossorigin="anonymous"
      referrerpolicy="no-referrer">
```

---

## 4. Experiencia de Usuario (UX) e Interacción

---

### Hallazgo X-01 — [Alta]: Sin Feedback Visual de Carga en Operaciones Críticas Asíncronas

**Componentes**: `ventas.html`, `compras.html`, `carga.html` — inferido de la arquitectura AJAX con `fetch`.

**Impacto**: Las operaciones de creación de ventas, registro de compras y carga masiva de Excel son peticiones AJAX que pueden tardar varios segundos (especialmente la carga masiva). Si no hay un estado de loading visible, el usuario puede:
1. Hacer clic múltiple en el botón de envío, generando duplicados de transacciones.
2. Cerrar la pestaña pensando que el sistema colgó.
3. Perder confianza en el sistema.

**Solución Propuesta**: El botón de submit debe deshabilitarse inmediatamente y mostrar un spinner:
```javascript
submitBtn.disabled = true;
submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i>Procesando...';
try {
    const response = await fetch(url, options);
    // ...
} finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = textoOriginal;
}
```

---

### Hallazgo X-02 — [Alta]: `vista_movimientos` Carga Todo el Histórico de Kardex sin Paginación

**Componentes**: [`views.py:L1106`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py#L1106).

**Impacto**: El queryset `MovimientoKardex.objects.all().order_by('-fecha_hora')` sin límite es pasado directamente al template. Con un volumen realista de 50 000+ movimientos, el template intentará iterar y renderizar todos los registros en una sola petición HTTP, causando timeouts de servidor y consumo masivo de memoria RAM.

**Solución Propuesta**: Aplicar paginación equivalente a la implementada en `catalogo`:
```python
paginator = Paginator(movimientos, 50)
try:
    page_obj = paginator.page(page)
except EmptyPage:
    page_obj = paginator.page(paginator.num_pages)
```

---

### Hallazgo X-03 — [Media]: Ausencia de Atributos ARIA en Componentes Interactivos

**Componentes**: [`base.html`](file:///y:/Proyectos/a2lt_stock_project/inventory/templates/inventory/base.html), [`login.html`](file:///y:/Proyectos/a2lt_stock_project/inventory/templates/inventory/login.html).

**Impacto**: Los botones, modales y controles interactivos carecen de atributos `aria-label`, `aria-expanded`, `aria-current`, `role` y `aria-live`. El sistema es inaccesible para usuarios con lectores de pantalla (WCAG 2.1 Nivel A — conformidad obligatoria en muchos contextos empresariales). El sidebar no tiene `role="navigation"` ni `aria-label`.

**Solución Propuesta** (ejemplos clave):
```html
<!-- Sidebar -->
<aside role="navigation" aria-label="Navegación principal">

<!-- Botón de logout -->
<a href="..." aria-label="Cerrar sesión de {{ request.user.username }}">

<!-- Links activos del sidebar -->
<a aria-current="page" ...>

<!-- Tema toggle -->
<button aria-label="Cambiar a modo oscuro" aria-pressed="false">
```

---

### Hallazgo X-04 — [Media]: No hay Estado Vacío Definido para el Dashboard sin Datos

**Componentes**: [`views.py:L107-209`](file:///y:/Proyectos/a2lt_stock_project/inventory/views.py#L107-L209) + `dashboard.html`.

**Impacto**: Un usuario nuevo que acaba de registrar su empresa verá el dashboard con métricas en cero (`$0.00`, `0 notas`, `Sin sync`). No existe ningún CTA (llamada a la acción) que le indique qué debe hacer a continuación. La experiencia de onboarding es nula, lo que eleva el riesgo de abandono en primeras sesiones.

**Solución Propuesta**: Añadir un banner de onboarding condicional:
```html
{% if valoracion_total == 0 and notas_mes == 0 %}
<div class="col-span-full bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-800 rounded-2xl p-6 text-center">
    <i class="fa-solid fa-rocket text-4xl text-indigo-500 mb-3"></i>
    <h3 class="font-bold text-slate-800 dark:text-slate-200">¡Bienvenido a A2LT Stock!</h3>
    <p class="text-sm text-slate-500 mt-1">Empieza configurando tu inventario:</p>
    <div class="flex gap-3 justify-center mt-4">
        <a href="{% url 'inventory:configuracion' %}" class="btn-primary">1. Configura tasas BCV</a>
        <a href="{% url 'inventory:carga_masiva' %}" class="btn-secondary">2. Carga tu inventario</a>
    </div>
</div>
{% endif %}
```

---

### Hallazgo X-05 — [Media]: Mensajes de Error del Sistema en el Login No Discriminan por Tipo

**Componentes**: [`login.html:L49-55`](file:///y:/Proyectos/a2lt_stock_project/inventory/templates/inventory/login.html#L49-L55).

**Impacto**: Todos los mensajes del framework de mensajes de Django se muestran con el mismo estilo visual de error (fondo rojo). Un mensaje informativo (`messages.warning` desde el middleware: "Inicia sesión para continuar") se ve idéntico a un error de "Credenciales inválidas". Esto confunde al usuario sobre la naturaleza del problema.

**Solución Propuesta**:
```html
{% for message in messages %}
<div class="mb-4 p-3 rounded-lg text-sm font-bold text-center border
    {% if message.tags == 'error' %}bg-rose-50 text-rose-600 border-rose-200 dark:bg-rose-500/10 dark:text-rose-400{% endif %}
    {% if message.tags == 'warning' %}bg-amber-50 text-amber-600 border-amber-200 dark:bg-amber-500/10{% endif %}
    {% if message.tags == 'success' %}bg-emerald-50 text-emerald-600 border-emerald-200{% endif %}">
    {{ message }}
</div>
{% endfor %}
```

---

### Hallazgo X-06 — [Baja]: Página de Error 403 es un String Plano de Django, No una Página de la App

**Componentes**: [`middleware.py:L113-143`](file:///y:/Proyectos/a2lt_stock_project/inventory/middleware.py#L113-L143) — retorna `HttpResponseForbidden('Acceso Denegado: ...')`.

**Impacto**: Cuando el middleware detecta acceso no autorizado, el usuario ve una página en blanco con texto plano. No hereda el diseño de la aplicación, no tiene botón de regreso, ni instrucciones de qué hacer.

**Solución Propuesta**: Renderizar una template personalizada:
```python
from django.shortcuts import render

def _forbidden(request, msg):
    return render(request, 'inventory/403.html', {'mensaje': msg}, status=403)
```

---

## Plan de Remediación Priorizado

| Prioridad | ID | Severidad | Hallazgo | Plazo Corto (Sprint 1-2) | Plazo Mediano (Sprint 3-6) |
|:---------:|:---:|:--------:|:---------|:------------------------|:--------------------------|
| 1 | S-01 | 🔴 Crítica | `SECRET_KEY` hardcodeada en `.env` commiteado | Rotar clave, purgar historial Git, forzar `sys.exit(1)` sin clave | Implementar secrets manager (ej. `python-dotenv` + vault en producción) |
| 2 | S-02 | 🟠 Alta | SSRF en `sincronizar_tasa_cambio()` | Validar URL contra allowlist y blocklist antes de persistirla | Añadir proxy HTTP intermediario para solicitudes externas |
| 3 | S-03 | 🟠 Alta | Exposición de stack traces en JSON 500 | Envolver todos los handlers genéricos con el patrón seguro | Centralizar manejo de errores con un decorator `@handle_api_errors` |
| 4 | S-04 | 🟠 Alta | Sin rate limiting en login (fuerza bruta) | Instalar y configurar `django-axes` con 5 intentos / 1h lockout | Añadir CAPTCHA (hCaptcha) para entornos públicos |
| 5 | S-05 | 🟠 Alta | IDOR en `vista_imprimir_coordenadas` — acceso cross-tenant | Añadir `empresa_id=empresa_id` al `get_object_or_404` | Auditar todas las vistas de detalle (vista_detalle_nc, etc.) |
| 6 | X-02 | 🟠 Alta | Kardex sin paginación — OOM en producción | Aplicar `Paginator` con 50 items por página | Evaluar paginación cursor-based para volúmenes > 100k |
| 7 | X-01 | 🟠 Alta | Sin feedback de carga en operaciones críticas | Deshabilitar botón submit + spinner en todas las views AJAX | Implementar sistema de notificaciones con toast unificado |
| 8 | A-01 | 🟠 Alta | God-file `services.py` / `views.py` | No fragmentar aún; añadir umbral de split al ADR-21 | Migración modular por dominio (kardex, ventas, compras, etc.) |
| 9 | A-03 | 🟠 Alta | N+1 queries en Dashboard (combo loop) | Limitar combos_qs a 5 con annotate básico | Prefetch recetas e inventarios con `Prefetch()` |
| 10 | S-06 | 🟡 Media | Logout sin `session.flush()` | Añadir `request.session.flush()` antes de `logout()` | — |
| 11 | S-07 | 🟡 Media | `CSRF_COOKIE_HTTPONLY = False` | Documentar el riesgo explícitamente en settings; evaluar cambio a lectura desde DOM | Cambiar a `True` y actualizar helper `getCsrfToken()` en `base.html` |
| 12 | S-08 | 🟡 Media | Sin validación multi-tenant en endpoint de seriales | Añadir filtros `empresa_id` en `vista_buscar_seriales_articulo` | Auditar todos los endpoints `/api/` con lookups de FK |
| 13 | A-04 | 🟡 Media | `configuracion_view` vulnerable a `None` si ContextVar es `None` | Reemplazar `.first()` por `get_object_or_404(empresa_id=...)` | — |
| 14 | A-05 | 🟡 Media | Lógica financiera de descuentos duplicada en 4 vistas | Extraer a `calcular_totales_documento()` utilitaria | Aplicar a generadores de PDF también |
| 15 | U-01 | 🟡 Media | Tailwind via CDN sin SRI en producción | Añadir SRI hash al `<script>` del CDN | Configurar build pipeline con `django-tailwind` o `Vite` |
| 16 | U-03 | 🟡 Media | Sidebar no responsive (inutilizable < 1024px) | Añadir toggle hamburguesa `lg:hidden` | Rediseño sidebar con drawer overlay para mobile |
| 17 | X-03 | 🟡 Media | Ausencia de atributos ARIA (accesibilidad) | Añadir `role="navigation"`, `aria-current`, `aria-label` base | Auditoría completa WCAG 2.1 Nivel A |
| 18 | X-04 | 🟡 Media | Sin estado vacío/onboarding en dashboard nuevo | Añadir banner condicional con CTAs para primeros pasos | Wizard de onboarding de 3 pasos |
| 19 | X-05 | 🟡 Media | Mensajes de error en login sin discriminación visual por tipo | Añadir clases CSS condicionales por `message.tags` | — |
| 20 | A-07 | 🟢 Baja | `logout_view` acepta GET (CSRF de disponibilidad) | Añadir `@require_POST` y convertir el link en `<form>` | — |
| 21 | S-09 | 🟢 Baja | `db.sqlite3` en raíz del repo | Añadir a `.gitignore` inmediatamente | Migrar a PostgreSQL para producción |
| 22 | U-02 | 🟢 Baja | `tailwind.config` duplicado entre templates | Centralizar en JS estático compartido | — |
| 23 | U-04 | 🟢 Baja | Avatar `OP` hardcodeado en sidebar | Usar iniciales del `request.user` | — |
| 24 | U-05 | 🟢 Baja | CDN de FA/Google Fonts sin SRI | Añadir atributos `integrity` y `crossorigin` | Autoalojar fuentes |
| 25 | X-06 | 🟢 Baja | Error 403 como texto plano | Crear `403.html` y renderizarla desde el middleware | — |
| 26 | A-02 | 🟢 Baja | Imports diferidos masivos en `views.py` | Refactor progresivo durante otras tareas | — |
| 27 | A-06 | 🟢 Baja | Función `celda()` definida dentro de loop | Mover al ámbito del módulo | — |

---

> **Nota de auditoría**: El proyecto muestra un nivel técnico sólido en la capa de negocio (atomicidad transaccional, multi-tenant via ContextVar, Regla Sagrada del Kárdex, RBAC funcional). Los hallazgos críticos y altos se concentran en la capa perimetral de seguridad y en las decisiones arquitectónicas de modularización. La base del código es refactorable sin reescritura.
