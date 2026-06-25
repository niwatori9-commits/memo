import json
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for


app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "tasks.db"))
OLD_TASKS_FILE = Path(os.environ.get("TASKS_FILE_PATH", BASE_DIR / "tasks.txt"))
DATE_FORMAT = "%Y-%m-%d"
STATUS_TODO = "todo"
STATUS_DONE = "done"


def get_connection():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                due_date TEXT,
                status TEXT NOT NULL DEFAULT 'todo',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def is_valid_date(date_text):
    if not date_text:
        return True

    try:
        datetime.strptime(date_text, DATE_FORMAT)
        return True
    except ValueError:
        return False


def normalize_old_task(task):
    text = str(task.get("text", "")).strip()
    due_date = task.get("due_date")
    status = task.get("status", STATUS_TODO)

    if not text:
        return None

    if not due_date or not is_valid_date(due_date):
        due_date = None

    if status not in [STATUS_TODO, STATUS_DONE]:
        status = STATUS_TODO

    return {
        "text": text,
        "due_date": due_date,
        "status": status,
    }


def parse_old_task_line(line):
    try:
        task = json.loads(line)
        if isinstance(task, dict):
            return normalize_old_task(task)
    except json.JSONDecodeError:
        pass

    if "\t" in line:
        text, due_date = line.split("\t", 1)
        return normalize_old_task({
            "text": text,
            "due_date": due_date or None,
            "status": STATUS_TODO,
        })

    return normalize_old_task({
        "text": line,
        "due_date": None,
        "status": STATUS_TODO,
    })


def migrate_tasks_txt_if_needed():
    if not OLD_TASKS_FILE.exists():
        return

    with get_connection() as connection:
        task_count = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        if task_count > 0:
            return

        with OLD_TASKS_FILE.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue

                task = parse_old_task_line(line)
                if task:
                    connection.execute(
                        """
                        INSERT INTO tasks (text, due_date, status, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            task["text"],
                            task["due_date"],
                            task["status"],
                            datetime.now().isoformat(timespec="seconds"),
                        ),
                    )

        connection.commit()


def format_task(row):
    task = dict(row)
    today = date.today().isoformat()
    due_date = task["due_date"]

    task["is_done"] = task["status"] == STATUS_DONE
    task["is_overdue"] = (
        bool(due_date)
        and due_date < today
        and task["status"] != STATUS_DONE
    )
    task["is_due_today"] = (
        due_date == today
        and task["status"] != STATUS_DONE
    )
    task["due_label"] = due_date if due_date else "No due date"
    return task


def get_tasks():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, text, due_date, status, created_at
            FROM tasks
            ORDER BY
                CASE WHEN status = 'done' THEN 1 ELSE 0 END,
                CASE WHEN due_date IS NULL THEN 1 ELSE 0 END,
                due_date ASC,
                id DESC
            """
        ).fetchall()

    return [format_task(row) for row in rows]


def add_task(task_text, due_date):
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO tasks (text, due_date, status, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                task_text,
                due_date or None,
                STATUS_TODO,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        connection.commit()


def toggle_task_status(task_id):
    with get_connection() as connection:
        task = connection.execute(
            "SELECT status FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()

        if not task:
            return

        next_status = STATUS_DONE if task["status"] == STATUS_TODO else STATUS_TODO
        connection.execute(
            "UPDATE tasks SET status = ? WHERE id = ?",
            (next_status, task_id),
        )
        connection.commit()


def delete_task_by_id(task_id):
    with get_connection() as connection:
        connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        connection.commit()


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        task_text = request.form.get("task", "").strip()
        due_date = request.form.get("due_date", "").strip()

        if task_text and is_valid_date(due_date):
            add_task(task_text, due_date)

        return redirect(url_for("index"))

    return render_template("index.html", tasks=get_tasks())


@app.post("/toggle/<int:task_id>")
def toggle_task(task_id):
    toggle_task_status(task_id)
    return redirect(url_for("index"))


@app.post("/delete/<int:task_id>")
def delete_task(task_id):
    delete_task_by_id(task_id)
    return redirect(url_for("index"))


init_db()
migrate_tasks_txt_if_needed()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
