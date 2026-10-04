"""Enviar preguntas por UDP y recoger lo que conteste cada aparato durante un rato.

mDNS, SSDP y NetBIOS funcionan igual: se manda una pregunta (a un aparato o a todos a la
vez, por multidifusión) y las respuestas van llegando de cualquiera. Aquí está lo común:
un socket atado a la IP de este ordenador en la red que se revisa (para que la pregunta
salga por el wifi y no por una VPN o una máquina virtual) y un bucle que recoge hasta que
se acaba el tiempo.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Callable, Iterable

MAX_PACKET = 65535


def open_socket(local_ip: str, multicast_ttl: int = 0) -> socket.socket:
    """Un socket atado a la IP de este ordenador. Con multicast_ttl, listo para preguntar a
    todos: el TTL dice cuántos routers puede cruzar la pregunta (mDNS, que no sale de la
    red, pide 255 en RFC 6762 §11; SSDP, 2 según UPnP)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.bind((local_ip, 0))
    if multicast_ttl:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, multicast_ttl)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 0)
    return sock


def send_all(sock: socket.socket, packets: Iterable[tuple[bytes, tuple[str, int]]]) -> int:
    """Envía sin pararse por los errores de un destino (un aparato que ya no está puede
    dar «host unreachable» en macOS). Devuelve cuántos han salido."""
    sent = 0
    for data, addr in packets:
        try:
            sock.sendto(data, addr)
            sent += 1
        except OSError:
            pass
    return sent


def collect(sock: socket.socket, seconds: float, handle: Callable[[str, int, bytes], None]) -> None:
    """Llama a handle(ip, puerto, datos) con cada respuesta hasta que pasen `seconds`."""
    deadline = time.monotonic() + seconds
    errors = 0
    while (left := deadline - time.monotonic()) > 0:
        sock.settimeout(left)
        try:
            data, (ip, port) = sock.recvfrom(MAX_PACKET)
        except TimeoutError:
            break
        except OSError:
            # En Windows, un ICMP «puerto cerrado» de un envío anterior llega como error
            # (WSAECONNRESET) en el siguiente recvfrom. No es nuestro problema: a seguir.
            errors += 1
            if errors > 2000:  # un socket roto de verdad: no dar vueltas en balde
                break
            continue
        handle(ip, port, data)
