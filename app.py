import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")  # TODO: set a real secret in production

DB_PATH = os.path.join(os.path.dirname(__file__), "connect.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # Seed one demo user so you can log in immediately (remove later)
    existing = conn.execute("SELECT * FROM users WHERE email = ?", ("demo@ops.on.ca",)).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@ops.on.ca", generate_password_hash("password123")),
        )
        conn.commit()
    conn.close()


@app.route("/", methods=["GET"])
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        error = None
        if not email or not password:
            error = "Please enter both email and password."
        else:
            conn = get_db()
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            conn.close()

            if user is None or not check_password_hash(user["password_hash"], password):
                error = "Invalid email or password."

        if error:
            flash(error, "error")
            return render_template("login.html", email=email)

        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        return redirect(url_for("dashboard"))

    return render_template("login.html", email="")


@app.route("/login/win")
def login_win():
    """
    Simulated WIN (OPS Workplace Identity Network) single sign-on.

    In production, replace this with a real SSO handshake (e.g. SAML or
    OAuth redirect to OPS's identity provider), then look up / provision
    the returned user instead of hardcoding the demo account below.
    """
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", ("demo@ops.on.ca",)).fetchone()
    conn.close()

    if user is None:
        flash("WIN sign-in failed. Please try email sign-in instead.", "error")
        return redirect(url_for("login"))

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["login_method"] = "win"
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return f"""
    <h1>Welcome, {session['user_name']}!</h1>
    <p>This is a placeholder dashboard — next piece we'll build out.</p>
    <a href='{url_for('logout')}'>Log out</a>
    """


if __name__ == "__main__":
    init_db()
    app.run(debug=True)