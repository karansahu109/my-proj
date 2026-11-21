import importlib
import os
import re
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

import database.db as db


@pytest.fixture
def auth_app(tmp_path, monkeypatch):
    # Patch before the first app import, which initializes and seeds on startup.
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    db.seed_db()
    app = importlib.import_module("app").app
    monkeypatch.setitem(app.config, "TESTING", True)
    monkeypatch.setitem(app.config, "SECRET_KEY", "test-only-secret")
    return app


@pytest.fixture
def client(auth_app):
    return auth_app.test_client()


def token_for(client, path):
    response = client.get(path)
    assert response.status_code == 200
    match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
    assert match, "form must include its CSRF token"
    return match.group(1).decode("ascii")


def post_form(client, path, data, form_path=None):
    token = token_for(client, form_path or path)
    return client.post(path, data={**data, "csrf_token": token})


def users():
    with closing(db.get_db()) as connection:
        return connection.execute("SELECT * FROM users ORDER BY id").fetchall()


def test_registration_persists_hash_and_signs_in(client):
    token = token_for(client, "/register")
    with client.session_transaction() as session:
        session["old_data"] = "remove me"
    response = client.post(
        "/register",
        data={"name": "  Alice Example  ", "email": "  ALICE@Example.COM ",
              "password": " space password ", "csrf_token": token},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    user = users()[-1]
    assert (user["name"], user["email"]) == ("Alice Example", "alice@example.com")
    assert user["password_hash"] != " space password "
    assert check_password_hash(user["password_hash"], " space password ")
    with client.session_transaction() as session:
        assert dict(session) == {"user_id": user["id"]}
    landing = client.get("/")
    assert b"Sign out" in landing.data
    assert b'<form method="POST" action="/logout">' in landing.data
    assert b"Get started</a>" not in landing.data
    assert "HttpOnly" in response.headers["Set-Cookie"]
    assert "SameSite=Lax" in response.headers["Set-Cookie"]
    # The anonymous token does not survive a change of authentication state.
    assert client.post("/logout", data={"csrf_token": token}).status_code == 400


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("name", "  ", b"Enter a name"),
        ("name", "x" * 101, b"Enter a name"),
        ("email", "", b"valid email"),
        ("email", "not-an-email", b"valid email"),
        ("email", "user@localhost", b"valid email"),
        ("email", "u" * 250 + "@a.com", b"valid email"),
        ("email", "usér@example.com", b"valid email"),
        ("email", "K@example.com", b"valid email"),
        ("email", ".alice@example.com", b"valid email"),
        ("email", "alice..test@example.com", b"valid email"),
        ("email", "a" * 65 + "@example.com", b"valid email"),
        ("email", "alice@" + "a" * 64 + ".com", b"valid email"),
        ("password", "", b"Password must"),
        ("password", "short", b"Password must"),
        ("password", "x" * 1025, b"Password must"),
    ],
)
def test_registration_validation(client, field, value, message):
    data = {"name": "Alice", "email": "alice@example.com", "password": "secret-password"}
    data[field] = value
    response = post_form(client, "/register", data)
    assert response.status_code == 400
    assert message in response.data
    assert b'secret-password' not in response.data
    assert len(users()) == 1
    with client.session_transaction() as session:
        assert "user_id" not in session


@pytest.mark.parametrize("length", [8, 1024])
def test_registration_accepts_password_boundaries(client, length):
    password = "x" * length
    response = post_form(client, "/register", {
        "name": "n" * 100, "email": "alice@example.com", "password": password
    })
    assert response.status_code == 302
    assert check_password_hash(users()[-1]["password_hash"], password)


def test_error_fields_are_retained_and_escaped(client):
    response = post_form(client, "/register", {
        "name": '<script>alert("x")</script>', "email": "InvalidEmail", "password": "secret-password"
    })
    assert response.status_code == 400
    assert b'&lt;script&gt;' in response.data
    assert b'<script>alert' not in response.data
    assert b'value="invalidemail"' in response.data
    assert b'secret-password' not in response.data


def test_duplicate_email_case_insensitive_for_demo_and_existing_records(client):
    with closing(db.get_db()) as connection, connection:
        connection.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Legacy", "Legacy@Example.COM", generate_password_hash("legacy-password")),
        )
    for email in (" DEMO@SPENDLY.COM ", "legacy@example.com"):
        response = post_form(client, "/register", {
            "name": "Other", "email": email, "password": "new-password"
        })
        assert response.status_code == 409
        assert b"already exists" in response.data
    assert len(users()) == 2
    response = post_form(client, "/login", {"email": "LEGACY@example.com", "password": "legacy-password"})
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session["user_id"] == users()[-1]["id"]


