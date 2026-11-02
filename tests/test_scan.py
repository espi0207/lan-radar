"""El escaneo entero con la red simulada: qué se cuenta como conectado y qué como desaparecido."""

import ipaddress

import pytest

from lanradar import net, scan
from lanradar.history import History

IP = ipaddress.ip_address
ROUTER, ME, LEFT = IP("192.168.1.1"), IP("192.168.1.2"), IP("192.168.1.50")
MACS = {ROUTER: "00:0e:59:3a:7b:01", ME: "aa:aa:aa:aa:aa:02", LEFT: "3c:22:fb:00:00:50"}


@pytest.fixture
def lan(monkeypatch):
    """Red de mentira: lo que devuelve cada pregunta se puede cambiar en cada prueba."""
    state = {"arp": [dict(MACS), dict(MACS)], "calls": 0}

    def table():
        snapshots = state["arp"]
        snap = snapshots[min(state["calls"], len(snapshots) - 1)]
        state["calls"] += 1
        return dict(snap)

    monkeypatch.setattr(scan.arp, "table", table)
    monkeypatch.setattr(scan.netbios, "query", lambda *a, **k: {})
    monkeypatch.setattr(scan.mdns, "query", lambda *a, **k: {})
    monkeypatch.setattr(scan.ssdp, "query", lambda *a, **k: {})
    monkeypatch.setattr(scan.probe, "reverse_dns", lambda *a, **k: {})
    return state


def local(network="192.168.1.0/24"):
    return net.LocalNet(ipaddress.ip_network(network), ME, "wlan0", MACS[ME], gateway=ROUTER)


def test_device_only_in_the_old_arp_cache_is_not_connected(lan):
    # .50 estaba en la caché ARP al empezar, pero tras preguntar a toda la red ya no contesta.
    gone = {ip: mac for ip, mac in MACS.items() if ip != LEFT}
    lan["arp"] = [dict(MACS), gone, gone, gone]
    result = scan.scan(local(), services=False)
    assert str(LEFT) not in {d.ip for d in result.devices}


def test_scanning_part_of_the_network_does_not_report_the_rest_as_missing(lan, tmp_path):
    history = History(tmp_path / "conocidos.json")
    far = IP("192.168.1.200")
    lan["arp"] = [{**MACS, far: "3c:22:fb:00:00:c8"}]
    scan.scan(local(), services=False, history=history)
    lan["calls"], lan["arp"] = 0, [dict(MACS)]
    result = scan.scan(local("192.168.1.0/25"), services=False, history=history)  # .200 no entra en /25
    assert "192.168.1.200" not in {m.get("ip") for m in result.missing}
