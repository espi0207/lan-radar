"""Lo que se ve llamando a la puerta: puertos conocidos, saludos y páginas de configuración.

Para cada aparato encontrado se prueba una lista corta de puertos (catalog.PORTS): los
que dicen qué es (631 = impresora, 62078 = iPhone, 8009 = Chromecast). Solo se abre la
conexión y se cierra; en los que se presentan solos se lee el saludo (SSH dice su
versión y a menudo el sistema: «OpenSSH_9.2p1 Debian»), y en los de web, el título de
la página y el servidor («Router Livebox», «HP LaserJet»).

También el nombre que le da el DNS de casa: muchos routers apuntan el nombre con el que
se presenta cada aparato al conectarse («Galaxy-S23.home»).
"""

from __future__ import annotations

import html
import http.client
import ipaddress
import re
import socket
import ssl

from . import parallel
from .catalog import PORTS

BANNER_PORTS = {21, 22}
# 7000: el receptor de AirPlay contesta con «Server: AirTunes/…» (Mac o Apple TV).
HTTP_PORTS = {80: False, 8080: False, 443: True, 8443: True, 5000: False, 5001: True, 7000: False}
_TITLE = re.compile(rb"<title[^>]*>(.*?)</title>", re.I | re.S)


def is_open(ip: str, port: int, timeout: float = 1.0) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((ip, port)) == 0


def open_ports(hosts, ports=None, timeout: float = 1.0, workers: int = 64) -> dict:
    """{IP: [puertos abiertos]} de cada aparato de `hosts`."""
    ports = sorted(ports or PORTS)
    pairs = [(str(h), p) for h in hosts for p in ports]
    found = parallel.run(
        lambda pair: is_open(*pair, timeout=timeout),
        pairs,
        workers=workers,
        timeout=timeout * (len(pairs) / workers + 2) + 5,
    )
    result: dict[ipaddress.IPv4Address, list[int]] = {}
    for (ip, port), opened in found.items():
        if opened:
            result.setdefault(ipaddress.IPv4Address(ip), []).append(port)
    return {ip: sorted(ports) for ip, ports in result.items()}


def banner(ip: str, port: int, timeout: float = 2.0) -> str:
    """La primera línea que manda el servicio nada más conectar (SSH, FTP)."""
    with socket.create_connection((ip, port), timeout=timeout) as sock:
        data = sock.recv(256)
    line = data.split(b"\n", 1)[0].decode("utf-8", errors="replace").strip()
    return "".join(c for c in line if c.isprintable())[:120]


def http_info(ip: str, port: int, tls: bool, timeout: float = 3.0) -> dict[str, str]:
    """El código de respuesta, la cabecera Server, adónde redirige y el <title> de la
    página principal. Sin seguir redirecciones: solo se mira el propio aparato."""
    if tls:
        # Los aparatos de casa usan certificados hechos por ellos mismos: no hay nada que
        # comprobar, solo se lee el título de la página.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        conn = http.client.HTTPSConnection(ip, port, timeout=timeout, context=context)
    else:
        conn = http.client.HTTPConnection(ip, port, timeout=timeout)
    try:
        conn.request("GET", "/", headers={"User-Agent": "lan-radar", "Connection": "close"})
        response = conn.getresponse()
        body = response.read(64 * 1024)
        info = {"status": str(response.status)}
        if server := response.getheader("Server"):
            info["server"] = _printable(server)
        if location := response.getheader("Location"):
            info["location"] = _printable(location)
        if m := _TITLE.search(body):
            title = html.unescape(m.group(1).decode("utf-8", errors="replace"))
            if title := " ".join(title.split()):
                info["title"] = _printable(title)
        return info
    finally:
        conn.close()


def _printable(text: str) -> str:
    return "".join(c for c in text if c.isprintable())[:120]


def details(ports_by_ip: dict, timeout: float = 3.0) -> tuple[dict, dict]:
    """Saludos y páginas web de los puertos abiertos: ({IP: {puerto: saludo}}, {IP: {puerto: info}})."""
    banner_jobs = [(str(ip), p) for ip, ports in ports_by_ip.items() for p in ports if p in BANNER_PORTS]
    http_jobs = [(str(ip), p) for ip, ports in ports_by_ip.items() for p in ports if p in HTTP_PORTS]
    banners = parallel.run(lambda job: banner(*job, timeout=timeout), banner_jobs, workers=16, timeout=timeout + 3)
    pages = parallel.run(
        lambda job: http_info(job[0], job[1], HTTP_PORTS[job[1]], timeout=timeout),
        http_jobs,
        workers=16,
        timeout=timeout * 2 + 3,
    )
    by_ip_banners: dict = {}
    for (ip, port), text in banners.items():
        if text:
            by_ip_banners.setdefault(ipaddress.IPv4Address(ip), {})[port] = text
    by_ip_pages: dict = {}
    for (ip, port), info in pages.items():
        by_ip_pages.setdefault(ipaddress.IPv4Address(ip), {})[port] = info
    return by_ip_banners, by_ip_pages


def reverse_dns(hosts, timeout: float = 4.0) -> dict:
    """{IP: nombre} según el DNS del sistema (normalmente, el del router)."""

    def lookup(ip):
        name = socket.gethostbyaddr(str(ip))[0]
        return "" if name == str(ip) else name

    names = parallel.run(lookup, list(hosts), workers=32, timeout=timeout)
    return {ipaddress.IPv4Address(str(ip)): name for ip, name in names.items() if name}
