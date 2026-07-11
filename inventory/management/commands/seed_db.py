"""
┌─────────────────────────────────────────────────────────────────────────────┐
│ seed_db.py  —  Población de Datos y Stress Testing (Módulo Seeder)          │
│                                                                             │
│ Uso:  python manage.py seed_db [--clear]                                    │
│                                                                             │
│ --clear:  Elimina TODOS los registros de Empresa en cascada antes de        │
│           sembrar. Usar con precaución (entorno local).                     │
│                                                                             │
│ Requisitos:  Python estándar + random. Sin dependencias externas.           │
└─────────────────────────────────────────────────────────────────────────────┘
"""

import random
import time
from decimal import Decimal
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError

from inventory.managers import set_current_empresa
from inventory.models import (
    Empresa,
    Almacen,
    Articulo,
    Contacto,
    ConfiguracionEmpresa,
    SerialArticulo,
    NotaEntrega,
    MovimientoKardex,
)
from inventory.services import (
    registrar_compra_proveedor,
    procesar_venta,
    reversar_nota_entrega,
)


# ─────────────────────────────────────────────────────────────────────────────
# DATOS SEMILLA (nombres realistas para una tienda de telecom/electrónica)
# ─────────────────────────────────────────────────────────────────────────────

CLIENTES = [
    ("Juan", "Pérez", "V-10000001"),
    ("María", "González", "V-10000002"),
    ("Carlos", "Rodríguez", "V-10000003"),
    ("Ana", "Martínez", "V-10000004"),
    ("Luis", "Hernández", "V-10000005"),
    ("Sofía", "López", "V-10000006"),
    ("Pedro", "Ramírez", "V-10000007"),
    ("Laura", "Torres", "V-10000008"),
    ("Miguel", "Díaz", "V-10000009"),
    ("Carmen", "Vargas", "V-10000010"),
]

PROVEEDORES = [
    ("Distribuidora Tecno C.A.", "J-20000001", "Ricardo Mendoza"),
    ("Importadora Global S.R.L.", "J-20000002", "Laura Castillo"),
    ("Suministros Eléctricos C.A.", "J-20000003", "Andrés Paredes"),
    ("Redes y Comunicaciones 3000", "J-20000004", "Gabriela Rivas"),
    ("Logística Express C.A.", "J-20000005", "Fernando Quintero"),
]

ARTICULOS_FISICOS = [
    ("A2LT-TEL-001", "Router Inalámbrico AX5400", "HOGAR", True, Decimal("45.0000"), Decimal("75.00")),
    ("A2LT-TEL-002", "Switch Gigabit 24 Puertos", "HERRAMIENTAS", False, Decimal("120.0000"), Decimal("195.00")),
    ("A2LT-TEL-003", "Cable UTP Cat6 x10m", "OTROS", False, Decimal("8.5000"), Decimal("15.00")),
    ("A2LT-TEL-004", "Teléfono IP Grandstream", "OTROS", True, Decimal("55.0000"), Decimal("89.00")),
    ("A2LT-TEL-005", "Access Point Ubiquiti U6", "HERRAMIENTAS", True, Decimal("85.0000"), Decimal("139.00")),
    ("A2LT-TEL-006", "Fuente POE 48V 30W", "OTROS", False, Decimal("22.0000"), Decimal("38.00")),
    ("A2LT-TEL-007", "Panel de Parcheo 48 Puertos", "HERRAMIENTAS", False, Decimal("35.0000"), Decimal("59.00")),
    ("A2LT-TEL-008", "UPS APC 1500VA", "HOGAR", False, Decimal("180.0000"), Decimal("299.00")),
    ("A2LT-TEL-009", "Conector RJ45 x100", "OTROS", False, Decimal("3.5000"), Decimal("7.00")),
    ("A2LT-TEL-010", "Crimpadora Profesional", "HERRAMIENTAS", False, Decimal("28.0000"), Decimal("49.00")),
    ("A2LT-TEL-011", "Antena 5GHz 30dBi", "SOLARES", False, Decimal("95.0000"), Decimal("159.00")),
    ("A2LT-TEL-012", "Módem Fibra Óptica GPON", "OTROS", True, Decimal("40.0000"), Decimal("69.00")),
    ("A2LT-TEL-013", "Patch Cord Cat6 x1m", "OTROS", False, Decimal("2.0000"), Decimal("4.50")),
    ("A2LT-TEL-014", "Gabinete Rack 12U", "HERRAMIENTAS", False, Decimal("65.0000"), Decimal("110.00")),
    ("A2LT-TEL-015", "Multímetro Digital Fluke", "HERRAMIENTAS", False, Decimal("150.0000"), Decimal("245.00")),
]

