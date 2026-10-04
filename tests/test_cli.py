import ipaddress
import json

import pytest

from lanradar import __main__ as cli
from lanradar import demo, net
from lanradar.history import History, network_key

HOME = net.LocalNet(
    ipaddress.ip_network("192.168.1.0/24"),
    ipaddress.ip_address("192.168.1.34"),
    "wlan0",
    "F0:D5:BF:12:34:56",
    ipaddress.ip_address("192.168.1.1"),
)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("LANRADAR_HOME", str(tmp_path))
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(cli.net, "local_networks", lambda: [HOME])


def test_demo(capsys):
    assert cli.main(["--demo"]) == 0
    out = capsys.readouterr().out
    assert "15 aparatos" in out and "iPhone de Ana" in out and "← nuevo" in out
    assert "Telnet" in out and "Portátil de Juan" in out


def test_demo_con_detalle(capsys):
    assert cli.main(["--demo", "--detalle"]) == 0
    out = capsys.readouterr().out
    assert "iPhone 14 Pro (iPhone15,2)" in out and "Por qué ese tipo" in out and "SSH-2.0-OpenSSH_9.2p1" in out


def test_json_por_pantalla(capsys):
    assert cli.main(["--demo", "--json", "-"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data["devices"]) == len(demo.devices()) and data["network"] == "192.168.1.0/24"


def test_json_a_un_archivo(tmp_path, capsys):
    out = tmp_path / "casa.json"
    assert cli.main(["--demo", "--json", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["devices"][0]["kind"] == "Router"
    assert "Todo guardado" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("red", "why"),
    [
        ("8.8.8.0/24", "no es una red privada"),
        ("10.0.0.0/16", "demasiado grande"),
        ("192.168.50.0/24", "no es la red de este ordenador"),
    ],
)
def test_no_revisa_otras_redes(red, why, capsys, monkeypatch):
    monkeypatch.setattr(cli, "scan", lambda *a, **k: pytest.fail("no debería ni empezar"))
    assert cli.main([red]) == 2
    assert why in capsys.readouterr().err


def test_revisa_la_red_del_wifi(capsys, monkeypatch):
    seen = {}

    def fake_scan(local, services, progress, history):
        seen.update(network=str(local.network), services=services)
        return demo.result()

    monkeypatch.setattr(cli, "scan", fake_scan)
    assert cli.main(["--rapido"]) == 0
    assert seen == {"network": "192.168.1.0/24", "services": False}
    assert "Router de casa" in capsys.readouterr().out


def test_sin_red(capsys, monkeypatch):
    monkeypatch.setattr(cli.net, "local_networks", lambda: [])
    assert cli.main([]) == 2
    assert "wifi" in capsys.readouterr().err


def test_redes(capsys):
    assert cli.main(["--redes"]) == 0
    assert "192.168.1.0/24 (wlan0): este ordenador es 192.168.1.34, router 192.168.1.1" in capsys.readouterr().out


def test_ponerle_nombre(capsys, monkeypatch):
    monkeypatch.setattr(cli.arp, "table", lambda: {HOME.gateway: "00:0E:59:3A:7B:01"})
    key = network_key("192.168.1.0/24", "00:0E:59:3A:7B:01")
    history = History()
    history.record(key, "192.168.1.0/24", demo.devices())
    history.save()

    assert cli.main(["--nombrar", "192.168.1.60", "Enchufe de la cafetera"]) == 0
    assert "se llamará «Enchufe de la cafetera»" in capsys.readouterr().out
    assert History().network(key)["devices"]["A4:CF:12:9F:00:01"]["nickname"] == "Enchufe de la cafetera"

    assert cli.main(["--nombrar", "a4:cf:12:9f:00:01", ""]) == 0
    assert "nickname" not in History().network(key)["devices"]["A4:CF:12:9F:00:01"]

    assert cli.main(["--nombrar", "192.168.1.250", "Nada"]) == 1
    assert "No conozco" in capsys.readouterr().err


def test_opciones_que_no_van_juntas(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--demo", "192.168.1.0/24"])
