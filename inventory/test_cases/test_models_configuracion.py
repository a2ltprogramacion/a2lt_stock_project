"""
DATA-05 + DATA-07 — ``ConfiguracionEmpresa.save()``: prioridad explícita,
``update_fields`` y redondeo comercial HALF_UP.

Contexto
--------
DATA-05. El ``save()`` actual mezcla 5 ramas dependientes del estado previo,
usa ``try/except DoesNotExist`` donde basta un ``filter().first()`` y NO
propaga los campos derivados cuando el caller usa ``update_fields``: si
alguien hace ``config.save(update_fields=['tasa_bcv'])``, el ``tasa_mercado``
recalculado vive solo en memoria y se pierde en la BD.

DATA-07. ``round(Decimal, n)`` usa ``ROUND_HALF_EVEN`` (banker's rounding):
``round(Decimal('0.00005'), 4) == 0.0000``. En moneda comercial se espera
``ROUND_HALF_UP``: ``0.00005 -> 0.0001``.

Invariante del modelo (documentada en ``ConfiguracionEmpresa.save()``)
---------------------------------------------------------------------
Con ``tasa_bcv > 0``:  ``tasa_mercado == tasa_bcv * factor_cobertura``
(ambos a 4 decimales). El BCV es la *fuente*; el factor de cobertura es la
*política comercial*; el mercado es *derivado* cuando cambian BCV o factor.

Prioridad EXPLÍCITA cuando varios campos cambian en el mismo ``save()``:
    1. Cambió el BCV (fuente)      -> mercado = bcv * factor (el factor es
                                      política y se respeta; el mercado
                                      entrante se descarta).
    2. Cambió solo el mercado      -> factor = mercado / bcv.
    3. Cambió solo el factor       -> mercado = bcv * factor.
    4. Nada detectable pero estado inconsistente -> el mercado manda
       (factor = mercado / bcv); si mercado == 0 -> mercado = bcv * factor.

Fijación de estado inicial
--------------------------
La señal ``create_tenant_defaults`` siembra ``tasa_bcv=60.0000`` y
``factor_cobertura=1.4000`` (mercado se deriva a ``84.0000``). Los helpers de
estos tests parten de ese estado y usan ``_fijar_estado()`` para establecer un
estado consistente (bcv, factor) antes de cada escenario.
"""

from decimal import Decimal

from django.test import TestCase

from inventory.managers import reset_current_empresa, set_current_empresa
from inventory.models import ConfiguracionEmpresa, Empresa


