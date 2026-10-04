"""Cada aparato: todo lo que se ha averiguado de él, junto, y qué es probablemente.

Las pistas llegan sueltas (la MAC dice "Apple", mDNS dice "iPhone-de-Ana", el puerto
62078 dice "iPhone o iPad") y aquí se juntan. El tipo se decide sumando pistas, y se
guarda el porqué: lan-radar dice "Móvil, porque…", no solo "Móvil".
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from . import catalog
from .catalog import (
    CAMERA,
    COMPUTER,
    MOBILE,
    NAS,
    PRINTER,
    ROUTER,
    SMART_HOME,
    SPEAKER,
    STREAMER,
    TABLET,
    TV,
    UNKNOWN,
    WATCH,
)
from .oui import is_device, is_random, normalize, short_vendor
from .oui import vendor as oui_vendor

ALTA, MEDIA, INFO, NUEVO = "alta", "media", "info", "nuevo"


@dataclass
class Device:
    ip: str
    mac: str = ""
    vendor: str = ""  # el fabricante de la tarjeta de red, tal como está en el registro
    brand: str = ""  # el mismo, abreviado: «Apple», «TP-Link»
    random_mac: bool = False
    shared_mac: bool = False  # otra IP tiene la misma MAC (un repetidor que contesta por otros)
    is_self: bool = False
    is_gateway: bool = False
    dns_name: str = ""  # el que le da el DNS del router: «Galaxy-S23.home»
    mdns_name: str = ""  # el que se pone él mismo: «iPhone-de-Ana.local»
    netbios_name: str = ""  # el de Windows: «PORTATIL-ANA»
    workgroup: str = ""
    friendly_name: str = ""  # el que le pusiste al configurarlo: «Salón», «Tele del cuarto»
    manufacturer: str = ""  # la marca según el propio aparato
    model: str = ""
    model_id: str = ""  # el identificador interno de Apple: «iPhone15,2»
    os: str = ""
    services: list[dict] = field(default_factory=list)  # mDNS: tipo, nombre, puerto, detalles
    upnp: list[dict] = field(default_factory=list)  # las fichas UPnP
    upnp_server: str = ""
    upnp_targets: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    banners: dict[str, str] = field(default_factory=dict)  # puerto → saludo
    web: dict[str, dict] = field(default_factory=dict)  # puerto → título, servidor…
    kind: str = UNKNOWN
    confidence: str = ""  # «seguro», «probable», «puede»
    reasons: list[str] = field(default_factory=list)
    notes: list[dict] = field(default_factory=list)  # {"level": alta/media/info/nuevo, "text": …}
    # Del historial
    nickname: str = ""  # el que le pones tú en lan-radar
    first_seen: str = ""
    last_seen: str = ""
    is_new: bool = False

    def key(self) -> str:
        """Cómo se reconoce de una vez a otra: por su MAC (la IP la reparte el router y
        cambia). Si la MAC la comparten varios, por las dos cosas."""
        if self.mac and self.shared_mac:
            return f"{self.mac}@{self.ip}"
        return self.mac or f"ip:{self.ip}"

    def name(self) -> str:
        """El nombre más humano que se tenga."""
        for candidate in (
            self.nickname,
            self.friendly_name,
            _label(self.mdns_name),
            self.netbios_name,
            _label(self.dns_name),
            self.model,
        ):
            if candidate:
                return candidate
        if self.brand and self.kind != UNKNOWN:
            return f"{self.kind} {self.brand}"
        return self.brand or "Sin nombre"

    def kind_label(self) -> str:
        if self.kind == UNKNOWN or self.confidence in ("", "seguro"):
            return self.kind
        return f"{self.kind} ({self.confidence})"

    def to_dict(self) -> dict:
        return asdict(self)


def _label(hostname: str) -> str:
    """«galaxy-s23.home» → «galaxy-s23»; «iPhone-de-Ana.local» → «iPhone-de-Ana»"""
    return hostname.split(".")[0] if hostname else ""


# Modelos de Apple: el identificador interno («iPhone15,2») dice la familia, y de los
# iPhone recientes, el nombre comercial (los publica Apple en su soporte técnico).
APPLE_FAMILIES = [
    ("iPhone", "iPhone", MOBILE, "iOS"),
    ("iPad", "iPad", TABLET, "iPadOS"),
    ("iPod", "iPod touch", MOBILE, "iOS"),
    ("MacBookPro", "MacBook Pro", COMPUTER, "macOS"),
    ("MacBookAir", "MacBook Air", COMPUTER, "macOS"),
    ("MacBook", "MacBook", COMPUTER, "macOS"),
    ("iMac", "iMac", COMPUTER, "macOS"),
    ("Macmini", "Mac mini", COMPUTER, "macOS"),
    ("MacPro", "Mac Pro", COMPUTER, "macOS"),
    ("Mac", "Mac", COMPUTER, "macOS"),
    ("AppleTV", "Apple TV", STREAMER, "tvOS"),
    ("AudioAccessory", "HomePod", SPEAKER, "audioOS"),
    ("Watch", "Apple Watch", WATCH, "watchOS"),
]
IPHONES = {
    "iPhone12,1": "iPhone 11",
    "iPhone12,3": "iPhone 11 Pro",
    "iPhone12,5": "iPhone 11 Pro Max",
    "iPhone12,8": "iPhone SE (2.ª generación)",
    "iPhone13,1": "iPhone 12 mini",
    "iPhone13,2": "iPhone 12",
    "iPhone13,3": "iPhone 12 Pro",
    "iPhone13,4": "iPhone 12 Pro Max",
    "iPhone14,4": "iPhone 13 mini",
    "iPhone14,5": "iPhone 13",
    "iPhone14,2": "iPhone 13 Pro",
    "iPhone14,3": "iPhone 13 Pro Max",
    "iPhone14,6": "iPhone SE (3.ª generación)",
    "iPhone14,7": "iPhone 14",
    "iPhone14,8": "iPhone 14 Plus",
    "iPhone15,2": "iPhone 14 Pro",
    "iPhone15,3": "iPhone 14 Pro Max",
    "iPhone15,4": "iPhone 15",
    "iPhone15,5": "iPhone 15 Plus",
    "iPhone16,1": "iPhone 15 Pro",
    "iPhone16,2": "iPhone 15 Pro Max",
    "iPhone17,3": "iPhone 16",
    "iPhone17,4": "iPhone 16 Plus",
    "iPhone17,1": "iPhone 16 Pro",
    "iPhone17,2": "iPhone 16 Pro Max",
    "iPhone17,5": "iPhone 16e",
}
_APPLE_ID = re.compile(r"^([A-Za-z]+)(\d+,\d+)$")

# Accesorios de HomeKit: el campo «ci» dice la categoría (HAP, tabla 12-3).
HOMEKIT_CATEGORIES = {
    "2": "puente de domótica",
    "5": "bombilla",
    "7": "enchufe",
    "8": "interruptor",
    "9": "termostato",
    "10": "sensor",
    "11": "alarma",
    "12": "puerta",
    "14": "persiana",
    "16": "repetidor",
    "17": "cámara",
    "18": "timbre con cámara",
    "19": "purificador de aire",
    "31": "televisor",
}

# Nombres de servicio que son identificadores y no nombres: «Chromecast-1a2b3c…»
_ID_LIKE = re.compile(r"[0-9a-f]{12,}|[0-9a-f]{8}-[0-9a-f]{4}-", re.I)
_MAC_IN_NAME = re.compile(r"\[([0-9a-f]{2}(?::[0-9a-f]{2}){5})\]", re.I)


def apple_model(identifier: str) -> tuple[str, str | None, str]:
    """«iPhone15,2» → («iPhone 14 Pro (iPhone15,2)», MOBILE, «iOS»)."""
    m = _APPLE_ID.match(identifier.strip())
    if not m:
        return "", None, ""
    for prefix, family, kind, os_name in APPLE_FAMILIES:
        if m.group(1) == prefix:
            pretty = IPHONES.get(identifier, family)
            return f"{pretty} ({identifier})", kind, os_name
    return "", None, ""


def os_from_banner(text: str) -> str:
    """Saludo SSH → sistema: «SSH-2.0-OpenSSH_9.2p1 Debian-2+deb12u3» → «Debian»."""
    low = text.lower()
    for word, name in (
        ("raspbian", "Raspberry Pi OS"),
        ("ubuntu", "Ubuntu"),
        ("debian", "Debian"),
        ("freebsd", "FreeBSD"),
        ("for_windows", "Windows"),
        ("dropbear", "Linux (aparato pequeño)"),
    ):
        if word in low:
            return name
    return ""


def os_from_server(header: str) -> str:
    """Cabecera SERVER de UPnP («Linux/4.9 UPnP/1.0 …») → «Linux 4.9»."""
    first = header.replace(",", " ").split()[0] if header.split() else ""
    name, slash, version = first.partition("/")
    if not slash or not name or name.upper() == "UPNP":
        return ""
    pretty = {"microsoft-windows": "Windows", "darwin": "macOS (Darwin)", "webos": "webOS", "tizen": "Tizen"}
    name = pretty.get(name.lower(), name.replace("_", " "))
    return f"{name} {version}".strip() if version and len(version) < 20 else name


class Evidence:
    """Las pistas sobre el tipo: cada una suma puntos a un tipo y deja su porqué."""

    def __init__(self):
        self.points: dict[str, int] = {}
        self.why: dict[str, list[str]] = {}

    def add(self, kind: str | None, weight: int, reason: str) -> None:
        if not kind or weight <= 0:
            return
        self.points[kind] = self.points.get(kind, 0) + weight
        if reason not in self.why.setdefault(kind, []):
            self.why[kind].append(reason)

    def decide(self) -> tuple[str, str, list[str]]:
        if not self.points:
            return UNKNOWN, "", []
        order = {k: i for i, k in enumerate(catalog.KINDS)}
        kind = max(self.points, key=lambda k: (self.points[k], -order.get(k, 99)))
        score = self.points[kind]
        confidence = "seguro" if score >= 60 else "probable" if score >= 30 else "puede"
        return kind, confidence, self.why[kind]


def classify(device: Device) -> None:
    """Decide el tipo (kind), con qué seguridad (confidence) y por qué (reasons)."""
    ev = Evidence()
    if device.is_gateway:
        ev.add(ROUTER, 100, "es la puerta de enlace: por él sale todo a Internet")
    if device.is_self:
        ev.add(COMPUTER, 100, "es este ordenador")

    if device.model_id and (found := apple_model(device.model_id))[0]:
        ev.add(found[1], 70, f"dice que es un {found[0].split(' (')[0]}")

    for service in device.services:
        stype, txt = service.get("type", ""), service.get("txt", {})
        label, kind, weight = catalog.SERVICES.get(stype, ("", None, 0))
        if stype == "_googlecast._tcp":
            kind, weight = _googlecast_kind(txt.get("md", ""))
        if stype == "_hap._tcp" and (category := HOMEKIT_CATEGORIES.get(txt.get("ci", ""))):
            label = f"{label}: {category}"
            if category in ("cámara", "timbre con cámara"):
                kind = CAMERA
            elif category == "televisor":
                kind = TV
        ev.add(kind, weight, f"anuncia «{label or stype}»")

    for port in device.ports:
        name, meaning, kind, weight = catalog.PORTS.get(port, ("", "", None, 0))
        ev.add(kind, weight, f"tiene abierto el puerto {port} ({name}: {meaning})")

    for upnp in device.upnp:
        dtype = upnp.get("deviceType", "")
        if "InternetGatewayDevice" in dtype:
            ev.add(ROUTER, 60, "se anuncia como router (UPnP InternetGatewayDevice)")
        elif "MediaRenderer" in dtype:
            maker = (upnp.get("manufacturer", "") + " " + upnp.get("modelName", "")).lower()
            if "sonos" in maker:
                ev.add(SPEAKER, 50, "se anuncia como altavoz Sonos (UPnP)")
            else:
                ev.add(TV, 30, "puede reproducir vídeo o música que le mandes (UPnP MediaRenderer)")
        elif "dial" in dtype.lower():
            ev.add(TV, 35, "se le pueden mandar vídeos desde el móvil (DIAL, como YouTube o Netflix)")
        elif "MediaServer" in dtype:
            ev.add(NAS, 20, "comparte vídeos o fotos con la tele (UPnP MediaServer)")
        elif "Printer" in dtype:
            ev.add(PRINTER, 50, "se anuncia como impresora (UPnP)")

    names = " ".join(
        filter(
            None,
            [
                device.friendly_name,
                device.mdns_name,
                device.netbios_name,
                device.dns_name,
                device.model,
                device.manufacturer,
            ],
        )
    )
    for pattern, kind, weight in catalog.NAME_HINTS:
        if names and re.search(pattern, names, re.I):
            ev.add(kind, weight, f"por su nombre («{_first_match(pattern, names)}»)")

    if device.netbios_name:
        ev.add(COMPUTER, 35, f"tiene nombre de red de Windows ({device.netbios_name})")
    if device.brand in catalog.VENDOR_HINTS:
        kind, weight = catalog.VENDOR_HINTS[device.brand]
        ev.add(kind, weight, f"lo fabrica {device.brand}")
    if device.random_mac:
        ev.add(MOBILE, 20, "usa una MAC privada, como hacen los móviles y tabletas")

    device.kind, device.confidence, device.reasons = ev.decide()
    if device.is_gateway:
        device.confidence = "seguro"


def _googlecast_kind(model: str) -> tuple[str, int]:
    low = model.lower()
    if any(w in low for w in ("home", "nest mini", "nest audio", "speaker", "altavoz")):
        return SPEAKER, 60
    if "hub" in low:
        return SPEAKER, 50
    if "chromecast" in low or "google tv" in low:
        return STREAMER, 60
    if model:
        return TV, 45  # las teles con Google Cast dan su modelo: «BRAVIA 4K VH2», «Philips 55PUS8007»
    return STREAMER, 40


def _first_match(pattern: str, text: str) -> str:
    m = re.search(pattern, text, re.I)
    return m.group(0) if m else ""


def pick_friendly_name(device: Device) -> str:
    """El nombre que le puso alguien al configurarlo, de entre los que anuncia."""
    for upnp in device.upnp:
        if (name := upnp.get("friendlyName", "")) and not _ID_LIKE.search(name):
            return name
    priority = [
        "_googlecast._tcp",
        "_amzn-wplay._tcp",
        "_airplay._tcp",
        "_companion-link._tcp",
        "_raop._tcp",
        "_ipp._tcp",
        "_hap._tcp",
        "_spotify-connect._tcp",
        "_sonos._tcp",
        "_androidtvremote2._tcp",
        "_esphomelib._tcp",
        "_shelly._tcp",
        "_smb._tcp",
        "_workstation._tcp",
    ]
    by_type = {s.get("type"): s for s in device.services}
    for stype in priority:
        service = by_type.get(stype)
        if not service:
            continue
        txt = service.get("txt", {})
        name = txt.get("fn") or txt.get("friendly_name") or (txt.get("n") if stype == "_amzn-wplay._tcp" else "")
        name = name or service.get("name", "").split("@")[-1]
        name = _MAC_IN_NAME.sub("", name).strip()
        if name and not _ID_LIKE.search(name) and name.lower() != _label(device.mdns_name).lower():
            return name
    return ""


def mac_from_services(device: Device) -> str:
    """Si la tabla ARP no la tiene, algunos anuncios la llevan dentro (AirPlay, Linux)."""
    for service in device.services:
        txt = service.get("txt", {})
        candidates = [txt.get("deviceid", ""), service.get("name", "").split("@")[0]]
        if m := _MAC_IN_NAME.search(service.get("name", "")):
            candidates.append(m.group(1))
        for value in candidates:
            mac = normalize(value)
            if mac and is_device(mac):
                return mac
    return ""


def describe(device: Device) -> None:
    """Modelo, fabricante y sistema. Primero lo que dicen sus anuncios (que es lo más
    concreto: «Chromecast»), luego su ficha UPnP y, por último, lo que se deduce."""
    txt_models = [s.get("txt", {}).get(k, "") for s in device.services for k in ("model", "am", "rpmd")]
    for value in [device.model, *txt_models]:
        pretty, _kind, os_name = apple_model(value)
        if pretty:
            device.model_id, device.model = value.strip(), pretty
            device.os = device.os or os_name
            device.manufacturer = device.manufacturer or "Apple"
            break
    for service in device.services:
        stype, txt = service.get("type", ""), service.get("txt", {})
        model = ""
        if stype == "_googlecast._tcp":
            model = txt.get("md", "")
        elif stype in ("_ipp._tcp", "_ipps._tcp", "_printer._tcp"):
            model = txt.get("ty") or txt.get("usb_mdl", "")
            device.manufacturer = device.manufacturer or txt.get("usb_mfg", "")
        elif stype == "_hap._tcp":
            model = txt.get("md", "")
        elif stype == "_esphomelib._tcp":
            model = " ".join(filter(None, [txt.get("platform", ""), txt.get("board", "")]))
        elif stype == "_airplay._tcp":  # las teles con AirPlay dicen marca y modelo
            model = txt.get("model", "")
            device.manufacturer = device.manufacturer or txt.get("manufacturer", "")
        device.model = device.model or model
    if device.upnp:
        root = device.upnp[0]
        device.manufacturer = device.manufacturer or root.get("manufacturer", "")
        device.model = device.model or " ".join(
            dict.fromkeys(filter(None, [root.get("modelName", ""), root.get("modelNumber", "")]))
        )
    if not device.model and device.brand == "Raspberry Pi":
        device.model = "Raspberry Pi"
    if not device.os:
        device.os = next(filter(None, (os_from_banner(text) for text in device.banners.values())), "")
    if not device.os and device.upnp_server:
        device.os = os_from_server(device.upnp_server)
    if not device.os and device.netbios_name and 3389 in device.ports:
        device.os = "Windows"


def finish(device: Device) -> Device:
    """Una vez juntadas todas las pistas: marca, modelo, nombre, tipo y avisos."""
    if not device.mac and (mac := mac_from_services(device)):
        device.mac = mac
    if device.mac:
        device.random_mac = is_random(device.mac)
        device.vendor = device.vendor or oui_vendor(device.mac)
    device.brand = short_vendor(device.vendor)
    describe(device)
    device.friendly_name = device.friendly_name or pick_friendly_name(device)
    classify(device)
    device.notes = observations(device)
    return device


def observations(device: Device) -> list[dict]:
    """Lo que conviene saber de este aparato, de más a menos importante."""
    notes = []

    def note(level, text):
        notes.append({"level": level, "text": text})

    ports = set(device.ports)
    if device.is_new:
        note(NUEVO, "No estaba la última vez que miraste. Si no sabes qué es, averígualo.")
    if 23 in ports:
        note(
            ALTA,
            "Tiene Telnet abierto: se entra a él sin cifrar y muchas veces con la contraseña de fábrica. "
            "Si no lo usas, desactívalo en su configuración.",
        )
    if 21 in ports:
        note(MEDIA, "Tiene FTP: pasa archivos y contraseñas sin cifrar.")
    if 3389 in ports:
        note(
            MEDIA,
            "Tiene el Escritorio remoto de Windows activado. Si no lo usas, desactívalo; y nunca lo "
            "abras hacia Internet.",
        )
    if 5900 in ports:
        note(MEDIA, "Deja ver y manejar su pantalla a distancia (VNC). Que tenga una buena contraseña.")
    if device.is_gateway:
        if any("InternetGatewayDevice" in u.get("deviceType", "") for u in device.upnp) or any(
            "InternetGatewayDevice" in t for t in device.upnp_targets
        ):
            note(
                MEDIA,
                "Tiene UPnP activado: cualquier aparato de casa puede abrir puertos hacia Internet sin "
                "preguntarte. Si no juegas online ni lo necesita nada, desactívalo en el router.",
            )
        if 80 in ports and 443 not in ports:
            note(
                INFO,
                "Su página de configuración va sin cifrar (http): quien esté en tu wifi podría ver la "
                "contraseña al entrar. Entra solo desde casa y con una contraseña que no uses en otro sitio.",
            )
    if 554 in ports and device.kind == CAMERA:
        note(INFO, "Emite vídeo por RTSP: comprueba que pide contraseña y que no es la de fábrica.")
    if 1883 in ports:
        note(INFO, "Habla MQTT (domótica) sin cifrar. Normal en un centro de domótica; raro en otra cosa.")
    if device.shared_mac and not device.is_gateway:
        note(
            INFO,
            "Otra IP tiene su misma MAC. Pasa con lo que está conectado a un repetidor wifi: el "
            "repetidor contesta por ellos, y entonces la marca es la del repetidor.",
        )
    if device.random_mac and not device.vendor:
        note(
            INFO,
            "Usa una MAC privada (la que se inventan iPhone y Android para cada wifi): por eso no se sabe la marca.",
        )
    if device.brand in catalog.CHIPMAKERS:
        note(INFO, f"{device.brand} fabrica el chip de wifi, no el aparato: la marca de verdad puede ser otra.")
    if device.kind == UNKNOWN and not (
        device.mdns_name or device.dns_name or device.netbios_name or device.services or device.ports or device.upnp
    ):
        note(
            INFO,
            "No cuenta nada de sí mismo: solo se sabe que está conectado. Mira en el router o apaga y "
            "enciende cosas de casa para ver cuál es.",
        )
    if device.kind == SMART_HOME and device.brand in ("Espressif", "Tuya"):
        note(
            INFO,
            "Los cacharros de domótica baratos casi nunca se actualizan. Si puedes, ponlos en la red de "
            "invitados del router.",
        )
    return notes
