import os
import re
import uuid
from datetime import datetime, timezone
from functools import wraps

import bleach
from flask import (Flask, abort, flash, redirect, render_template, request,
                   session, url_for)

import storage
from letter_templates import LETTER_TYPES, render_body

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me")

ALLOWED_TAGS = ["p", "br", "strong", "em", "u", "s", "h1", "h2", "h3", "ul", "ol",
                "li", "blockquote", "span", "div", "a"]
ALLOWED_ATTRS = {"*": ["style", "class"], "a": ["href"]}


def clean_mobile(raw):
    digits = re.sub(r"\D", "", raw or "")
    return digits[-10:] if len(digits) >= 10 else None


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if "mobile" not in session:
            return redirect(url_for("login"))
        doctor = storage.get_doctor(session["mobile"])
        if not doctor or not doctor.get("active", True):
            session.clear()
            flash("Your account is deactivated. Contact the administrator.")
            return redirect(url_for("login"))
        return fn(*a, **kw)
    return wrapper

def wrap_letterhead(doctor, body_html, document_title):
    """Generate a print-friendly letter using a common hospital design."""
    return render_template(
        "letter_final.html",
        doctor=doctor,
        body=body_html,
        document_title=document_title
    )

# ---------- access by mobile number ----------
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        mobile = clean_mobile(request.form.get("mobile"))
        doctor = storage.get_doctor(mobile) if mobile else None
        if not doctor.get("active", True):
            flash("This doctor is deactivated. Cannot login.")
            return redirect(url_for("login"))
        # TODO: send/verify an OTP here (SMS gateway) before setting the session.
        session["mobile"] = mobile
        return redirect(url_for("letters"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
# ---------- add doctor from login page ----------
@app.route("/register", methods=["POST"])
def register_doctor():
    mobile = clean_mobile(request.form.get("mobile"))
    name = request.form.get("name", "").strip()
    if not mobile or not name:
        flash("Enter a valid doctor name and 10 digit mobile number.")
        return redirect(url_for("login"))
    if storage.get_doctor(mobile):
        flash("This mobile number is already added.")
        return redirect(url_for("login"))
    storage.save_doctor(mobile, {
        "name": name,
        "qualification": request.form.get("qualification", "").strip(),
        "reg_no": request.form.get("reg_no", "").strip(),
        "clinic": request.form.get("clinic", "").strip(),
        "address": request.form.get("address", "").strip(),
    })
    flash(f"Dr. {name} added. You can login now.")
    return redirect(url_for("login"))


# ---------- activate / deactivate ----------
@app.route("/doctor-status", methods=["POST"])
def doctor_status():
    mobile = clean_mobile(request.form.get("mobile"))
    action = request.form.get("action")
    doctor = storage.get_doctor(mobile) if mobile else None
    if not doctor:
        flash("Mobile number not registered.")
        return redirect(url_for("login"))
    doctor["active"] = (action == "activate")
    storage.save_doctor(mobile, doctor)
    flash(f"Dr. {doctor['name']} is now {'ACTIVE' if doctor['active'] else 'DEACTIVATED'}.")
    return redirect(url_for("login"))


# ---------- create letter ----------
@app.route("/new")
@login_required
def choose_type():
    return render_template("choose.html", types=LETTER_TYPES)


@app.route("/new/<letter_type>", methods=["GET", "POST"])
@login_required
def fill_form(letter_type):
    cfg = LETTER_TYPES.get(letter_type) or abort(404)
    if request.method == "POST":
        doctor = storage.get_doctor(session["mobile"])
        values = {name: request.form.get(name, "") for name, _, _ in cfg["fields"]}
        values["doctor_name"] = doctor["name"]
        values["date"] = datetime.now().strftime("%d %b %Y")
        body = render_body(letter_type, values)
        return render_template("editor.html", letter_type=letter_type, cfg=cfg,
                               body=body, title=values.get("patient_name", ""))
    return render_template("form.html", letter_type=letter_type, cfg=cfg)


@app.route("/finalize/<letter_type>", methods=["POST"])
@login_required
def finalize(letter_type):
    cfg = LETTER_TYPES.get(letter_type) or abort(404)
    mobile = session["mobile"]
    doctor = storage.get_doctor(mobile)
    body = bleach.clean(request.form["body"], tags=ALLOWED_TAGS,
                        attributes=ALLOWED_ATTRS, strip=True)
    letter = {
        "id": uuid.uuid4().hex[:12],
        "type": letter_type,
        "type_label": cfg["label"],
        "title": request.form.get("title", "").strip() or cfg["label"],
        "body": body,
        "doctor_mobile": mobile,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    storage.save_letter(
     mobile,
     letter,
     wrap_letterhead(doctor, body, cfg["label"])
)
    flash("Letter saved.")
    return redirect(url_for("view_letter", letter_id=letter["id"]))


# ---------- retrieve / share ----------
@app.route("/letters")
@login_required
def letters():
    return render_template("letters.html", letters=storage.list_letters(session["mobile"]))


@app.route("/letters/<letter_id>")
@login_required
def view_letter(letter_id):
    letter = storage.get_letter(session["mobile"], letter_id) or abort(404)
    html = storage.get_letter_html(session["mobile"], letter_id)
    return render_template("view.html", letter=letter, html=html)


@app.route("/letters/<letter_id>/share")
@login_required
def share(letter_id):
    storage.get_letter(session["mobile"], letter_id) or abort(404)
    token = storage.create_share_token(session["mobile"], letter_id)
    return render_template("share.html", url=url_for("shared", token=token, _external=True),
                           letter_id=letter_id)


@app.route("/shared/<token>")
def shared(token):
    """Public, expiring link (works for people who can reach this computer's address)."""
    html = storage.get_shared_html(token)
    return html if html else abort(404)


# ---------- admin CLI: flask --app app add-doctor 9876543210 "Asha Rao" ----------
@app.cli.command("init-db")
def init_db_command():
    storage.init_db()
    print("PostgreSQL database tables created successfully!")
@app.cli.command("add-doctor")
def add_doctor():
    import click
    mobile = clean_mobile(click.prompt("Mobile"))
    profile = {
        "name": click.prompt("Doctor name"),
        "qualification": click.prompt("Qualification", default=""),
        "reg_no": click.prompt("Registration no.", default=""),
        "clinic": click.prompt("Clinic / hospital", default=""),
        "address": click.prompt("Address", default=""),
    }
    storage.save_doctor(mobile, profile)
    click.echo(f"Saved doctor {mobile}")


if __name__ == "__main__":
    app.run(debug=True)