ARTICULOS_COMBO = [
    ("A2LT-COMBO-001", "Kit Oficina Básica (Router+Switch+UTP)", Decimal("185.0000"), Decimal("299.00")),
    ("A2LT-COMBO-002", "Kit Cámaras WiFi (3 Cámaras + NVR)", Decimal("320.0000"), Decimal("499.00")),
    ("A2LT-COMBO-003", "Kit Red Doméstica (AP+POE+UTP)", Decimal("115.0000"), Decimal("179.00")),
    ("A2LT-COMBO-004", "Kit Herramientas Red (Crimpadora+Conectores+Probador)", Decimal("45.0000"), Decimal("79.00")),
    ("A2LT-COMBO-005", "Kit Oficina Premium (UPS+Switch+Router+POE)", Decimal("410.0000"), Decimal("649.00")),
]

CATEGORIAS = {"HOGAR", "HERRAMIENTAS", "SOLARES", "OTROS"}

SOCIAL_MESSAGES = {
    # ── Artículos Físicos ──────────────────────────────────────────────────
    "A2LT-TEL-001": {
        "ficha": "• Marca: TP-Link\n• Modelo: Archer AX72\n• Estándar: WiFi 6 (802.11ax)\n• Velocidad: AX5400 (574 Mbps + 4804 Mbps)\n• Puertos: 4x Gigabit LAN, 1x WAN\n• Antenas: 6 externas fijas",
        "cross": "📶 Router AX5400 (A2LT-TEL-001) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ WiFi 6 doble banda + 6 antenas. Ideal para gaming y streaming 4K sin cortes.",
        "quick": "Hola 👋\n\n✅ Sí, tenemos disponible el Router Inalámbrico AX5400 WiFi 6.\n\n📍 C.C. San Diego / Local M9-5.\n📞 0412.186.92.11 | 📱 Instagram: @g3multistore\n🛵 Delivery GRATIS 👉 Consulta tu zona\n\n📶 Router AX5400 (A2LT-TEL-001) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ WiFi 6 de doble banda, 6 antenas externas, cobertura total para hogar u oficina.",
    },
    "A2LT-TEL-002": {
        "ficha": "• Marca: Cisco\n• Modelo: SG350-24\n• Puertos: 24x Gigabit Ethernet\n• Capa: Layer 3 Lite\n• PoE+: 24 puertos (380W)\n• Ventilador: Smart Fan silencioso",
        "cross": "🔧 Switch Gigabit 24 Puertos (A2LT-TEL-002) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ 24 puertos PoE+ gestionable. Perfecto para redes empresariales.",
        "quick": "Hola 👋\n\n✅ Sí, disponemos del Switch Gigabit 24 Puertos PoE+ gestionable.\n\n📍 C.C. San Diego / Gran Bazar, Local M9-5.\n📞 0412.186.92.11\n🛵 Delivery GRATIS 👉 Consulta tu zona\n\n🔧 Switch Gigabit 24P PoE+ (A2LT-TEL-002) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ Capa 3 Lite + 380W PoE+. Ideal para oficinas y cámaras IP.",
    },
    "A2LT-TEL-003": {
        "ficha": "• Tipo: Cable UTP\n• Categoría: Cat6\n• Longitud: 10 metros\n• Frecuencia: 250 MHz\n• Conectores: RJ45 blindados\n• Norma: TIA/EIA-568-B",
        "cross": "🔌 Cable UTP Cat6 x10m (A2LT-TEL-003) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ 250 MHz, listo para Gigabit Ethernet. Conectividad confiable.",
        "quick": "Hola 👋\n\n✅ Tenemos cable UTP Cat6 de 10 metros disponible.\n\n📍 C.C. San Diego.\n📞 0412.186.92.11\n\n🔌 Cable UTP Cat6 x10m (A2LT-TEL-003) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ Blindado, 250 MHz, ideal para conectar tu red a máxima velocidad.",
    },
    "A2LT-TEL-004": {
        "ficha": "• Marca: Grandstream\n• Modelo: GXP2170\n• Líneas: 12 líneas SIP\n• Pantalla: 4.3\" color TFT\n• Puertos: 2x Gigabit LAN\n• PoE: 802.3af Class 2",
        "cross": "📞 Teléfono IP Grandstream (A2LT-TEL-004) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ 12 líneas SIP + pantalla a color. Profesional para tu oficina.",
        "quick": "Hola 👋\n\n✅ Sí, tenemos el Teléfono IP Grandstream GXP2170 en stock.\n\n📍 C.C. San Diego / Local M9-5.\n📞 0412.186.92.11\n🛵 Delivery GRATIS\n\n📞 Teléfono IP Grandstream (A2LT-TEL-004) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ 12 líneas, PoE, pantalla color. Calidad de llamada excepcional.",
    },
    "A2LT-TEL-005": {
        "ficha": "• Marca: Ubiquiti Networks\n• Estándar: Wi-Fi 6 (802.11ax)\n• Interfaz: 1 Puerto GbE RJ45\n• Alimentación: PoE Pasivo / AT",
        "cross": "📡 *Access Point Ubiquiti U6* ➡️ $[PRECIO_USD] USD / $[PRECIO_BCV] Bs\n⚡ Rendimiento Wi-Fi 6 empresarial de alta densidad.",
        "quick": "¡Hola!👋 Sí, tenemos disponible el *Access Point Ubiquiti U6* de alta densidad. Precio: $[PRECIO_USD] USD o al cambio oficial $[PRECIO_BCV] Bs. ¿Te lo reservamos?",
    },
    "A2LT-TEL-006": {
        "ficha": "• Voltaje: 48V DC\n• Potencia: 30W\n• Estándar: 802.3af/at\n• Puertos: 1x Gigabit LAN\n• Protección: Sobrecarga y cortocircuito\n• Conector: RJ45 + terminal",
        "cross": "⚡ Fuente POE 48V 30W (A2LT-TEL-006) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ 48V 30W, estándar 802.3af/at. Alimenta tu AP o cámara IP.",
        "quick": "Hola 👋\n\n✅ Tenemos fuente POE 48V 30W disponible.\n\n📍 C.C. San Diego.\n📞 0412.186.92.11\n\n⚡ Fuente POE 48V (A2LT-TEL-006) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ 30W, estándar 802.3af/at, protección incluida. Ideal para alimentar tus dispositivos PoE.",
    },
    "A2LT-TEL-007": {
        "ficha": "• Capacidad: 48 puertos\n• Tipo: Cat6\n• Altura: 1U\n• Blindaje: Apantallado\n• Color: Negro\n• Norma: TIA/EIA-568",
        "cross": "🔲 Panel de Parcheo 48 Puertos (A2LT-TEL-007) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ 48 puertos Cat6 1U. Organización profesional para tu rack.",
        "quick": "Hola 👋\n\n✅ Panel de Parcheo 48 Puertos Cat6 disponible.\n\n📍 C.C. San Diego / Local M9-5.\n📞 0412.186.92.11\n\n🔲 Panel Parcheo 48P (A2LT-TEL-007) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ 1U, blindado, listo para montar en tu rack. Calidad profesional.",
    },
    "A2LT-TEL-008": {
        "ficha": "• Marca: APC\n• Modelo: SMT1500\n• Potencia: 1500VA / 1000W\n• Topología: Online interactivo\n• Autonomía: 10 min a media carga\n• Tomas: 6x NEMA 5-15R + protección",
        "cross": "🔋 UPS APC 1500VA (A2LT-TEL-008) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ 1500VA, 6 tomas, protección contra sobretensión. Tu equipo seguro.",
        "quick": "Hola 👋\n\n✅ UPS APC 1500VA en stock, ideal para proteger tu servidor o PC.\n\n📍 C.C. San Diego / Gran Bazar.\n📞 0412.186.92.11\n🛵 Delivery GRATIS\n\n🔋 UPS APC 1500VA (A2LT-TEL-008) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ 1500VA, 6 tomas con regulación, respaldo de 10 min a media carga.",
    },
    "A2LT-TEL-009": {
        "ficha": "• Tipo: Conector RJ45\n• Categoría: Cat6\n• Blindaje: Blindado (STP)\n• Presentación: Bolsa x100 unidades\n• Compatible: Cable sólido y flexible\n• Estándar: T568A / T568B",
        "cross": "🔌 Conector RJ45 x100 (A2LT-TEL-009) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ Cat6 blindado, compatible T568A/B. Ideal para tu instalación.",
        "quick": "Hola 👋\n\n✅ Conectores RJ45 Cat6 x100 unidades disponibles.\n\n📍 C.C. San Diego.\n📞 0412.186.92.11\n\n🔌 Conectores RJ45 x100 (A2LT-TEL-009) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ Blindados, estándar T568A/B. Todo lo que necesitas para tu crimpado.",
    },
    "A2LT-TEL-010": {
        "ficha": "• Tipo: Crimpadora profesional\n• Compatible: RJ45 / RJ11 / RJ12\n• Características: Corte + crimpado + pelado\n• Material: Acero carbono temple\n• Mango: Ergonomico antideslizante",
        "cross": "🛠️ Crimpadora Profesional (A2LT-TEL-010) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ 3 en 1: corta, pela y crimpa. Herramienta esencial para técnicos.",
        "quick": "Hola 👋\n\n✅ Crimpadora Profesional RJ45 disponible.\n\n📍 C.C. San Diego / Local M9-5.\n📞 0412.186.92.11\n\n🛠️ Crimpadora Pro (A2LT-TEL-010) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ Acero templado, 3 funciones, mango ergonómico. La herramienta que todo técnico necesita.",
    },
    "A2LT-TEL-011": {
        "ficha": "• Frecuencia: 5 GHz\n• Ganancia: 30 dBi\n• Polarización: Dual Lineal\n• Ángulo: 8° horizontal / 8° vertical\n• Protección: IP65\n• Conector: N-Female",
        "cross": "📡 *Antena 5GHz 30dBi* ➡️ $[PRECIO_USD] USD / $[PRECIO_BCV] Bs\n✔️ Enlace punto a punto profesional para larga distancia.",
        "quick": "¡Hola!👋 Sí, tenemos la Antena 5GHz 30dBi profesional. Precio: $[PRECIO_USD] USD o al cambio oficial $[PRECIO_BCV] Bs. Ideal para enlaces punto a punto de larga distancia. ¿Te asesoramos?",
    },
    "A2LT-TEL-012": {
        "ficha": "• Marca: Huawei\n• Modelo: HG8245H\n• Tipo: GPON ONT\n• Puertos: 4x Gigabit LAN + 2x VoIP + WiFi\n• Estándar: ITU-T G.984\n• Alcance: hasta 20 km",
        "cross": "🌐 Módem Fibra GPON (A2LT-TEL-012) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ GPON 4 LAN + VoIP + WiFi. Perfecto para fibra óptica residencial.",
        "quick": "Hola 👋\n\n✅ Módem Fibra Óptica GPON Huawei disponible.\n\n📍 C.C. San Diego / Local M9-5.\n📞 0412.186.92.11\n\n🌐 Módem GPON (A2LT-TEL-012) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ 4 puertos LAN, VoIP, WiFi integrado. La solución completa para fibra óptica.",
    },
    "A2LT-TEL-013": {
        "ficha": "• Tipo: Patch Cord\n• Categoría: Cat6\n• Longitud: 1 metro\n• Conectores: RJ45 blindados\n• Color: Varios colores\n• Norma: TIA/EIA-568-B",
        "cross": "🔌 Patch Cord Cat6 x1m (A2LT-TEL-013) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ 1 metro, blindado. Calidad profesional para tu rack.",
        "quick": "Hola 👋\n\n✅ Patch Cord Cat6 de 1 metro disponible.\n\n📍 C.C. San Diego.\n📞 0412.186.92.11\n\n🔌 Patch Cord Cat6 (A2LT-TEL-013) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ Blindado, varios colores. El cable perfecto para organizar tu rack.",
    },
    "A2LT-TEL-014": {
        "ficha": "• Capacidad: 12U\n• Tipo: Rack abierto\n• Material: Acero laminado\n• Medidas: 600x600 mm\n• Color: Negro\n• Incluye: Tornillería + bases niveladoras",
        "cross": "🏗️ Gabinete Rack 12U (A2LT-TEL-014) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ 12U, acero laminado. Monta tu red de forma profesional y ordenada.",
        "quick": "Hola 👋\n\n✅ Gabinete Rack 12U en stock.\n\n📍 C.C. San Diego / Gran Bazar.\n📞 0412.186.92.11\n🛵 Delivery GRATIS\n\n🏗️ Rack 12U (A2LT-TEL-014) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ Acero laminado, medidas estándar 600x600. Organiza tu red como un profesional.",
    },
    "A2LT-TEL-015": {
        "ficha": "• Marca: Fluke\n• Modelo: 117\n• Tipo: True RMS\n• Voltaje: 600V AC/DC\n• Resistencia: 40 MΩ\n• Capacitancia: 10,000 µF\n• Categoría: CAT III 600V",
        "cross": "⚡ Multímetro Fluke 117 (A2LT-TEL-015) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ True RMS, CAT III 600V. La precisión que un técnico profesional merece.",
        "quick": "Hola 👋\n\n✅ Multímetro Digital Fluke 117 True RMS disponible.\n\n📍 C.C. San Diego / Local M9-5.\n📞 0412.186.92.11\n\n⚡ Fluke 117 (A2LT-TEL-015) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ True RMS, CAT III 600V, mide capacitancia. Herramienta profesional de diagnóstico eléctrico.",
    },
    # ── Combos ──────────────────────────────────────────────────────────────
    "A2LT-COMBO-001": {
        "ficha": "• Router AX5400 WiFi 6\n• Switch Gigabit 24 Puertos\n• Cable UTP Cat6 x10m\n• Ideal para: Oficina pequeña/mediana",
        "cross": "💼 Kit Oficina Básica (A2LT-COMBO-001) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ Router AX5400 + Switch 24P + UTP. Todo lo que tu oficina necesita.",
        "quick": "Hola 👋\n\n✅ Kit Oficina Básica completo y listo para instalar.\n\n📍 C.C. San Diego / Gran Bazar.\n📞 0412.186.92.11\n\n💼 Kit Oficina (A2LT-COMBO-001) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ Incluye router AX5400, switch 24P y cable UTP. Solución completa para tu negocio.",
    },
    "A2LT-COMBO-002": {
        "ficha": "• 3 Cámaras WiFi 1080p\n• NVR 4 canales PoE\n• Disco Duro 1TB\n• Ideal para: Vigilancia residencial o comercial",
        "cross": "📹 Kit Cámaras WiFi (A2LT-COMBO-002) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ 3 cámaras + NVR + 1TB. Vigilancia 24/7 para tu hogar o negocio.",
        "quick": "Hola 👋\n\n✅ Kit de Cámaras WiFi 3 cámaras + NVR disponible.\n\n📍 C.C. San Diego.\n📞 0412.186.92.11\n\n📹 Kit Cámaras (A2LT-COMBO-002) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ 3 cámaras 1080p, NVR 4 canales, disco 1TB. Tu seguridad en las mejores manos.",
    },
    "A2LT-COMBO-003": {
        "ficha": "• Access Point Ubiquiti U6\n• Fuente POE 48V 30W\n• Cable UTP Cat6 x10m\n• Ideal para: Hogar inteligente",
        "cross": "🏠 Kit Red Doméstica (A2LT-COMBO-003) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ AP Ubiquiti + POE + UTP. Expande tu red con cobertura total.",
        "quick": "Hola 👋\n\n✅ Kit Red Doméstica con Access Point Ubiquiti.\n\n📍 C.C. San Diego / Local M9-5.\n📞 0412.186.92.11\n\n🏠 Kit Red Doméstica (A2LT-COMBO-003) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ AP Ubiquiti U6, POE 48V y cable UTP. Cobertura WiFi total en tu hogar.",
    },
    "A2LT-COMBO-004": {
        "ficha": "• Crimpadora Profesional\n• Conectores RJ45 x100\n• Patch Cord Cat6 x1m\n• Ideal para: Técnicos instaladores",
        "cross": "🧰 Kit Herramientas Red (A2LT-COMBO-004) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ Crimpadora + 100 conectores + patch cord. El kit esencial del técnico.",
        "quick": "Hola 👋\n\n✅ Kit de Herramientas para Red completo.\n\n📍 C.C. San Diego.\n📞 0412.186.92.11\n\n🧰 Kit Herramientas (A2LT-COMBO-004) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ Crimpadora, 100 conectores RJ45 y patch cord. Todo lo que necesitas para tus instalaciones.",
    },
    "A2LT-COMBO-005": {
        "ficha": "• UPS APC 1500VA\n• Switch Gigabit 24 Puertos\n• Router AX5400 WiFi 6\n• Fuente POE 48V 30W\n• Ideal para: Oficina premium",
        "cross": "⭐ Kit Oficina Premium (A2LT-COMBO-005) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ UPS + Switch + Router + POE. La solución definitiva para tu empresa.",
        "quick": "Hola 👋\n\n✅ Kit Oficina Premium, la solución más completa.\n\n📍 C.C. San Diego / Gran Bazar.\n📞 0412.186.92.11\n🛵 Delivery GRATIS\n\n⭐ Kit Premium (A2LT-COMBO-005) ➡️ $[Precio_USD] (Divisas) | $[Precio_BCV] (BCV)\n✔️ UPS APC 1500VA, switch 24P, router AX5400 y POE. Máxima productividad para tu empresa.",
    },
}


