"""La tabla ARP: qué MAC tiene cada IP, según lo que el sistema ya ha hablado con la red.

Cuando este ordenador habla con un aparato de la red, apunta su MAC en una tabla (la tabla
ARP, o "de vecinos"). Leerla es gratis y no envía nada: es lo primero que mira lan-radar.
Para los que no estén en la tabla hace falta el barrido de probe.py, que sí los contacta.

ARP solo funciona dentro de la red local (no cruza el router), así que la MAC de un aparato
de tu red siempre es la suya de verdad; la de una IP de fuera sería la del router.
"""

from __future__ import annotations

import ipaddress
import re
import sys

from . import net
from .oui import is_device, normalize

# Linux `ip neigh`: «192.168.1.1 dev wlan0 lladdr aa:bb:.. REACHABLE»; también FAILED, STALE…
_LINUX = re.compile(r"^(\d+\.\d+\.\d+\.\d+)\s+dev\s+\S+\s+lladdr\s+(\S+)\s+(\w+)", re.M)
# `arp -a` (Windows, macOS, BSD): «? (192.168.1.1) at aa-bb-.. [ether] on en0» / «dynamic»
_ARP_A = re.compile(r"\(?(\d+\.\d+\.\d+\.\d+)\)?\s+at\s+([0-9A-Fa-f:.-]+)", re.I)
# Windows `arp -a`:  «  192.168.1.1          aa-bb-cc-dd-ee-ff     dinámico»
_ARP_WIN = re.compile(r"^\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2}){5})\s+(\w+)", re.M)


def parse_proc(text: str) -> dict[str, str]:
    """/proc/net/arp en Linux: la fuente más limpia, sin pasar por ninguna orden."""
    found = {}
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4 and parts[3] != "00:00:00:00:00:00":
            found[parts[0]] = normalize(parts[3])
    return found


def parse_ip_neigh(text: str) -> dict[str, str]:
    found = {}
    for ip, mac, state in _LINUX.findall(text):
        if state != "FAILED":
            found[ip] = normalize(mac)
    return found


def parse_arp(text: str) -> dict[str, str]:
    """`arp -a`, tanto el de Windows (columnas) como el de macOS/BSD («… at … »)."""
    found = {}
    for ip, mac, _state in _ARP_WIN.findall(text):
        found[ip] = normalize(mac)
    for ip, mac in _ARP_A.findall(text):
        if (norm := normalize(mac)) and ip not in found:  # «at (incomplete)» no da MAC válida
            found[ip] = norm
    return found


def table() -> dict[ipaddress.IPv4Address, str]:
    """Lo que el sistema ya sabe: {IP: MAC} de los aparatos con los que ha hablado."""
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/net/arp", encoding="utf-8") as f:
                found = parse_proc(f.read())
        except OSError:
            found = parse_ip_neigh(net._run(["ip", "neigh", "show"]))
    elif sys.platform == "win32":
        found = parse_arp(net._run(["arp", "-a"]))
    else:
        found = parse_arp(net._run(["arp", "-a", "-n"]))
    result = {}
    for ip, mac in found.items():
        if is_device(mac):
            try:
                result[ipaddress.IPv4Address(ip)] = mac
            except ipaddress.AddressValueError:
                pass
    return result
