"""Qué significa cada cosa que anuncia un aparato, en cristiano.

Los aparatos anuncian servicios por mDNS/Bonjour ("_ipp._tcp" = soy una impresora) y
escuchan en puertos conocidos (62078 = iPhone o iPad). Aquí está la traducción de los más
habituales en una casa, y qué tipo de aparato sugiere cada uno.
"""

from __future__ import annotations

# Tipos de aparato. El orden es el de la tabla cuando hay empate.
ROUTER = "Router"
MOBILE = "Móvil"
TABLET = "Tableta"
COMPUTER = "Ordenador"
TV = "Televisor"
STREAMER = "Reproductor multimedia"
SPEAKER = "Altavoz"
PRINTER = "Impresora"
CAMERA = "Cámara"
CONSOLE = "Consola"
NAS = "Disco en red (NAS)"
SMART_HOME = "Domótica"
WATCH = "Reloj"
ACCESS_POINT = "Repetidor o punto de acceso"
VACUUM = "Robot aspirador"
APPLIANCE = "Electrodoméstico"
SERVER = "Servidor"
VM = "Máquina virtual"
UNKNOWN = "Desconocido"

KINDS = [
    ROUTER,
    MOBILE,
    TABLET,
    COMPUTER,
    TV,
    STREAMER,
    SPEAKER,
    PRINTER,
    CAMERA,
    CONSOLE,
    NAS,
    SMART_HOME,
    WATCH,
    ACCESS_POINT,
    VACUUM,
    APPLIANCE,
    SERVER,
    VM,
]

# Para los resúmenes: «1 móvil», «3 móviles».
NAMES = {
    ROUTER: ("router", "routers"),
    MOBILE: ("móvil", "móviles"),
    TABLET: ("tableta", "tabletas"),
    COMPUTER: ("ordenador", "ordenadores"),
    TV: ("televisor", "televisores"),
    STREAMER: ("reproductor multimedia", "reproductores multimedia"),
    SPEAKER: ("altavoz", "altavoces"),
    PRINTER: ("impresora", "impresoras"),
    CAMERA: ("cámara", "cámaras"),
    CONSOLE: ("consola", "consolas"),
    NAS: ("disco en red", "discos en red"),
    SMART_HOME: ("aparato de domótica", "aparatos de domótica"),
    WATCH: ("reloj", "relojes"),
    ACCESS_POINT: ("repetidor", "repetidores"),
    VACUUM: ("robot aspirador", "robots aspiradores"),
    APPLIANCE: ("electrodoméstico", "electrodomésticos"),
    SERVER: ("servidor", "servidores"),
    VM: ("máquina virtual", "máquinas virtuales"),
    UNKNOWN: ("sin identificar", "sin identificar"),
}

