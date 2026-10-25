import os
import threading
import time
from contextlib import contextmanager

import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from flask import Flask, Response, g, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

app = Flask(__name__)

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_NAME = os.getenv("DB_NAME", "shop")
DB_USER = os.getenv("DB_USER", "shop")
DB_PASS = os.getenv("DB_PASS", "shop")
# Пул соединений: без него каждый заказ — это connect(), то есть fork
# backend-процесса и SCRAM-аутентификация в postgres. Под перегрузкой
# именно это съедало CPU postgres и копило процессы до OOM.
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
DB_POOL_TIMEOUT = float(os.getenv("DB_POOL_TIMEOUT", "3"))

# Метка называется path, а не endpoint: prometheus-operator сам вешает
# на таргет метку endpoint (имя порта), и наша бы переименовалась.
REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "Request duration in seconds",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.5, 5.0),
)


def get_conn():
    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS,
        connect_timeout=3,
    )


_pool = None
_pool_lock = threading.Lock()
# ThreadedConnectionPool при исчерпании сразу бросает PoolError, а нам
# нужно подождать свободное соединение — поэтому семафор на размер пула.
_pool_slots = threading.BoundedSemaphore(DB_POOL_SIZE)


def get_pool():
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadedConnectionPool(
                1, DB_POOL_SIZE,
                host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS,
                connect_timeout=3,
            )
        return _pool


@contextmanager
def db():
    if not _pool_slots.acquire(timeout=DB_POOL_TIMEOUT):
        raise RuntimeError("no free DB connection in pool")
    try:
        pool = get_pool()
        conn = pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            # соединение могло умереть (рестарт postgres) — не возвращаем
            # его в пул, следующий запрос откроет новое
            pool.putconn(conn, close=True)
            raise
        else:
            pool.putconn(conn)
    finally:
        _pool_slots.release()


def ensure_schema():
    # Таблицу создаёт сам api: postgres из CNPG поднимается пустым.
    while True:
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "CREATE TABLE IF NOT EXISTS orders ("
                "id SERIAL PRIMARY KEY, item TEXT NOT NULL, "
                "processed BOOLEAN NOT NULL DEFAULT false)"
            )
            conn.commit()
            cur.close()
            conn.close()
            print("Schema is ready", flush=True)
            return
        except Exception as e:
            print(f"Waiting for postgres: {e}", flush=True)
            time.sleep(2)


@app.before_request
def start_timer():
    g.start = time.perf_counter()


@app.after_request
def record_metrics(response):
    if request.path in ("/metrics", "/health"):
        return response
    path = request.url_rule.rule if request.url_rule else "unknown"
    REQUESTS_TOTAL.labels(request.method, path, str(response.status_code)).inc()
    REQUEST_DURATION.labels(request.method, path).observe(time.perf_counter() - g.start)
    return response


@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.route("/health")
def health():
    if os.getenv("HEALTH_FAIL", "").lower() == "true":
        return "fail", 500
    return "ok", 200


@app.route("/order", methods=["POST"])
def create_order():
    data = request.get_json(silent=True) or {}
    try:
        with db() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO orders (item, processed) VALUES (%s, false) RETURNING id",
                (data.get("item", "unknown"),),
            )
            order_id = cur.fetchone()[0]
    except Exception as e:
        # Явный 500, чтобы ошибка попала в метрики (after_request не
        # вызывается при необработанном исключении).
        return jsonify({"error": str(e)}), 500
    return jsonify({"id": order_id}), 201


@app.route("/orders")
def list_orders():
    try:
        with db() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, item, processed FROM orders ORDER BY id DESC LIMIT 100")
            rows = cur.fetchall()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify([{"id": r[0], "item": r[1], "processed": r[2]} for r in rows])


if __name__ == "__main__":
    threading.Thread(target=ensure_schema, daemon=True).start()
    app.run(host="0.0.0.0", port=8080, threaded=True)
