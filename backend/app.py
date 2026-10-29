"""app.py - Flask entry point: auth + registers the assessment/step/report/neuro blueprints."""
import re
import secrets
import time
from functools import wraps

from flask import Flask, request, jsonify, g
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

import config
import db
from db import get_connection
from routes.assessments import assessments_bp
from routes.steps import steps_bp
from routes.report import report_bp
from routes.neuro import neuro_bp

app = Flask(__name__)
CORS(app)

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 300
TOKEN_LIFETIME_SECONDS = 12 * 60 * 60   # 12 hours
MIN_PASSWORD_LENGTH = 8
USERNAME_PATTERN = re.compile(r'^[A-Za-z0-9_]{3,32}$')


# ---------- Auth helpers ----------

def new_recovery_code():
    raw = secrets.token_hex(5).upper()
    return f'{raw[:5]}-{raw[5:]}'


def validate_username(username):
    return bool(USERNAME_PATTERN.match(username))


def check_lockout(account):
    remaining = account['lockout_until'] - time.time()
    return int(remaining) + 1 if remaining > 0 else 0


def record_failed_attempt(conn, account):
    attempts = account['failed_attempts'] + 1
    lockout = time.time() + LOCKOUT_SECONDS if attempts >= MAX_LOGIN_ATTEMPTS else 0
    if attempts >= MAX_LOGIN_ATTEMPTS:
        attempts = 0
    conn.execute(
        'UPDATE accounts SET failed_attempts = ?, lockout_until = ? WHERE id = ?',
        (attempts, lockout, account['id'])
    )
    return MAX_LOGIN_ATTEMPTS - attempts if lockout == 0 else 0


def clear_failed_attempts(conn, account_id):
    conn.execute('UPDATE accounts SET failed_attempts = 0, lockout_until = 0 WHERE id = ?', (account_id,))


def issue_token(conn, account_id):
    token = secrets.token_urlsafe(32)
    conn.execute(
        'INSERT INTO auth_tokens (token, account_id, expires_at) VALUES (?, ?, ?)',
        (token, account_id, time.time() + TOKEN_LIFETIME_SECONDS)
    )
    return token


def check_auth():
    """Validate the Bearer token on the request. Sets g.account_id on success.
    Returns (json_response, status_code) on failure, or None on success."""
    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        return jsonify({'error': 'Please sign in first.'}), 401
    token = header[len('Bearer '):].strip()
    with get_connection() as conn:
        row = conn.execute(
            'SELECT account_id, expires_at FROM auth_tokens WHERE token = ?', (token,)
        ).fetchone()
        if row is None or time.time() > row['expires_at']:
            if row is not None:
                conn.execute('DELETE FROM auth_tokens WHERE token = ?', (token,))
            return jsonify({'error': 'Your session has expired. Please sign in again.'}), 401
        g.account_id = row['account_id']
    return None


def require_auth(view):
    """Decorator for individual routes (used by /api/auth/me and /logout)."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        err = check_auth()
        if err:
            return err
        return view(*args, **kwargs)
    return wrapper


def _auth_guard():
    """Blueprint-level before_request hook. Returning a value short-circuits Flask
    and sends that as the response, so every route in a guarded blueprint is protected."""
    return check_auth()


# ---------- Auth routes ----------

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))

    if not data.get('consent'):
        return jsonify({'error': 'You must agree to the privacy policy to create an account.'}), 400
    if not validate_username(username):
        return jsonify({'error': 'Username must be 3 to 32 letters, numbers or underscores.'}), 400
    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({'error': f'Password must be at least {MIN_PASSWORD_LENGTH} characters.'}), 400

    recovery_code = new_recovery_code()
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                'INSERT INTO accounts (username, password_hash, recovery_hash) VALUES (?, ?, ?)',
                (username, generate_password_hash(password), generate_password_hash(recovery_code))
            )
            conn.execute('INSERT INTO consent_logs (account_id) VALUES (?)', (cursor.lastrowid,))
    except Exception as e:
        if 'UNIQUE' in str(e):
            return jsonify({'error': 'That username is already taken.'}), 400
        raise

    return jsonify({
        'status': 'success',
        'message': 'Account created. Save your recovery code now. It is shown only once.',
        'recovery_code': recovery_code,
    }), 201


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))

    with get_connection() as conn:
        account = conn.execute('SELECT * FROM accounts WHERE username = ?', (username,)).fetchone()

        if account is None:
            return jsonify({'error': 'Invalid username or password.'}), 401

        locked_for = check_lockout(account)
        if locked_for:
            return jsonify({'error': f'Too many failed attempts. Try again in {locked_for} seconds.'}), 403

        if not check_password_hash(account['password_hash'], password):
            left = record_failed_attempt(conn, account)
            if left == 0:
                return jsonify({'error': 'Too many failed attempts. Account locked for 5 minutes.'}), 403
            return jsonify({'error': f'Invalid username or password. {left} attempts left.'}), 401

        clear_failed_attempts(conn, account['id'])
        token = issue_token(conn, account['id'])

    return jsonify({'status': 'success', 'token': token, 'username': account['username']})


@app.route('/api/auth/logout', methods=['POST'])
@require_auth
def logout():
    token = request.headers.get('Authorization', '')[len('Bearer '):].strip()
    with get_connection() as conn:
        conn.execute('DELETE FROM auth_tokens WHERE token = ?', (token,))
    return jsonify({'status': 'success'})


@app.route('/api/auth/me', methods=['GET'])
@require_auth
def me():
    with get_connection() as conn:
        account = conn.execute('SELECT username FROM accounts WHERE id = ?', (g.account_id,)).fetchone()
    return jsonify({'username': account['username']})


@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip()
    recovery_code = str(data.get('recovery_code', '')).strip().upper()
    new_password = str(data.get('new_password', ''))

    if len(new_password) < MIN_PASSWORD_LENGTH:
        return jsonify({'error': f'New password must be at least {MIN_PASSWORD_LENGTH} characters.'}), 400

    with get_connection() as conn:
        account = conn.execute('SELECT * FROM accounts WHERE username = ?', (username,)).fetchone()
        if account is None:
            return jsonify({'error': 'Username or recovery code is incorrect.'}), 400

        locked_for = check_lockout(account)
        if locked_for:
            return jsonify({'error': f'Too many failed attempts. Try again in {locked_for} seconds.'}), 403

        if not check_password_hash(account['recovery_hash'], recovery_code):
            record_failed_attempt(conn, account)
            return jsonify({'error': 'Username or recovery code is incorrect.'}), 400

        conn.execute(
            'UPDATE accounts SET password_hash = ? WHERE id = ?',
            (generate_password_hash(new_password), account['id'])
        )
        conn.execute('DELETE FROM auth_tokens WHERE account_id = ?', (account['id'],))
        clear_failed_attempts(conn, account['id'])

    return jsonify({'status': 'success', 'message': 'Password changed. Please sign in with the new password.'})


# ---------- Protect the existing assessment/step/report/neuro routes ----------
assessments_bp.before_request(_auth_guard)
steps_bp.before_request(_auth_guard)
report_bp.before_request(_auth_guard)
neuro_bp.before_request(_auth_guard)

app.register_blueprint(assessments_bp)
app.register_blueprint(steps_bp)
app.register_blueprint(report_bp)
app.register_blueprint(neuro_bp)


if __name__ == '__main__':
    db.init_db()
    app.run(port=config.PORT, debug=config.DEBUG)