"""Monta una red de casa de mentira en esta máquina (Linux, como root) y la desmonta.

    puente lrbr0 (192.168.77.2: "este ordenador")
      ├─ router      192.168.77.1   Sagemcom
      ├─ iphone      192.168.77.20  MAC privada
      ├─ chromecast  192.168.77.30  Google
      └─ …

Uso a mano:  sudo python tests/e2e/fake_lan.py   (Ctrl+C para desmontarla)
             y en otra terminal:  sudo lan-radar 192.168.77.0/24
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

BRIDGE = "lrbr0"
MY_IP = "192.168.77.2"
NETWORK = "192.168.77.0/24"
HERE = Path(__file__).resolve().parent

# nombre → (IP, MAC)
DEVICES = {
    "router": ("192.168.77.1", "00:0E:59:3A:7B:01"),
    "iphone": ("192.168.77.20", "DA:A1:19:5E:22:01"),
    "chromecast": ("192.168.77.30", "F4:F5:D8:6C:11:02"),
    "printer": ("192.168.77.40", "9C:8E:99:5A:1B:2C"),
    "windows": ("192.168.77.50", "F0:D5:BF:12:34:56"),
    "raspberry": ("192.168.77.60", "DC:A6:32:AB:CD:EF"),
    "plug": ("192.168.77.70", "A4:CF:12:9F:00:01"),
    "camera": ("192.168.77.80", "00:BC:99:44:55:66"),
    "tv": ("192.168.77.90", "8C:79:F5:12:34:56"),
}


def available() -> str:
    """Por qué no se puede montar aquí, o cadena vacía si se puede."""
    if not sys.platform.startswith("linux"):
        return "solo en Linux"
    if shutil.which("ip") is None:
        return "falta la orden ip (iproute2)"
    try:
        import os

        if os.geteuid() != 0:
            return "hace falta ser root (sudo)"
    except AttributeError:
        return "solo en Linux"
    return ""


def sh(*args: str, check: bool = True) -> None:
    subprocess.run(args, check=check, capture_output=True)


def ns(name: str) -> str:
    return f"lr-{name}"


@contextlib.contextmanager
def fake_lan():
    processes = []
    teardown()
    try:
        sh("ip", "link", "add", BRIDGE, "type", "bridge")
        # Sin "snooping", el puente reparte la multidifusión a todos, como un router de casa.
        sh("ip", "link", "set", BRIDGE, "type", "bridge", "mcast_snooping", "0")
        sh("ip", "addr", "add", f"{MY_IP}/24", "dev", BRIDGE)
        sh("ip", "link", "set", BRIDGE, "up")
        for i, (name, (ip, mac)) in enumerate(DEVICES.items()):
            veth = f"lrv{i}"
            sh("ip", "netns", "add", ns(name))
            sh("ip", "link", "add", veth, "type", "veth", "peer", "name", "eth0", "netns", ns(name))
            sh("ip", "link", "set", veth, "master", BRIDGE, "up")
            run = ("ip", "netns", "exec", ns(name))
            sh(*run, "ip", "link", "set", "eth0", "address", mac)
            sh(*run, "ip", "addr", "add", f"{ip}/24", "dev", "eth0")
            sh(*run, "ip", "link", "set", "eth0", "up")
            sh(*run, "ip", "link", "set", "lo", "up")
            sh(*run, "ip", "route", "add", "default", "dev", "eth0")
            processes.append(
                subprocess.Popen(
                    [*run, sys.executable, str(HERE / "fake_device.py"), name, ip, mac],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            )
        for process in processes:
            line = process.stdout.readline()
            if "listo" not in line:
                raise RuntimeError(f"un aparato de prueba no arranca: {line}{process.stdout.read()}")
        time.sleep(0.5)  # que los puertos del puente pasen a "forwarding"
        yield
    finally:
        for process in processes:
            process.kill()
            process.wait()
        teardown()


def teardown() -> None:
    for name in DEVICES:
        sh("ip", "netns", "del", ns(name), check=False)
    sh("ip", "link", "del", BRIDGE, check=False)


if __name__ == "__main__":
    if reason := available():
        sys.exit(f"No se puede montar la red de prueba: {reason}.")
    with fake_lan():
        print(f"Red de prueba {NETWORK} montada con {len(DEVICES)} aparatos. Ctrl+C para desmontarla.")
        with contextlib.suppress(KeyboardInterrupt):
            while True:
                time.sleep(1)
