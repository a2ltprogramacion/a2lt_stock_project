from .models import ConfiguracionEmpresa

def inject_config(request):
    try:
        # Puesto que EmpresaManager filtra por el _local_empresa.empresa_id seteado en el middleware,
        # .first() traerá automáticamente la configuración de la empresa activa en la sesión.
        config = ConfiguracionEmpresa.objects.first()
        return {'config': config}
    except Exception:
        return {'config': None}
