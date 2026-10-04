"""Cómo se cuenta lo encontrado: la tabla, los avisos y la ficha de cada aparato.

Lo usan la terminal y la ventana, así que aquí no se pinta nada: solo se decide qué decir.
"""

from __future__ import annotations

from datetime import datetime

from .catalog import NAMES, PORTS, SERVICES, UNKNOWN
from .device import ALTA, INFO, MEDIA, NUEVO, Device
from .scan import Result

LEVEL_LABEL = {ALTA: "Importante", MEDIA: "Conviene revisarlo", INFO: "Bueno saberlo", NUEVO: "Nuevo"}


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def ago(iso: str, now: datetime | None = None) -> str:
    """«2026-10-01T21:04:00» → «hace 3 días»."""
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    seconds = ((now or datetime.now()) - then).total_seconds()
    if seconds < 3600:
        return "hace un rato"
    if seconds < 86400:
        return f"hace {plural(int(seconds // 3600), 'hora', 'horas')}"
    days = int(seconds // 86400)
    if days < 60:
        return "ayer" if days == 1 else f"hace {days} días"
    return f"el {then:%d/%m/%Y}"


def when(iso: str) -> str:
    try:
        return f"{datetime.fromisoformat(iso):%d/%m/%Y %H:%M}"
    except ValueError:
        return iso


def display_name(device: Device) -> str:
    return f"{device.name()} (este ordenador)" if device.is_self else device.name()


def brand_text(device: Device) -> str:
    if device.brand:
        return device.brand
    if device.random_mac:
        return "MAC privada"
    return "" if device.mac else "sin MAC"


def headline(result: Result) -> str:
    parts = [f"Red {result.network}" + (f" ({result.interface})" if result.interface else "")]
    if result.gateway:
        parts.append(f"router {result.gateway}")
    parts.append(plural(len(result.devices), "aparato", "aparatos"))
    if result.seconds:
        parts.append(f"{result.seconds:.1f} s".replace(".", ","))
    return " · ".join(parts)


def table_rows(result: Result) -> list[tuple[str, str, str, str, str]]:
    """(IP, nombre, tipo, marca, marca de nuevo) por aparato."""
    return [(d.ip, display_name(d), d.kind_label(), brand_text(d), "nuevo" if d.is_new else "") for d in result.devices]


def alerts(result: Result) -> list[tuple[str, Device, str]]:
    """(nivel, aparato, texto) de lo importante y lo que conviene revisar."""
    found = []
    for level in (ALTA, MEDIA):
        for device in result.devices:
            for note in device.notes:
                if note["level"] == level:
                    found.append((level, device, note["text"]))
    return found


def details(device: Device) -> list[tuple[str, str]]:
    """La ficha completa: (etiqueta, valor), solo de lo que se sabe."""
    rows: list[tuple[str, str]] = []

    def add(label, value):
        if value:
            rows.append((label, value))

    if device.nickname:
        add("Tu nombre", device.nickname)
    kind = device.kind_label()
    add("Tipo", kind if device.kind != UNKNOWN else "no se sabe")
    if device.mac:
        extra = " (privada: se la inventa el propio aparato)" if device.random_mac else ""
        add("MAC", device.mac + extra)
    add("Fabricante", device.vendor + (f" ({device.brand})" if device.brand and device.brand != device.vendor else ""))
    if device.manufacturer and _letters(device.manufacturer) not in _letters(device.vendor):
        add("Marca que dice", device.manufacturer)
    add("Modelo", device.model)
    add("Sistema", device.os)
    add("Nombre puesto", device.friendly_name if device.friendly_name != device.nickname else "")
    add("Nombre Bonjour", device.mdns_name)
    add("Nombre en el DNS", device.dns_name)
    if device.netbios_name:
        add("Nombre Windows", device.netbios_name + (f" (grupo {device.workgroup})" if device.workgroup else ""))
    for service in device.services:
        label = SERVICES.get(service.get("type", ""), (service.get("type", ""),))[0]
        txt = service.get("txt", {})
        extra = ", ".join(f"{k}={v}" for k, v in list(txt.items())[:6] if v and len(v) < 60)
        name = service.get("name", "")
        value = label + (f" — «{name}»" if name else "") + (f" [{extra}]" if extra else "")
        add("Anuncia", value)
    for upnp in device.upnp:
        parts = [upnp.get("deviceType", "").split(":")[-2] if upnp.get("deviceType", "").count(":") >= 2 else ""]
        parts += [upnp.get("manufacturer", ""), upnp.get("modelName", ""), upnp.get("modelNumber", "")]
        add("UPnP", " · ".join(dict.fromkeys(p for p in parts if p)))
    add("Servidor UPnP", device.upnp_server)
    for port in device.ports:
        name, meaning, *_ = PORTS.get(port, ("", "", None, 0))
        add("Puerto abierto", f"{port} — {name}: {meaning}" if name else str(port))
    for port, text in device.banners.items():
        add(f"Saludo ({port})", text)
    for port, info in device.web.items():
        bits = []
        if title := info.get("title"):
            bits.append(f"«{title}»")
        if server := info.get("server"):
            bits.append(f"servidor {server}")
        if location := info.get("location"):
            bits.append(f"lleva a {location}")
        add(f"Web ({port})", ", ".join(bits) or f"contesta (código {info.get('status', '?')})")
    if device.reasons:
        add("Por qué ese tipo", "; ".join(device.reasons))
    if device.first_seen:
        add("Visto por primera vez", when(device.first_seen))
    return rows


def summary_line(result: Result) -> str:
    """«3 móviles, 2 ordenadores, 1 router…» para el resumen de arriba."""
    counts: dict[str, int] = {}
    for d in result.devices:
        counts[d.kind] = counts.get(d.kind, 0) + 1
    order = list(NAMES)
    parts = []
    for kind, n in sorted(counts.items(), key=lambda kv: (-kv[1], order.index(kv[0]) if kv[0] in order else 99)):
        one, many = NAMES.get(kind, (kind.lower(), kind.lower()))
        parts.append(plural(n, one, many))
    return ", ".join(parts)


def _letters(text: str) -> str:
    """Para comparar marcas sin fijarse en comas y puntos: «Google Inc.» ~ «Google, Inc.»."""
    return "".join(c for c in text.lower() if c.isalnum())
