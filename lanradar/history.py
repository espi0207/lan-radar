"""Lo que se acuerda lan-radar de una vez a otra: qué aparatos ha visto y cómo los llamas.

Así puede decir "este es nuevo" o "este estaba y ya no está", y recordar que el
«Aparato desconocido» de la .34 es «La Thermomix». Se guarda en un archivo JSON en la
carpeta de datos del usuario (o en LANRADAR_HOME, si existe esa variable).

Cada red se guarda aparte. Muchas casas usan la misma 192.168.1.0/24, así que la red se
reconoce por la MAC de su router; si no se sabe, por su dirección.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .device import Device

FILE = "conocidos.json"


def data_dir() -> Path:
    if custom := os.environ.get("LANRADAR_HOME"):
        return Path(custom)
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "lan-radar"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "lan-radar"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "lan-radar"


def network_key(network: str, gateway_mac: str = "") -> str:
    return f"router:{gateway_mac}" if gateway_mac else f"red:{network}"


class History:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / FILE
        self.data = {"version": 1, "networks": {}}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("networks"), dict):
                self.data = loaded
        except (OSError, ValueError):
            pass  # la primera vez no hay archivo; si está roto, se empieza de cero

    def network(self, key: str) -> dict:
        return self.data["networks"].setdefault(key, {"label": "", "scans": 0, "devices": {}})

    def record(self, key: str, label: str, devices: list[Device], when: datetime | None = None) -> list[dict]:
        """Apunta lo visto en esta pasada: marca los nuevos y les pone el nombre que les
        diste. Devuelve los que se habían visto antes y ahora no están."""
        when_text = (when or datetime.now()).isoformat(timespec="seconds")
        net = self.network(key)
        known = net["devices"]
        first_time = net["scans"] == 0
        seen = set()
        for device in devices:
            k = device.key()
            seen.add(k)
            entry = known.get(k)
            if entry is None:
                device.is_new = not first_time
                entry = known[k] = {"first_seen": when_text}
            device.nickname = entry.get("nickname", "")
            device.first_seen = entry.get("first_seen", when_text)
            device.last_seen = when_text
            entry.update(
                last_seen=when_text,
                ip=device.ip,
                mac=device.mac,
                kind=device.kind,
                name=device.name(),
                brand=device.brand,
            )
        missing = [dict(v, key=k) for k, v in known.items() if k not in seen]
        missing.sort(key=lambda v: v.get("last_seen", ""), reverse=True)
        net["label"] = label
        net["scans"] += 1
        net["last_scan"] = when_text
        return missing

    def is_first_scan(self, key: str) -> bool:
        return self.data["networks"].get(key, {}).get("scans", 0) <= 1

    def rename(self, key: str, device_key: str, nickname: str) -> None:
        entry = self.network(key)["devices"].setdefault(device_key, {})
        if nickname.strip():
            entry["nickname"] = nickname.strip()[:80]
        else:
            entry.pop("nickname", None)

    def forget(self, key: str, device_key: str) -> bool:
        return self.network(key)["devices"].pop(device_key, None) is not None

    def save(self) -> None:
        """Escribe a un temporal y lo cambia por el bueno: si se corta a medias, el de
        antes sigue entero."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".conocidos-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1, sort_keys=True)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
