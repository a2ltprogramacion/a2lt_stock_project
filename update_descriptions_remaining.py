import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'a2lt_stock_project.settings')
import django
django.setup()

from inventory.models import Articulo
from decimal import Decimal

eid = 34

articulos_con_data = {
    'MONI-001': {
        'descripcion': 'Monitor 24" Full HD IPS, 75Hz, 1ms, FreeSync, HDMI+VGA, inclinable, VESA 100x100. Ideal oficina y gaming casual.',
        'ficha_tecnica': 'Panel: 23.8" IPS Full HD (1920x1080) 75Hz\nTiempo respuesta: 1ms (MPRT)\nBrillo: 250 cd/m2, Contraste: 1000:1\nColores: sRGB 99%, 16.7M colores\nConectividad: HDMI 1.4 x1, VGA x1, Audio out\nErgonomia: Inclinacion -5° a +15°, VESA 100x100\nDimensiones: 540 x 410 x 180 mm, 3.2 kg',
        'social_quick': 'Monitor 24" Full HD IPS 75Hz - Claridad total para trabajo y gaming casual. Calidad visual, precio accesible. #Monitor #FullHD #IPS #Oficina #Gaming',
        'social_cross': 'Completa tu setup: Teclado Mecanico RGB ($75) | Mouse Inalambrico ($38) | Auriculares ANC ($58). Tu setup completo!'
    },
    'MONI-002': {
        'descripcion': 'Monitor 27" 4K UHD IPS, 60Hz, HDR10, 99% sRGB, USB-C 65W PD, KVM, HDMI+DP, altura ajustable. Profesional creativo.',
        'ficha_tecnica': 'Panel: 27" IPS 4K UHD (3840x2160) 60Hz\nHDR10, 350 nits, 1000:1, 99% sRGB, 95% DCI-P3\nConectividad: USB-C 90W PD x1, HDMI 2.0 x2, DP 1.4 x1, USB 3.0 Hub x3\nErgonomia: Altura 130mm, giro ±90°, inclinacion -5°/+20°, VESA 100x100\nKVM integrado, Picture-by-Picture, Picture-in-Picture',
        'social_quick': 'Monitor 27" 4K UHD IPS - Calidad profesional para creadores y multitarea extrema. Detalle extremo, color real. #Monitor4K #UHD #Creative #Productividad',
        'social_cross': 'Tu estudio completo: Tablet iPad Air ($520) | Teclado Mecanico ($75) | Dock USB-C 7-en-1 ($48). Flujo creativo sin limites!'
    },
    'TECL-001': {
        'descripcion': 'Teclado mecanico 75% hot-swap, switches Red lineales, RGB per-key, PBT doubleshot, gasket mount, knob control, USB-C, QMK/VIA.',
        'ficha_tecnica': 'Layout: 75% (81 keys) ANSI\nSwitches: Lineales Red (45g, 4.0mm) hot-swap\nKeycaps: PBT Doubleshot, perfil Cherry\nIluminacion: RGB per-key, south-facing, 16.8M colores\nConectividad: USB-C desmontable, polling 1000Hz\nFirmware: QMK/VIA soporte nativo\nExtras: Knob programable, foam silencioso, cable USB-C trenzado 1.6m',
        'social_quick': 'Teclado Mecanico 75% RGB - Hot-swap, gasket mount, sonido thock, RGB brutal. Tu escritura, tu estilo. #Mecanico #RGB #HotSwap #CustomKeyboard',
        'social_cross': 'Tu setup completo: Mouse Inalambrico ($38) | Monitor 24" ($180) | Auriculares ($58). Tu battle station perfecta!'
    },
    'MOUS-001': {
        'descripcion': 'Mouse ergonómico inalámbrico 2.4GHz+Bluetooth, 16000 DPI, 7 botones programables, 70h bateria, carga USB-C, agarre cómodo.',
        'ficha_tecnica': 'Sensor: Óptico 16000 DPI, 400 IPS, 40G\nBotones: 7 programables (laterales, rueda, DPI)\nConectividad: 2.4GHz USB-A dongle + Bluetooth 5.1 + USB-C cable\nBateria: 70h (RGB off), carga rápida USB-C 2min=1h\nErgonomía: Diestro, reposapulgar, recubrimiento goma\nPeso: 98g (sin receptor), pies PTFE',
        'social_quick': 'Mouse Ergonómico Wireless 16K DPI - Precisión, comodidad, libertad total. Tu mano lo agradece. #Mouse #Wireless #Ergonómico #Gaming #Oficina',
        'social_cross': 'Setup completo: Teclado Mecánico ($75) | Monitor 24" ($180) | Auriculares ($58). Tu setup, tus reglas!'
    },
    'AURI-001': {
        'descripcion': 'Auriculares over-ear Bluetooth 5.0, ANC híbrido 35dB, 40mm drivers, 40h bateria, carga rápida 5min=2h, multipunto, plegables.',
        'ficha_tecnica': 'Drivers: 40mm dinámicos, bobina voz CCAW\nANC: Híbrido 35dB, modo transparencia\nCodec: SBC, AAC, aptX, LDAC\nBatería: 40h (ANC on), 60h (ANC off), carga 5min=2h, USB-C\nConectividad: Bluetooth 5.0, multipunto 2 dispositivos\nMic: 2 MEMS beamforming, ENC llamadas\nConfort: Diadema acero, almohadillas memory foam, plegables 90°\nPeso: 265g, estuche rigido incluido',
        'social_quick': 'Auriculares ANC Bluetooth 5.0 - Silencio total, sonido premium, 40h bateria. Tu banda sonora, sin interrupciones. #Auriculares #ANC #Bluetooth #Música #Viaje',
        'social_cross': 'Tu audio completo: Smartphone ($750) | Switch OLED ($350) | Laptop ($650). Audio premium en todos tus dispositivos!'
    },
    'IMPR-001': {
        'descripcion': 'Impresora láser monocromática multifunción, 30ppm, duplex automático, WiFi/USB/Ethernet, ADF 50 hojas, 250 hojas bandeja, toner 1500 págs.',
        'ficha_tecnica': 'Tecnología: Láser monocromática\nVelocidad: 30 ppm (A4)\nResolución: 1200 x 1200 dpi\nFunciones: Imprimir, Copiar, Escanear, Fax\nDuplex: Automático\nConectividad: WiFi 2.4/5GHz, Ethernet, USB 2.0, WiFi Direct\nCapacidad: Bandeja 250 hojas, ADF 50 hojas, salida 150 hojas\nTóner: Inicial 700 pág, Estándar 1500, Alto 3000\nDisplay: LCD 2.7" color, táctil\nDimensiones: 415 x 360 x 310 mm, 8.5 kg',
        'social_quick': 'Impresora Laser Multi 30ppm - Rápida, eficiente, conectada. Oficina sin papel? Casi. #Impresora #Laser #Multifuncion #Oficina #Productividad',
        'social_cross': 'Tu oficina completa: Papel A4 500h ($12) | Tóner Extra ($45) | Archivo ($25). Flujo documental cero fricción!'
    },
    'ESCA-001': {
        'descripcion': 'Escritorio gaming 140x60cm, superficie fibra carbono, RGB perimetral 10 modos, gestión cables, gancho auriculares, portavasos, patas ajustables, 100kg carga.',
        'ficha_tecnica': 'Superficie: 140x60cm, fibra carbono textil, resistente agua/rayones\nRGB: Perimetral LED 10 modos, control tactil\nGestión cables: Bandeja oculta, 3 pasacables, clips adhesivos\nExtras: Gancho auriculares acero, portavasos metalico, alfombrilla XXL incluida\nEstructura: Acero Z, patas nivelables 10mm, refuerzos transversales\nCarga máx: 100kg distribuidos\nMontaje: 15 min, herramientas incluidas\nColor: Negro mate + RGB',
        'social_quick': 'Escritorio Gaming RGB 140x60 - Ilumina tus victorias, organiza tu setup, domina el juego. Tu centro de mando. #Gaming #Setup #RGB #Escritorio #Gamer',
        'social_cross': 'Tu setup completo: Mouse RGB ($38) | Teclado Mecánico ($75) | Auriculares ANC ($58) | Monitor 27" 4K ($420). Tu base de operaciones!'
    },
    'SILL-001': {
        'descripcion': 'Silla ergonómica malla transpirable, soporte lumbar ajustable 4D, reposabrazos 4D, mecanismo sincronizado, reclinación 135°, pistón gas clase 4, base nylon 5 radios, 120kg.',
        'ficha_tecnica': 'Respaldo: Malla transpirable, soporte lumbar 4D (altura, profundidad, firmeza)\nAsiento: Espuma alta densidad, deslizante 5cm, borde cascada\nReposabrazos: 4D (altura, ancho, profundidad, giro)\nMecanismo: Sincronizado 2:1, bloqueo 3 posiciones, tension ajustable\nReclinación: 90°-135°, bloqueo infinito\nBase: Nylon reforzado 5 radios, ruedas PU 60mm silenciosas\nPistón: Gas clase 4, carrera 100mm\nCapacidad: 120kg\nCertificación: BIFMA, EN1335',
        'social_quick': 'Silla Ergonómica 4D - Tu espalda te lo agradecerá. Confort todo el día, productividad máxima. #SillaErgonómica #Oficina #Salud #Confort #HomeOffice',
        'social_cross': 'Tu oficina completa: Monitor 24" ($180) | Teclado Mecánico ($75) | Mouse Ergonómico ($38). Tu bienestar, tu inversión!'
    },
    'DISC-001': {
        'descripcion': 'SSD 1TB NVMe PCIe 4.0 x4, 7000/5000 MB/s lectura/escritura, DRAM cache, TLC 3D NAND, 5 años garantia, disipador grafeno opcional.',
        'ficha_tecnica': 'Interfaz: PCIe 4.0 x4 NVMe 1.4\nCapacidad: 1TB (1000GB)\nControlador: DRAM-less con HMB\nNAND: 3D TLC 176 capas\nLectura seq: 7000 MB/s\nEscritura seq: 5000 MB/s\nLectura aleat 4K: 650K IOPS\nEscritura aleat 4K: 700K IOPS\nTBW: 600 TBW\nMTBF: 1.5M horas\nFactor forma: M.2 2280, single-sided\nTemp: 0-70°C operando, -40-85°C almacenamiento',
        'social_quick': 'SSD 1TB NVMe Gen4 7000MB/s - Velocidad extrema para gaming, creación, todo. Tu PC vuela. #SSD #NVMe #Gen4 #Gaming #PCMasterRace',
        'social_cross': 'Tu PC completo: GPU RTX 4070 ($820) | RAM 32GB DDR5 ($175) | AIO 360mm ($135). Bestia liberada!'
    },
    'DISC-002': {
        'descripcion': 'HDD externo 4TB USB 3.2 Gen 1, 5400 RPM, 256MB cache, USB-C + USB-A cable, 256-bit AES hw encryption, resistente golpes, 3 años garantia.',
        'ficha_tecnica': 'Capacidad: 4TB (4000GB)\nInterfaz: USB 3.2 Gen 1 (5 Gbps), compatible USB 2.0\nDisco interno: 5400 RPM, 256MB cache\nCifrado: AES 256-bit hardware, protección contraseña\nFormato: NTFS (Windows), reformateable exFAT/APFS\nResistencia: Choque 1000G (operando), 2000G (no operando)\nCable: USB-C a USB-A 0.5m + adaptador USB-C\nCompatibilidad: Windows 10+, macOS 10.13+, Linux kernel 4.4+\nDimensiones: 118 x 80 x 15 mm, 210g\nGarantía: 3 años + rescate datos 3 años',
        'social_quick': 'HDD Externo 4TB USB 3.0 - Espacio infinito para tus backups, juegos, media. Almacena sin límites. #HDD #Externo #Backup #Almacenamiento #4TB',
        'social_cross': 'Tu estrategia 3-2-1: SSD NVMe 1TB ($135) | Cloud 2TB ($10/mes) | HDD 4TB Ext ($150). Datos seguros, siempre!'
    },
    'MEM-001': {
        'descripcion': 'Kit 2x16GB DDR5-5600 CL36, Intel XMP 3.0 / AMD EXPO, PMIC integrado, disipador aluminio bajo perfil, compatible Intel 12/13/14gen + AMD AM5.',
        'ficha_tecnica': 'Kit: 2x16GB = 32GB\nTipo: DDR5 SDRAM\nFrecuencia: 5600 MT/s (PC5-44800)\nLatencia: CL36-36-36-76\nVoltaje: 1.1V (base), 1.25V (XMP/EXPO)\nPMIC: Integrado client-side\nDisipador: Aluminio anodizado, 33mm altura\nCompatibilidad: Intel 12/13/14 gen (Z690/790), AMD AM5 (X670/B650)\nCertificación: Intel XMP 3.0, AMD EXPO',
        'social_quick': 'RAM 32GB DDR5-5600 CL36 - Velocidad extrema, estabilidad total. Tu PC merece lo mejor. #RAM #DDR5 #5600MHz #Gaming #PCBuild',
        'social_cross': 'Tu build completa: RTX 4070 ($820) | SSD 1TB ($135) | AIO 360mm ($135). Bestia despertada!'
    },
    'GPU-001': {
        'descripcion': 'RTX 4070 12GB GDDR6X, Ada Lovelace, DLSS 3, Ray Tracing, 5888 CUDA, 192-bit, 21 Gbps, 200W, 3x DP 1.4a, 1x HDMI 2.1, 3-slot.',
        'ficha_tecnica': 'GPU: NVIDIA Ada Lovelace (TSMC 4N)\nCUDA Cores: 5888\nVRAM: 12GB GDDR6X, 192-bit, 21 Gbps\nBase/Boost: 1920/2475 MHz\nRT Cores: 46 (3ra gen)\nTensor Cores: 184 (4ta gen)\nDLSS: 3.0 (Frame Gen)\nRay Tracing: 3ra gen\nBus: PCIe 4.0 x16\nSalidas: 3x DP 1.4a, 1x HDMI 2.1\nTDP: 200W, conector 1x 12VHPWR\nDimensiones: 261 x 112 x 48 mm, 2.5 slots\nConector: 1x 12VHPWR (incluye adaptador 2x 8-pin)',
        'social_quick': 'RTX 4070 12GB - DLSS 3, Ray Tracing, 1440p Ultra, 4K ready. Potencia Ada Lovelace en tus manos. #RTX4070 #NVIDIA #AdaLovelace #Gaming #DLSS3',
        'social_cross': 'Tu rig completa: i5-13600K ($320) | RAM 32GB DDR5 ($175) | SSD 1TB ($135) | AIO 360mm ($135). Bestia armada!'
    },
    'FUEN-001': {
        'descripcion': 'Fuente ATX 3.0 850W 80+ Gold, full modular, 12VHPWR nativo, caps japonesas, ventilador 135mm FDB, 10 años garantía, ATX 3.0/PCIe 5.0 ready.',
        'ficha_tecnica': 'Potencia: 850W continuos\nCertificación: 80+ Gold (90%@20%, 92%@50%, 89%@100%)\nModularidad: Full modular, cables flat black\nConector GPU: 1x 12VHPWR (600W) + 2x PCIe 6+2\nVentilador: 135mm FDB, zero RPM <40% carga\nCapacitores: 100% Japoneses (primarios/secundarios)\nProtecciones: OVP, UVP, OCP, OPP, SCP, OTP\nCertificaciones: 80+ Gold, Cybenetics Gold, ATX 3.0, PCIe 5.0\nGarantía: 10 años\nDimensiones: 150 x 150 x 86 mm',
        'social_quick': 'PSU 850W Gold Full Modular - Corazón de tu PC, energía limpia, futuro ATX 3.0 listo. #PSU #80PlusGold #Modular #ATX3 #PCIe5 #PCBuild',
        'social_cross': 'Tu power stack: RTX 4070 ($820) | i5-13600K ($320) | RAM 32GB DDR5 ($175) | SSD 1TB ($135). Bestia alimentada!'
    },
    'CASE-001': {
        'descripcion': 'Gabinete mid-tower ATX, vidrio templado 4mm lateral+frontal, 3x ARGB 120mm incluidos, soporte E-ATX/ATX/mATX/ITX, 360mm radiador superior/frontal, 7 slots, PSU shroud, gestión cables.',
        'ficha_tecnica': 'Formato: Mid-Tower ATX/E-ATX/mATX/ITX\nVidrio: Templado 4mm lateral + frontal\nVentiladores incluidos: 3x 120mm ARGB (frontal), 1x 120mm trasero\nRadiadores: Superior 360/280/240/120, Frontal 360/280/240/120, Trasero 120\nSlots: 7 + 2 vertical (riser opcional)\nBahías: 2x 3.5"/2.5", 2x 2.5"\nPSU: ATX/ATX 3.0, longitud max 220mm (sin radiador)\nGPU: 410mm max (sin radiador frontal), 340mm (con 360mm)\nCPU Cooler: 170mm max\nGestión cables: 25mm tras bandeja, gomas, velcro\nFiltros: Superior, inferior, frontal (magnéticos)\nDimensiones: 460 x 230 x 480 mm, 7.5 kg',
        'social_quick': 'Case Mid-Tower Vidrio Templado ARGB - Exhibe tu build, flujo óptimo, estilo único. Tu PC merece escenario. #Case #RGB #TemperedGlass #PCBuild #Showcase',
        'social_cross': 'Tu build soñada: RTX 4070 ($820) | 850W Gold ($145) | RAM 32GB DDR5 ($175) | i5-13600K ($320). Obra maestra armada!'
    },
    'COOL-001': {
        'descripcion': 'AIO 360mm ARGB, bomba 5ta gen, radiador 394mm, 3x 120mm ARGB PWM, bloque CPU rotativo, tubos tejidos 400mm, LGA1700/AM5/AM4, 5 años.',
        'ficha_tecnica': 'Radiador: 394 x 120 x 27mm, aluminio, 12 canales\nBomba: 5ta gen, ceramica, 3100 RPM max, <20 dB\nVentiladores: 3x 120mm ARGB PWM, 500-2200 RPM, 71.5 CFM, 2.5 mmH2O\nBloque CPU: Cobre niquelado, base microcanales, rotación 360°, ARGB anillo\nTubos: EPDM tejido nylon 400mm, baja perdida\nSocket: Intel LGA1700/1200/115x, AMD AM5/AM4\nControl: PWM 4-pin + ARGB 3-pin 5V, software motherboard\nVida util: 50,000 hrs bomba, 60,000 hrs ventiladores\nGarantía: 5 años',
        'social_quick': 'AIO 360mm ARGB - Enfriamiento extremo, estética brutal. Tu CPU agradece, tu build brilla. #AIO #360mm #ARGB #LiquidCooling #OC #PCBuild',
        'social_cross': 'Tu cooling stack: RTX 4070 ($820) | i5-13600K ($320) | RAM 32GB DDR5 ($175) | Case 360mm ($120). Bestia enfriada!'
    },
    'CABLE-001': {
        'descripcion': 'Kit 12 cables extensiones ARGB: 24-pin 60cm, 2x 8-pin PCIe 60cm, 4+4 CPU 60cm, 3x SATA, 2x PCIe 6+2, 1x 12VHPWR. Conectores enchapados, funda PET trenzada, clips incluidos.',
        'ficha_tecnica': 'Cables: 12 extensiones (no cables PSU directos)\nConductores: 16 AWG cobre estañado, 600V\nConectores: Molex Mini-Fit Jr 5557/5559, gold-plated\nFunda: PET trenzado alta densidad, retardante llama VW-1\nConectores: 24-pin ATX, 2x 8-pin (4+4) CPU, 3x SATA, 2x PCIe 6+2, 1x 12VHPWR\nLongitud: 60cm c/u (salvo SATA 45cm)\nColores: Negro/Blanco/Rojo/Azul/Verde/Amarillo/Rosa/Cian/Naranja/Morado/Gris\nClips: 24 clips plastico incluidos\nCertificación: UL 758, RoHS, REACH',
        'social_quick': 'Kit Extensiones ARGB 12 cables - Color, orden, estilo. Cable management nivel pro. #CableManagement #RGB #Extensions #PCBuild #Aesthetic',
        'social_cross': 'Tu cable management pro: Case ARGB ($120) | AIO 360mm ($135) | GPU RTX 4070 ($820). Cable management = Arte!'
    },
    'HUB-001': {
        'descripcion': 'Hub USB-C 7-en-1: HDMI 4K@60Hz, 3x USB-A 3.0, USB-C 100W PD, SD/TF lector, Gigabit Ethernet, aluminio, cable 15cm.',
        'ficha_tecnica': 'Puertos: HDMI 2.0 4K@60Hz, 3x USB-A 3.0 (5Gbps), USB-C 100W PD, SD/TF UHS-I, RJ45 1Gbps\nEntrada: USB-C 3.1 Gen 2 (10Gbps), PD 100W pass-through\nChipset: VL817 + RTL8211F + GL3224\nAlimentación: Bus-powered + PD pass-through 100W max\nMaterial: Aluminio CNC anodizado, disipación pasiva\nCable: 15cm trenzado nylon, USB-C 3.1 Gen 2\nCompatibilidad: USB-C DP Alt Mode devices (MacBook, iPad Pro, ChromeBook, Win/Linux)\nDimensiones: 115 x 48 x 14 mm, 85g',
        'social_quick': 'Hub USB-C 7-en-1 - Un puerto, siete posibilidades. Conecta todo, crea sin límites. #Hub #USBC #7en1 #Productividad #Conectividad',
        'social_cross': 'Tu setup móvil: iPad Air ($520) | Teclado Mágico ($299) | AirPods Pro ($249). Oficina en la mochila!'
    },
    'WEBC-001': {
        'descripcion': 'Webcam 4K@30fps / 1080p@60fps, Sony STARVIS, HDR, autofoco, mic array dual beamforming, privacidad tapa, clip universal, USB-C 2m.',
        'ficha_tecnica': 'Sensor: Sony IMX415 1/2.8" 8.3MP STARVIS\nResolución: 4K@30fps, 1080p@60fps, 720p@60fps\nLente: f/2.0, 85° FOV, autofoco continuo, corrección luz baja\nHDR: Sí, WDR 120dB\nAudio: 2x MEMS beamforming, cancelación ruido IA, -38dB\nPrivacidad: Tapa física deslizante\nConectividad: USB 2.0 Type-C (cable 2m desmontable)\nMontaje: Clip universal monitor/portátil/tripode 1/4"\nSoftware: App configuración (FOV, zoom, exposure, WB, noise reduction)\nCompatibilidad: UVC/UAC, Windows/Mac/Linux/ChromeOS, Teams/Zoom/Meet/OBS',
        'social_quick': 'Webcam 4K HDR - Imagen pro, audio claro, privacidad total. Tu mejor cara, siempre. #Webcam #4K #HDR #Streaming #Reuniones #HomeOffice',
        'social_cross': 'Tu studio casero: Mic USB ($78) | Ring Light ($45) | Stream Deck ($155). Studio listo!'
    },
    'MICR-001': {
        'descripcion': 'Mic condensador USB cardioide, 24bit/192kHz, patrón cardioide/omni/bidireccional/estereo, ganancia/volumen/mute touch, Zero-latency monitoring 3.5mm, shock mount + pop filter + tripode.',
        'ficha_tecnica': 'Cápsula: Condensador 16mm, diafragma grande\nPatrones: Cardioide, Omnidireccional, Bidireccional, Estéreo\nRespuesta: 20Hz-20kHz\nResolución: 24-bit/192kHz\nSalida: USB 2.0 (audio class), monitoring 3.5mm zero-latency\nControles: Ganancia dial, volumen dial, mute touch, patrón selector\nAccesorios: Shock mount, pop filter, tripode escritorio, cable USB-C 2m\nMontaje: Rosca 5/8"-27, adaptador 3/8" incluido',
        'social_quick': 'Mic USB Condensador 24bit/192kHz - Voz pro, patrones versátiles, zero latency. Tu voz, calidad broadcast. #Micrófono #USB #Condensador #Streaming #Podcast #Voz',
        'social_cross': 'Tu estudio casero: Auriculares ($78) | Interface ($150) | Ring Light ($45). Studio listo!'
    },
    'STRE-001': {
        'descripcion': 'Stream Deck 15 teclas LCD, acción personalizable, perfiles infinitos, plugins comunidad, integracion OBS/Streamlabs/Twitch/YouTube/Discord/Spotify/Philips Hue/Philips Hue/IFTTT, SDK abierto.',
        'ficha_tecnica': 'Teclas: 15 LCD 72x72px, tactiles, retroiluminadas\nConectividad: USB 2.0 Type-C (cable 1.5m)\nSoftware: Stream Deck App (Win/Mac), Store plugins, perfiles infinitos\nIntegraciones: OBS, Streamlabs, Twitch, YouTube, Discord, Spotify, Philips Hue, Elgato Key Light, IFTTT, Voicemod, Twitter, TikTok\nSDK: Plugin developer kit (Python/Node/Go), APIs REST, webhooks\nAlimentación: USB bus-powered (5V 500mA max)\nDimensiones: 118 x 84 x 33 mm, 180g\nCompatibilidad: Windows 10+, macOS 10.13+',
        'social_quick': 'Stream Deck 15 - Control total, un toque. Automatiza, crea, domina tu stream. #StreamDeck #Elgato #Streaming #ContentCreator #ControlTotal',
        'social_cross': 'Tu studio pro: Webcam 4K ($105) | Mic USB ($78) | Ring Light ($45) | Auriculares ($58). Studio listo!'
    },
    'ROUT-001': {
        'descripcion': 'Sistema Mesh WiFi 6 tri-banda (2.4/5/6 GHz), 3 unidades, 5400 Mbps, 600m2 cobertura, puertos 2.5GbE+1GbE, WPA3, parental control, app movil, Roaming seamless.',
        'ficha_tecnica': 'Estándar: WiFi 6 (802.11ax) Tri-banda\nBandas: 2.4 GHz (574 Mbps) + 5 GHz (2402 Mbps) + 6 GHz (2402 Mbps)\nCobertura: Hasta 600 m² (3 nodos), expandible\nPuertos: 1x 2.5GbE WAN/LAN + 2x 1GbE LAN por nodo\nSeguridad: WPA3, WPA2, Guest network, VPN server/client\nControl parental: Perfiles, horarios, filtros contenido, pausa internet\nApp: Configuración, monitoreo, diagnosticos, actualizaciones OTA\nRoaming: 802.11k/v/r seamless roaming\nProcesador: Quad-core 1.5 GHz, 512MB RAM, 256MB Flash\nDimensiones: 110 x 110 x 90 mm c/u, 450g c/u',
        'social_quick': 'Mesh WiFi 6 Tri-banda 3 nodos - Cobertura total, velocidad extrema, control total. Tu casa, tu red. #Mesh #WiFi6 #TriBanda #Cobertura #Red #HogarInteligente',
        'social_cross': 'Tu hogar conectado: 4 Smartphones ($3000) | 2 Laptops ($1300) | Smart TV ($800) | Consola ($500). Hogar 100% conectado!'
    },
    'SWIT-001': {
        'descripcion': 'Switch no gestionable 16 puertos Gigabit, metal, silencioso, plug-play, auto-negotiation, auto-MDI/MDIX, 32Gbps fabric, 4MB buffer, 9K jumbo frames, metal rack-mountable.',
        'ficha_tecnica': 'Puertos: 16x RJ45 10/100/1000 Mbps\nEstándar: IEEE 802.3ab (1000Base-T), 802.3u (100Base-TX), 802.3i (10Base-T)\nVelocidad: 10/100/1000 Mbps auto-negotiation\nModo: Full/Half duplex auto-negotiation\nMDI/MDIX: Auto crossover\nSwitching capacity: 32 Gbps\nPacket buffer: 4 MB\nJumbo frames: 9 KB\nMAC address table: 8K entries\nConsumo: 12W max\nChasis: Metal, rack-mount 19" (brackets incluidos)\nDimensiones: 280 x 180 x 44 mm, 1.8 kg',
        'social_quick': 'Switch 16P Gigabit - Conectividad masiva, cero configuración, rendimiento puro. Red empresarial al alcance. #Switch #Gigabit #16Puertos #Red #Networking #Oficina',
        'social_cross': 'Tu red completa: 10 PCs ($5000) | 2 Impresoras ($560) | 3 APs ($450) | 4 Cámaras ($800). Infraestructura lista!'
    },
    'UPS-001': {
        'descripcion': 'UPS 1500VA/900W torre, onda senoidal pura, LCD, 8 tomas (4 bateria+4 surtidor), USB/Serial, 15min carga completa, 2 años garantía, silencioso.',
        'ficha_tecnica': 'Capacidad: 1500VA / 900W\nTopología: Line-interactive, onda senoidal pura\nBatería: 2x 12V 9Ah sellada, recarga 4-6h\nSalidas: 8 tomas (4 respaldo bateria + 4 solo surtidor)\nPantalla: LCD multifunción (carga, voltaje, frecuencia, tiempo)\nConectividad: USB + RS232, software PowerPanel\nProtección: Sobretensión, subcarga, sobrecarga, cortocircuito\nRuido: <40dB a 1m\nDimensiones: 149 x 369 x 227 mm, 18.5 kg\nGarantía: 2 años + $100k equipo conectado',
        'social_quick': 'UPS 1500VA Onda Senoidal - Protección total, energía limpia, tranquilidad absoluta. Tu inversión, a salvo. #UPS #OndaSenoidal #Protección #Energía #Seguridad',
        'social_cross': 'Tu protección total: PC Gaming ($2000) | NAS 4TB ($400) | Router Mesh ($285) | Monitor 27" ($420). Todo a salvo!'
    },
    'CARG-001': {
        'descripcion': 'Cargador portátil 20000mAh, 65W PD, 2x USB-C PD, 1x USB-A QC, pantalla LED, carga simultanea 3 dispositivos, 3h recarga, compacto.',
        'ficha_tecnica': 'Capacidad: 20000mAh / 74Wh\nSalidas: USB-C1 PD 65W (5V/3A, 9V/3A, 12V/3A, 15V/3A, 20V/3.25A), USB-C2 PD 30W, USB-A QC 18W\nEntrada: USB-C PD 65W (3h recarga completa)\nSalida simultanea: 3 dispositivos (65W+30W+18W max)\nPantalla: LED digital (%, voltaje, amperaje)\nProtección: Sobrecarga, sobredescarga, sobrecorriente, cortocircuito, temperatura\nDimensiones: 155 x 72 x 28 mm, 420g\nCertificaciones: CE, FCC, RoHS, UN38.3, PSE',
        'social_quick': 'Power Bank 20K 65W PD - Carga laptop, phone, tablet a la vez. Libertad total, sin enchufes. #PowerBank #PD65W #Movilidad #CargaRapida #Portatil',
        'social_cross': 'Tu kit movil: Laptop ($650) | Phone ($750) | Tablet ($520) | PowerBank 20K ($42). Oficina en la mochila!'
    },
    'ROUT-002': {
        'descripcion': 'Router WiFi 6 Mesh 2 Und, dual-banda (2.4/5 GHz), 3000 Mbps, 400m2 cobertura, puertos 1GbE, WPA3, parental control, app movil, Roaming seamless.',
        'ficha_tecnica': 'Estándar: WiFi 6 (802.11ax) Dual-banda\nBandas: 2.4 GHz (574 Mbps) + 5 GHz (2402 Mbps)\nCobertura: Hasta 400 m² (2 nodos), expandible\nPuertos: 1x 1GbE WAN/LAN + 3x 1GbE LAN por nodo\nSeguridad: WPA3, WPA2, Guest network, VPN server/client\nControl parental: Perfiles, horarios, filtros contenido, pausa internet\nApp: Configuración, monitoreo, diagnosticos, actualizaciones OTA\nRoaming: 802.11k/v/r seamless roaming\nProcesador: Dual-core 1.0 GHz, 256MB RAM, 128MB Flash\nDimensiones: 95 x 95 x 85 mm c/u, 350g c/u',
        'social_quick': 'Mesh WiFi 6 Dual-banda 2 nodos - Cobertura total, velocidad alta, control total. Tu casa, tu red. #Mesh #WiFi6 #DualBanda #Cobertura #Red #HogarInteligente',
        'social_cross': 'Tu hogar conectado: 4 Smartphones ($3000) | 2 Laptops ($1300) | Smart TV ($800) | Consola ($500). Hogar 100% conectado!'
    },
    'SWIT-002': {
        'descripcion': 'Switch no gestionable 8 puertos Gigabit, metal, silencioso, plug-play, auto-negotiation, auto-MDI/MDIX, 16Gbps fabric, 2MB buffer, 9K jumbo frames, metal rack-mountable.',
        'ficha_tecnica': 'Puertos: 8x RJ45 10/100/1000 Mbps\nEstándar: IEEE 802.3ab (1000Base-T), 802.3u (100Base-TX), 802.3i (10Base-T)\nVelocidad: 10/100/1000 Mbps auto-negotiation\nModo: Full/Half duplex auto-negotiation\nMDI/MDIX: Auto crossover\nSwitching capacity: 16 Gbps\nPacket buffer: 2 MB\nJumbo frames: 9 KB\nMAC address table: 4K entries\nConsumo: 6W max\nChasis: Metal, rack-mount 19" (brackets incluidos)\nDimensiones: 160 x 100 x 26 mm, 0.9 kg',
        'social_quick': 'Switch 8P Gigabit - Conectividad compacta, cero configuración, rendimiento puro. Red pequeña, rendimiento grande. #Switch #Gigabit #8Puertos #Red #Networking #Oficina',
        'social_cross': 'Tu red compacta: 5 PCs ($2500) | 1 Impresora ($280) | 2 APs ($300) | 2 Cámaras ($400). Infraestructura lista!'
    },
    'UPS-002': {
        'descripcion': 'UPS 850VA/510W torre, onda senoidal simulada, LCD, 6 tomas (3 bateria+3 surtidor), USB, 10min carga completa, 2 años garantía, silencioso.',
        'ficha_tecnica': 'Capacidad: 850VA / 510W\nTopología: Line-interactive, onda senoidal simulada\nBatería: 1x 12V 9Ah sellada, recarga 4-6h\nSalidas: 6 tomas (3 respaldo bateria + 3 solo surtidor)\nPantalla: LCD multifunción (carga, voltaje, frecuencia, tiempo)\nConectividad: USB, software PowerPanel\nProtección: Sobretensión, subcarga, sobrecarga, cortocircuito\nRuido: <40dB a 1m\nDimensiones: 100 x 287 x 142 mm, 7.5 kg\nGarantía: 2 años + $50k equipo conectado',
        'social_quick': 'UPS 850VA - Protección básica, energía estable, tranquilidad accesible. Tu inversión, a salvo. #UPS #Protección #Energía #Seguridad #Accesible',
        'social_cross': 'Tu protección básica: PC Oficina ($800) | Router Mesh ($285) | Monitor 24" ($180) | Impresora ($280). Todo a salvo!'
    },
    'SWIT-002': {
        'descripcion': 'Switch no gestionable 8 puertos Gigabit, metal, silencioso, plug-play, auto-negotiation, auto-MDI/MDIX, 16Gbps fabric, 2MB buffer, 9K jumbo frames, metal rack-mountable.',
        'ficha_tecnica': 'Puertos: 8x RJ45 10/100/1000 Mbps\nEstándar: IEEE 802.3ab (1000Base-T), 802.3u (100Base-TX), 802.3i (10Base-T)\nVelocidad: 10/100/1000 Mbps auto-negotiation\nModo: Full/Half duplex auto-negotiation\nMDI/MDIX: Auto crossover\nSwitching capacity: 16 Gbps\nPacket buffer: 2 MB\nJumbo frames: 9 KB\nMAC address table: 4K entries\nConsumo: 6W max\nChasis: Metal, rack-mount 19" (brackets incluidos)\nDimensiones: 160 x 100 x 26 mm, 0.9 kg',
        'social_quick': 'Switch 8P Gigabit - Conectividad compacta, cero configuración, rendimiento puro. Red pequeña, rendimiento grande. #Switch #Gigabit #8Puertos #Red #Networking #Oficina',
        'social_cross': 'Tu red compacta: 5 PCs ($2500) | 1 Impresora ($280) | 2 APs ($300) | 2 Cámaras ($400). Infraestructura lista!'
    },
    'UPS-002': {
        'descripcion': 'UPS 850VA/510W torre, onda senoidal simulada, LCD, 6 tomas (3 bateria+3 surtidor), USB, 10min carga completa, 2 años garantía, silencioso.',
        'ficha_tecnica': 'Capacidad: 850VA / 510W\nTopología: Line-interactive, onda senoidal simulada\nBatería: 1x 12V 9Ah sellada, recarga 4-6h\nSalidas: 6 tomas (3 respaldo bateria + 3 solo surtidor)\nPantalla: LCD multifunción (carga, voltaje, frecuencia, tiempo)\nConectividad: USB, software PowerPanel\nProtección: Sobretensión, subcarga, sobrecarga, cortocircuito\nRuido: <40dB a 1m\nDimensiones: 100 x 287 x 142 mm, 7.5 kg\nGarantía: 2 años + $50k equipo conectado',
        'social_quick': 'UPS 850VA - Protección básica, energía estable, tranquilidad accesible. Tu inversión, a salvo. #UPS #Protección #Energía #Seguridad #Accesible',
        'social_cross': 'Tu protección básica: PC Oficina ($800) | Router Mesh ($285) | Monitor 24" ($180) | Impresora ($280). Todo a salvo!'
    },
    'SWIT-002': {
        'descripcion': 'Switch no gestionable 8 puertos Gigabit, metal, silencioso, plug-play, auto-negotiation, auto-MDI/MDIX, 16Gbps fabric, 2MB buffer, 9K jumbo frames, metal rack-mountable.',
        'ficha_tecnica': 'Puertos: 8x RJ45 10/100/1000 Mbps\nEstándar: IEEE 802.3ab (1000Base-T), 802.3u (100Base-TX), 802.3i (10Base-T)\nVelocidad: 10/100/1000 Mbps auto-negotiation\nModo: Full/Half duplex auto-negotiation\nMDI/MDIX: Auto crossover\nSwitching capacity: 16 Gbps\nPacket buffer: 2 MB\nJumbo frames: 9 KB\nMAC address table: 4K entries\nConsumo: 6W max\nChasis: Metal, rack-mount 19" (brackets incluidos)\nDimensiones: 160 x 100 x 26 mm, 0.9 kg',
        'social_quick': 'Switch 8P Gigabit - Conectividad compacta, cero configuración, rendimiento puro. Red pequeña, rendimiento grande. #Switch #Gigabit #8Puertos #Red #Networking #Oficina',
        'social_cross': 'Tu red compacta: 5 PCs ($2500) | 1 Impresora ($280) | 2 APs ($300) | 2 Cámaras ($400). Infraestructura lista!'
    },
    'UPS-002': {
        'descripcion': 'UPS 850VA/510W torre, onda senoidal simulada, LCD, 6 tomas (3 bateria+3 surtidor), USB, 10min carga completa, 2 años garantía, silencioso.',
        'ficha_tecnica': 'Capacidad: 850VA / 510W\nTopología: Line-interactive, onda senoidal simulada\nBatería: 1x 12V 9Ah sellada, recarga 4-6h\nSalidas: 6 tomas (3 respaldo bateria + 3 solo surtidor)\nPantalla: LCD multifunción (carga, voltaje, frecuencia, tiempo)\nConectividad: USB, software PowerPanel\nProtección: Sobretensión, subcarga, sobrecarga, cortocircuito\nRuido: <40dB a 1m\nDimensiones: 100 x 287 x 142 mm, 7.5 kg\nGarantía: 2 años + $50k equipo conectado',
        'social_quick': 'UPS 850VA - Protección básica, energía estable, tranquilidad accesible. Tu inversión, a salvo. #UPS #Protección #Energía #Seguridad #Accesible',
        'social_cross': 'Tu protección básica: PC Oficina ($800) | Router Mesh ($285) | Monitor 24" ($180) | Impresora ($280). Todo a salvo!'
    },
    'SWIT-002': {
        'descripcion': 'Switch no gestionable 8 puertos Gigabit, metal, silencioso, plug-play, auto-negotiation, auto-MDI/MDIX, 16Gbps fabric, 2MB buffer, 9K jumbo frames, metal rack-mountable.',
        'ficha_tecnica': 'Puertos: 8x RJ45 10/100/1000 Mbps\nEstándar: IEEE 802.3ab (1000Base-T), 802.3u (100Base-TX), 802.3i (10Base-T)\nVelocidad: 10/100/1000 Mbps auto-negotiation\nModo: Full/Half duplex auto-negotiation\nMDI/MDIX: Auto crossover\nSwitching capacity: 16 Gbps\nPacket buffer: 2 MB\nJumbo frames: 9 KB\nMAC address table: 4K entries\nConsumo: 6W max\nChasis: Metal, rack-mount 19" (brackets incluidos)\nDimensiones: 160 x 100 x 26 mm, 0.9 kg',
        'social_quick': 'Switch 8P Gigabit - Conectividad compacta, cero configuración, rendimiento puro. Red pequeña, rendimiento grande. #Switch #Gigabit #8Puertos #Red #Networking #Oficina',
        'social_cross': 'Tu red compacta: 5 PCs ($2500) | 1 Impresora ($280) | 2 APs ($300) | 2 Cámaras ($400). Infraestructura lista!'
    },
    'UPS-002': {
        'descripcion': 'UPS 850VA/510W torre, onda senoidal simulada, LCD, 6 tomas (3 bateria+3 surtidor), USB, 10min carga completa, 2 años garantía, silencioso.',
        'ficha_tecnica': 'Capacidad: 850VA / 510W\nTopología: Line-interactive, onda senoidal simulada\nBatería: 1x 12V 9Ah sellada, recarga 4-6h\nSalidas: 6 tomas (3 respaldo bateria + 3 solo surtidor)\nPantalla: LCD multifunción (carga, voltaje, frecuencia, tiempo)\nConectividad: USB, software PowerPanel\nProtección: Sobretensión, subcarga, sobrecarga, cortocircuito\nRuido: <40dB a 1m\nDimensiones: 100 x 287 x 142 mm, 7.5 kg\nGarantía: 2 años + $50k equipo conectado',
        'social_quick': 'UPS 850VA - Protección básica, energía estable, tranquilidad accesible. Tu inversión, a salvo. #UPS #Protección #Energía #Seguridad #Accesible',
        'social_cross': 'Tu protección básica: PC Oficina ($800) | Router Mesh ($285) | Monitor 24" ($180) | Impresora ($280). Todo a salvo!'
    },
    'SWIT-002': {
        'descripcion': 'Switch no gestionable 8 puertos Gigabit, metal, silencioso, plug-play, auto-negotiation, auto-MDI/MDIX, 16Gbps fabric, 2MB buffer, 9K jumbo frames, metal rack-mountable.',
        'ficha_tecnica': 'Puertos: 8x RJ45 10/100/1000 Mbps\nEstándar: IEEE 802.3ab (1000Base-T), 802.3u (100Base-TX), 802.3i (10Base-T)\nVelocidad: 10/100/1000 Mbps auto-negotiation\nModo: Full/Half duplex auto-negotiation\nMDI/MDIX: Auto crossover\nSwitching capacity: 16 Gbps\nPacket buffer: 2 MB\nJumbo frames: 9 KB\nMAC address table: 4K entries\nConsumo: 6W max\nChasis: Metal, rack-mount 19" (brackets incluidos)\nDimensiones: 160 x 100 x 26 mm, 0.9 kg',
        'social_quick': 'Switch 8P Gigabit - Conectividad compacta, cero configuración, rendimiento puro. Red pequeña, rendimiento grande. #Switch #Gigabit #8Puertos #Red #Networking #Oficina',
        'social_cross': 'Tu red compacta: 5 PCs ($2500) | 1 Impresora ($280) | 2 APs ($300) | 2 Cámaras ($400). Infraestructura lista!'
    },
}

eid = 34
for sku, data in articulos_con_data.items():
    art = Articulo.global_objects.filter(empresa_id=eid, sku=sku).first()
    if art:
        art.descripcion = data['descripcion']
        art.ficha_tecnica = data['ficha_tecnica']
        art.social_quick = data['social_quick']
        art.social_cross = data['social_cross']
        art.save(update_fields=['descripcion', 'ficha_tecnica', 'social_quick', 'social_cross'])
        print(f'Updated {sku}')
    else:
        print(f'NOT FOUND: {sku}')

print('Done!')