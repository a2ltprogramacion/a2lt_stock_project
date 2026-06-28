import json
import logging
import shutil
import time
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.text import slugify

from inventory.services import exportar_datos_tenant
from inventory.models import Empresa

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Ejecuta un respaldo lógico y aislado para un Tenant específico.'

    def add_arguments(self, parser):
        parser.add_argument('empresa_id', type=int, help='ID de la Empresa a respaldar.')
        parser.add_argument('--meses', type=int, default=6, help='Meses históricos de Kárdex a respaldar (default: 6).')
        parser.add_argument('--out', type=str, default='backups', help='Directorio de salida de los respaldos.')

    def handle(self, *args, **options):
        empresa_id = options['empresa_id']
        meses = options['meses']
        out_dir = options['out']

        # 1. Telemetría de Almacenamiento Local (Ticket #13)
        self.verificar_telemetria_disco()

        # 2. Validación de Empresa
        try:
            empresa = Empresa.objects.get(pk=empresa_id)
        except Empresa.DoesNotExist:
            raise CommandError(f'Empresa con ID {empresa_id} no existe.')

        self.stdout.write(self.style.SUCCESS(f"Iniciando respaldo para el Tenant: {empresa.nombre} (ID: {empresa.pk})"))

        # 3. Exportación Lógica
        payload = exportar_datos_tenant(empresa_id=empresa.pk, meses_historico=meses)
        json_data = json.dumps(payload, cls=DjangoJSONEncoder, indent=2)

        # 4. Guardado Físico
        path = Path(out_dir)
        path.mkdir(parents=True, exist_ok=True)
        
        rif_slug = slugify(payload['metadata']['empresa_rif'])
        timestamp = int(time.time())
        filename = f"respaldo_a2lt_{rif_slug}_{timestamp}.json"
        
        filepath = path / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(json_data)

        self.stdout.write(self.style.SUCCESS(f"Respaldo generado exitosamente: {filepath}"))

    def verificar_telemetria_disco(self):
        """
        Verifica el espacio libre en el disco duro local utilizando shutil.disk_usage.
        Si el espacio cae por debajo del 15%, registra una alerta crítica.
        """
        try:
            total, used, free = shutil.disk_usage('/')
            free_percent = (free / total) * 100
            
            if free_percent < 15.0:
                logger.warning(f"[ALERTA CRITICA] Espacio en disco muy bajo: {free_percent:.2f}% libre.")
                self.stdout.write(self.style.WARNING(f"⚠️  ALERTA CRITICA: Queda menos del 15% de espacio en disco ({free_percent:.2f}%)."))
            else:
                self.stdout.write(self.style.SUCCESS(f"✅ Telemetría de disco OK: {free_percent:.2f}% libre."))
        except Exception as e:
            logger.error(f"Error al verificar telemetría de disco: {e}")
            self.stdout.write(self.style.ERROR(f"Error al verificar disco: {e}"))