class TestData05Data07ConfiguracionSave(TestCase):
    """DATA-05/DATA-07: derivación de tasas y redondeo en ``save()``."""

    def setUp(self):
        sufijo = abs(hash(self._testMethodName)) % (10 ** 8)
        self.empresa = Empresa.objects.create(
            nombre=f'DATA05 {self._testMethodName[:27]}',
            rif=f'J-DATA05-{sufijo:08d}',
            activa=True,
        )
        # La señal de creación de Empresa ya siembra la ConfiguracionEmpresa
        # (bcv=60.0000, factor=1.4000, mercado derivado=84.0000).
        token = set_current_empresa(self.empresa.id)
        self.addCleanup(reset_current_empresa, token)
        self.config = ConfiguracionEmpresa.objects.get(empresa=self.empresa)

    # -- Helpers --------------------------------------------------------

    def _fijar_estado(self, tasa_bcv, factor_cobertura):
        """
        Establece un estado consistente ``(bcv, factor)`` dejando que
        ``save()`` derive ``tasa_mercado = bcv * factor``.

        Cambiar BCV y factor a la vez es determinista en ambas lógicas
        (vieja y nueva): el mercado siempre termina en ``bcv * factor``.
        """
        self.config.tasa_bcv = Decimal(tasa_bcv)
        self.config.factor_cobertura = Decimal(factor_cobertura)
        self.config.save()
        self.config.refresh_from_db()

    def _tasas_en_bd(self):
        """Relee las tres tasas desde la BD (fuera de la caché del ORM)."""
        fresh = ConfiguracionEmpresa.global_objects.get(pk=self.config.pk)
        return fresh.tasa_bcv, fresh.tasa_mercado, fresh.factor_cobertura

    # -- DATA-05: prioridad explícita de las ramas -----------------------

    def test_data05_cambio_solo_bcv_recalcula_mercado(self):
        """BCV 40->50 con factor 1.5: el mercado se deriva a 75.0000."""
        # Arrange: estado consistente bcv=40, factor=1.5 -> mercado=60.
        self._fijar_estado('40.0000', '1.5000')

        # Act: solo la fuente (BCV) cambia; el factor es política y se respeta.
        self.config.tasa_bcv = Decimal('50.0000')
        self.config.save()

        # Assert: mercado == bcv * factor (invariante a 4 decimales).
        self.config.refresh_from_db()
        self.assertEqual(self.config.tasa_mercado, Decimal('75.0000'))
        self.assertEqual(self.config.factor_cobertura, Decimal('1.5000'))

    def test_data05_cambio_solo_mercado_recalcula_factor(self):
        """Con bcv=40, mercado 40->60: el factor se deriva a 1.5000."""
        # Arrange: estado consistente bcv=40, factor=1.0 -> mercado=40.
        self._fijar_estado('40.0000', '1.0000')

        # Act: el usuario mueve el mercado (p.ej. Binance P2P).
        self.config.tasa_mercado = Decimal('60.0000')
        self.config.save()

        # Assert: factor = mercado / bcv = 60 / 40 = 1.5000.
        self.config.refresh_from_db()
        self.assertEqual(self.config.factor_cobertura, Decimal('1.5000'))

    def test_data05_cambio_solo_factor_recalcula_mercado(self):
        """Con bcv=40, factor 1.0->1.25: el mercado se deriva a 50.0000."""
        # Arrange: estado consistente bcv=40, factor=1.0 -> mercado=40.
        self._fijar_estado('40.0000', '1.0000')

        # Act: la política comercial (factor) cambia.
        self.config.factor_cobertura = Decimal('1.2500')
        self.config.save()

        # Assert: mercado = bcv * factor = 40 * 1.25 = 50.0000.
        self.config.refresh_from_db()
        self.assertEqual(self.config.tasa_mercado, Decimal('50.0000'))

    def test_data05_cambio_bcv_y_mercado_prioriza_bcv(self):
        """
        Cambio simultáneo BCV (40->50) y mercado (60->999): gana el BCV.

        La prioridad es EXPLÍCITA: el BCV es la fuente y el factor es la
        política; el mercado entrante (999) se descarta y se deriva
        ``mercado = bcv * factor = 50 * 1.0 = 50.0000``.
        """
        # Arrange: estado consistente bcv=40, factor=1.0 -> mercado=40.
        self._fijar_estado('40.0000', '1.0000')

        # Act: el caller (p.ej. un formulario) envía ambos campos.
        self.config.tasa_bcv = Decimal('50.0000')
        self.config.tasa_mercado = Decimal('999.0000')
        self.config.save()

        # Assert: BCV manda; el factor (política) no se toca.
        self.config.refresh_from_db()
        self.assertEqual(self.config.tasa_mercado, Decimal('50.0000'))
        self.assertEqual(self.config.factor_cobertura, Decimal('1.0000'))

    def test_data05_tasa_bcv_cero_no_divide_por_cero(self):
        """Con bcv=0 no hay división: factor se resetea a 1 y mercado a 0."""
        # Act: tasa oficial anulada (p.ej. borrador inicial del tenant).
        self.config.tasa_bcv = Decimal('0')
        self.config.tasa_mercado = Decimal('58.5000')
        self.config.factor_cobertura = Decimal('1.4000')
        self.config.save()

        # Assert: estado degradado seguro, sin ZeroDivisionError.
        self.config.refresh_from_db()
        self.assertEqual(self.config.factor_cobertura, Decimal('1.0000'))
        self.assertEqual(self.config.tasa_mercado, Decimal('0.0000'))

    def test_data05_sin_cambios_es_idempotente(self):
        """Un segundo ``save()`` sin cambios no altera ningún campo."""
        # Arrange: estado consistente bcv=40, factor=1.5 -> mercado=60.
        self._fijar_estado('40.0000', '1.5000')
        antes = self._tasas_en_bd()

        # Act: re-guardar sin tocar nada.
        self.config.save()
        self.config.refresh_from_db()

        # Assert: exactamente el mismo triple en BD.
        despues = self._tasas_en_bd()
        self.assertEqual(despues, antes)

    def test_data05_update_fields_incluye_campos_derivados(self):
        """
        ``save(update_fields=['tasa_bcv'])`` debe persistir TAMBIÉN los
        campos derivados que ``save()`` recalculó (hoy se perderían).
        """
        # Arrange: estado consistente bcv=40, factor=1.5 -> mercado=60.
        self._fijar_estado('40.0000', '1.5000')

        # Act: guardado parcial; save() deriva mercado=50*1.5=75 en memoria.
        self.config.tasa_bcv = Decimal('50.0000')
        self.config.save(update_fields=['tasa_bcv'])

        # Assert: el mercado recalculado (75.0000) debe llegar a la BD.
        # Se relee con global_objects (sin depender del tenant threadlocal)
        # y se fuerza refresh_from_db para no leer la caché del ORM.
        self.config.refresh_from_db()
        fresh = ConfiguracionEmpresa.global_objects.get(pk=self.config.pk)
        self.assertEqual(fresh.tasa_bcv, Decimal('50.0000'))
        self.assertEqual(fresh.tasa_mercado, Decimal('75.0000'))
        self.assertEqual(fresh.factor_cobertura, Decimal('1.5000'))

    # -- DATA-07: redondeo comercial HALF_UP -----------------------------

    def test_data07_redondeo_es_half_up_no_bankers(self):
        """
        ``round()`` usa banker's rounding: 0.00005 -> 0.0000. La moneda
        comercial exige ROUND_HALF_UP: 0.00005 -> 0.0001.
        """
        # Act/Assert: caso que distingue HALF_UP de HALF_EVEN.
        self.config.tasa_bcv = Decimal('0.00005')
        self.config.save()
        self.config.refresh_from_db()
        self.assertEqual(self.config.tasa_bcv, Decimal('0.0001'))

        with self.subTest(tasa_bcv='0.00015'):
            self.config.tasa_bcv = Decimal('0.00015')
            self.config.save()
            self.config.refresh_from_db()
            self.assertEqual(self.config.tasa_bcv, Decimal('0.0002'))

    def test_data07_factor_se_redondea_a_4_decimales_half_up(self):
        """El factor derivado se redondea a 4 decimales con HALF_UP."""
        # Arrange: estado consistente bcv=3, factor=1.0 -> mercado=3.
        self._fijar_estado('3.0000', '1.0000')

        # Act: el mercado cambia a un valor con 5 decimales.
        self.config.tasa_mercado = Decimal('4.00015')
        self.config.save()

        # Assert: 4.00015 / 3 = 1.333383... -> HALF_UP a 4dp -> 1.3334
        # (y el mercado de entrada también se cuantiza: 4.00015 -> 4.0002).
        self.config.refresh_from_db()
        self.assertEqual(self.config.factor_cobertura, Decimal('1.3334'))
        self.assertEqual(self.config.tasa_mercado, Decimal('4.0002'))
