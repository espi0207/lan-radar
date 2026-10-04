"""SSDP / UPnP: la ficha técnica que publican teles, routers, altavoces y consolas.

Es lo que usa el móvil para encontrar la tele cuando le das a "enviar a la TV". A la
pregunta "¿quién hay?" (M-SEARCH), cada aparato contesta con un enlace a su ficha, un XML
con su nombre («[TV] Samsung Q60 Salón»), fabricante, modelo y qué sabe hacer (reproducir
vídeo, abrir puertos en el router…).

Solo se descargan fichas que estén en el propio aparato que contesta y dentro de la red
que se revisa: un aparato no puede mandar a lan-radar a leer nada de fuera.
"""

from __future__ import annotations

import http.client
import ipaddress
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from . import parallel, udp

GROUP = "239.255.255.250"
PORT = 1900
MAX_XML = 256 * 1024
SEARCH_TARGETS = ["ssdp:all", "upnp:rootdevice"]
FIELDS = ("friendlyName", "manufacturer", "modelName", "modelNumber", "modelDescription", "deviceType")


@dataclass
class Device:
    deviceType: str = ""  # noqa: N815 (así se llaman en UPnP)
    friendlyName: str = ""  # noqa: N815
    manufacturer: str = ""
    modelName: str = ""  # noqa: N815
    modelNumber: str = ""  # noqa: N815
    modelDescription: str = ""  # noqa: N815


@dataclass
class Info:
    server: str = ""  # cabecera SERVER: «Linux/4.9 UPnP/1.0 Cling/2.0»
    targets: set[str] = field(default_factory=set)  # los ST que anuncia
    locations: set[str] = field(default_factory=set)
    devices: list[Device] = field(default_factory=list)


def search_packet(target: str, host: str = f"{GROUP}:{PORT}", mx: int = 2) -> bytes:
    return (
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {host}\r\n"
        'MAN: "ssdp:discover"\r\n'
        f"MX: {mx}\r\n"
        f"ST: {target}\r\n"
        "USER-AGENT: lan-radar UPnP/1.1\r\n\r\n"
    ).encode("ascii")


def parse_headers(data: bytes) -> dict[str, str]:
    """Las cabeceras de una respuesta (o de un anuncio NOTIFY), con el nombre en minúsculas."""
    text = data[:8192].decode("utf-8", errors="replace")
    lines = text.split("\r\n") if "\r\n" in text else text.split("\n")
    if not lines or not (lines[0].startswith("HTTP/") or lines[0].startswith("NOTIFY")):
        return {}
    headers = {}
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if sep and name.strip():
            headers.setdefault(name.strip().lower(), value.strip())
    return headers


def location_allowed(url: str, source: ipaddress.IPv4Address) -> bool:
    """Solo fichas por http, en la misma IP que ha contestado."""
    try:
        parts = urlsplit(url)
        host = ipaddress.ip_address(parts.hostname or "")
        parts.port  # noqa: B018 (lanza ValueError si el puerto no es un número)
    except ValueError:
        return False
    return parts.scheme == "http" and host == source


def parse_description(text: str) -> list[Device]:
    """El XML de la ficha: el aparato principal y los que lleva dentro (un router tiene
    dentro un "WANDevice", una tele un "MediaRenderer"…)."""
    head = text[:4096].upper()
    if "<!DOCTYPE" in head or "<!ENTITY" in text.upper():
        return []  # una ficha de verdad no los lleva; con ellos se puede montar un XML bomba
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    devices = []
    for element in root.iter():
        if _local_name(element.tag) != "device":
            continue
        values = {}
        for child in element:
            name = _local_name(child.tag)
            if name in FIELDS and child.text:
                values[name] = " ".join(child.text.split())[:200]
        if values:
            devices.append(Device(**values))
    return devices


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def fetch(url: str, timeout: float = 3.0) -> str:
    """Descarga la ficha sin seguir redirecciones (que podrían llevar fuera de la red)."""
    parts = urlsplit(url)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    conn = http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=timeout)
    try:
        conn.request("GET", path, headers={"User-Agent": "lan-radar", "Connection": "close"})
        response = conn.getresponse()
        if response.status != 200:
            return ""
        return response.read(MAX_XML).decode("utf-8", errors="replace")
    finally:
        conn.close()


def query(
    local_ip: str,
    network,
    hosts=(),
    wait: float = 2.5,
    port: int = PORT,
    group: str | None = GROUP,
    fetch_descriptions: bool = True,
) -> dict:
    """Pregunta a todos (y a cada aparato de `hosts`) y descarga sus fichas."""
    found: dict[ipaddress.IPv4Address, Info] = {}

    def handle(ip, _port, data):
        try:
            source = ipaddress.IPv4Address(ip)
        except ValueError:
            return
        headers = parse_headers(data)
        if source not in network or not headers:
            return
        info = found.setdefault(source, Info())
        info.server = info.server or headers.get("server", "")[:200]
        if target := headers.get("st") or headers.get("nt"):
            info.targets.add(target[:200])
        location = headers.get("location", "")
        if location and location_allowed(location, source) and len(info.locations) < 4:
            info.locations.add(location)

    with udp.open_socket(local_ip, multicast_ttl=2 if group else 0) as sock:
        packets = []
        if group:
            packets += [(search_packet(t), (group, port)) for t in SEARCH_TARGETS] * 2
        packets += [(search_packet("ssdp:all", host=f"{h}:{port}", mx=1), (str(h), port)) for h in hosts]
        udp.send_all(sock, packets)
        udp.collect(sock, wait, handle)

    if fetch_descriptions:
        urls = {url: info for info in found.values() for url in info.locations}
        fetched = parallel.run(lambda url: parse_description(fetch(url)), sorted(urls), workers=16, timeout=6)
        for url in sorted(fetched):
            info = urls[url]
            for device in fetched[url]:
                if device not in info.devices:
                    info.devices.append(device)
    return found
