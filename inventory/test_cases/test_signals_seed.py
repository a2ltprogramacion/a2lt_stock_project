"""
Limpieza de ``inventory/signals.py`` — expresión ofuscada en el seed.

Contexto
--------
La señal ``create_tenant_defaults`` sembraba la fecha de la tasa inicial
USD→VES con una expresión ofuscada y frágil:

    fecha=Decimal('60.0000') and __import__('datetime').date.today(),

Eso evalúa a ``date.today()`` SOLO porque ``Decimal('60.0000')`` es truthy:
es una constante muerta disfrazada de operando de ``and``, con un
``__import__`` dinámico que oculta la dependencia real del módulo
``datetime``. La limpieza sustituye la línea por ``fecha=date.today()`` y
declara ``from datetime import date`` en el bloque de imports superior.
``Decimal`` permanece importado: la señal lo usa para ``tasa_bcv``,
``factor_cobertura``, ``margen_global`` y el cálculo de ``tasa``.

Qué garantiza esta suite
------------------------
1. El seed siembra la tasa USD→VES con ``fecha == date.today()`` y
   ``tasa == 60 × 1.40 = 84``.
2. El archivo fuente queda libre de ofuscación: sin ``__import__`` y sin la
   subcadena ``Decimal('60.0000') and``.

Nota sobre la comparación de fechas
----------------------------------
settings usa ``USE_TZ=True`` con ``TIME_ZONE='America/Caracas'``, así que
``timezone.localdate()`` es la fecha en la zona del proyecto (Caracas),
mientras que ``date.today()`` es la fecha local del HOST. El seed escribe
``date.today()``, por lo que el test afirma contra ``date.today()`` y solo
REPORTA (no falla) si ``timezone.localdate()`` difiere: divergencia
esperable si el host corre fuera de America/Caracas o la ejecución cruza
la medianoche local.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

from django.test import TestCase
from django.utils import timezone

from inventory.models import Empresa, TasaCambio

RUTA_SIGNALS = Path(__file__).resolve().parent.parent / 'signals.py'


class TestSignalSiembraTasaInicial(TestCase):
    """El seed de la señal usa la fecha de hoy, sin ofuscación."""

    # -- 1. La señal siembra la tasa con fecha de hoy y valor 60×1.40 -----
    def test_signal_siembra_tasa_con_fecha_de_hoy(self):
        # Arrange: RIF único para esta corrida (el pk puede reciclarse entre
        # corridas de tests si la BD conserva filas; el RIF es lo único).
        sufijo = abs(hash(self._testMethodName)) % (10 ** 8)

        # Act: crear la Empresa dispara create_tenant_defaults (post_save).
        empresa = Empresa.objects.create(
            nombre=f'SEED {self._testMethodName[:24]}',
            rif=f'J-SEED-{sufijo:08d}',
            activa=True,
        )

        # Assert: la señal siembra exactamente UNA tasa USD→VES...
        tasas = TasaCambio.global_objects.filter(empresa=empresa)
        self.assertEqual(tasas.count(), 1)
        tasa_seed = tasas.get()

        # ...con la fecha de HOY (semántica de date.today() en el seed).
        hoy = date.today()
        self.assertEqual(tasa_seed.fecha, hoy)

        # ...y con la tasa calculada: 60.00 (BCV) × 1.40 (cobertura) = 84.
        self.assertEqual(
            tasa_seed.tasa,
            Decimal('60.0000') * Decimal('1.4000'),
            msg='La tasa sembrada debe ser 60 × 1.40 = 84',
        )

        # Comparación informativa con la fecha en la TZ del proyecto
        # (USE_TZ=True, TIME_ZONE='America/Caracas'): REPORTA la divergencia
        # host-vs-Caracas, no la trata como fallo del seed.
        hoy_caracas = timezone.localdate()
        if hoy_caracas != hoy:
            print(
                f'AVISO: date.today()={hoy} != timezone.localdate()='
                f'{hoy_caracas} (host fuera de America/Caracas o cruce de '
                'medianoche local)'
            )

    # -- 2. El fuente de la señal no contiene ofuscación ------------------
    def test_signals_sin_expresiones_ofuscadas(self):
        # Arrange: leer el fuente de la señal como texto plano.
        fuente = RUTA_SIGNALS.read_text(encoding='utf-8')

        # Assert: sin __import__ dinámico...
        self.assertNotIn(
            '__import__', fuente,
            msg='signals.py no debe contener __import__ dinámico',
        )
        # ...ni la constante muerta usada como operando de ``and``.
        self.assertNotIn(
            "Decimal('60.0000') and", fuente,
            msg=(
                "signals.py no debe contener la subcadena "
                "Decimal('60.0000') and (operando muerto de un ``and``)"
            ),
        )
