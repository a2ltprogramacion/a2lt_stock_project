from django.http import HttpResponseForbidden
from .managers import set_current_empresa, reset_current_empresa

class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_paths = ['/admin/', '/login/', '/static/', '/favicon.ico']

    def __call__(self, request):
        # NORMALIZACIÓN: Forzar la evaluación con trailing slash virtual para la exención
        current_path = request.path
        if not current_path.endswith('/'):
            current_path += '/'

        # Evaluar la exención: coincidencia exacta para '/' y startswith para el resto
        is_exempt = current_path == '/' or any(current_path.startswith(path) for path in self.exempt_paths)
        if is_exempt:
            token = set_current_empresa(None)
        else:
            empresa_id = request.session.get('empresa_id')
            if not empresa_id:
                return HttpResponseForbidden("Acceso Denegado: No se encontró una empresa asociada en la sesión.")
            
            # Verificar si la empresa está activa
            from .models import Empresa
            try:
                empresa = Empresa.objects.get(pk=empresa_id)
                if not empresa.activa:
                    return HttpResponseForbidden("Cuenta de comercio suspendida o inactiva.")
            except Empresa.DoesNotExist:
                return HttpResponseForbidden("Acceso Denegado: La empresa asociada no existe.")
            
            token = set_current_empresa(empresa_id)

        try:
            response = self.get_response(request)
        finally:
            reset_current_empresa(token)

        return response