# mDNS: tipo de servicio → (qué es, tipo de aparato que sugiere o None, peso)
SERVICES: dict[str, tuple[str, str | None, int]] = {
    "_airplay._tcp": ("AirPlay: se le puede mandar vídeo o la pantalla desde un aparato de Apple", None, 0),
    "_raop._tcp": ("AirPlay: se le puede mandar música", None, 0),
    "_googlecast._tcp": ("Google Cast (Chromecast): se le puede mandar vídeo o música", STREAMER, 40),
    "_googlezone._tcp": ("Grupo de altavoces de Google", None, 0),
    "_androidtvremote2._tcp": ("Android TV / Google TV (se maneja desde el móvil)", TV, 40),
    "_amzn-wplay._tcp": ("Fire TV de Amazon", STREAMER, 50),
    "_amzn-alexa._tcp": ("Alexa", SPEAKER, 40),
    "_spotify-connect._tcp": ("Spotify Connect: se puede poner música en él desde Spotify", None, 0),
    "_sonos._tcp": ("Sonos", SPEAKER, 60),
    "_mediaremotetv._tcp": ("Apple TV (mando desde el iPhone)", STREAMER, 60),
    "_touch-able._tcp": ("Apple TV o iTunes (mando a distancia)", STREAMER, 30),
    "_daap._tcp": ("Biblioteca de música compartida (iTunes / Música)", COMPUTER, 20),
    "_ipp._tcp": ("Impresora (IPP)", PRINTER, 70),
    "_ipps._tcp": ("Impresora (IPP cifrado)", PRINTER, 70),
    "_printer._tcp": ("Impresora (LPD)", PRINTER, 70),
    "_pdl-datastream._tcp": ("Impresora (puerto 9100)", PRINTER, 70),
    "_uscan._tcp": ("Escáner (eSCL / AirScan)", PRINTER, 50),
    "_uscans._tcp": ("Escáner (eSCL cifrado)", PRINTER, 50),
    "_scanner._tcp": ("Escáner", PRINTER, 50),
    "_privet._tcp": ("Impresora de Google Cloud Print", PRINTER, 50),
    "_hap._tcp": ("Accesorio de HomeKit (casa de Apple)", SMART_HOME, 50),
    "_hap._udp": ("Accesorio de HomeKit por Thread", SMART_HOME, 50),
    "_homekit._tcp": ("HomeKit", None, 0),
    "_matter._tcp": ("Matter (domótica)", SMART_HOME, 40),
    "_matterc._udp": ("Matter, esperando a que lo configures", SMART_HOME, 40),
    "_meshcop._udp": ("Router de borde Thread (domótica)", None, 0),
    "_hue._tcp": ("Philips Hue (luces)", SMART_HOME, 60),
    "_esphomelib._tcp": ("ESPHome (aparato de domótica casero)", SMART_HOME, 60),
    "_home-assistant._tcp": ("Home Assistant (centro de domótica)", COMPUTER, 40),
    "_shelly._tcp": ("Shelly (relé o enchufe inteligente)", SMART_HOME, 60),
    "_miio._udp": ("Xiaomi Mi Home", SMART_HOME, 50),
    "_nanoleafapi._tcp": ("Nanoleaf (luces)", SMART_HOME, 60),
    "_wled._tcp": ("WLED (tira de LED)", SMART_HOME, 60),
    "_mqtt._tcp": ("MQTT (mensajería de domótica)", None, 0),
    "_axis-video._tcp": ("Cámara de vídeo", CAMERA, 60),
    "_companion-link._tcp": ("Aparato de Apple (Continuidad: Handoff, AirDrop…)", None, 0),
    "_apple-mobdev2._tcp": ("iPhone o iPad (sincronización por wifi)", MOBILE, 40),
    "_remotepairing._tcp": ("iPhone o iPad (emparejamiento con el Mac)", MOBILE, 30),
    "_rdlink._tcp": ("Aparato de Apple (Continuidad)", None, 0),
    "_sleep-proxy._udp": ("Bonjour Sleep Proxy (despierta a los Mac dormidos)", None, 0),
    "_airport._tcp": ("AirPort de Apple", ACCESS_POINT, 60),
    "_adisk._tcp": ("Disco para copias de Time Machine", NAS, 30),
    "_afpovertcp._tcp": ("Carpetas compartidas de Mac (AFP)", None, 0),
    "_smb._tcp": ("Carpetas compartidas (SMB)", None, 0),
    "_workstation._tcp": ("Ordenador (lo anuncia Linux)", COMPUTER, 40),
    "_device-info._tcp": ("Información del aparato", None, 0),
    "_ssh._tcp": ("SSH: se puede entrar a su terminal", None, 0),
    "_sftp-ssh._tcp": ("SFTP: pasar archivos por SSH", None, 0),
    "_rfb._tcp": ("Pantalla compartida (VNC)", COMPUTER, 30),
    "_http._tcp": ("Tiene página web", None, 0),
    "_https._tcp": ("Tiene página web segura", None, 0),
    "_plexmediasvr._tcp": ("Servidor de Plex (películas y series)", None, 0),
    "_octoprint._tcp": ("OctoPrint (impresora 3D)", None, 0),
    "_nvstream._tcp": ("NVIDIA GameStream (juegos en streaming)", COMPUTER, 30),
    "_elg._tcp": ("Elgato", SMART_HOME, 30),
    "_ewelink._tcp": ("Sonoff / eWeLink (enchufe o relé)", SMART_HOME, 60),
    "_dyson_mqtt._tcp": ("Dyson (ventilador o purificador)", SMART_HOME, 60),
    "_xbmc-jsonrpc._tcp": ("Kodi (centro multimedia)", STREAMER, 45),
    "_xbmc-jsonrpc-h._tcp": ("Kodi (centro multimedia)", STREAMER, 45),
    "_rtsp._tcp": ("Emite vídeo en directo (RTSP)", CAMERA, 40),
    "_ptp._tcp": ("Cámara de fotos (pasar fotos por wifi)", CAMERA, 30),
    "_kdeconnect._udp": ("KDE Connect (móvil y ordenador enlazados)", None, 0),
}

