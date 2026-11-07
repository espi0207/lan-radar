"""Tipos y pistas añadidos en noviembre de 2026."""

import pytest

from lanradar.catalog import (
    APPLIANCE,
    CAMERA,
    CONSOLE,
    KINDS,
    NAMES,
    SERVER,
    SMART_HOME,
    SPEAKER,
    STREAMER,
    TABLET,
    TV,
    VACUUM,
    VM,
)
from lanradar.device import ALTA, MEDIA, Device, finish


def svc(stype, name="", port=0, **txt):
    return {"type": stype, "name": name, "port": port, "txt": txt}


@pytest.mark.parametrize("kind", [VACUUM, APPLIANCE, VM, SERVER])
def test_new_kinds_are_complete(kind):
    assert kind in KINDS and kind in NAMES


@pytest.mark.parametrize(
    ("mac", "platform"),
    [
        ("00:0C:29:12:34:56", "VMware"),
        ("00:50:56:AB:CD:EF", "VMware"),
        ("08:00:27:11:22:33", "VirtualBox"),
        ("52:54:00:12:34:56", "QEMU/KVM"),  # MAC «administrada localmente», pero no es de un móvil
        ("00:15:5D:01:02:03", "Hyper-V"),
        ("00:1C:42:00:00:01", "Parallels"),
    ],
)
def test_virtual_machines_by_mac(mac, platform):
    device = finish(Device("1", mac))
    assert (device.kind, device.brand) == (VM, platform)
    assert device.random_mac is False
    assert not any("MAC privada" in n["text"] for n in device.notes)


@pytest.mark.parametrize(
    ("device", "kind"),
    [
        (Device("1", "B0:4A:39:00:00:01"), VACUUM),  # Roborock
        (Device("1", dns_name="roborock-vacuum-a15.home"), VACUUM),
        (Device("1", mdns_name="iRobot-1234ABCD.local"), VACUUM),
        (Device("1", dns_name="Conga-7490.home"), VACUUM),
        (Device("1", dns_name="BSH-Lavadora-WAX32.home"), APPLIANCE),
        (Device("1", friendly_name="Frigorífico"), APPLIANCE),
        (Device("1", dns_name="aire-acondicionado-salon.home"), APPLIANCE),
        (Device("1", ports=[8006]), SERVER),  # Proxmox
        (Device("1", web={"443": {"title": "VMware ESXi", "server": ""}}), SERVER),
        (Device("1", ports=[1400]), SPEAKER),  # Sonos
        (Device("1", ports=[8060]), STREAMER),  # Roku
        (Device("1", ports=[37777]), CAMERA),  # Dahua
        (Device("1", ports=[34567]), CAMERA),  # grabadores XMEye
        (Device("1", ports=[6668]), SMART_HOME),  # Tuya
        (Device("1", ports=[9999]), SMART_HOME),  # TP-Link Kasa
        (Device("1", services=[svc("_ewelink._tcp", "x")]), SMART_HOME),
        (Device("1", services=[svc("_dyson_mqtt._tcp", "x")]), SMART_HOME),
        (Device("1", services=[svc("_xbmc-jsonrpc._tcp", "Kodi")]), STREAMER),
        (Device("1", dns_name="steamdeck.home"), CONSOLE),
        (Device("1", dns_name="kindle-ana.home"), TABLET),
        (Device("1", dns_name="Philips-TV.home"), TV),
    ],
)
def test_new_hints(device, kind):
    assert finish(device).kind == kind


def test_open_adb_on_an_android_is_a_high_risk_note():
    device = finish(Device("1", "6E:3B:90:11:A4:0C", ports=[5555], dns_name="android-tv.home"))
    [adb] = [n for n in device.notes if "ADB" in n["text"]]
    assert adb["level"] == ALTA


def test_cheap_dvr_ports_get_a_note():
    device = finish(Device("1", ports=[34567]))
    assert any(n["level"] == MEDIA and "34567" in n["text"] for n in device.notes)


def test_databases_open_to_the_lan_get_a_note():
    device = finish(Device("1", ports=[3306, 6379]))
    texts = " ".join(n["text"] for n in device.notes)
    assert "MySQL" in texts and "Redis" in texts
