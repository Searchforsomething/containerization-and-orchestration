import os
import time
import psycopg2

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_NAME = os.getenv("DB_NAME", "shop")
DB_USER = os.getenv("DB_USER", "shop")
DB_PASS = os.getenv("DB_PASS", "shop")

while True:
    try:
        conn = psycopg2.connect(
            host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )
        cur = conn.cursor()
        cur.execute(
            "UPDATE orders SET processed = true WHERE processed = false RETURNING id"
        )
        updated = cur.fetchall()
        conn.commit()
        cur.close()
        conn.close()
        if updated:
            print(f"Processed orders: {[u[0] for u in updated]}", flush=True)
    except Exception as e:
        print(f"Error: {e}", flush=True)
    time.sleep(5)