# Los que se preguntan directamente a todos: hay aparatos que no contestan a "¿qué
# servicios tienes?" pero sí a "¿quién es una impresora?".
ASK_DIRECTLY = [
    "_googlecast._tcp",
    "_airplay._tcp",
    "_raop._tcp",
    "_ipp._tcp",
    "_printer._tcp",
    "_pdl-datastream._tcp",
    "_hap._tcp",
    "_companion-link._tcp",
    "_apple-mobdev2._tcp",
    "_spotify-connect._tcp",
    "_sonos._tcp",
    "_amzn-wplay._tcp",
    "_androidtvremote2._tcp",
    "_smb._tcp",
    "_workstation._tcp",
    "_hue._tcp",
    "_esphomelib._tcp",
    "_matter._tcp",
    "_home-assistant._tcp",
    "_shelly._tcp",
    "_uscan._tcp",
    "_ssh._tcp",
]

# Puertos TCP que se prueban en cada aparato: pocos y conocidos, los que dicen qué es.
# puerto → (nombre, qué quiere decir, tipo que sugiere o None, peso)
PORTS: dict[int, tuple[str, str, str | None, int]] = {
    21: ("FTP", "pasar archivos (sin cifrar)", None, 0),
    22: ("SSH", "entrar a su terminal a distancia", None, 0),
    23: ("Telnet", "entrar a su terminal sin cifrar", None, 0),
    53: ("DNS", "traduce nombres de webs; lo suele tener el router", ROUTER, 30),
    80: ("HTTP", "página web (de configuración, normalmente)", None, 0),
    139: ("NetBIOS", "red de Windows (antigua)", COMPUTER, 15),
    443: ("HTTPS", "página web segura", None, 0),
    445: ("SMB", "carpetas compartidas de Windows", COMPUTER, 20),
    548: ("AFP", "carpetas compartidas de Mac", None, 0),
    554: ("RTSP", "emite vídeo en directo", CAMERA, 40),
    631: ("IPP", "impresora", PRINTER, 50),
    1883: ("MQTT", "mensajería de domótica (sin cifrar)", None, 0),
    3389: ("Escritorio remoto", "manejar este Windows a distancia", COMPUTER, 40),
    5000: ("UPnP / Synology", "panel de un NAS Synology o servicio UPnP", None, 0),
    5001: ("Synology (HTTPS)", "panel de un NAS Synology", NAS, 30),
    5900: ("VNC", "ver y manejar la pantalla a distancia", None, 0),
    7000: ("AirPlay", "recibe vídeo o música de aparatos de Apple", None, 0),
    8008: ("Google Cast", "Chromecast o algo con Google Cast", STREAMER, 30),
    8009: ("Google Cast", "Chromecast o algo con Google Cast", STREAMER, 30),
    8080: ("HTTP alternativo", "otra página web", None, 0),
    8123: ("Home Assistant", "centro de domótica", COMPUTER, 30),
    8443: ("HTTPS alternativo", "otra página web segura", None, 0),
    9100: ("Impresión directa", "impresora (JetDirect)", PRINTER, 50),
    32400: ("Plex", "servidor de películas y series", None, 0),
    62078: ("iPhone / iPad", "sincronización de un iPhone o iPad", MOBILE, 50),
    515: ("LPD", "impresora (protocolo antiguo)", PRINTER, 40),
    902: ("VMware ESXi", "servidor de máquinas virtuales de VMware", SERVER, 50),
    1400: ("Sonos", "altavoz Sonos", SPEAKER, 50),
    3306: ("MySQL", "base de datos", None, 0),
    5432: ("PostgreSQL", "base de datos", None, 0),
    5555: ("ADB", "depuración de Android por red", None, 0),
    6379: ("Redis", "base de datos en memoria", None, 0),
    6668: ("Tuya", "enchufe o bombilla de Tuya (Smart Life)", SMART_HOME, 50),
    8006: ("Proxmox", "servidor de máquinas virtuales Proxmox", SERVER, 60),
    8060: ("Roku", "reproductor Roku (control por red)", STREAMER, 50),
    9999: ("TP-Link Kasa", "enchufe o bombilla Kasa de TP-Link", SMART_HOME, 50),
    27017: ("MongoDB", "base de datos", None, 0),
    34567: ("XMEye", "grabador o cámara china barata (DVR/NVR)", CAMERA, 60),
    37777: ("Dahua", "cámara o grabador Dahua", CAMERA, 60),
}

