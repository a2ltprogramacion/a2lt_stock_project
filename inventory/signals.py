from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from decimal import Decimal
from .models import Empresa, ConfiguracionEmpresa, Almacen, Contacto

@receiver(post_save, sender=Empresa)
def create_tenant_defaults(sender, instance, created, **kwargs):
    """
    Al crear una nueva Empresa, se genera automáticamente:
    1. Su configuración asociada (Tasa BCV 60.00, Cobertura 1.40, Margen 30.00).
    2. Su almacén principal.
    3. Su cliente genérico.
    """
    if created:
        with transaction.atomic():
            ConfiguracionEmpresa.objects.create(
                empresa=instance,
                tasa_bcv=Decimal('60.0000'),
                factor_cobertura=Decimal('1.4000'),
                margen_global=Decimal('30.00'),
            )
            Almacen.objects.create(empresa=instance, nombre="Principal", es_principal=True)
            Contacto.objects.create(empresa=instance, identificacion=f"GEN-{instance.pk}", nombre="Cliente Genérico", tipo="CLIENTE")
