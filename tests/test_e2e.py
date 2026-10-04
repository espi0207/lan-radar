"""La prueba de verdad: una red de casa de mentira (tests/e2e/fake_lan.py) con nueve
aparatos que contestan como los reales, y lan-radar revisándola con paquetes de verdad.

Necesita Linux y ser root (crea "namespaces" de red), así que solo se hace si se pide:
    sudo LANRADAR_E2E=1 python -m pytest tests/test_e2e.py
La CI la hace en cada cambio.
"""

import ipaddress
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "e2e"))
import fake_lan  # noqa: E402

from lanradar import net, scan  # noqa: E402
from lanradar.catalog import CAMERA, COMPUTER, MOBILE, PRINTER, ROUTER, SMART_HOME, STREAMER, TV  # noqa: E402
from lanradar.history import History  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.environ.get("LANRADAR_E2E") or bool(fake_lan.available()),
    reason=f"prueba con red de mentira: {fake_lan.available() or 'pon LANRADAR_E2E=1 para hacerla'}",
)


@pytest.fixture(scope="module")
def lan():
    with fake_lan.fake_lan():
        yield


def test_encuentra_y_reconoce_cada_aparato(lan, tmp_path):
    local = net.LocalNet(
        ipaddress.ip_network(fake_lan.NETWORK),
        ipaddress.ip_address(fake_lan.MY_IP),
        "lrbr0",
        gateway=ipaddress.ip_address("192.168.77.1"),
    )
    result = scan.scan(local, history=History(tmp_path / "conocidos.json"))
    found = {d.ip: d for d in result.devices}
    expected = {ip for ip, _mac in fake_lan.DEVICES.values()} | {fake_lan.MY_IP}
    assert set(found) == expected

    by_name = {name: found[ip] for name, (ip, _mac) in fake_lan.DEVICES.items()}
    for name, (_ip, mac) in fake_lan.DEVICES.items():
        assert by_name[name].mac == mac, name  # de la tabla ARP

    router = by_name["router"]
    assert (router.kind, router.name(), router.model, router.brand) == (
        ROUTER,
        "Router de casa",
        "F@st 5657",
        "Sagemcom",
    )
    assert any("UPnP" in n["text"] for n in router.notes)

    iphone = by_name["iphone"]
    assert (iphone.kind, iphone.name(), iphone.model, iphone.os) == (
        MOBILE,
        "iPhone de Ana",
        "iPhone 14 Pro (iPhone15,2)",
        "iOS",
    )
    assert iphone.random_mac and iphone.mdns_name == "iPhone-de-Ana.local" and 62078 in iphone.ports

    chromecast = by_name["chromecast"]
    assert (chromecast.kind, chromecast.name(), chromecast.model) == (STREAMER, "Salón", "Chromecast")

    printer = by_name["printer"]
    assert (printer.kind, printer.model) == (PRINTER, "HP LaserJet M110w")
    assert printer.web["80"]["title"] == "HP LaserJet M110w"

    windows = by_name["windows"]
    assert (windows.kind, windows.netbios_name, windows.workgroup) == (COMPUTER, "PORTATIL-ANA", "WORKGROUP")

    raspberry = by_name["raspberry"]
    assert (raspberry.kind, raspberry.os, raspberry.mdns_name) == (COMPUTER, "Debian", "homeassistant.local")
    assert raspberry.banners["22"].startswith("SSH-2.0-OpenSSH_9.2p1")

    assert by_name["plug"].kind == SMART_HOME and by_name["plug"].ports == []  # solo ARP, y aun así está
    camera = by_name["camera"]
    assert camera.kind == CAMERA and camera.notes[0]["level"] == "alta"  # Telnet
    tv = by_name["tv"]
    assert (tv.kind, tv.model, tv.friendly_name) == (TV, "QE55Q60B", "[TV] Tele del salón")


def test_la_orden_entera(lan, tmp_path):
    env = dict(os.environ, LANRADAR_HOME=str(tmp_path), NO_COLOR="1")
    run = [sys.executable, "-m", "lanradar", fake_lan.NETWORK, "--rapido"]
    first = subprocess.run(run, capture_output=True, text=True, env=env, timeout=120)
    assert first.returncode == 0, first.stderr
    assert "10 aparatos" in first.stdout and "iPhone de Ana" in first.stdout
    assert "primera vez" in first.stdout

    second = subprocess.run(run, capture_output=True, text=True, env=env, timeout=120)
    assert second.returncode == 0 and "← nuevo" not in second.stdout  # la segunda vez, nada es nuevo
