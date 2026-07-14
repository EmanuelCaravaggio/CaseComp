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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recognitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user_id INTEGER NOT NULL,
            to_user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (from_user_id) REFERENCES users (id),
            FOREIGN KEY (to_user_id) REFERENCES users (id)
        )
    """)


    conn.execute("""
    CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        title TEXT NOT NULL,

        type TEXT NOT NULL,

        status TEXT DEFAULT 'Draft',

        estimated_timeframe TEXT,

        description TEXT,

        organizational_priority TEXT,

        performance_measures TEXT,

        feedback TEXT,

        progress_updates TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")




    
    conn.commit()

    # Seed demo users so recognition feels like a real team (remove later)
    demo_users = [
        ("Johan Geosy", "demo@ops.on.ca", "password123"),
        ("Priya Nair", "priya.nair@ops.on.ca", "password123"),
        ("Marcus Chen", "marcus.chen@ops.on.ca", "password123"),
        ("Aisha Bello", "aisha.bello@ops.on.ca", "password123"),
    ]
    for name, email, pw in demo_users:
        existing = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(pw)),
            )
    conn.commit()

    # Rename demo user to Johan
    conn.execute(
    "UPDATE users SET name = ? WHERE email = ?",
    ("Johan Geosy", "demo@ops.on.ca")
)
    conn.commit()

    # Seed a couple of sample recognitions so the feed isn't empty on first run
    count = conn.execute("SELECT COUNT(*) AS c FROM recognitions").fetchone()["c"]
    if count == 0:
        users = {row["email"]: row["id"] for row in conn.execute("SELECT id, email FROM users").fetchall()}
        sample = [
            (users["priya.nair@ops.on.ca"], users["demo@ops.on.ca"], "Teamwork",
             "Thanks for jumping in to help troubleshoot the ministry laptop issue last-minute — saved the whole team a lot of stress!"),
            (users["marcus.chen@ops.on.ca"], users["aisha.bello@ops.on.ca"], "Going Above & Beyond",
             "Aisha stayed late to walk a new employee through their onboarding checklist step by step. That kind of patience matters."),
            (users["demo@ops.on.ca"], users["marcus.chen@ops.on.ca"], "Innovation",
             "Your idea to automate the ticket triage process is going to save the team hours every week."),
        ]
        for from_id, to_id, category, message in sample:
            conn.execute(
                "INSERT INTO recognitions (from_user_id, to_user_id, category, message) VALUES (?, ?, ?, ?)",
                (from_id, to_id, category, message),
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


RECOGNITION_CATEGORIES = [
    "Teamwork",
    "Innovation",
    "Leadership",
    "Going Above & Beyond",
    "Client Service",
    "Mentorship",
]


@app.route("/dashboard")
def dashboard():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    conn = get_db()

    colleagues = conn.execute(
        "SELECT id, name FROM users WHERE id != ? ORDER BY name", (user_id,)
    ).fetchall()

    feed = conn.execute("""
        SELECT r.id, r.category, r.message, r.created_at,
               sender.name AS from_name,
               receiver.name AS to_name
        FROM recognitions r
        JOIN users sender ON r.from_user_id = sender.id
        JOIN users receiver ON r.to_user_id = receiver.id
        ORDER BY r.created_at DESC
        LIMIT 20
    """).fetchall()

    given_count = conn.execute(
        "SELECT COUNT(*) AS c FROM recognitions WHERE from_user_id = ?", (user_id,)
    ).fetchone()["c"]
    received_count = conn.execute(
        "SELECT COUNT(*) AS c FROM recognitions WHERE to_user_id = ?", (user_id,)
    ).fetchone()["c"]

    conn.close()

    return render_template(
        "dashboard.html",
        user_name=session["user_name"],
        colleagues=colleagues,
        feed=feed,
        given_count=given_count,
        received_count=received_count,
        categories=RECOGNITION_CATEGORIES,
    )


@app.route("/recognition/give", methods=["POST"])
def give_recognition():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    to_user_id = request.form.get("to_user_id")
    category = request.form.get("category", "").strip()
    message = request.form.get("message", "").strip()

    if not to_user_id or not category or not message:
        flash("Please fill out all fields to send recognition.", "error")
        return redirect(url_for("dashboard"))

    if str(to_user_id) == str(user_id):
        flash("You can't send recognition to yourself.", "error")
        return redirect(url_for("dashboard"))

    conn = get_db()
    conn.execute(
        "INSERT INTO recognitions (from_user_id, to_user_id, category, message) VALUES (?, ?, ?, ?)",
        (user_id, to_user_id, category, message),
    )
    conn.commit()
    conn.close()

    flash("Recognition sent!", "success")
    return redirect(url_for("dashboard"))



@app.route("/profile")
def profile():
    return render_template("profile.html")

@app.route("/mentorship", methods=["GET", "POST"])
def mentorship():

    if request.method == "POST":

        pronouns = request.form.get("pronouns")
        location = request.form.get("location")
        language = request.form.get("language")

        mentorship_goals = request.form.get("mentorship_goals")

        learning_methods = request.form.getlist("learning_methods")

        employee_networks = request.form.getlist("employee_networks")

        meeting_types = request.form.getlist("meeting_types")

        meeting_frequency = request.form.getlist("meeting_frequency")

        meeting_length = request.form.getlist("meeting_length")

        mentorship_duration = request.form.getlist("mentorship_duration")


        # TODO:
        # Save this information into your database here


        flash("Mentorship profile saved successfully!", "success")

        return redirect(url_for("mentorship"))


    return render_template(
        "mentorship.html",
        user_name="Johan"
    )

@app.route("/connections")
def connections():
    return render_template("connections.html")




@app.route("/performance")
def performance():


    user_name = session.get("user_name", "Johan Geosy")

    conn = get_db()


    goals = conn.execute(
        "SELECT * FROM goals ORDER BY created_at DESC"
    ).fetchall()


    selected_goal = None


    goal_id = request.args.get("goal_id")


    if goal_id:

        selected_goal = conn.execute(
            "SELECT * FROM goals WHERE id = ?",
            (goal_id,)
        ).fetchone()



    conn.close()


    return render_template(
        "performance.html",
        user_name=user_name,
        goals=goals,
        selected_goal=selected_goal
    )

@app.route("/create_goal", methods=["GET", "POST"])
def create_goal():

    if request.method == "POST":

        title = request.form["title"]

        goal_type = request.form["type"]


        conn = get_db()


        conn.execute("""
            INSERT INTO goals
            (
                title,
                type,
                status,
                estimated_timeframe,
                description,
                organizational_priority,
                performance_measures,
                feedback,
                progress_updates
            )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

        """,
        (
            title,
            goal_type.lower().replace(" goal", ""),
            "Draft",
            "May 2026 to Aug 2026",
            "",
            "",
            "",
            "",
            ""
        ))


        conn.commit()

        conn.close()



        flash(
            "Goal created successfully!",
            "success"
        )


        return redirect(
            url_for("performance")
        )



    return render_template(
        "create_goal.html",
        user_name=session.get("user_name", "Johan Geosy")
    )









@app.route("/update_goal/<int:goal_id>", methods=["POST"])
def update_goal(goal_id):


    conn = get_db()



    conn.execute("""
        UPDATE goals

        SET

            title = ?,
            estimated_timeframe = ?,
            description = ?,
            organizational_priority = ?,
            performance_measures = ?,
            feedback = ?,
            progress_updates = ?

        WHERE id = ?

    """,
    (
        request.form["goal_title"],

        f"{request.form.get('start_date')} to {request.form.get('end_date')}",

        request.form["description"],

        request.form["organizational_priority"],

        request.form["performance_measures"],

        request.form["feedback"],

        request.form["progress_updates"],

        goal_id
    ))



    conn.commit()

    conn.close()



    flash(
        "Goal updated successfully!",
        "success"
    )



    return redirect(
        url_for(
            "performance",
            goal_id=goal_id
        )
    )



@app.route("/delete_goal/<int:goal_id>", methods=["POST"])
def delete_goal(goal_id):


    conn = get_db()



    conn.execute(
        """
        DELETE FROM goals
        WHERE id = ?
        """,
        (goal_id,)
    )



    conn.commit()

    conn.close()



    flash(
        "Goal deleted successfully!",
        "success"
    )



    return redirect(
        url_for("performance")
    )

@app.route("/profile/<person>")
def person_profile(person):

    profiles = {

        "sarah": {
            "name": "Sarah Thompson",
            "role": "Program Advisor",
            "department": "Student Services",
            "bio": "Helping teams improve programs and employee engagement."
        },


        "david": {
            "name": "David Kumar",
            "role": "Business Analyst",
            "department": "Operations",
            "bio": "Focused on analytics, reporting, and process improvement."
        },


        "emma": {
            "name": "Emma Wilson",
            "role": "Project Coordinator",
            "department": "Projects",
            "bio": "Coordinates projects and supports cross-functional teams."
        }

    }


    profile = profiles.get(person)


    return render_template(
        "person_profile.html",
        profile=profile
    )



if __name__ == "__main__":
    init_db()
    app.run(debug=True)