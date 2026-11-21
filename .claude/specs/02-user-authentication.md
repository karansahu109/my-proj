# Spec Document: User Login and Signup

## 1. Overview

Implement account registration, login, and logout for the existing Flask application, using the SQLite users table established by database setup. The landing page remains an illustrative static page; expense and profile features remain placeholders.

## 2. Depends on

- `.claude/specs/01-database-setup.md`: initialized SQLite `users` table and `get_db()` helper.
- Existing Flask and Werkzeug dependencies; no new packages or ORM.

## 3. Routes and Expected Behavior

- `GET /register` and `GET /login` display their forms. `POST` submits them with a CSRF token.
- `POST /register` trims the name, trims and lowercases the email, validates the fields, hashes the password, and creates one user. It immediately signs in the new user and redirects to `/`.
- `POST /login` normalizes the email and verifies the password against the stored hash. On success it signs in the user and redirects to `/`. The existing seeded demo credentials must work even though its password is shorter than the new signup minimum.
- `POST /logout` requires a valid CSRF token, clears the session, and redirects to `/`. `GET /logout` must not change state.
- The navigation shows Sign in / Get started to signed-out visitors and a Sign out button to signed-in visitors, including on mobile.
- Authentication does not implement or protect the existing placeholder profile and expense routes in this step.

## 4. Validation and Errors

- Name is required after trimming and at most 100 characters.
- Email is required, at most 254 characters, and must have a conventional ASCII local part and dotted domain. The local part is at most 64 characters with no leading, trailing, or consecutive dots; domain labels are at most 63 characters. Matching and duplicate checks are case-insensitive, including for existing mixed-case database records. Registered email is stored lowercase.
- New passwords must be 8–1024 characters; passwords are not trimmed. Login accepts existing shorter passwords but rejects missing or over-1024-character passwords.
- Missing or invalid fields redisplay the appropriate form with an actionable error and HTTP 400. Duplicate emails redisplay registration with HTTP 409. Failed logins use one generic error and HTTP 400 for unknown email or wrong password.
- Preserve submitted name/email on errors, but never render submitted passwords or hashes. Reject missing or invalid CSRF tokens on all three POST routes with HTTP 400 without changing authentication or account data.
- Use parameterized SQL, explicitly close connections, and make duplicate checking and insertion safe against concurrent registrations. Unexpected database errors must not be reported as ordinary duplicate emails.

## 5. Session and Security

- Clear old session data when signing in; store only the user's ID in the signed session. Never store passwords or password hashes in it.
- Generate and verify unpredictable session-bound CSRF tokens, using constant-time comparison; rotate them when authentication state changes.
- Configure `HttpOnly` and `SameSite=Lax` session cookies. A stable secret must be supplied via `SECRET_KEY` for persistent sessions across restarts and workers; otherwise use an ephemeral random key for local development. Set `SESSION_COOKIE_SECURE=1` when serving over HTTPS.
- This step does not add rate limiting, email verification, password reset, or production deployment safeguards. Existing startup seeding still creates publicly known demo credentials on an empty database, so the application must not be deployed publicly without addressing that behavior and other production hardening.

## 6. Files

- Change: `app.py`, `templates/base.html`, `templates/login.html`, `templates/register.html`, `static/css/style.css`.
- Create: automated tests for authentication, this specification, and the corresponding implementation plan.
- Preserve the existing database schema, database setup implementation, and unrelated routes.

## 7. Definition of Done

- [x] Valid registration persists a normalized user with a verifiable password hash and signs them in.
- [x] Required fields, length and email rules, duplicate/mixed-case emails, and generic login errors behave as specified without exposing passwords.
- [x] Valid login (including the seeded demo account) creates a session; failed login does not.
- [x] Logout requires POST and a valid CSRF token, then clears authentication.
- [x] All three state-changing auth actions reject absent or invalid CSRF tokens without side effects.
- [x] Navigation reflects authentication state.
- [ ] Navigation remains usable on mobile: the stylesheet was inspected, but no mobile browser rendering was tested.
- [x] Tests run against isolated temporary databases, verify these criteria and preserve existing seed/startup behavior.
- [x] Environment configuration and production limitations are documented.

## 8. Verification Results

- `python -m pytest -q`: **41 passed**, using temporary SQLite databases and Flask's test client. Tests include concurrent duplicate registration, password boundaries, legacy mixed-case email, seeded demo login, CSRF rejection and session rotation, and environment configuration.
- The mobile CSS hides non-CTA navigation links, not the sign-out button. This was a source inspection only, not a viewport or browser test.
- The fallback `SECRET_KEY` is regenerated on restart, so sessions will not survive restarts or work across independently started workers. Supply the same strong secret to all workers and use HTTPS with `SESSION_COOKIE_SECURE=1`. The existing debug-mode entry point and publicly known seeded demo account are development-only; production hardening, including rate limiting, remains out of scope.
