import os
import sys

import pytest

tk = pytest.importorskip("tkinter")

from lanradar import gui  # noqa: E402


@pytest.mark.skipif(
    sys.platform.startswith("linux") and not os.environ.get("DISPLAY"),
    reason="en Linux hace falta una pantalla (en la CI, xvfb-run)",
)
def test_la_ventana_carga_la_demo_pone_nombre_y_exporta(tmp_path, monkeypatch):
    # Lo mismo que hace la CI con el programa ya instalado.
    monkeypatch.setenv("LANRADAR_HOME", str(tmp_path))
    assert gui.self_check() == 0
