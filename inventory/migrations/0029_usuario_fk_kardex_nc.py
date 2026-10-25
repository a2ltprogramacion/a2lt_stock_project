# EST-04 (REQ-EST04-01/02/03): usuario forense en kárdex y notas de crédito.
#
# El CharField histórico `usuario` pasa a ser el snapshot `usuario_nombre`
# (RenameField: los datos históricos se preservan) y `usuario` queda libre
# para la FK a auth_user (SET_NULL: la baja del usuario nunca borra el
# histórico, Gherkin EST04-05). El backfill resuelve la FK por match exacto
# username→auth_user; sin match ('seed_db', 'Sistema', 'Demo Setup',
# literales de tests) la FK queda NULL y el snapshot se conserva — el
# snapshot ES la trazabilidad (REQ-EST04-03).
#
# NOTA (autodetector): `makemigrations` con rename+FK en un solo paso genera
# AddField+AlterField (drop de columna en SQLite = pérdida de datos). Esta
# migración escribe a mano las operaciones RenameField+AddField del plan
# aprobado (Gate G2, cap. 3); `makemigrations --check` verifica la
# equivalencia de estado con los modelos.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_usuario_fk(apps, schema_editor):
    """REQ-EST04-03: match exacto username→auth_user; sin match→FK NULL.

    Idempotente: en la 2ª pasada `pk != fila.usuario_id` ya no se cumple
    para las filas resueltas y las sin match se saltan (pk es None).
    Modelos históricos con manager plano (EmpresaManager no define
    use_in_migrations): el backfill ve TODO el histórico, multi-tenant.
    """
    User = apps.get_model('auth', 'User')
    mapa = dict(User.objects.values_list('username', 'pk'))
    for nombre in ('MovimientoKardex', 'NotaCredito'):
        M = apps.get_model('inventory', nombre)
        for fila in M.objects.exclude(usuario_nombre=''):
            pk = mapa.get(fila.usuario_nombre)
            if pk is not None and pk != fila.usuario_id:
                fila.usuario_id = pk
                fila.save(update_fields=['usuario'])


def limpiar_usuario_fk(apps, schema_editor):
    """Reversibilidad (spec §5.3): FK a NULL; el snapshot NUNCA se toca."""
    for nombre in ('MovimientoKardex', 'NotaCredito'):
        apps.get_model('inventory', nombre).objects.update(usuario=None)


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0028_alter_tasacambio_moneda_destino_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField('movimientokardex', 'usuario', 'usuario_nombre'),
        migrations.AddField(
            model_name='movimientokardex',
            name='usuario',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='kardex_registrado_por',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Usuario (FK)',
            ),
        ),
        migrations.RenameField('notacredito', 'usuario', 'usuario_nombre'),
        migrations.AddField(
            model_name='notacredito',
            name='usuario',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='notas_credito_emitidas',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Usuario (FK)',
            ),
        ),
        migrations.RunPython(backfill_usuario_fk, limpiar_usuario_fk),
    ]