# Marcas (tal como salen de oui.short_vendor) y qué suelen ser. Peso bajo: una marca hace
# muchas cosas (Samsung hace móviles, teles y lavadoras).
VENDOR_HINTS: dict[str, tuple[str, int]] = {
    "Samsung": (MOBILE, 15),
    "Huawei": (MOBILE, 15),
    "Honor": (MOBILE, 25),
    "Xiaomi": (MOBILE, 15),
    "OPPO": (MOBILE, 25),
    "vivo": (MOBILE, 25),
    "OnePlus": (MOBILE, 25),
    "realme": (MOBILE, 25),
    "Motorola": (MOBILE, 25),
    "Nothing": (MOBILE, 25),
    "Fairphone": (MOBILE, 25),
    "Raspberry Pi": (COMPUTER, 30),
    "Sagemcom": (ROUTER, 20),
    "Askey": (ROUTER, 20),
    "MitraStar": (ROUTER, 20),
    "Arcadyan": (ROUTER, 20),
    "Sercomm": (ROUTER, 20),
    "Comtrend": (ROUTER, 20),
    "FiberHome": (ROUTER, 20),
    "ZTE": (ROUTER, 15),
    "AVM (FRITZ!Box)": (ROUTER, 25),
    "Zyxel": (ROUTER, 20),
    "Netgear": (ACCESS_POINT, 15),
    "D-Link": (ACCESS_POINT, 15),
    "Ubiquiti": (ACCESS_POINT, 25),
    "eero": (ACCESS_POINT, 30),
    "TP-Link": (ACCESS_POINT, 10),
    "Epson": (PRINTER, 35),
    "Canon": (PRINTER, 30),
    "Brother": (PRINTER, 40),
    "HP": (PRINTER, 15),
    "Sony PlayStation": (CONSOLE, 50),
    "Nintendo": (CONSOLE, 50),
    "Roku": (STREAMER, 50),
    "Sonos": (SPEAKER, 50),
    "Amazon": (SPEAKER, 20),
    "Google Nest": (SMART_HOME, 30),
    "Philips Hue": (SMART_HOME, 50),
    "Synology": (NAS, 50),
    "QNAP": (NAS, 50),
    "Hikvision": (CAMERA, 45),
    "EZVIZ": (CAMERA, 45),
    "Reolink": (CAMERA, 45),
    "Wyze": (CAMERA, 35),
    "Espressif": (SMART_HOME, 30),
    "Tuya": (SMART_HOME, 40),
    "Meross": (SMART_HOME, 40),
    "Silicon Labs": (SMART_HOME, 20),
    "Hisense": (TV, 30),
    "TCL": (TV, 25),
    "LG": (TV, 15),
    "Sony": (TV, 15),
    "Garmin": (WATCH, 25),
    "Fitbit": (WATCH, 30),
    "Withings": (SMART_HOME, 25),
    "Dyson": (SMART_HOME, 40),
    "Dell": (COMPUTER, 30),
    "Lenovo": (COMPUTER, 20),
    "Microsoft": (COMPUTER, 15),
    "Intel": (COMPUTER, 25),
    "Roborock": (VACUUM, 60),
    "iRobot": (VACUUM, 60),
    "Ecovacs": (VACUUM, 60),
    "Dreame": (VACUUM, 60),
    "Bosch-Siemens": (APPLIANCE, 60),
    "Miele": (APPLIANCE, 60),
    "Whirlpool": (APPLIANCE, 50),
    "Haier": (APPLIANCE, 35),
    "Daikin": (APPLIANCE, 50),
    "Valve": (CONSOLE, 40),
    "Vestel": (TV, 40),
    "Philips TV": (TV, 50),
    "Bose": (SPEAKER, 45),
    "Dahua": (CAMERA, 45),
    "Ring": (CAMERA, 45),
    "ecobee": (SMART_HOME, 50),
}

# Fabricantes del chip de wifi, no del aparato: la marca de verdad es otra.
CHIPMAKERS = {
    "Espressif",
    "Tuya",
    "Murata",
    "AzureWave",
    "Realtek",
    "USI",
    "Fugui",
    "Foxconn",
    "Lite-On",
    "Compal",
    "Wistron",
    "Quanta",
    "Pegatron",
    "Chicony",
    "Texas Instruments",
    "Silicon Labs",
    "Intel",
}

