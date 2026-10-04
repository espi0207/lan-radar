"""Mensajes DNS (RFC 1035), lo justo para mDNS: preguntar y leer respuestas.

Los paquetes llegan de cualquier aparato de la red, así que la lectura no se fía de nada:
nombres comprimidos con punteros que dan vueltas, longitudes que se salen del paquete…
Cualquier cosa rara es un BadPacket y ese paquete se ignora.
"""

from __future__ import annotations

import ipaddress
import struct
from dataclasses import dataclass, field

A, PTR, TXT, AAAA, SRV, NSEC, ANY = 1, 12, 16, 28, 33, 47, 255
HINFO = 13
QU = 0x8000  # en la pregunta: "contéstame a mí directamente, no a todos"
MAX_JUMPS = 32


class BadPacket(ValueError):
    pass


@dataclass
class Record:
    name: str
    type: int
    ttl: int
    data: object  # str (PTR, nombre), list[str] (TXT), tuple (SRV), IP, o bytes si no se entiende


@dataclass
class Message:
    id: int
    is_response: bool
    questions: list[tuple[str, int]] = field(default_factory=list)
    records: list[Record] = field(default_factory=list)  # respuestas + adicionales, todo junto


def encode_name(name: str) -> bytes:
    out = b""
    for label in name.rstrip(".").split("."):
        raw = label.encode("utf-8")
        if not raw or len(raw) > 63:
            raise ValueError(f"nombre DNS no válido: {name!r}")
        out += bytes([len(raw)]) + raw
    return out + b"\x00"


def build_query(questions: list[tuple[str, int]], query_id: int = 0, unicast: bool = False) -> bytes:
    header = struct.pack("!HHHHHH", query_id, 0, len(questions), 0, 0, 0)
    qclass = 1 | (QU if unicast else 0)  # 1 = IN (Internet)
    body = b"".join(encode_name(name) + struct.pack("!HH", qtype, qclass) for name, qtype in questions)
    return header + body


def reverse_name(ip) -> str:
    """192.168.1.23 → 23.1.168.192.in-addr.arpa (para preguntar el nombre de una IP)."""
    return ipaddress.ip_address(ip).reverse_pointer


def read_name(data: bytes, offset: int) -> tuple[str, int]:
    """Lee un nombre (con compresión) y devuelve (nombre, dónde sigue el paquete)."""
    labels: list[str] = []
    end = None
    jumps = 0
    while True:
        if offset >= len(data):
            raise BadPacket("nombre cortado")
        length = data[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(data):
                raise BadPacket("puntero cortado")
            jumps += 1
            if jumps > MAX_JUMPS:
                raise BadPacket("punteros en bucle")
            if end is None:
                end = offset + 2
            offset = ((length & 0x3F) << 8) | data[offset + 1]
            continue
        if length & 0xC0:
            raise BadPacket("tipo de etiqueta desconocido")
        offset += 1
        if length == 0:
            break
        if offset + length > len(data):
            raise BadPacket("etiqueta cortada")
        labels.append(data[offset : offset + length].decode("utf-8", errors="replace"))
        offset += length
        if len(labels) > 128:
            raise BadPacket("nombre demasiado largo")
    return ".".join(labels), (end if end is not None else offset)


def _rdata(data: bytes, rtype: int, start: int, length: int) -> object:
    raw = data[start : start + length]
    if rtype == A and length == 4:
        return ipaddress.IPv4Address(raw)
    if rtype == AAAA and length == 16:
        return ipaddress.IPv6Address(raw)
    if rtype == PTR:
        return read_name(data, start)[0]
    if rtype == SRV and length >= 7:
        priority, weight, port = struct.unpack("!HHH", raw[:6])
        return (priority, weight, port, read_name(data, start + 6)[0])
    if rtype == TXT:
        strings, i = [], 0
        while i < len(raw):
            n = raw[i]
            strings.append(raw[i + 1 : i + 1 + n].decode("utf-8", errors="replace"))
            i += 1 + n
        return strings
    if rtype == HINFO:
        parts, i = [], 0
        while i < len(raw) and len(parts) < 2:
            n = raw[i]
            parts.append(raw[i + 1 : i + 1 + n].decode("utf-8", errors="replace"))
            i += 1 + n
        return parts
    return raw


def parse(data: bytes) -> Message:
    if len(data) < 12:
        raise BadPacket("demasiado corto")
    query_id, flags, qd, an, ns, ar = struct.unpack("!HHHHHH", data[:12])
    msg = Message(query_id, bool(flags & 0x8000))
    offset = 12
    for _ in range(qd):
        name, offset = read_name(data, offset)
        if offset + 4 > len(data):
            raise BadPacket("pregunta cortada")
        qtype, _qclass = struct.unpack("!HH", data[offset : offset + 4])
        offset += 4
        msg.questions.append((name, qtype))
    for _ in range(an + ns + ar):
        name, offset = read_name(data, offset)
        if offset + 10 > len(data):
            raise BadPacket("registro cortado")
        rtype, _rclass, ttl, length = struct.unpack("!HHIH", data[offset : offset + 10])
        offset += 10
        if offset + length > len(data):
            raise BadPacket("datos cortados")
        msg.records.append(Record(name, rtype, ttl, _rdata(data, rtype, offset, length)))
        offset += length
    return msg


def txt_dict(strings: list[str]) -> dict[str, str]:
    """["md=Chromecast", "fn=Salón"] → {"md": "Chromecast", "fn": "Salón"}"""
    out = {}
    for s in strings:
        key, sep, value = s.partition("=")
        if key and sep:
            out.setdefault(key.lower(), value)
    return out
