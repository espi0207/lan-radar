import threading
import time

from lanradar import parallel


def test_no_new_work_starts_after_the_time_limit():
    # Antes, pasado el límite, los hilos seguían cogiendo trabajo y abriendo conexiones
    # mientras el programa ya estaba en la fase siguiente.
    started = []
    lock = threading.Lock()

    def slow(item):
        with lock:
            started.append(item)
        time.sleep(0.2)
        return item

    results = parallel.run(slow, range(20), workers=1, timeout=0.3)
    time.sleep(0.6)
    assert len(results) <= 2
    assert len(started) <= 3  # el que estaba en marcha al cortar puede acabar, pero no empieza otro


def test_everything_finishes_when_there_is_time():
    assert parallel.run(lambda x: x * 2, range(10), workers=4, timeout=5) == {i: i * 2 for i in range(10)}
