"""Una pasada por la red: encontrar los aparatos y preguntar a cada uno todo lo que cuenta.

1. Quién hay. Se manda una pregunta de NetBIOS a cada IP de la red: el sistema tiene que
   averiguar antes la MAC de cada una (ARP), y los aparatos encendidos contestan a eso
   aunque no contesten a nada más. Después se lee la tabla ARP.
2. Quién es cada uno. A la vez: mDNS/Bonjour, SSDP/UPnP y el DNS del router.
3. Qué hace cada uno (se puede saltar): los puertos conocidos, los saludos y las páginas
   de configuración.
Todo se junta en device.py, y el historial dice qué es nuevo.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime

from . import arp, mdns, net, netbios, parallel, probe, ssdp
from .device import Device, finish, observations
from .history import History, network_key

Progress = Callable[[str, float], None]


@dataclass
class Timing:
    """Cuánto se espera a las respuestas. Las pruebas lo acortan."""

    netbios: float = 1.5
    mdns: float = 1.2
    ssdp: float = 2.5
    dns: float = 4.0
    port: float = 1.0
    http: float = 3.0


@dataclass
class Result:
    network: str
    interface: str = ""
    address: str = ""
    gateway: str = ""
    started: str = ""
    seconds: float = 0.0
    services_checked: bool = True
    network_key: str = ""
    first_scan: bool = False
    devices: list[Device] = field(default_factory=list)
    missing: list[dict] = field(default_factory=list)  # vistos otras veces, ahora no

    def to_dict(self) -> dict:
        return asdict(self)


def scan(
    local: net.LocalNet,
    services: bool = True,
    progress: Progress | None = None,
    history: History | None = None,
    timing: Timing | None = None,
) -> Result:
    net.check_network(local.network)  # aquí también: que no se pueda llamar con otra red
    report = progress or (lambda _text, _fraction: None)
    timing = timing or Timing()
    started, clock = datetime.now(), time.monotonic()
    me = str(local.address)
    targets = net.hosts(local.network)  # este ordenador incluido: también se pregunta a sí mismo

    # 1. Quién hay
    report(f"Buscando aparatos en {local.network}…", 0.02)
    before = arp.table()
    others = [t for t in targets if t != local.address]
    names_nb = netbios.query(me, local.network, others, wait=timing.netbios, rounds=1)
    macs = {ip: mac for ip, mac in {**before, **arp.table()}.items() if ip in local.network}
    macs = _without_proxy_arp(macs, keep=set(names_nb) | {local.gateway})
    alive = (set(macs) | set(names_nb) | {local.address}) & set(targets)
    # Segunda vuelta de NetBIOS solo a los que están y no han contestado (el wifi pierde
    # paquetes). Repetirla a toda la red costaría segundos: el sistema retiene cada paquete
    # a una IP vacía mientras espera su ARP, y con muchos el envío se queda esperando.
    retry = sorted(ip for ip in alive if ip not in names_nb)
    names_nb.update(netbios.query(me, local.network, retry, wait=timing.netbios * 0.6, rounds=1))

    # 2. Quién es cada uno
    report(f"{len(alive)} aparatos conectados. Preguntando a cada uno quién es…", 0.3)
    hosts = sorted(alive)
    jobs = {
        "mdns": lambda: mdns.query(me, local.network, hosts, wait=timing.mdns),
        "ssdp": lambda: ssdp.query(me, local.network, [h for h in hosts if h != local.address], wait=timing.ssdp),
        "dns": lambda: probe.reverse_dns(hosts, timeout=timing.dns),
    }
    answers = parallel.run(lambda name: jobs[name](), list(jobs), workers=3, timeout=timing.ssdp + 12)
    found_mdns, found_ssdp, found_dns = answers.get("mdns", {}), answers.get("ssdp", {}), answers.get("dns", {})
    alive |= (set(found_mdns) | set(found_ssdp)) & set(targets)
    hosts = sorted(alive)
    for ip, mac in arp.table().items():  # los que no estaban en la tabla y han contestado ahora
        if ip in alive and ip not in macs:
            macs[ip] = mac

    # 3. Qué hace cada uno
    ports, banners, pages = {}, {}, {}
    if services:
        report(f"Mirando qué servicios tiene cada uno de los {len(hosts)}…", 0.6)
        ports = probe.open_ports(hosts, timeout=timing.port)
        report("Leyendo las páginas de configuración y los saludos…", 0.85)
        banners, pages = probe.details(ports, timeout=timing.http)

    devices = []
    for ip in hosts:
        device = Device(
            ip=str(ip),
            mac=macs.get(ip, ""),
            is_self=ip == local.address,
            is_gateway=local.gateway is not None and ip == local.gateway,
        )
        if device.is_self:
            device.mac = local.mac
            device.friendly_name = socket.gethostname()
        device.dns_name = found_dns.get(ip, "")
        if info := names_nb.get(ip):
            device.netbios_name, device.workgroup = info.name, info.workgroup
            device.mac = device.mac or info.mac
        if info := found_mdns.get(ip):
            device.mdns_name, device.model, device.os = info.hostname, info.model, _hinfo_os(info.hinfo)
            device.services = [{"type": s.type, "name": s.name, "port": s.port, "txt": s.txt} for s in info.services]
        if info := found_ssdp.get(ip):
            device.upnp_server = info.server
            device.upnp_targets = sorted(info.targets)
            device.upnp = [{k: v for k, v in asdict(d).items() if v} for d in info.devices]
        device.ports = ports.get(ip, [])
        device.banners = {str(p): text for p, text in banners.get(ip, {}).items()}
        device.web = {str(p): info for p, info in pages.get(ip, {}).items()}
        devices.append(finish(device))
    devices.sort(key=lambda d: (not d.is_gateway, not d.is_self, ipaddress.IPv4Address(d.ip)))
    per_mac = Counter(d.mac for d in devices if d.mac)
    for device in devices:
        if per_mac[device.mac] > 1:
            device.shared_mac = True
            device.notes = observations(device)

    gateway_mac = next((d.mac for d in devices if d.is_gateway), "")
    key = network_key(str(local.network), gateway_mac)
    result = Result(
        network=str(local.network),
        interface=local.interface,
        address=me,
        gateway=str(local.gateway or ""),
        started=started.isoformat(timespec="seconds"),
        services_checked=services,
        network_key=key,
        devices=devices,
    )
    if history is not None:
        result.missing = history.record(key, str(local.network), devices, started)
        result.first_scan = history.is_first_scan(key)
        for device in devices:
            device.notes = observations(device)  # ahora que se sabe cuáles son nuevos
        history.save()
    result.seconds = round(time.monotonic() - clock, 1)
    report(f"Hecho: {len(devices)} aparatos.", 1.0)
    return result


def _without_proxy_arp(macs: dict, keep: set, limit: int = 8) -> dict:
    """Hay routers que contestan al ARP de todas las IP de la red, estén ocupadas o no
    ("proxy ARP"). Entonces una misma MAC sale en decenas de IP: de esas solo se quedan
    las que han dado alguna otra señal de vida."""
    crowded = {mac for mac, n in Counter(macs.values()).items() if n > limit}
    return {ip: mac for ip, mac in macs.items() if mac not in crowded or ip in keep}


def _hinfo_os(hinfo: str) -> str:
    """HINFO de avahi: «X86_64 LINUX» → «Linux (x86_64)»."""
    parts = hinfo.split()
    if len(parts) == 2:
        return f"{parts[1].capitalize()} ({parts[0].lower()})"
    return hinfo.title()
