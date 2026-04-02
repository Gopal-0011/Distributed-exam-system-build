import json
import os
import shutil
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import urlencode

import requests
from flask import (
    Response,
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "replace-this-in-production")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")

JSON_FILES = {
    "users": os.path.join(DATA_DIR, "users.json"),
    "exams": os.path.join(DATA_DIR, "exams.json"),
    "questions": os.path.join(DATA_DIR, "questions.json"),
    "results": os.path.join(DATA_DIR, "results.json"),
    "logs": os.path.join(DATA_DIR, "logs.json"),
}

DATA_LOCK = threading.Lock()
ALLOWED_ROLES = {"admin", "examiner", "student"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_data_files() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)

    for file_path in JSON_FILES.values():
        if not os.path.exists(file_path):
            with open(file_path, "w", encoding="utf-8") as file:
                json.dump([], file, indent=2)

    users = read_json("users")
    questions = read_json("questions")
    exams = read_json("exams")

    if not users:
        seed_users = [
            {
                "id": str(uuid.uuid4()),
                "name": "System Admin",
                "email": "admin@example.com",
                "password_hash": generate_password_hash("Admin@123"),
                "role": "admin",
                "created_at": utc_now_iso(),
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Examiner One",
                "email": "examiner@example.com",
                "password_hash": generate_password_hash("Examiner@123"),
                "role": "examiner",
                "created_at": utc_now_iso(),
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Student One",
                "email": "student@example.com",
                "password_hash": generate_password_hash("Student@123"),
                "role": "student",
                "created_at": utc_now_iso(),
            },
        ]
        write_json("users", seed_users)

    users = read_json("users")
    examiner = next((user for user in users if user["role"] == "examiner"), None)

    if examiner and not questions:
        seed_questions = [
            {
                "id": str(uuid.uuid4()),
                "text": "What is the time complexity of binary search?",
                "type": "mcq",
                "options": ["O(n)", "O(log n)", "O(n log n)", "O(1)"],
                "correct_answer": "O(log n)",
                "marks": 2,
                "created_by": examiner["id"],
                "created_at": utc_now_iso(),
            },
            {
                "id": str(uuid.uuid4()),
                "text": "Explain the difference between processes and threads.",
                "type": "descriptive",
                "options": [],
                "correct_answer": "",
                "marks": 8,
                "created_by": examiner["id"],
                "created_at": utc_now_iso(),
            },
        ]
        write_json("questions", seed_questions)

    questions = read_json("questions")
    if examiner and not exams and questions:
        seed_exam = {
            "id": str(uuid.uuid4()),
            "title": "Data Structures Fundamentals",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": "10:00",
            "duration_minutes": 20,
            "examiner_id": examiner["id"],
            "question_ids": [question["id"] for question in questions],
            "created_at": utc_now_iso(),
        }
        write_json("exams", [seed_exam])


