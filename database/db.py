"""SQLite connection, schema, and development seed data."""

import calendar
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash


DB_PATH = Path(__file__).resolve().parent.parent / "expense_tracker.db"


def get_db():
    """Open a database connection; the caller is responsible for closing it."""
    connection = sqlite3.connect(DB_PATH)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
    except BaseException:
        connection.close()
        raise
    return connection


def init_db():
    """Create the database tables if they do not already exist."""
    with closing(get_db()) as connection:
        with connection:
            connection.execute("BEGIN")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    date TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
                """
            )


def seed_db():
    """Seed a demo account and expenses only when there are no users."""
    with closing(get_db()) as connection:
        with connection:
            # Serialize the check and inserts across concurrent app startups.
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                return

            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
            )
            user_id = cursor.lastrowid
            today = date.today()
            last_day = calendar.monthrange(today.year, today.month)[1]
            examples = (
                ("Food", 24.50, "Groceries"),
                ("Transport", 15.00, "Bus fare"),
                ("Bills", 80.00, "Electricity"),
                ("Health", 30.00, "Pharmacy"),
                ("Entertainment", 12.50, "Movie"),
                ("Shopping", 45.00, "Household items"),
                ("Other", 10.00, "Miscellaneous"),
                ("Food", 18.00, "Lunch"),
            )
            expenses = [
                (
                    user_id,
                    amount,
                    category,
                    date(today.year, today.month, 1 + index * (last_day - 1) // 7).isoformat(),
                    description,
                )
                for index, (category, amount, description) in enumerate(examples)
            ]
            connection.executemany(
                """
                INSERT INTO expenses (user_id, amount, category, date, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                expenses,
            )
