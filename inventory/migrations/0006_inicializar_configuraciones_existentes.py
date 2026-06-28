from django.db import migrations
from decimal import Decimal


def inicializar_configuraciones(apps, schema_editor):
    Empresa = apps.get_model('inventory', 'Empresa')
    ConfiguracionEmpresa = apps.get_model('inventory', 'ConfiguracionEmpresa')
    for empresa in Empresa.objects.all():
        ConfiguracionEmpresa.objects.get_or_create(
            empresa=empresa,
            defaults={
                'tasa_bcv': Decimal('60.0000'),
                'factor_cobertura': Decimal('1.4000'),
                'margen_global': Decimal('30.00'),
            },
        )


def revertir(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0005_configuracionempresa_cross_selling_footer_and_more'),
    ]

    operations = [
        migrations.RunPython(inicializar_configuraciones, revertir),
    ]
