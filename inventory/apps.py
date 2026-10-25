from django.apps import AppConfig


class InventoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'inventory'
    verbose_name = 'Gestión de Inventario'

    def ready(self):
        import inventory.signals
        # EST-01: conecta los receivers pre_save/pre_delete de MovimientoKardex
        # (kardex_guard importa models; no hay ciclo de imports).
        import inventory.kardex_guard  # noqa: F401
