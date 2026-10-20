import os
import psycopg2
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_NAME = os.getenv("DB_NAME", "shop")
DB_USER = os.getenv("DB_USER", "shop")
DB_PASS = os.getenv("DB_PASS", "shop")

def get_conn():
    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )

@app.route("/health")
def health():
    if os.getenv("HEALTH_FAIL", "").lower() == "true":
        return "fail", 500
    return "ok", 200

@app.route("/order", methods=["POST"])
def create_order():
    data = request.get_json()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orders (item, processed) VALUES (%s, false) RETURNING id",
        (data["item"],),
    )
    order_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"id": order_id}), 201

@app.route("/orders")
def list_orders():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, item, processed FROM orders ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{"id": r[0], "item": r[1], "processed": r[2]} for r in rows])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)