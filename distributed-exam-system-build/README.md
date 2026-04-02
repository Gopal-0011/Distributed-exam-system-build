# Distributed Exam Management System (Flask + JSON)

This project includes a complete Flask-based distributed exam management system with role-based workflows for Admin, Examiner, and Student users.

## Features Implemented

- Registration and login with hashed passwords and session-based authentication.
- Google OAuth 2.0 login flow (`/auth/google`, `/auth/google/callback`).
- Admin dashboard for user CRUD, exam scheduling, logs, result publishing, and backups.
- Examiner dashboard for question bank CRUD, exam question assignment, and descriptive answer evaluation.
- Student dashboard for one-attempt timed exams, answer submission, auto-submit support, and result history.
- Automatic MCQ evaluation and manual descriptive evaluation.
- Distributed JSON storage using separate files:
  - `data/users.json`
  - `data/exams.json`
  - `data/questions.json`
  - `data/results.json`
- Backup strategy:
  - Automatic file backup before each JSON write.
  - Manual snapshot backup from Admin panel.

## Project Structure

- `app.py` Flask backend
- `templates/` HTML templates
- `static/style.css` modern responsive UI
- `data/` distributed JSON files and backups

## Local Run

1. Create and activate a Python virtual environment.
2. Install dependencies:
   - `pip install flask requests`
3. Optional for Google OAuth:
   - Set `GOOGLE_CLIENT_ID`
   - Set `GOOGLE_CLIENT_SECRET`
   - Set `FLASK_SECRET_KEY`
4. Start server:
   - `python app.py`
5. Open:
   - `http://127.0.0.1:5000`

## Seed Accounts

When `data/users.json` is empty, the system auto-seeds:

- Admin: `admin@example.com` / `Admin@123`
- Examiner: `examiner@example.com` / `Examiner@123`
- Student: `student@example.com` / `Student@123`

## Notes

- JSON writes are atomic and guarded by a lock for basic concurrent safety.
- Student attempts are restricted to one per exam.
- Timed interface auto-submits on countdown completion.