"""Regenera lanradar/data/oui.txt.gz, la lista de fabricantes por MAC.

Los tres primeros bytes de una MAC (el OUI) dicen quién fabricó la tarjeta de red. El
registro es público y lo publica el IEEE. Este script lo descarga (o lo lee de un archivo
que ya tengas) y lo deja en el formato que usa lan-radar: «PREFIJO<tab>Fabricante» por
línea, comprimido y siempre igual byte a byte para que git no vea cambios si no los hay.

Uso:
    python scripts/update_oui.py                 # descarga https://standards-oui.ieee.org/oui/oui.txt
    python scripts/update_oui.py oui.txt         # el oui.txt del IEEE ya descargado
    python scripts/update_oui.py mac-vendors.txt # o una lista «PREFIJO:Fabricante»
"""

from __future__ import annotations

import gzip
import re
import sys
import urllib.request
from pathlib import Path

URL = "https://standards-oui.ieee.org/oui/oui.txt"
OUT = Path(__file__).resolve().parent.parent / "lanradar" / "data" / "oui.txt.gz"

IEEE_LINE = re.compile(r"^([0-9A-F]{6})\s+\(base 16\)\s+(.+)$")
SIMPLE_LINE = re.compile(r"^([0-9A-Fa-f]{6}):(.+)$")
# Bloques que el IEEE reparte en trozos más pequeños (MA-M y MA-S): el prefijo de 3 bytes
# no dice de quién es el aparato.
NOT_A_VENDOR = {"IEEE Registration Authority", "Private"}


def parse(text: str) -> dict[str, str]:
    vendors = {}
    for line in text.splitlines():
        line = line.strip()
        m = IEEE_LINE.match(line) or SIMPLE_LINE.match(line)
        if not m:
            continue
        prefix, name = m.group(1).upper(), " ".join(m.group(2).split())
        if name and name not in NOT_A_VENDOR:
            vendors.setdefault(prefix, name)
    return vendors


def main(argv: list[str]) -> int:
    if argv:
        text = Path(argv[0]).read_text(encoding="utf-8", errors="replace")
    else:
        request = urllib.request.Request(URL, headers={"User-Agent": "lan-radar"})
        with urllib.request.urlopen(request, timeout=60) as response:
            text = response.read().decode("utf-8", errors="replace")
    vendors = parse(text)
    if len(vendors) < 10_000:
        print(f"Solo {len(vendors)} fabricantes: ¿seguro que es la lista buena?", file=sys.stderr)
        return 1
    data = "".join(f"{prefix}\t{name}\n" for prefix, name in sorted(vendors.items())).encode("utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0, filename="") as gz:
        gz.write(data)
    print(f"{len(vendors)} fabricantes en {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
