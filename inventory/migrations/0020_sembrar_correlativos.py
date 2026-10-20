"""
EST-03 — Siembra inicial de la tabla ``Correlativo``.

Crea una fila ``Correlativo`` por (empresa, tipo de documento) con
``ultimo_numero = max(numero)`` real de los documentos existentes. Es
idempotente (``get_or_create``) y nunca retrocede.

IMPORTANTE (trampa del tenant): se usa ``apps.get_model(...)`` para obtener los
modelos *históricos*. En el estado de migración los managers custom NO se
propagan, por lo que el manager disponible es el ``Manager`` por defecto SIN
filtro de tenant. Si se usara el ``EmpresaManager`` real (que devuelve
``.none()`` fuera de una request) veríamos una "BD vacía" falsa y no se
sembraría nada.
"""

from django.db import migrations
from django.db.models import Max


# (tipo_documento, nombre del modelo histórico)
TIPOS_Y_MODELOS = [
    ('NOTA_ENTREGA', 'NotaEntrega'),
    ('FACTURA_COMPRA', 'DocumentoCompra'),
    ('NOTA_CREDITO', 'NotaCredito'),
]


def sembrar_correlativos(apps, schema_editor):
    Empresa = apps.get_model('inventory', 'Empresa')
    Correlativo = apps.get_model('inventory', 'Correlativo')

    for empresa in Empresa.objects.all().iterator():
        for tipo_documento, model_name in TIPOS_Y_MODELOS:
            Documento = apps.get_model('inventory', model_name)
            max_num = (
                Documento.objects
                .filter(empresa_id=empresa.pk)
                .aggregate(m=Max('numero'))['m']
            ) or 0
            Correlativo.objects.get_or_create(
                empresa_id=empresa.pk,
                tipo_documento=tipo_documento,
                defaults={'ultimo_numero': int(max_num)},
            )


def revertir(apps, schema_editor):
    """No-op: borrar correlativos perdería información; la tabla se elimina
    por la migración 0019 al revertir."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0019_correlativo_and_more'),
    ]

    operations = [
        migrations.RunPython(sembrar_correlativos, revertir),
    ]