class Command(BaseCommand):
    help = "Pobla la BD con datos de prueba realistas para stress testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Elimina TODAS las empresas y sus datos en cascada antes de sembrar.",
        )

    def handle(self, *args, **options):
        self.start_time = time.time()
        random.seed(42)  # Reproducibilidad

        if options["clear"]:
            self._clear_all()

        self.stdout.write(self.style.SUCCESS("=" * 64))
        self.stdout.write(self.style.SUCCESS("  SEED DB — Población de Datos para Stress Testing"))
        self.stdout.write(self.style.SUCCESS("=" * 64))

        # ── FASE 1: Aislamiento SaaS ──────────────────────────────────────────
        self.stdout.write("\n[1/7] Aislamiento SaaS — Creando 2 empresas...")
        empresa_a = Empresa.objects.create(
            nombre="A2LT Telecom", rif="J-40404040", activa=True
        )
        empresa_b = Empresa.objects.create(
            nombre="Demo Store B", rif="J-50505050", activa=True
        )
        set_current_empresa(empresa_a.id)
        self.stdout.write(
            self.style.SUCCESS(f"  [OK] {empresa_a.nombre} (RIF: {empresa_a.rif})")
        )
        self.stdout.write(
            self.style.SUCCESS(f"  [OK] {empresa_b.nombre} (RIF: {empresa_b.rif})")
        )

        # ── FASE 2: Parámetros Base ───────────────────────────────────────────
        self.stdout.write("\n[2/7] Parámetros Base — Tasa BCV y Almacenes...")
        config, _ = ConfiguracionEmpresa.objects.get_or_create(empresa=empresa_a)
        config.tasa_bcv = Decimal("36.5000")
        config.factor_cobertura = Decimal("1.0500")
        config.save()
        self.stdout.write(self.style.SUCCESS("  [OK] Tasa BCV = 36.50 Bs/USD"))
        self.stdout.write(self.style.SUCCESS("  [OK] Factor Cobertura = 1.05"))

        almacen_central = Almacen.objects.create(
            empresa=empresa_a, nombre="Central", es_principal=True
        )
        almacen_sucursal = Almacen.objects.create(
            empresa=empresa_a, nombre="Sucursal", es_principal=False
        )
        self.stdout.write(
            self.style.SUCCESS(f"  [OK] Almacén '{almacen_central.nombre}' (Principal)")
        )
        self.stdout.write(
            self.style.SUCCESS(f"  [OK] Almacén '{almacen_sucursal.nombre}'")
        )
        almacenes = [almacen_central, almacen_sucursal]

        # ── FASE 3: Entidades — Contactos ──────────────────────────────────────
        self.stdout.write("\n[3/7] Contactos — 10 Clientes + 5 Proveedores...")
        for nombre, apellido, ident in CLIENTES:
            Contacto.objects.create(
                empresa=empresa_a,
                identificacion=ident,
                nombre=f"{nombre} {apellido}",
                tipo="CLIENTE",
                telefono=f"0412-{random.randint(1000000, 9999999)}",
            )
        self.stdout.write(self.style.SUCCESS("  [OK] 10 Clientes creados"))

        proveedores = []
        for razon_social, rif_prov, asesor in PROVEEDORES:
            prov = Contacto.objects.create(
                empresa=empresa_a,
                identificacion=rif_prov,
                nombre=razon_social,
                tipo="PROVEEDOR",
                rif=rif_prov,
                nombre_asesor=asesor,
                telefono=f"0212-{random.randint(1000000, 9999999)}",
            )
            proveedores.append(prov)
        self.stdout.write(self.style.SUCCESS("  [OK] 5 Proveedores creados"))

        # ── FASE 4: Catálogo ──────────────────────────────────────────────────
        self.stdout.write("\n[4/7] Catálogo — 15 Artículos Físicos + 5 Combos...")
        articulos_fisicos = []
        for sku, nombre, cat, serial, costo, precio in ARTICULOS_FISICOS:
            msg = SOCIAL_MESSAGES.get(sku, {})
            art = Articulo.objects.create(
                empresa=empresa_a,
                sku=sku,
                nombre=nombre,
                tipo="FISICO",
                categoria=cat,
                costo=costo,
                precio_divisa=precio,
                usa_serial=serial,
                margen_ind=Decimal("30.00"),
                ficha_tecnica=msg.get("ficha", ""),
                social_cross=msg.get("cross", ""),
                social_quick=msg.get("quick", ""),
            )
            articulos_fisicos.append(art)
        self.stdout.write(self.style.SUCCESS("  [OK] 15 Artículos Físicos creados"))

        for sku, nombre, costo, precio in ARTICULOS_COMBO:
            msg = SOCIAL_MESSAGES.get(sku, {})
            Articulo.objects.create(
                empresa=empresa_a,
                sku=sku,
                nombre=nombre,
                tipo="COMBO",
                categoria="OTROS",
                costo=costo,
                precio_divisa=precio,
                ficha_tecnica=msg.get("ficha", ""),
                social_cross=msg.get("cross", ""),
                social_quick=msg.get("quick", ""),
            )
        self.stdout.write(self.style.SUCCESS("  [OK] 5 Combos creados"))

        # Separar serializados
        articulos_con_serial = [a for a in articulos_fisicos if a.usa_serial]
        articulos_sin_serial = [a for a in articulos_fisicos if not a.usa_serial]

        # ── FASE 5: Ingestión de Inventario ────────────────────────────────────
        self.stdout.write("\n[5/7] Ingestión de Inventario — Compras masivas...")
        hoy = date.today()
        serial_counter = 1
        facturas_compra = []

        for idx, articulo in enumerate(articulos_fisicos):
            proveedor = random.choice(proveedores)
            cantidad = random.randint(30, 150)
            costo_unitario = articulo.costo
            monto_total = cantidad * costo_unitario

            # Generar seriales si aplica
            seriales = []
            if articulo.usa_serial:
                for _ in range(cantidad):
                    seriales.append(f"SN-{articulo.sku}-{serial_counter:05d}")
                    serial_counter += 1

            item = {
                "sku": articulo.sku,
                "cantidad": Decimal(str(cantidad)),
                "costo_factura": costo_unitario,
            }
            if seriales:
                item["seriales"] = seriales

            fecha_compra = hoy - timedelta(days=random.randint(1, 30))
            res = registrar_compra_proveedor(
                proveedor_id=str(proveedor.pk),
                numero_factura=f"FACT-SEED-{idx + 1:03d}",
                fecha_compra=fecha_compra.isoformat(),
                monto_total_usd=monto_total,
                almacen_id=almacen_central.pk,
                lista_items=[item],
                usuario="seed_db",
            )
            facturas_compra.append(res["documento_id"])
            self.stdout.write(
                f"    + {articulo.nombre}: {cantidad} uds  "
                f"(Factura FACT-SEED-{idx + 1:03d})"
            )

        self.stdout.write(
            self.style.SUCCESS("  [OK] Inventario ingresado correctamente")
        )

        # ── FASE 6: Simulación de Mostrador ───────────────────────────────────
        self.stdout.write(
            "\n[6/7] Simulación de Mostrador — 30 facturas de venta..."
        )
        clientes = list(Contacto.objects.filter(empresa=empresa_a, tipo="CLIENTE"))
        notas_emitidas = []

        for i in range(30):
            num_items = random.randint(1, 4)
            items_venta = []

            for _ in range(num_items):
                if random.random() < 0.3 and articulos_con_serial:
                    articulo = random.choice(articulos_con_serial)
                else:
                    articulo = random.choice(articulos_sin_serial)
                catidad_vender = random.randint(1, 3)

                seriales_venta = []
                if articulo.usa_serial:
                    disponibles = list(
                        SerialArticulo.objects.filter(
                            articulo=articulo,
                            almacen=almacen_central,
                            estado="DISPONIBLE",
                        )[:catidad_vender]
                    )
                    if len(disponibles) < catidad_vender:
                        continue
                    seriales_venta = [s.serial for s in disponibles]

                items_venta.append(
                    {
                        "articulo_sku": articulo.sku,
                        "cantidad": catidad_vender,
                        "precio_base": str(articulo.precio_divisa),
                        "precio_unitario_usd": str(articulo.precio_divisa),  # alias retrocompat
                        "seriales": seriales_venta,
                    }
                )

            if not items_venta:
                continue

            cliente = random.choice(clientes)
            try:
                nota = procesar_venta(
                    cliente_id=cliente.pk,
                    lista_items=items_venta,
                    almacen_id=almacen_central.pk,
                    usuario="seed_db",
                    observaciones=f"Venta simulación #{i + 1}",
                )
                notas_emitidas.append(nota)
                self.stdout.write(
                    f"    + Nota #{nota.numero} — {cliente.nombre} "
                    f"({len(items_venta)} ítems)"
                )
            except ValueError as e:
                self.stdout.write(
                    self.style.WARNING(f"    ~ Venta #{i + 1} omitida: {e}")
                )

        total_facturadas = len(notas_emitidas)
        self.stdout.write(
            self.style.SUCCESS(
                f"  [OK] {total_facturadas} facturas emitidas exitosamente"
            )
        )

        # ── FASE 7: Contingencia — Reversos ────────────────────────────────────
        self.stdout.write("\n[7/7] Contingencia — Reversando 3 ventas...")
        if notas_emitidas:
            reversas = random.sample(
                notas_emitidas, min(3, len(notas_emitidas))
            )
            for nota in reversas:
                try:
                    resultado = reversar_nota_entrega(
                        empresa_id=empresa_a.pk,
                        nota_id=nota.pk,
                        motivo="Reverso por stress testing (Fase 7)",
                    )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  [OK] Nota #{nota.numero} reversada — "
                            f"{resultado['mensaje']}"
                        )
                    )
                except ValueError as e:
                    self.stdout.write(
                        self.style.WARNING(f"  ~ Reverso omitido: {e}")
                    )
        else:
            self.stdout.write(self.style.WARNING("  ~ No hay notas para reversar."))

        # ── RESUMEN ────────────────────────────────────────────────────────────
        elapsed = time.time() - self.start_time
        self.stdout.write("\n" + "=" * 64)
        self.stdout.write(
            self.style.SUCCESS(f"  SEED COMPLETADO en {elapsed:.2f} segundos")
        )
        self.stdout.write("=" * 64)
        self.stdout.write(f"  Empresas:          2")
        self.stdout.write(f"  Almacenes:         {Almacen.objects.count()}")
        self.stdout.write(f"  Contactos:         {Contacto.objects.count()}")
        self.stdout.write(f"  Artículos:         {Articulo.objects.count()}")
        self.stdout.write(f"  Facturas emitidas: {total_facturadas}")
        self.stdout.write(f"  Reversos:          {len(reversas) if notas_emitidas else 0}")
        self.stdout.write(
            f"  Movs. Kárdex:      {MovimientoKardex.objects.count()}"
        )

        set_current_empresa(None)

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _clear_all(self):
        """Elimina todos los registros en orden inverso de dependencias."""
        from inventory.models import (
            MovimientoKardex, SerialArticulo, DetalleNotaEntrega,
            NotaEntrega, InventarioAlmacen, DocumentoCompra,
            Contacto, Articulo, RecetaCombo, Almacen,
            ConfiguracionEmpresa,
        )
        self.stdout.write(self.style.WARNING("Limpiando base de datos existente..."))
        try:
            MovimientoKardex.global_objects.all().delete()
            SerialArticulo.global_objects.all().delete()
            DetalleNotaEntrega.objects.all().delete()
            NotaEntrega.global_objects.all().delete()
            InventarioAlmacen.global_objects.all().delete()
            DocumentoCompra.global_objects.all().delete()
            RecetaCombo.objects.all().delete()
            Contacto.global_objects.all().delete()
            Articulo.global_objects.all().delete()
            Almacen.global_objects.all().delete()
            ConfiguracionEmpresa.global_objects.all().delete()
            Empresa.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("  [OK] Base de datos limpia."))
        except Exception as e:
            raise CommandError(f"Error al limpiar BD: {e}")
