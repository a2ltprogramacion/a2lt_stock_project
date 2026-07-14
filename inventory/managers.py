from django.db import models
import contextvars

_current_empresa = contextvars.ContextVar('current_empresa', default=None)

def set_current_empresa(empresa_id):
    """
    Asigna el ID de la empresa activa al contexto actual.
    Retorna el token de asignación para poder restaurarlo luego.
    """
    return _current_empresa.set(empresa_id)

def get_current_empresa():
    """
    Obtiene el ID de la empresa activa en el contexto actual.
    """
    return _current_empresa.get()

def reset_current_empresa(token):
    """
    Restaura el contexto de la empresa a su valor anterior usando el token.
    """
    _current_empresa.reset(token)

class EmpresaQuerySet(models.QuerySet):
    def para_empresa(self):
        empresa_id = get_current_empresa()
        if empresa_id is not None:
            return self.filter(empresa_id=empresa_id)
        return self


class EmpresaManager(models.Manager):
    """
    Manager multi-tenant que filtra automáticamente por la empresa activa (ADR-17).

    SEGURIDAD: Si el ContextVar no tiene empresa (None), retorna un queryset
    VACÍO en lugar de toda la tabla, previniendo fugas de datos cross-tenant.
    Use global_objects para consultas administrativas explícitas.

    IMPORTANTE: Requiere que cada modelo multi-tenant posea una columna
    física ``empresa_id`` en la BD (vía FK ``models.ForeignKey(Empresa,
    ...)``). Modelos 'transitivos' sin columna ``empresa_id`` propia
    deber usar ``global_objects`` y filtrar manualmente via su cabecera.
    """
    def get_queryset(self):
        empresa_id = get_current_empresa()
        qs = super().get_queryset()
        if empresa_id is None:
            return qs.none()
        return qs.filter(empresa_id=empresa_id)

