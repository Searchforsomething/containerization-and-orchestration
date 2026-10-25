"""Заглушка «ночной аналитики»: бесконечно жрёт CPU и память, ничего не делая.

BATCH_MEMORY_MB  — сколько памяти держать (набирается постепенно, чтобы
                   kubelet успел заметить давление и выселить под до того,
                   как придёт OOM-killer ядра);
BATCH_STEP_MB    — шаг набора памяти в секунду;
BATCH_CPU_DUTY   — доля времени, которую процесс крутит CPU (0..1).
"""
import hashlib
import os
import time

MEMORY_MB = int(os.getenv("BATCH_MEMORY_MB", "100"))
STEP_MB = int(os.getenv("BATCH_STEP_MB", "20"))
CPU_DUTY = float(os.getenv("BATCH_CPU_DUTY", "1.0"))

hog = []
held_mb = 0
print(f"batch: target memory {MEMORY_MB} MiB, step {STEP_MB} MiB/s, cpu duty {CPU_DUTY}", flush=True)

while True:
    tick = time.monotonic()

    if held_mb < MEMORY_MB:
        chunk = min(STEP_MB, MEMORY_MB - held_mb)
        # b"\x01" * n реально записывает страницы, так что память
        # попадает в working set, а не остаётся ленивым резервом.
        hog.append(b"\x01" * (chunk * 1024 * 1024))
        held_mb += chunk
        print(f"batch: holding {held_mb} MiB", flush=True)

    digest = b""
    while time.monotonic() - tick < CPU_DUTY:
        digest = hashlib.sha256(digest).digest()

    rest = 1.0 - (time.monotonic() - tick)
    if rest > 0:
        time.sleep(rest)
