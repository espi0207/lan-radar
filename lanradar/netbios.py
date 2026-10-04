"""NetBIOS: el nombre de los ordenadores con Windows (y de los NAS y Linux con Samba).

A la pregunta "¿qué nombres tienes?" (NBSTAT, RFC 1002 §4.2.18), contestan con el nombre
del equipo («PORTATIL-ANA»), su grupo de trabajo («WORKGROUP») y si comparte carpetas.

Como la pregunta va a cada IP de la red, sirve también para despertar a los aparatos:
para mandarle algo a una IP, el sistema tiene que preguntar antes su MAC, y así queda
apuntada en la tabla ARP aunque el aparato no conteste nada más.
"""

from __future__ import annotations

import ipaddress
import struct
from dataclasses import dataclass

from . import dns, udp
from .oui import is_device, normalize

PORT = 137
NBSTAT = 0x21
GROUP_FLAG = 0x8000
# El nombre «*» (todos), con la codificación de NetBIOS: cada medio byte, una letra desde la A.
_STAR = b"*" + b"\x00" * 15
ENCODED_STAR = bytes(c for b in _STAR for c in (0x41 + (b >> 4), 0x41 + (b & 0x0F)))


@dataclass
class Info:
    name: str = ""  # el del equipo
    workgroup: str = ""
    shares_files: bool = False  # tiene el servicio de servidor de archivos (sufijo 0x20)
    mac: str = ""  # Samba suele dar ceros; Windows, la de verdad


def build_query(query_id: int) -> bytes:
    header = struct.pack("!HHHHHH", query_id & 0xFFFF, 0, 1, 0, 0, 0)
    return header + bytes([32]) + ENCODED_STAR + b"\x00" + struct.pack("!HH", NBSTAT, 1)


def parse_response(data: bytes) -> Info | None:
    if len(data) < 12 or not data[2] & 0x80 or struct.unpack("!H", data[6:8])[0] < 1:
        return None  # no es una respuesta, o no trae nada
    try:
        _name, offset = dns.read_name(data, 12)
        rtype, _cls, _ttl, length = struct.unpack("!HHIH", data[offset : offset + 10])
    except (struct.error, dns.BadPacket):
        return None
    if rtype != NBSTAT:
        return None
    rdata = data[offset + 10 : offset + 10 + length]
    if not rdata:
        return None
    count = rdata[0]
    info = Info()
    pos = 1
    for _ in range(count):
        entry = rdata[pos : pos + 18]
        if len(entry) < 18:
            return None
        pos += 18
        name = entry[:15].decode("latin-1").rstrip(" \x00")
        suffix = entry[15]
        flags = struct.unpack("!H", entry[16:18])[0]
        is_group = bool(flags & GROUP_FLAG)
        if suffix == 0x00 and not is_group and not info.name:
            info.name = name
        elif suffix == 0x00 and is_group and not info.workgroup:
            info.workgroup = name
        elif suffix == 0x20 and not is_group:
            info.shares_files = True
    mac = normalize(rdata[pos : pos + 6].hex()) if len(rdata) >= pos + 6 else ""
    info.mac = mac if is_device(mac) else ""
    if not info.name.isprintable():
        info.name = ""
    if not info.workgroup.isprintable():
        info.workgroup = ""
    return info if info.name else None


def query(local_ip: str, network, hosts, wait: float = 1.5, port: int = PORT, rounds: int = 2) -> dict:
    """Pregunta a cada IP de `hosts`. Devuelve {IP: Info} de los que contestan."""
    found: dict[ipaddress.IPv4Address, Info] = {}

    def handle(ip, _port, data):
        try:
            source = ipaddress.IPv4Address(ip)
        except ValueError:
            return
        if source in network and (info := parse_response(data)):
            found[source] = info

    hosts = [str(h) for h in hosts]
    with udp.open_socket(local_ip) as sock:
        for _ in range(rounds):
            pending = [h for h in hosts if ipaddress.IPv4Address(h) not in found]
            udp.send_all(sock, ((build_query(i), (h, port)) for i, h in enumerate(pending)))
            udp.collect(sock, wait, handle)
    return found
