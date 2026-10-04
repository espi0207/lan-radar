"""Qué red se puede revisar: la de casa, y nada más.

lan-radar solo mira la red a la que está conectado este ordenador, si es privada (las de
casas y oficinas: 192.168.x.x, 10.x.x.x, 172.16-31.x.x) y como mucho del tamaño de una red
doméstica. Revisar aparatos ajenos no es cosa de esta herramienta: con cualquier otra red
se niega antes de enviar nada.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from .oui import normalize

# Una red de casa grande es una /24 (254 aparatos). Se deja hasta /22 (1022) para oficinas
# pequeñas; más que eso ya no es "mi wifi".
MAX_HOSTS = 1022
PRIVATE = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class NotAllowed(ValueError):
    """La red pedida no es la red privada (y pequeña) de este ordenador."""


@dataclass(frozen=True)
class LocalNet:
    network: ipaddress.IPv4Network
    address: ipaddress.IPv4Address  # la IP de este ordenador en esa red
    interface: str = ""
    mac: str = ""  # la de este ordenador
    gateway: ipaddress.IPv4Address | None = None  # el router

    def label(self) -> str:
        return f"{self.network} ({self.interface})" if self.interface else str(self.network)


def is_private(network: ipaddress.IPv4Network) -> bool:
    return network.version == 4 and any(network.subnet_of(p) for p in PRIVATE)


def check_network(network) -> ipaddress.IPv4Network:
    """Devuelve la red si es privada y pequeña; si no, NotAllowed con el motivo."""
    if network.version != 4:
        raise NotAllowed("solo redes IPv4")
    if not is_private(network):
        raise NotAllowed(f"{network} no es una red privada: lan-radar solo revisa la red de tu casa")
    if network.num_addresses - 2 > MAX_HOSTS:
        raise NotAllowed(f"{network} es demasiado grande para una red de casa (como mucho /22)")
    return network


def parse_network(text: str) -> ipaddress.IPv4Network:
    try:
        network = ipaddress.ip_network(text.strip(), strict=False)
    except ValueError as exc:
        raise NotAllowed(f"no entiendo «{text}»: escríbela como 192.168.1.0/24") from exc
    return check_network(network)


def default_target(local: LocalNet) -> ipaddress.IPv4Network:
    """La parte de la red que se revisa si no se dice otra: entera si es de casa; en una
    red grande (la de una empresa), solo la /24 de este ordenador."""
    if local.network.num_addresses - 2 <= MAX_HOSTS:
        return local.network
    return ipaddress.ip_network(f"{local.address}/24", strict=False)


def choose_target(network: ipaddress.IPv4Network, locals_: list[LocalNet]) -> LocalNet:
    """La red de este ordenador que contiene la pedida, con la red cambiada por la pedida.
    Si no está dentro de ninguna, NotAllowed: no se revisan redes a las que no se está
    conectado (habría que pasar por el router, y eso ya es la red de otro)."""
    check_network(network)
    for local in locals_:
        if network.subnet_of(local.network):
            return replace(local, network=network)
    mine = ", ".join(str(n.network) for n in locals_) or "ninguna"
    raise NotAllowed(f"{network} no es la red de este ordenador (está conectado a: {mine})")


def hosts(network: ipaddress.IPv4Network, skip=()) -> list[ipaddress.IPv4Address]:
    skip = {ipaddress.ip_address(s) for s in skip}
    return [h for h in network.hosts() if h not in skip]


# Las redes de este ordenador. Cada sistema lo cuenta a su manera.

_INET_LINUX = re.compile(r"inet (\d+\.\d+\.\d+\.\d+)/(\d+)")
_IFCONFIG_IP = re.compile(r"\binet (?:addr:)?(\d+\.\d+\.\d+\.\d+)")
_IFCONFIG_MASK = re.compile(r"(?:\bnetmask\s+|Mask:)(0x[0-9a-f]+|\d+\.\d+\.\d+\.\d+)", re.I)
_ETHER = re.compile(r"(?:\bether|HWaddr)\s+([0-9a-fA-F]{1,2}(?::[0-9a-fA-F]{1,2}){5})")
_IPV4 = re.compile(r"\b(\d+\.\d+\.\d+\.\d+)\b")
# ipconfig sale en el idioma de Windows, y las tildes llegan según la página de códigos de
# la consola: por eso «.» en vez de «ó» o «í».
_IPCONFIG_IP = re.compile(r"IPv4[^:]*:\s*(\d+\.\d+\.\d+\.\d+)")
_IPCONFIG_MASK = re.compile(r"(?:Subnet Mask|M.scara de subred)[^:]*:\s*(\d+\.\d+\.\d+\.\d+)", re.I)
_IPCONFIG_MAC = re.compile(
    r"(?:Physical Address|Direcci.n f.sica)[^:]*:\s*([0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2}){5})", re.I
)
_IPCONFIG_GATEWAY = re.compile(r"(?:Default Gateway|Puerta de enlace predeterminada)[^:]*:(.*)", re.I)


def _mask(text: str) -> str:
    if text.lower().startswith("0x"):  # macOS: netmask 0xffffff00
        return str(ipaddress.IPv4Address(int(text, 16)))
    return text


def _local(ip: str, mask: str, iface: str = "", mac: str = "", gateway: str | None = None) -> LocalNet | None:
    try:
        interface = ipaddress.ip_interface(f"{ip}/{mask}")
    except ValueError:
        return None
    if interface.ip.is_loopback or interface.ip.is_link_local:
        return None
    gw = None
    if gateway:
        try:
            gw = ipaddress.IPv4Address(gateway)
        except ValueError:
            gw = None
        if gw is not None and gw not in interface.network:
            gw = None
    return LocalNet(interface.network, interface.ip, iface, normalize(mac), gw)


def parse_ip_addr(output: str, macs: dict | None = None, gateways: dict | None = None) -> list[LocalNet]:
    """`ip -4 -o addr` (Linux): «2: wlan0    inet 192.168.1.23/24 brd ...»"""
    macs, gateways = macs or {}, gateways or {}
    nets = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[2] == "inet":
            iface = parts[1]
            m = _INET_LINUX.search(line)
            if m:
                nets.append(_local(m.group(1), m.group(2), iface, macs.get(iface, ""), gateways.get(iface)))
    return [n for n in nets if n]


def parse_ip_route(output: str) -> dict[str, str]:
    """`ip -4 route show default`: «default via 192.168.1.1 dev wlan0 ...» → {interfaz: router}"""
    gateways = {}
    for line in output.splitlines():
        parts = line.split()
        if "via" in parts and "dev" in parts:
            gateways.setdefault(parts[parts.index("dev") + 1], parts[parts.index("via") + 1])
    return gateways


def parse_ifconfig(output: str, gateway: str | None = None, gateway_iface: str = "") -> list[LocalNet]:
    """`ifconfig` (macOS y Linux antiguos). Cada interfaz es un bloque que empieza sin sangría."""
    blocks: list[tuple[str, list[str]]] = []
    for line in output.splitlines():
        if line and not line[0].isspace():
            blocks.append((line.split(":")[0].split()[0], [line]))
        elif blocks:
            blocks[-1][1].append(line)
    nets = []
    for iface, lines in blocks:
        text = "\n".join(lines)
        mac = m.group(1) if (m := _ETHER.search(text)) else ""
        gw = gateway if not gateway_iface or gateway_iface == iface else None
        for line in lines:
            # macOS: «inet 192.168.1.23 netmask 0xffffff00»; Linux antiguo: «inet addr:… Mask:…»
            ip, mask = _IFCONFIG_IP.search(line), _IFCONFIG_MASK.search(line)
            if ip and mask:
                nets.append(_local(ip.group(1), _mask(mask.group(1)), iface, mac, gw))
    return [n for n in nets if n]


def parse_route_get(output: str) -> tuple[str | None, str]:
    """`route -n get default` (macOS): las líneas «gateway: …» e «interface: …»."""
    gateway = re.search(r"gateway:\s*(\d+\.\d+\.\d+\.\d+)", output)
    iface = re.search(r"interface:\s*(\S+)", output)
    return (gateway.group(1) if gateway else None), (iface.group(1) if iface else "")


def parse_ipconfig(output: str) -> list[LocalNet]:
    """`ipconfig /all` (Windows, en inglés o en español). Cada adaptador es un bloque que
    empieza sin sangría y acaba en «:»; la puerta de enlace puede venir en la línea de
    debajo (cuando antes va la de IPv6)."""
    nets = []
    block: dict = {}

    def flush():
        for ip, mask in block.get("addresses", []):
            nets.append(_local(ip, mask, block.get("name", ""), block.get("mac", ""), block.get("gateway")))

    in_gateway = False
    for line in output.splitlines():
        if line and not line[0].isspace():
            if line.rstrip().endswith(":"):
                flush()
                block = {"name": line.rstrip(": ").strip(), "addresses": []}
            in_gateway = False
            continue
        if m := _IPCONFIG_GATEWAY.search(line):
            in_gateway = True
            if ip := _IPV4.search(m.group(1)):
                block.setdefault("gateway", ip.group(1))
            continue
        if in_gateway and line.strip() and " : " not in line:
            # Línea de continuación: solo una dirección, sin «Nombre . . . :» delante.
            if ip := _IPV4.fullmatch(line.strip()):
                block.setdefault("gateway", ip.group(1))
            continue
        in_gateway = False
        if m := _IPCONFIG_MAC.search(line):
            block["mac"] = m.group(1)
        elif m := _IPCONFIG_IP.search(line):
            block["pending"] = m.group(1)
        elif (m := _IPCONFIG_MASK.search(line)) and block.get("pending"):
            block["addresses"].append((block.pop("pending"), m.group(1)))
    flush()
    return [n for n in nets if n]


def _run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=5, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return ""
    # En Windows, las órdenes de consola escriben en la página de códigos OEM (850 en España).
    return result.stdout.decode("oem" if sys.platform == "win32" else "utf-8", errors="replace")


def _linux_macs() -> dict[str, str]:
    macs = {}
    for path in Path("/sys/class/net").glob("*/address"):
        try:
            macs[path.parent.name] = path.read_text().strip()
        except OSError:
            pass
    return macs


def local_networks() -> list[LocalNet]:
    """Las redes privadas a las que está conectado este ordenador (normalmente una: el
    wifi), la que lleva al router primero."""
    if sys.platform == "win32":
        nets = parse_ipconfig(_run(["ipconfig", "/all"]))
    elif sys.platform == "darwin":
        gateway, iface = parse_route_get(_run(["route", "-n", "get", "default"]))
        nets = parse_ifconfig(_run(["ifconfig"]), gateway, iface)
    else:
        gateways = parse_ip_route(_run(["ip", "-4", "route", "show", "default"]))
        nets = parse_ip_addr(_run(["ip", "-4", "-o", "addr"]), _linux_macs(), gateways)
        if not nets:
            nets = parse_ifconfig(_run(["ifconfig"]))
    if not nets:
        nets = _fallback()
    result = []
    for net in nets:
        if is_private(net.network) and net not in result:
            result.append(net)
    return sorted(result, key=lambda n: n.gateway is None)


def _fallback() -> list[LocalNet]:
    """Si no hay forma de preguntar al sistema: la IP con la que se sale a la red, en una /24."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # no se envía nada: solo elige por qué interfaz saldría
            ip = s.getsockname()[0]
    except OSError:
        return []
    net = _local(ip, "255.255.255.0")
    return [net] if net else []
