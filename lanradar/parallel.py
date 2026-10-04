"""Hacer muchas esperas a la vez, con un límite de tiempo para todas.

Preguntar a 30 aparatos uno detrás de otro, con un segundo de espera cada uno, son 30
segundos. A la vez, uno. Los hilos son "daemon": si alguno se queda colgado (una búsqueda
de DNS que no vuelve), no impide que el programa termine.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable, Iterable


def run(func: Callable, items: Iterable, workers: int = 32, timeout: float = 30.0) -> dict:
    """{item: func(item)} de los que acaban antes de `timeout` sin lanzar una excepción."""
    todo: queue.Queue = queue.Queue()
    items = list(items)
    for item in items:
        todo.put(item)
    results: dict = {}
    lock = threading.Lock()

    def worker():
        while True:
            try:
                item = todo.get_nowait()
            except queue.Empty:
                return
            try:
                value = func(item)
            except Exception:  # un aparato que contesta algo raro no para a los demás
                continue
            with lock:
                results[item] = value

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(min(workers, len(items)))]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout
    for thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))
    with lock:
        return dict(results)
