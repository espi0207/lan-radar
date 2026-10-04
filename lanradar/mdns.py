"""mDNS / Bonjour: lo que cada aparato cuenta de sí mismo.

Móviles, ordenadores, teles, impresoras y altavoces se anuncian en la red local para que
los demás los encuentren (es como el AirPlay o el Chromecast sale en la lista del móvil).
Contestan a preguntas como "¿quién eres?" (su nombre: «iPhone-de-Ana.local»), "¿qué
servicios tienes?" (AirPlay, impresora…) y dan detalles: modelo, nombre que le pusiste…

Se pregunta de dos formas, porque el wifi pierde muchos paquetes de multidifusión:
- a todos a la vez (al grupo 224.0.0.251), los servicios más comunes;
- a cada aparato por separado, su nombre y sus servicios.
Como las preguntas no salen del puerto 5353, los aparatos contestan solo a quien pregunta
(RFC 6762 §6.7), sin molestar al resto.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field

from . import dns, udp
from .catalog import ASK_DIRECTLY

GROUP = "224.0.0.251"
PORT = 5353
META = "_services._dns-sd._udp.local"


@dataclass
class Service:
    type: str  # "_airplay._tcp"
    name: str  # el nombre del anuncio: «Salón», «HP LaserJet M110w (A1B2C3)»
    port: int = 0
    txt: dict[str, str] = field(default_factory=dict)


@dataclass
class Info:
    hostname: str = ""  # «iPhone-de-Ana.local»
    services: list[Service] = field(default_factory=list)
    model: str = ""  # de _device-info: «iPhone15,2», «MacBookPro18,3»
    hinfo: str = ""  # «X86_64 LINUX», lo que publica avahi en Linux


def _short_type(name: str) -> str:
    """«_airplay._tcp.local» → «_airplay._tcp»"""
    parts = name.lower().rstrip(".").split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else name


def _split_instance(fullname: str) -> tuple[str, str]:
    """«Salón._googlecast._tcp.local» → («Salón», «_googlecast._tcp»). El nombre puede
    llevar puntos, así que se corta por el final."""
    parts = fullname.rstrip(".").split(".")
    if len(parts) >= 4 and parts[-1].lower() == "local" and parts[-2].lower() in ("_tcp", "_udp"):
        return ".".join(parts[:-3]), f"{parts[-3].lower()}.{parts[-2].lower()}"
    return fullname, ""


class Collector:
    """Va juntando lo que llega. Los registros de un aparato se apuntan a su IP: a la
    que diga su registro A si lo hay (un Apple TV puede contestar por un Mac dormido) o,
    si no, a la IP de la que viene la respuesta."""

    def __init__(self, network: ipaddress.IPv4Network):
        self.network = network
        self.by_ip: dict[ipaddress.IPv4Address, Info] = {}
        self.types: dict[ipaddress.IPv4Address, set[str]] = {}
        self.host_ip: dict[str, ipaddress.IPv4Address] = {}  # «iphone-de-ana.local» → IP
        self.instances: dict[str, dict] = {}  # nombre completo en minúsculas → datos

    def info(self, ip) -> Info:
        return self.by_ip.setdefault(ip, Info())

    def handle(self, ip: str, _port: int, data: bytes) -> None:
        try:
            source = ipaddress.IPv4Address(ip)
            msg = dns.parse(data)
        except (ValueError, dns.BadPacket):
            return
        if source not in self.network or not msg.is_response:
            return
        for record in msg.records:
            self._record(source, record)

    def _record(self, source, record: dns.Record) -> None:
        name = record.name.rstrip(".")
        lname = name.lower()
        if record.type == dns.A and isinstance(record.data, ipaddress.IPv4Address):
            if record.data in self.network:
                self.host_ip[lname] = record.data
                if not self.info(record.data).hostname:
                    self.info(record.data).hostname = name
        elif record.type == dns.PTR and isinstance(record.data, str):
            target = record.data.rstrip(".")
            if lname.endswith(".in-addr.arpa"):
                try:
                    ip = ipaddress.ip_address(".".join(reversed(lname.split(".")[:4])))
                except ValueError:
                    return
                if ip == source:
                    self.info(source).hostname = target
            elif lname == META:
                self.types.setdefault(source, set()).add(_short_type(target))
            else:
                label, stype = _split_instance(target)
                if stype:
                    entry = self.instances.setdefault(target.lower(), {"name": label, "type": stype})
                    entry.setdefault("source", source)
                    self.types.setdefault(source, set()).add(stype)
        elif record.type == dns.SRV and isinstance(record.data, tuple):
            label, stype = _split_instance(name)
            if stype:
                entry = self.instances.setdefault(lname, {"name": label, "type": stype})
                entry.setdefault("source", source)
                entry["port"], entry["target"] = record.data[2], record.data[3].rstrip(".").lower()
        elif record.type == dns.TXT and isinstance(record.data, list):
            label, stype = _split_instance(name)
            if stype == "_device-info._tcp":
                model = dns.txt_dict(record.data).get("model", "")
                if model:
                    self.info(source).model = model
            elif stype:
                entry = self.instances.setdefault(lname, {"name": label, "type": stype})
                entry.setdefault("source", source)
                entry["txt"] = dns.txt_dict(record.data)
        elif record.type == dns.HINFO and isinstance(record.data, list):
            self.info(source).hinfo = " ".join(record.data).strip()

    def result(self) -> dict[ipaddress.IPv4Address, Info]:
        for entry in self.instances.values():
            ip = self.host_ip.get(entry.get("target", ""), entry.get("source"))
            if ip is None:
                continue
            info = self.info(ip)
            if any(s.type == entry["type"] and s.name == entry["name"] for s in info.services):
                continue
            info.services.append(Service(entry["type"], entry["name"], entry.get("port", 0), entry.get("txt", {})))
        for info in self.by_ip.values():
            info.services.sort(key=lambda s: (s.type, s.name))
        return {ip: info for ip, info in self.by_ip.items() if info.hostname or info.services or info.model}


def query(local_ip: str, network, hosts, wait: float = 1.2, port: int = PORT, group: str | None = GROUP) -> dict:
    """Pregunta a la red y a cada aparato de `hosts`, en hasta tres vueltas: cada una
    pregunta lo que la anterior ha descubierto que hay. Tarda unos 3 × `wait` segundos."""
    collector = Collector(network)
    asked: set[tuple] = set()
    everyone = dns.build_query([(META, dns.PTR)] + [(f"{t}.local", dns.PTR) for t in ASK_DIRECTLY])
    with udp.open_socket(local_ip, multicast_ttl=255 if group else 0) as sock:
        for round_ in range(3):
            packets = []
            if round_ == 0:
                # A cada uno: su nombre y qué servicios tiene.
                for i, host in enumerate(str(h) for h in hosts):
                    questions = [(dns.reverse_name(host), dns.PTR), (META, dns.PTR)]
                    packets.append((dns.build_query(questions, query_id=i + 1), (host, port)))
            else:
                packets = _follow_up(collector, asked, port)
                if not packets:
                    break
            if group and round_ < 2:
                packets.insert(0, (everyone, (group, port)))  # dos veces: el wifi pierde paquetes
            udp.send_all(sock, packets)
            udp.collect(sock, wait, collector.handle)
    return collector.result()


def _follow_up(collector: Collector, asked: set, port: int) -> list[tuple[bytes, tuple[str, int]]]:
    """Lo que falta por preguntar a cada aparato: de cada servicio que ha dicho que tiene,
    el anuncio entero (nombre, puerto, detalles); y, por cada nombre, su ficha
    (_device-info, donde los aparatos de Apple dicen el modelo)."""
    packets = []
    for ip, types in collector.types.items():
        wanted = [(f"{t}.local", dns.PTR) for t in sorted(types) if t != "_device-info._tcp"]
        for entry in list(collector.instances.values()):
            if entry.get("source") != ip:
                continue
            if "txt" not in entry or "port" not in entry:
                wanted.append((f"{entry['name']}.{entry['type']}.local", dns.ANY))
            label = entry["name"].split("@")[-1]  # AirPlay de audio: «A1B2C3D4E5F6@Salón»
            wanted.append((f"{label}._device-info._tcp.local", dns.TXT))
        questions = []
        for name, qtype in wanted:
            if (ip, name.lower(), qtype) not in asked:
                asked.add((ip, name.lower(), qtype))
                questions.append((name, qtype))
        for i in range(0, len(questions), 12):  # que cada paquete quepa holgado
            if data := _safe_query(questions[i : i + 12]):
                packets.append((data, (str(ip), port)))
    return packets


def _safe_query(questions) -> bytes:
    good = []
    for name, qtype in questions:
        try:
            dns.encode_name(name)
        except ValueError:
            continue  # un nombre con una etiqueta de más de 63 bytes: ese no se pregunta
        good.append((name, qtype))
    return dns.build_query(good) if good else b""
