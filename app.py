import os
import re
import secrets
from contextlib import closing

from flask import Flask, abort, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db, init_db, seed_db

app = Flask(__name__)
# Set a stable SECRET_KEY in every deployment; this fallback is for local use.
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
)

with app.app_context():
    init_db()
    seed_db()


EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+"
)


def valid_email(email):
    if not email.isascii() or len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        return False
    local, domain = email.split("@")
    return (
        len(local) <= 64
        and not local.startswith(".")
        and not local.endswith(".")
        and ".." not in local
        and all(len(label) <= 63 for label in domain.split("."))
    )


def csrf_token():
    """Return a random token bound to this browser's signed session."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def require_csrf():
    token = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not expected or not token.isascii() or not secrets.compare_digest(token, expected):
        abort(400, description="Invalid or missing CSRF token.")


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token}


def sign_in(user_id):
    session.clear()
    session["user_id"] = user_id


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    require_csrf()
    name = request.form.get("name", "").strip()
    raw_email = request.form.get("email", "").strip()
    email = raw_email.lower()
    password = request.form.get("password", "")

    if not name or len(name) > 100:
        error = "Enter a name of 1 to 100 characters."
    elif not valid_email(raw_email):
        error = "Enter a valid email address."
    elif not 8 <= len(password) <= 1024:
        error = "Password must be between 8 and 1024 characters."
    else:
        error = None
    if error:
        return render_template("register.html", error=error, name=name, email=email), 400

    password_hash = generate_password_hash(password)
    with closing(get_db()) as connection:
        with connection:
            # Keep the duplicate check and insertion atomic across registrations.
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT id FROM users WHERE email = ? COLLATE NOCASE LIMIT 1", (email,)
            ).fetchone()
            if existing:
                return render_template(
                    "register.html", error="An account with this email already exists.",
                    name=name, email=email,
                ), 409
            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, password_hash),
            )
            user_id = cursor.lastrowid

    sign_in(user_id)
    return redirect(url_for("landing"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    require_csrf()
    raw_email = request.form.get("email", "").strip()
    email = raw_email.lower()
    password = request.form.get("password", "")
    user = None
    if raw_email.isascii() and email and len(email) <= 254 and password and len(password) <= 1024:
        with closing(get_db()) as connection:
            user = connection.execute(
                "SELECT id, password_hash FROM users WHERE email = ? COLLATE NOCASE LIMIT 1",
                (email,),
            ).fetchone()
    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template(
            "login.html", error="Invalid email or password.", email=email
        ), 400

    sign_in(user["id"])
    return redirect(url_for("landing"))


@app.route("/logout", methods=["POST"])
def logout():
    require_csrf()
    session.clear()
    return redirect(url_for("landing"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #


@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