# Pistas en el nombre que el propio aparato se pone ("iPhone-de-Ana", "Galaxy-S23", "BRW…").
# (expresión regular, tipo, peso)
NAME_HINTS: list[tuple[str, str, int]] = [
    (r"iphone", MOBILE, 60),
    (r"ipad", TABLET, 60),
    (r"\bwatch\b|apple-?watch|galaxy-?watch", WATCH, 50),
    (
        r"android|galaxy|redmi|\bpoco|pixel|oneplus|\boppo|\bvivo|realme|huawei-?[pm]|honor|moto[- ]?[geg]|xiaomi|"
        r"\bmi-?\d|nothing-?phone",
        MOBILE,
        45,
    ),
    (r"\btab\b|tablet|galaxy-?tab|mipad|lenovo-?tab", TABLET, 50),
    (r"macbook|laptop|portatil|notebook|thinkpad|ideapad|vivobook|zenbook|surface", COMPUTER, 45),
    (r"desktop-|imac|mac-?mini|\bpc\b|-pc\b|^pc-|ordenador|workstation", COMPUTER, 40),
    (r"raspberry|raspberrypi|\brpi\b", COMPUTER, 40),
    (r"chromecast", STREAMER, 60),
    (r"apple-?tv|appletv|fire-?tv|firetv|roku|mibox|shield", STREAMER, 50),
    (r"\btv\b|-tv\b|^tv-|bravia|lgwebos|webos|tizen|samsung-?tv|smart-?tv|android-?tv", TV, 45),
    (r"\becho\b|alexa|google-?home|nest-?(mini|audio|hub)|homepod|sonos", SPEAKER, 50),
    (r"\bps[345]\b|playstation|xbox|nintendo|switch", CONSOLE, 50),
    (r"printer|impresora|laserjet|deskjet|officejet|envy|epson|^brw|^brn|canon|mf\d{3}", PRINTER, 50),
    (r"camera|camara|cam-|ipcam|ezviz|reolink|tapo-?c\d|hikvision|ring-", CAMERA, 45),
    (r"\bnas\b|synology|diskstation|qnap", NAS, 50),
    (
        r"esp[_-]|esp32|esp8266|tasmota|shelly|sonoff|tuya|smart-?plug|enchufe|bombilla|bulb|meross|wled|"
        r"tapo-?p\d|kasa|hue-?bridge|philips-hue",
        SMART_HOME,
        45,
    ),
    (r"repeater|repetidor|extender|mesh|deco-|eero|\bap\b", ACCESS_POINT, 40),
    (r"roborock|roomba|irobot|ecovacs|deebot|dreame|conga|aspirador|vacuum|rockrobo|viomi", VACUUM, 55),
    (
        r"lavadora|lavavajillas|secadora|frigor[ií]fico|nevera|horno|microondas|washer|dryer|dishwasher|fridge|"
        r"\boven\b|aire-?acondicionado|\bclima\b|thinq|home-?connect|bsh-|miele",
        APPLIANCE,
        50,
    ),
    (r"proxmox|\bpve\b|esxi|truenas-?scale|unraid|\bsrv\b|^srv-|servidor|server", SERVER, 40),
    (r"steam-?deck|steamdeck", CONSOLE, 55),
    (r"kindle|kobo|e-?reader", TABLET, 50),
    (r"philips-?tv|androidtv|google-?tv|hisense|vidaa", TV, 40),
]


# Pistas en la página de configuración (el <title> y la cabecera Server). Más corta que
# NAME_HINTS a propósito: en un título salen palabras como «switch» o «mesh» que no dicen
# nada del aparato, así que solo van marcas y productos que se reconocen sin dudas.
WEB_HINTS: list[tuple[str, str, int]] = [
    (r"laserjet|deskjet|officejet|envy|epson|brother|canon|\bprinter\b|impresora", PRINTER, 45),
    (r"hikvision|reolink|ezviz|dahua|ipcam|network camera|webcam|foscam", CAMERA, 45),
    (r"synology|diskstation|qnap|truenas|openmediavault|unraid", NAS, 45),
    (r"tasmota|shelly|wled|esphome|home assistant|sonoff", SMART_HOME, 45),
    (r"fritz!?box|livebox|router|openwrt|dd-wrt|pfsense|opnsense|mikrotik|routeros", ROUTER, 40),
    (r"repeater|repetidor|range extender", ACCESS_POINT, 40),
    (r"proxmox|vmware esxi|cockpit|webmin|portainer", SERVER, 45),
]

# MAC que ponen los programas de máquinas virtuales a sus máquinas. La de QEMU/KVM
# (52:54:00) está marcada como «administrada localmente», igual que las privadas de los
# móviles, pero no es de un móvil.
VM_PREFIXES = {
    "00:50:56": "VMware",
    "00:0C:29": "VMware",
    "00:05:69": "VMware",
    "08:00:27": "VirtualBox",
    "52:54:00": "QEMU/KVM",
    "00:15:5D": "Hyper-V",
    "00:1C:42": "Parallels",
    "00:16:3E": "Xen",
}
