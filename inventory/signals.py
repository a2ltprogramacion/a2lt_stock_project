from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from decimal import Decimal
from .models import (
    Empresa, ConfiguracionEmpresa, Almacen, Contacto,
    Moneda, TasaCambio,
)


@receiver(post_save, sender=Empresa)
def create_tenant_defaults(sender, instance, created, **kwargs):
    """
    Al crear una nueva Empresa, se genera automaticamente:
    1. Su configuracion asociada (Tasa BCV 60.00, Cobertura 1.40, Margen 30.00).
    2. Su almacen principal.
    3. Su cliente generico.
    4. Fase 3: sus monedas base USD/VES y tasa inicial 1:1.
    """
    if created:
        with transaction.atomic():
            config = ConfiguracionEmpresa.global_objects.create(
                empresa=instance,
                tasa_bcv=Decimal('60.0000'),
                factor_cobertura=Decimal('1.4000'),
                margen_global=Decimal('30.00'),
            )
            Almacen.objects.create(empresa=instance, nombre="Principal", es_principal=True)
            Contacto.objects.create(
                empresa=instance,
                # Usamos el RIF (único) en vez de instance.pk, porque pk puede
                # colisionar tras tests si la BD conserva filas entre test runs.
                identificacion=f"GEN-{instance.rif}",
                nombre="Cliente Generico", tipo="CLIENTE"
            )

            # FASE 3 — Multimodeda: monedas USD (base) + VES + tasa inicial 1:1
            usd = Moneda.objects.create(
                empresa=instance, codigo='USD', nombre='Dolar Americano',
                simbolo='$', decimales=2, es_base=True, activa=True
            )
            ves = Moneda.objects.create(
                empresa=instance, codigo='VES', nombre='Bolivar Venezolano',
                simbolo='Bs', decimales=2, es_base=False, activa=True
            )
            TasaCambio.objects.create(
                empresa=instance,
                moneda_origen=usd,
                moneda_destino=ves,
                tasa=Decimal(config.tasa_bcv) * Decimal(config.factor_cobertura),
                fecha=Decimal('60.0000') and __import__('datetime').date.today(),
                fuente='MANUAL',
                notas='Tasa inicial al crear empresa'
            )
