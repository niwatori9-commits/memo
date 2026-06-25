import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for


app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
TASKS_FILE = Path(os.environ.get("TASKS_FILE_PATH", BASE_DIR / "tasks.txt"))
DATE_FORMAT = "%Y-%m-%d"
STATUS_TODO = "todo"
STATUS_DONE = "done"


def is_valid_date(date_text):
    if not date_text:
        return True

    try:
        datetime.strptime(date_text, DATE_FORMAT)
        return True
    except ValueError:
        return False


def normalize_task(task):
    text = str(task.get("text", "")).strip()
    due_date = task.get("due_date")
    status = task.get("status", STATUS_TODO)

    if not text:
        return None

    if not due_date:
        due_date = None

    if due_date and not is_valid_date(due_date):
        due_date = None

    if status not in [STATUS_TODO, STATUS_DONE]:
        status = STATUS_TODO

    return {
        "text": text,
        "due_date": due_date,
        "status": status,
    }


def parse_task_line(line):
    try:
        task = json.loads(line)
        if isinstance(task, dict):
            return normalize_task(task)
    except json.JSONDecodeError:
        pass

    if "\t" in line:
        text, due_date = line.split("\t", 1)
        return normalize_task({
            "text": text,
            "due_date": due_date or None,
            "status": STATUS_TODO,
        })

    return normalize_task({
        "text": line,
        "due_date": None,
        "status": STATUS_TODO,
    })


def ensure_tasks_file():
    try:
        TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        TASKS_FILE.touch(exist_ok=True)
        return True
    except PermissionError as error:
        app.logger.error("Permission denied while creating tasks file: %s", error)
        return False
    except OSError as error:
        app.logger.error("Could not create tasks file: %s", error)
        return False


def load_tasks():
    if not ensure_tasks_file():
        return []

    try:
        with TASKS_FILE.open("r", encoding="utf-8") as file:
            tasks = []
            for line in file:
                line = line.strip()
                if not line:
                    continue

                task = parse_task_line(line)
                if task:
                    tasks.append(task)

            return tasks
    except FileNotFoundError:
        return []
    except PermissionError as error:
        app.logger.error("Permission denied while reading tasks file: %s", error)
        return []
    except OSError as error:
        app.logger.error("Could not read tasks file: %s", error)
        return []


def save_tasks(tasks):
    if not ensure_tasks_file():
        return False

    temp_file_name = None

    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=TASKS_FILE.parent,
            delete=False,
        ) as temp_file:
            temp_file_name = temp_file.name

            for task in tasks:
                normalized_task = normalize_task(task)
                if normalized_task:
                    line = json.dumps(normalized_task, ensure_ascii=False)
                    temp_file.write(line + "\n")

        os.replace(temp_file_name, TASKS_FILE)
        return True
    except PermissionError as error:
        app.logger.error("Permission denied while writing tasks file: %s", error)
        return False
    except OSError as error:
        app.logger.error("Could not write tasks file: %s", error)
        return False
    finally:
        if temp_file_name and os.path.exists(temp_file_name):
            try:
                os.remove(temp_file_name)
            except OSError:
                pass


@app.route("/", methods=["GET", "POST"])
def index():
    tasks = load_tasks()

    if request.method == "POST":
        task_text = request.form.get("task", "").strip()
        due_date = request.form.get("due_date", "").strip()

        if task_text and is_valid_date(due_date):
            tasks.append({
                "text": task_text,
                "due_date": due_date or None,
                "status": STATUS_TODO,
            })
            save_tasks(tasks)
        return redirect(url_for("index"))

    return render_template("index.html", tasks=tasks)


@app.route("/delete/<int:task_id>")
def delete_task(task_id):
    tasks = load_tasks()

    if 0 <= task_id < len(tasks):
        tasks.pop(task_id)
        save_tasks(tasks)

    return redirect(url_for("index"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
