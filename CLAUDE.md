# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development commands

From the repository root, create a virtual environment and install the pinned dependencies:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

- Run the development server: `python app.py` (Flask debug mode, port 5001).
- Run tests: `python -m pytest`.
- Run one test, once tests exist: `python -m pytest path/to/test_file.py::test_name`.

There are currently no project tests; pytest exits with code 5 when it collects none. No build or lint command is configured.

## Architecture

This is a small server-rendered Flask application. `app.py` defines one module-level app and all routes; there is no app factory or blueprint layer. The landing, login, and registration routes render Jinja templates. The logout, profile, and expense add/edit/delete routes are placeholders.

`templates/base.html` supplies the shared navigation, layout, and CSS/JavaScript assets; the page templates extend it. The landing page's dashboard is illustrative static markup, not data from the server. `static/js/main.js` is currently a placeholder.

Authentication and persistence are not implemented. The login and registration forms submit POST requests, but their routes currently accept only GET, so submitting them returns 405. `database/db.py` describes future SQLite helpers but is not wired into the app; `expense_tracker.db` is ignored by Git.
