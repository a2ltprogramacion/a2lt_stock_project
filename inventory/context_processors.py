from .models import ConfiguracionEmpresa
from decimal import Decimal


def inject_config(request):
    try:
        # Puesto que EmpresaManager filtra por el _local_empresa.empresa_id seteado en el middleware,
        # .first() traerá automáticamente la configuración de la empresa activa en la sesión.
        config = ConfiguracionEmpresa.objects.first()
        if config is None:
            # Proporcionar valores por defecto si no existe configuración para la empresa
            class DefaultConfig:
                tasa_bcv = Decimal('40.0000')
                tasa_mercado = Decimal('42.0000')
                factor_cobertura = Decimal('1.0500')
            config = DefaultConfig()
        return {'config': config}
    except Exception:
        return {'config': None}