def read_json(key: str):
    file_path = JSON_FILES[key]
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def backup_file(file_path: str) -> None:
    if os.path.exists(file_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_name = f"{os.path.basename(file_path)}.{timestamp}.bak"
        shutil.copy(file_path, os.path.join(BACKUP_DIR, backup_name))


def write_json(key: str, payload) -> None:
    file_path = JSON_FILES[key]
    with DATA_LOCK:
        backup_file(file_path)
        fd, temp_path = tempfile.mkstemp(prefix="json_tmp_", suffix=".json", dir=DATA_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
                json.dump(payload, temp_file, indent=2)
            os.replace(temp_path, file_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


def log_event(action: str, details: str = "") -> None:
    logs = read_json("logs")
    actor_id = session.get("user_id")
    logs.append(
        {
            "id": str(uuid.uuid4()),
            "actor_id": actor_id,
            "action": action,
            "details": details,
            "ip": request.remote_addr,
            "timestamp": utc_now_iso(),
        }
    )
    write_json("logs", logs)


def get_user_by_id(user_id: str):
    users = read_json("users")
    return next((user for user in users if user["id"] == user_id), None)


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def role_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if session.get("role") not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def find_exam(exam_id: str):
    exams = read_json("exams")
    return next((exam for exam in exams if exam["id"] == exam_id), None)


def find_result(result_id: str):
    results = read_json("results")
    return next((item for item in results if item["id"] == result_id), None)


def calculate_grade(score: float, total_marks: float) -> str:
    if total_marks <= 0:
        return "N/A"
    percent = (score / total_marks) * 100
    if percent >= 90:
        return "A+"
    if percent >= 80:
        return "A"
    if percent >= 70:
        return "B"
    if percent >= 60:
        return "C"
    if percent >= 50:
        return "D"
    return "F"


def evaluate_mcq(answers: dict, questions: list) -> float:
    score = 0.0
    for question in questions:
        if question["type"] != "mcq":
            continue
        given = answers.get(question["id"], "").strip()
        if given and given == question.get("correct_answer", "").strip():
            score += float(question.get("marks", 0))
    return score


ensure_data_files()


@app.context_processor
def inject_context():
    user = get_current_user()
    return {
        "current_user": user,
        "current_year": datetime.now().year,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "student").strip().lower()

        if len(name) < 2 or "@" not in email or len(password) < 8 or role not in ALLOWED_ROLES:
            flash("Invalid registration details. Use a valid name, email, role, and strong password.", "error")
            return redirect(url_for("register"))

        users = read_json("users")
        if any(user["email"] == email for user in users):
            flash("Email already exists.", "error")
            return redirect(url_for("register"))

        new_user = {
            "id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "password_hash": generate_password_hash(password),
            "role": role,
            "created_at": utc_now_iso(),
        }
        users.append(new_user)
        write_json("users", users)
        flash("Registration successful. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        users = read_json("users")

        user = next((entry for entry in users if entry["email"] == email), None)
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid credentials.", "error")
            return redirect(url_for("login"))

        session["user_id"] = user["id"]
        session["role"] = user["role"]
        session.permanent = True
        log_event("login", f"User {user['email']} logged in")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/auth/google")
def google_login():
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    if not client_id:
        flash("Google OAuth is not configured. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.", "error")
        return redirect(url_for("login"))

    selected_role = request.args.get("role", "student").lower()
    if selected_role not in ALLOWED_ROLES:
        selected_role = "student"

    state = str(uuid.uuid4())
    session["oauth_state"] = state
    session["oauth_role"] = selected_role

    params = {
        "client_id": client_id,
        "redirect_uri": url_for("google_callback", _external=True),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    google_auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return redirect(google_auth_url)


@app.route("/auth/google/callback")
def google_callback():
    state = request.args.get("state", "")
    code = request.args.get("code", "")
    expected_state = session.get("oauth_state")

    if not code or not expected_state or state != expected_state:
        flash("Invalid OAuth response.", "error")
        return redirect(url_for("login"))

    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        flash("Google OAuth is not configured.", "error")
        return redirect(url_for("login"))

    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": url_for("google_callback", _external=True),
        },
        timeout=20,
    )

    if token_response.status_code != 200:
        flash("Google token exchange failed.", "error")
        return redirect(url_for("login"))

    access_token = token_response.json().get("access_token")
    if not access_token:
        flash("Google token missing.", "error")
        return redirect(url_for("login"))

    user_info_response = requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    if user_info_response.status_code != 200:
        flash("Unable to fetch profile from Google.", "error")
        return redirect(url_for("login"))

    profile = user_info_response.json()
    email = str(profile.get("email", "")).lower().strip()
    name = profile.get("name", "Google User")
    role = session.pop("oauth_role", "student")
    session.pop("oauth_state", None)

    if not email:
        flash("Google account did not return an email.", "error")
        return redirect(url_for("login"))

    users = read_json("users")
    user = next((entry for entry in users if entry["email"] == email), None)
    if not user:
        user = {
            "id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "password_hash": generate_password_hash(str(uuid.uuid4())),
            "role": role,
            "created_at": utc_now_iso(),
            "oauth_provider": "google",
        }
        users.append(user)
        write_json("users", users)

    session["user_id"] = user["id"]
    session["role"] = user["role"]
    log_event("google_login", f"User {email} logged in with Google")
    return redirect(url_for("dashboard"))


@app.route("/logout")
@login_required
def logout():
    log_event("logout", f"User {session.get('user_id')} logged out")
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    role = session.get("role")
    if role == "admin":
        return redirect(url_for("admin_dashboard"))
    if role == "examiner":
        return redirect(url_for("examiner_dashboard"))
    return redirect(url_for("student_dashboard"))


@app.route("/admin")
@login_required
@role_required("admin")
def admin_dashboard():
    users = read_json("users")
    exams = read_json("exams")
    results = read_json("results")
    logs = read_json("logs")
    return render_template(
        "admin_dashboard.html",
        users=users,
        exams=exams,
        results=results,
        logs=logs[-20:][::-1],
    )


@app.route("/admin/users/add", methods=["POST"])
@login_required
@role_required("admin")
def admin_add_user():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    role = request.form.get("role", "student").strip().lower()

    if len(name) < 2 or "@" not in email or len(password) < 8 or role not in ALLOWED_ROLES:
        flash("Invalid user payload.", "error")
        return redirect(url_for("admin_dashboard"))

    users = read_json("users")
    if any(user["email"] == email for user in users):
        flash("Email already exists.", "error")
        return redirect(url_for("admin_dashboard"))

    users.append(
        {
            "id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "password_hash": generate_password_hash(password),
            "role": role,
            "created_at": utc_now_iso(),
        }
    )
    write_json("users", users)
    log_event("admin_add_user", f"Added user {email}")
    flash("User added.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/users/<user_id>/update", methods=["POST"])
@login_required
@role_required("admin")
def admin_update_user(user_id):
    users = read_json("users")
    user = next((entry for entry in users if entry["id"] == user_id), None)
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("admin_dashboard"))

    name = request.form.get("name", user["name"]).strip()
    role = request.form.get("role", user["role"]).strip().lower()
    password = request.form.get("password", "")
    if role not in ALLOWED_ROLES or len(name) < 2:
        flash("Invalid role or name.", "error")
        return redirect(url_for("admin_dashboard"))

    user["name"] = name
    user["role"] = role
    if password:
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return redirect(url_for("admin_dashboard"))
        user["password_hash"] = generate_password_hash(password)

    write_json("users", users)
    log_event("admin_update_user", f"Updated user {user['email']}")
    flash("User updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/users/<user_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def admin_delete_user(user_id):
    if session.get("user_id") == user_id:
        flash("Admin cannot delete own account while logged in.", "error")
        return redirect(url_for("admin_dashboard"))

    users = read_json("users")
    filtered = [entry for entry in users if entry["id"] != user_id]
    if len(filtered) == len(users):
        flash("User not found.", "error")
        return redirect(url_for("admin_dashboard"))

    write_json("users", filtered)
    log_event("admin_delete_user", f"Deleted user {user_id}")
    flash("User deleted.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/exams/create", methods=["POST"])
@login_required
@role_required("admin")
def admin_create_exam():
    title = request.form.get("title", "").strip()
    exam_date = request.form.get("date", "")
    exam_time = request.form.get("time", "")
    duration = request.form.get("duration_minutes", "0")
    examiner_id = request.form.get("examiner_id", "")

    try:
        duration_int = int(duration)
    except ValueError:
        duration_int = 0

    if len(title) < 3 or duration_int < 1:
        flash("Invalid exam details.", "error")
        return redirect(url_for("admin_dashboard"))

    users = read_json("users")
    if not any(user["id"] == examiner_id and user["role"] == "examiner" for user in users):
        flash("Choose a valid examiner.", "error")
        return redirect(url_for("admin_dashboard"))

    exams = read_json("exams")
    exams.append(
        {
            "id": str(uuid.uuid4()),
            "title": title,
            "date": exam_date,
            "time": exam_time,
            "duration_minutes": duration_int,
            "examiner_id": examiner_id,
            "question_ids": [],
            "created_at": utc_now_iso(),
        }
    )
    write_json("exams", exams)
    log_event("admin_create_exam", f"Created exam {title}")
    flash("Exam created.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/exams/<exam_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def admin_delete_exam(exam_id):
    exams = read_json("exams")
    filtered = [exam for exam in exams if exam["id"] != exam_id]
    if len(filtered) == len(exams):
        flash("Exam not found.", "error")
        return redirect(url_for("admin_dashboard"))

    write_json("exams", filtered)
    log_event("admin_delete_exam", f"Deleted exam {exam_id}")
    flash("Exam deleted.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/results/<result_id>/publish", methods=["POST"])
@login_required
@role_required("admin")
def admin_publish_result(result_id):
    results = read_json("results")
    target = next((item for item in results if item["id"] == result_id), None)
    if not target:
        flash("Result not found.", "error")
        return redirect(url_for("admin_dashboard"))

    if target.get("status") == "pending_evaluation":
        flash("Evaluate descriptive answers before publishing.", "error")
        return redirect(url_for("admin_dashboard"))

    target["status"] = "published"
    write_json("results", results)
    log_event("admin_publish_result", f"Published result {result_id}")
    flash("Result published.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/backup", methods=["POST"])
@login_required
@role_required("admin")
def admin_manual_backup():
    snapshot_dir = os.path.join(BACKUP_DIR, f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(snapshot_dir, exist_ok=True)
    for file_path in JSON_FILES.values():
        shutil.copy(file_path, os.path.join(snapshot_dir, os.path.basename(file_path)))
    log_event("admin_backup", f"Created backup snapshot {snapshot_dir}")
    flash("Backup created successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/examiner")
@login_required
@role_required("examiner")
def examiner_dashboard():
    user_id = session.get("user_id")
    questions = [question for question in read_json("questions") if question["created_by"] == user_id]
    exams = [exam for exam in read_json("exams") if exam["examiner_id"] == user_id]
    results = read_json("results")
    pending = []
    for result_item in results:
        exam = find_exam(result_item["exam_id"])
        if exam and exam["examiner_id"] == user_id and result_item.get("status") == "pending_evaluation":
            pending.append(result_item)

    return render_template(
        "examiner_dashboard.html",
        questions=questions,
        exams=exams,
        pending_results=pending,
    )


@app.route("/examiner/questions/add", methods=["POST"])
@login_required
@role_required("examiner")
def examiner_add_question():
    question_text = request.form.get("text", "").strip()
    q_type = request.form.get("type", "mcq").strip().lower()
    marks_raw = request.form.get("marks", "1").strip()

    try:
        marks = int(marks_raw)
    except ValueError:
        marks = 0

    if len(question_text) < 5 or q_type not in {"mcq", "descriptive"} or marks <= 0:
        flash("Invalid question data.", "error")
        return redirect(url_for("examiner_dashboard"))

    options = []
    correct_answer = ""
    if q_type == "mcq":
        options_raw = request.form.get("options", "")
        options = [item.strip() for item in options_raw.split("|") if item.strip()]
        correct_answer = request.form.get("correct_answer", "").strip()
        if len(options) < 2 or correct_answer not in options:
            flash("MCQ needs at least two options and a valid correct answer.", "error")
            return redirect(url_for("examiner_dashboard"))

    questions = read_json("questions")
    questions.append(
        {
            "id": str(uuid.uuid4()),
            "text": question_text,
            "type": q_type,
            "options": options,
            "correct_answer": correct_answer,
            "marks": marks,
            "created_by": session["user_id"],
            "created_at": utc_now_iso(),
        }
    )
    write_json("questions", questions)
    log_event("examiner_add_question", f"Added question: {question_text[:40]}")
    flash("Question added.", "success")
    return redirect(url_for("examiner_dashboard"))


@app.route("/examiner/questions/<question_id>/delete", methods=["POST"])
@login_required
@role_required("examiner")
def examiner_delete_question(question_id):
    user_id = session.get("user_id")
    questions = read_json("questions")
    question = next((item for item in questions if item["id"] == question_id), None)
    if not question or question["created_by"] != user_id:
        flash("Question not found or unauthorized.", "error")
        return redirect(url_for("examiner_dashboard"))

    questions = [item for item in questions if item["id"] != question_id]
    write_json("questions", questions)

    exams = read_json("exams")
    for exam in exams:
        exam["question_ids"] = [qid for qid in exam.get("question_ids", []) if qid != question_id]
    write_json("exams", exams)

    log_event("examiner_delete_question", f"Deleted question {question_id}")
    flash("Question deleted.", "success")
    return redirect(url_for("examiner_dashboard"))


@app.route("/examiner/questions/<question_id>/update", methods=["POST"])
@login_required
@role_required("examiner")
def examiner_update_question(question_id):
    user_id = session.get("user_id")
    questions = read_json("questions")
    question = next((item for item in questions if item["id"] == question_id), None)
    if not question or question["created_by"] != user_id:
        flash("Question not found or unauthorized.", "error")
        return redirect(url_for("examiner_dashboard"))

    text = request.form.get("text", question["text"]).strip()
    marks_raw = request.form.get("marks", str(question.get("marks", 1))).strip()
    try:
        marks = int(marks_raw)
    except ValueError:
        marks = 0
    if len(text) < 5 or marks <= 0:
        flash("Invalid updated question.", "error")
        return redirect(url_for("examiner_dashboard"))

    question["text"] = text
    question["marks"] = marks
    if question["type"] == "mcq":
        options = [item.strip() for item in request.form.get("options", "").split("|") if item.strip()]
        correct_answer = request.form.get("correct_answer", "").strip()
        if len(options) < 2 or correct_answer not in options:
            flash("Invalid MCQ options or answer.", "error")
            return redirect(url_for("examiner_dashboard"))
        question["options"] = options
        question["correct_answer"] = correct_answer

    write_json("questions", questions)
    log_event("examiner_update_question", f"Updated question {question_id}")
    flash("Question updated.", "success")
    return redirect(url_for("examiner_dashboard"))


@app.route("/examiner/exams/<exam_id>/assign", methods=["POST"])
@login_required
@role_required("examiner")
def examiner_assign_questions(exam_id):
    user_id = session.get("user_id")
    exams = read_json("exams")
    exam = next((item for item in exams if item["id"] == exam_id), None)
    if not exam or exam["examiner_id"] != user_id:
        flash("Exam not found or unauthorized.", "error")
        return redirect(url_for("examiner_dashboard"))

    selected_ids = request.form.getlist("question_ids")
    own_question_ids = {question["id"] for question in read_json("questions") if question["created_by"] == user_id}
    valid_selected = [qid for qid in selected_ids if qid in own_question_ids]

    exam["question_ids"] = valid_selected
    write_json("exams", exams)
    log_event("examiner_assign_questions", f"Assigned {len(valid_selected)} question(s) to exam {exam_id}")
    flash("Questions assigned.", "success")
    return redirect(url_for("examiner_dashboard"))


@app.route("/examiner/evaluate/<result_id>", methods=["GET", "POST"])
@login_required
@role_required("examiner")
def examiner_evaluate_result(result_id):
    user_id = session.get("user_id")
    results = read_json("results")
    result_item = next((entry for entry in results if entry["id"] == result_id), None)
    if not result_item:
        flash("Result not found.", "error")
        return redirect(url_for("examiner_dashboard"))

    exam = find_exam(result_item["exam_id"])
    if not exam or exam["examiner_id"] != user_id:
        abort(403)

    questions = read_json("questions")
    q_map = {question["id"]: question for question in questions}
    descriptive_questions = [
        q_map[qid]
        for qid in exam.get("question_ids", [])
        if qid in q_map and q_map[qid]["type"] == "descriptive"
    ]

    if request.method == "POST":
        manual_breakdown = {}
        manual_total = 0.0

        for question in descriptive_questions:
            key = f"marks_{question['id']}"
            raw_value = request.form.get(key, "0")
            try:
                score = float(raw_value)
            except ValueError:
                score = 0.0
            max_marks = float(question.get("marks", 0))
            score = max(0.0, min(score, max_marks))
            manual_breakdown[question["id"]] = score
            manual_total += score

        total_marks = sum(float(q_map[qid].get("marks", 0)) for qid in exam.get("question_ids", []) if qid in q_map)
        auto_score = float(result_item.get("auto_score", 0.0))
        total_score = auto_score + manual_total

        result_item["manual_score"] = manual_total
        result_item["manual_breakdown"] = manual_breakdown
        result_item["total_score"] = total_score
        result_item["total_marks"] = total_marks
        result_item["grade"] = calculate_grade(total_score, total_marks)
        result_item["status"] = "evaluated"
        result_item["evaluated_at"] = utc_now_iso()

        write_json("results", results)
        log_event("examiner_evaluate", f"Evaluated result {result_id}")
        flash("Result evaluated and ready for publishing.", "success")
        return redirect(url_for("examiner_dashboard"))

    student = get_user_by_id(result_item["student_id"])
    return render_template(
        "evaluate_exam.html",
        result_item=result_item,
        exam=exam,
        student=student,
        descriptive_questions=descriptive_questions,
    )


@app.route("/student")
@login_required
@role_required("student")
def student_dashboard():
    user_id = session.get("user_id")
    exams = read_json("exams")
    results = read_json("results")
    attempts = {item["exam_id"] for item in results if item["student_id"] == user_id}

    exam_cards = []
    for exam in exams:
        exam_cards.append(
            {
                "exam": exam,
                "can_attempt": exam["id"] not in attempts,
            }
        )

    history = [item for item in results if item["student_id"] == user_id]
    history.sort(key=lambda item: item.get("submitted_at", ""), reverse=True)

    return render_template("student_dashboard.html", exam_cards=exam_cards, history=history)


@app.route("/student/exams/<exam_id>/start")
@login_required
@role_required("student")
def student_start_exam(exam_id):
    user_id = session.get("user_id")
    exam = find_exam(exam_id)
    if not exam:
        flash("Exam not found.", "error")
        return redirect(url_for("student_dashboard"))

    results = read_json("results")
    if any(item["exam_id"] == exam_id and item["student_id"] == user_id for item in results):
        flash("Multiple attempts are not allowed.", "error")
        return redirect(url_for("student_dashboard"))

    q_map = {question["id"]: question for question in read_json("questions")}
    questions = [q_map[qid] for qid in exam.get("question_ids", []) if qid in q_map]
    if not questions:
        flash("No questions assigned to this exam yet.", "error")
        return redirect(url_for("student_dashboard"))

    exam_key = f"exam_start_{exam_id}"
    if exam_key not in session:
        session[exam_key] = utc_now_iso()

    return render_template("exam_take.html", exam=exam, questions=questions)


@app.route("/student/exams/<exam_id>/submit", methods=["POST"])
@login_required
@role_required("student")
def student_submit_exam(exam_id):
    user_id = session.get("user_id")
    exam = find_exam(exam_id)
    if not exam:
        flash("Exam not found.", "error")
        return redirect(url_for("student_dashboard"))

    results = read_json("results")
    if any(item["exam_id"] == exam_id and item["student_id"] == user_id for item in results):
        flash("You already submitted this exam.", "error")
        return redirect(url_for("student_dashboard"))

    exam_key = f"exam_start_{exam_id}"
    start_iso = session.get(exam_key)
    if not start_iso:
        flash("Exam session expired. Please restart.", "error")
        return redirect(url_for("student_dashboard"))

    try:
        start_time = datetime.fromisoformat(start_iso)
    except ValueError:
        start_time = datetime.now(timezone.utc)

    elapsed_seconds = max(0, (datetime.now(timezone.utc) - start_time).total_seconds())
    max_seconds = int(exam.get("duration_minutes", 1)) * 60

    questions = read_json("questions")
    q_map = {question["id"]: question for question in questions}
    assigned = [q_map[qid] for qid in exam.get("question_ids", []) if qid in q_map]

    answers = {}
    for question in assigned:
        answer = request.form.get(f"q_{question['id']}", "").strip()
        answers[question["id"]] = answer

    auto_score = evaluate_mcq(answers, assigned)
    total_marks = float(sum(float(question.get("marks", 0)) for question in assigned))

    has_descriptive = any(question["type"] == "descriptive" for question in assigned)
    status = "pending_evaluation" if has_descriptive else "evaluated"
    manual_score = 0.0
    total_score = auto_score
    grade = calculate_grade(total_score, total_marks) if not has_descriptive else "Pending"

    result_item = {
        "id": str(uuid.uuid4()),
        "exam_id": exam_id,
        "student_id": user_id,
        "answers": answers,
        "auto_score": auto_score,
        "manual_score": manual_score,
        "total_score": total_score,
        "total_marks": total_marks,
        "grade": grade,
        "status": status,
        "submitted_at": utc_now_iso(),
        "elapsed_seconds": int(elapsed_seconds),
        "time_limit_seconds": max_seconds,
    }
    results.append(result_item)
    write_json("results", results)

    session.pop(exam_key, None)
    if elapsed_seconds > max_seconds:
        log_event("student_auto_submit", f"Auto-submitted exam {exam_id} for user {user_id}")
    else:
        log_event("student_submit", f"Submitted exam {exam_id} for user {user_id}")

    flash("Exam submitted successfully.", "success")
    return redirect(url_for("student_dashboard"))


@app.route("/student/results/<result_id>/download")
@login_required
@role_required("student")
def student_download_result(result_id):
    result_item = find_result(result_id)
    if not result_item or result_item["student_id"] != session.get("user_id"):
        abort(404)

    exam = find_exam(result_item["exam_id"])
    exam_title = exam["title"] if exam else "Unknown Exam"
    text_payload = (
        f"Result ID: {result_item['id']}\n"
        f"Exam: {exam_title}\n"
        f"Score: {result_item.get('total_score', 0)} / {result_item.get('total_marks', 0)}\n"
        f"Grade: {result_item.get('grade', 'N/A')}\n"
        f"Status: {result_item.get('status', 'N/A')}\n"
        f"Submitted At: {result_item.get('submitted_at', 'N/A')}\n"
    )

    return Response(
        text_payload,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment; filename=result_{result_id}.txt"},
    )


@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", message="Access denied."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", message="Page not found."), 404


if __name__ == "__main__":
    ensure_data_files()
    app.run(debug=True, host="0.0.0.0", port=5000)