def test_unexpected_database_errors_are_not_reported_as_duplicates(client):
    with closing(db.get_db()) as connection, connection:
        connection.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON users BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="test failure"):
        post_form(client, "/register", {"name": "Alice", "email": "alice@example.com", "password": "password123"})
    assert len(users()) == 1


def test_concurrent_registrations_do_not_create_case_variants(auth_app):
    barrier = threading.Barrier(2)

    def register(email):
        with auth_app.test_client() as client:
            token = token_for(client, "/register")
            barrier.wait(timeout=10)
            return client.post("/register", data={
                "name": "Alice", "email": email, "password": "password123", "csrf_token": token
            }).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(register, ["alice@example.com", "ALICE@example.com"]))
    assert sorted(statuses) == [302, 409]
    assert len(users()) == 2


def test_seeded_demo_login_and_logout(client):
    response = post_form(client, "/login", {"email": " DEMO@SPENDLY.COM ", "password": "demo123"})
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session["user_id"] == users()[0]["id"]
    assert client.get("/logout").status_code == 405
    with client.session_transaction() as session:
        assert "user_id" in session
    response = post_form(client, "/logout", {}, form_path="/")
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert not session
    landing = client.get("/")
    assert b"Sign in" in landing.data
    assert b"Get started" in landing.data
    assert b"Sign out" not in landing.data


def test_registered_user_can_log_in_again(client):
    assert post_form(client, "/register", {
        "name": "Alice", "email": "alice@example.com", "password": "password123"
    }).status_code == 302
    assert post_form(client, "/logout", {}, form_path="/").status_code == 302
    assert post_form(client, "/login", {
        "email": " ALICE@EXAMPLE.COM ", "password": "password123"
    }).status_code == 302
    with client.session_transaction() as session:
        assert session["user_id"] == users()[-1]["id"]


@pytest.mark.parametrize("email,password", [
    ("demo@spendly.com", "wrong-password"),
    ("nobody@example.com", "wrong-password"),
    ("", "password123"),
    ("demo@spendly.com", ""),
    ("demo@spendly.com", "x" * 1025),
    ("' OR 1=1 --@example.com", "password123"),
])
def test_invalid_login_is_generic_and_does_not_sign_in(client, email, password):
    response = post_form(client, "/login", {"email": email, "password": password})
    assert response.status_code == 400
    assert b"Invalid email or password." in response.data
    if password:
        assert password.encode() not in response.data
    with client.session_transaction() as session:
        assert "user_id" not in session


@pytest.mark.parametrize("path", ["/register", "/login", "/logout"])
@pytest.mark.parametrize("csrf", [None, "invalid", "é"])
def test_auth_posts_reject_bad_csrf_without_side_effects(client, path, csrf):
    assert post_form(client, "/login", {"email": "demo@spendly.com", "password": "demo123"}).status_code == 302
    token_for(client, "/")
    data = {"name": "Alice", "email": "alice@example.com", "password": "password123"}
    if csrf is not None:
        data["csrf_token"] = csrf
    assert client.post(path, data=data).status_code == 400
    assert len(users()) == 1
    with client.session_transaction() as session:
        assert session["user_id"] == users()[0]["id"]


def test_environment_config_and_startup_use_isolated_database(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = (
        "import sys; from pathlib import Path; import database.db as db; "
        "db.DB_PATH = Path(sys.argv[1]); import app; "
        "print(app.app.config['SECRET_KEY']); print(app.app.config['SESSION_COOKIE_SECURE']); "
        "print(db.get_db().execute('SELECT COUNT(*) FROM users').fetchone()[0]); "
        "print(db.get_db().execute('SELECT COUNT(*) FROM expenses').fetchone()[0]); "
        "print('Secure' in app.app.test_client().get('/login').headers['Set-Cookie'])"
    )
    env = dict(os.environ, SECRET_KEY="configured-test-key", SESSION_COOKIE_SECURE="1")
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "startup.db")], cwd=root,
        env=env, text=True, capture_output=True, check=True,
    )
    assert result.stdout.splitlines() == ["configured-test-key", "True", "1", "8", "True"]


def test_development_secret_is_ephemeral(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = (
        "import sys; from pathlib import Path; import database.db as db; "
        "db.DB_PATH = Path(sys.argv[1]); import app; print(app.app.config['SECRET_KEY'])"
    )
    env = dict(os.environ)
    env.pop("SECRET_KEY", None)
    keys = []
    for index in range(2):
        result = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path / f"fallback-{index}.db")],
            cwd=root, env=env, text=True, capture_output=True, check=True,
        )
        keys.append(result.stdout.strip())
    assert all(len(key) == 64 for key in keys)
    assert keys[0] != keys[1]
