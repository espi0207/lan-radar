"""Quién fabricó cada aparato, a partir de su MAC.

Los tres primeros bytes de una MAC son el OUI, que el IEEE asigna a cada fabricante. La
lista va dentro del paquete (data/oui.txt.gz, unas 38 000 marcas) y se regenera con
scripts/update_oui.py.

Los móviles de hoy no enseñan su MAC de verdad en cada wifi: se inventan una ("dirección
privada" en iPhone, "MAC aleatoria" en Android) y la marcan como "administrada
localmente". Esa no tiene fabricante, pero sí dice algo: casi seguro que es un móvil, una
tableta o un ordenador moderno.
"""

from __future__ import annotations

import gzip
import re
from functools import cache
from importlib import resources

_HEX = re.compile(r"[0-9a-fA-F]+")

# Los nombres del registro son los de la empresa ("HUAWEI TECHNOLOGIES CO.,LTD"), y la misma
# marca sale escrita de varias formas. Para la tabla basta con la marca: primero se busca
# en esta lista (la primera que encaje, por eso las más concretas van antes) y, si no está,
# se le quita la forma jurídica (short_vendor).
BRANDS = [
    ("apple", "Apple"),
    ("samsung", "Samsung"),
    ("huawei", "Huawei"),
    ("honor device", "Honor"),
    ("xiaomi", "Xiaomi"),
    ("guangdong oppo", "OPPO"),
    ("vivo mobile", "vivo"),
    ("oneplus", "OnePlus"),
    ("realme", "realme"),
    ("motorola mobility", "Motorola"),
    ("nothing technology", "Nothing"),
    ("fairphone", "Fairphone"),
    ("nest labs", "Google Nest"),
    ("google", "Google"),
    ("amazon", "Amazon"),
    ("raspberry pi", "Raspberry Pi"),
    ("tp-link", "TP-Link"),
    ("sagemcom", "Sagemcom"),
    ("zte corporation", "ZTE"),
    ("askey", "Askey"),
    ("mitrastar", "MitraStar"),
    ("arcadyan", "Arcadyan"),
    ("sercomm", "Sercomm"),
    ("comtrend", "Comtrend"),
    ("fiberhome", "FiberHome"),
    ("avm audiovisuelles", "AVM (FRITZ!Box)"),
    ("zyxel", "Zyxel"),
    ("netgear", "Netgear"),
    ("d-link", "D-Link"),
    ("ubiquiti", "Ubiquiti"),
    ("asustek", "ASUS"),
    ("cisco", "Cisco"),
    ("hewlett packard enterprise", "HPE"),
    ("hewlett packard", "HP"),
    ("hp inc", "HP"),
    ("seiko epson", "Epson"),
    ("canon", "Canon"),
    ("brother industries", "Brother"),
    ("intel corporate", "Intel"),
    ("intel corporation", "Intel"),
    ("dell", "Dell"),
    ("lenovo", "Lenovo"),
    ("microsoft", "Microsoft"),
    ("sony interactive", "Sony PlayStation"),
    ("sony", "Sony"),
    ("nintendo", "Nintendo"),
    ("lg electronics", "LG"),
    ("lg innotek", "LG"),
    ("hisense", "Hisense"),
    ("tcl", "TCL"),
    ("roku", "Roku"),
    ("sonos", "Sonos"),
    ("philips lighting", "Philips Hue"),
    ("signify", "Philips Hue"),
    ("synology", "Synology"),
    ("qnap", "QNAP"),
    ("hangzhou hikvision", "Hikvision"),
    ("ezviz", "EZVIZ"),
    ("reolink", "Reolink"),
    ("wyze", "Wyze"),
    ("tuya", "Tuya"),
    ("meross", "Meross"),
    ("espressif", "Espressif"),
    ("garmin", "Garmin"),
    ("fitbit", "Fitbit"),
    ("withings", "Withings"),
    ("dyson", "Dyson"),
    ("hon hai", "Foxconn"),
    ("liteon", "Lite-On"),
    ("azurewave", "AzureWave"),
    ("murata", "Murata"),
    ("realtek", "Realtek"),
    ("universal global scientific", "USI"),
    ("chongqing fugui", "Fugui"),
    ("compal", "Compal"),
    ("pegatron", "Pegatron"),
    ("wistron", "Wistron"),
    ("quanta", "Quanta"),
    ("chicony", "Chicony"),
    ("texas instruments", "Texas Instruments"),
    ("silicon laboratories", "Silicon Labs"),
    ("sky uk", "Sky"),
]
_BRANDS = [(re.compile(r"\b" + re.escape(key) + r"\b", re.I), brand) for key, brand in BRANDS]

_SUFFIX = re.compile(
    r"[\s,.(]*\b(co|company|corp|corporation|inc|incorporated|ltd|limited|llc|gmbh|ag|s\.?a\.?s?|b\.?v|"
    r"plc|pte|pty|oy|ab|srl|s\.?p\.?a|kg|co\.,? ?ltd|technolog(y|ies)|electronics?|communications?|"
    r"international|holdings?|group|industr(y|ies|ial)|manufacturing|systems?)\b[.,)]*\s*$",
    re.I,
)


def normalize(mac: str) -> str:
    """«aa-bb-cc-dd-ee-ff», «aabb.ccdd.eeff» o «0:1b:2:…» (macOS quita los ceros) →
    «AA:BB:CC:DD:EE:FF». Si no parece una MAC, cadena vacía."""
    parts = _HEX.findall(mac)
    if len(parts) == 6 and all(len(p) <= 2 for p in parts):
        digits = "".join(p.zfill(2) for p in parts)
    elif len(parts) == 3 and all(len(p) == 4 for p in parts):
        digits = "".join(parts)
    elif len(parts) == 1 and len(parts[0]) == 12:
        digits = parts[0]
    else:
        return ""
    digits = digits.upper()
    return ":".join(digits[i : i + 2] for i in range(0, 12, 2))


def is_random(mac: str) -> bool:
    """MAC inventada por el propio aparato (bit "administrada localmente")."""
    mac = normalize(mac)
    return bool(mac) and bool(int(mac[:2], 16) & 0x02)


def is_device(mac: str) -> bool:
    """Descarta lo que no es un aparato: la de difusión, las de multidifusión y la de ceros."""
    mac = normalize(mac)
    return bool(mac) and mac != "00:00:00:00:00:00" and not int(mac[:2], 16) & 0x01


@cache
def _table() -> dict[str, str]:
    data = resources.files("lanradar").joinpath("data/oui.txt.gz").read_bytes()
    table = {}
    for line in gzip.decompress(data).decode("utf-8").splitlines():
        prefix, _, name = line.partition("\t")
        table[prefix] = name
    return table


def vendor(mac: str) -> str:
    """El fabricante tal como está en el registro, o cadena vacía si no se sabe."""
    mac = normalize(mac)
    if not mac or is_random(mac):
        return ""
    return _table().get(mac.replace(":", "")[:6], "")


def short_vendor(name: str) -> str:
    """La marca sin la forma jurídica: «Shenzhen Foo Technology Co.,Ltd» → «Shenzhen Foo»."""
    if not name:
        return ""
    for pattern, brand in _BRANDS:
        if pattern.search(name):
            return brand
    short = name
    while True:
        trimmed = _SUFFIX.sub("", short).strip(" ,.-")
        if trimmed == short or not trimmed:
            break
        short = trimmed
    if short.isupper() and len(short) > 4:
        short = short.title()
    return short
