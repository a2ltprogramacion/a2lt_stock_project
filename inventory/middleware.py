from django.http import HttpResponseForbidden
from .managers import set_current_empresa, reset_current_empresa


class TenantMiddleware:
    """
    Resuelve la empresa activa del contexto multi-tenant.

    Antes de hacer disponible el id de empresa en el ContextVar
    EmpresaManager, valida:
      1. Usuario autenticado y con PerfilUsuario creado.
      2. La empresa en sesion existe y esta activa.
      3. La empresa en sesion esta incluida en empresas_permitidas
         del perfil (multi-tenant seguro).

    Si alguna validacion falla, retorna 403 Forbidden con un
    mensaje claro para el operador.

    Rutas exentas (no requieren sesion): /admin/, /login/, /static/,
    /favicon.ico y la raiz '/'. En exencion el ContextVar se setea
    a None y el resto del codigo no debe depender de tenant (ej.
    pantalla de login).
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_paths = ['/admin/', '/login/', '/static/', '/favicon.ico']

    def __call__(self, request):
        current_path = request.path
        if not current_path.endswith('/'):
            current_path += '/'

        # Exencion explicita (rutas sin tenant)
        is_exempt = current_path == '/' or any(
            current_path.startswith(path) for path in self.exempt_paths
        )

        if is_exempt:
            token = set_current_empresa(None)
        else:
            forbidden = self._authorize(request)
            if forbidden is not None:
                return forbidden
            token = set_current_empresa(request.session.get('empresa_id'))

        try:
            response = self.get_response(request)
        finally:
            reset_current_empresa(token)

        return response

    def _authorize(self, request):
        """
        Retorna:
          - None si la peticion esta autorizada (empresa cargada en sesion).
          - HttpResponseForbidden (403) en caso contrario.

        Validaciones en orden:
        1. usuario autenticado.
        2. PerfilUsuario existe.
        3. empresa_id en sesion.
        4. Empresa existe y activa.
        5. Empresa esta en perfil.empresas_permitidas.
        """
        # 1. autenticacion
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return HttpResponseForbidden(
                'Acceso Denegado: requiere sesion de usuario.'
            )

        # 2. perfil
        perfil = getattr(user, 'perfil', None)
        if perfil is None:
            return HttpResponseForbidden(
                'Acceso Denegado: usuario sin perfil asignado.'
            )

        # 3. empresa_id en sesion
        empresa_id = request.session.get('empresa_id')
        if not empresa_id:
            return HttpResponseForbidden(
                'Acceso Denegado: no se encontro empresa asociada en la sesion.'
            )

        # 4. empresa existe y activa
        from .models import Empresa
        try:
            empresa = Empresa.objects.get(pk=empresa_id)
        except Empresa.DoesNotExist:
            return HttpResponseForbidden(
                'Acceso Denegado: la empresa asociada no existe.'
            )
        if not empresa.activa:
            return HttpResponseForbidden(
                'Cuenta de comercio suspendida o inactiva.'
            )

        # 5. multi-tenant: empresa en empresas_permitidas del perfil
        # PerfilUsuario.empresas_permitidas es M2M, sin manager tenant
        # (es el modelo raiz). Filtrar por pk directo es seguro.
        tiene_permiso = perfil.empresas_permitidas.filter(pk=empresa.id).exists()
        if not tiene_permiso:
            return HttpResponseForbidden(
                'Acceso Denegado: no tiene permiso para operar esta empresa.'
            )

        # OK: el ContextVar se setea fuera de _authorize
        return None
