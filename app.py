import os
import time

from flask import Flask, jsonify, request
import psycopg2
import redis

app = Flask(__name__)

DB_HOST = os.getenv("DB_HOST", "db")
DB_NAME = os.getenv("DB_NAME", "tasks")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "admin")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))


def wait_for_postgres(retries=20, delay=2):
    for _ in range(retries):
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
            )
            conn.close()
            return
        except psycopg2.OperationalError:
            time.sleep(delay)
    raise RuntimeError("PostgreSQL indisponible")


def wait_for_redis(retries=20, delay=2):
    for _ in range(retries):
        try:
            client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=0,
                decode_responses=True,
            )
            client.ping()
            return client
        except redis.exceptions.RedisError:
            time.sleep(delay)
    raise RuntimeError("Redis indisponible")


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL
        )
        """
    )
    conn.commit()
    cur.close()
    conn.close()


wait_for_postgres()
redis_client = wait_for_redis()
init_db()


@app.route("/", methods=["GET"])
def home():
    visits = redis_client.incr("home_visits")
    return jsonify({
        "message": "Bienvenue sur MiniCloud API!",
        "home_visits": visits,
    })


@app.route("/tasks", methods=["GET"])
def get_tasks():
    visits = redis_client.incr("tasks_visits")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, title FROM tasks ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    tasks = [{"id": row[0], "title": row[1]} for row in rows]
    return jsonify({"visits": visits, "tasks": tasks})


@app.route("/tasks", methods=["POST"])
def add_task():
    data = request.get_json(silent=True)

    if not data or not data.get("title"):
        return jsonify({"error": "Title is required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tasks (title) VALUES (%s) RETURNING id",
        (data["title"],),
    )
    task_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "message": "Task added",
        "task": {"id": task_id, "title": data["title"]},
    }), 201


@app.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, title FROM tasks WHERE id = %s", (task_id,))
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return jsonify({"error": "Task not found"}), 404

    cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "message": "Task deleted",
        "task": {"id": row[0], "title": row[1]},
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
