import os
import hmac
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from flask import (Flask, jsonify, render_template, redirect, url_for, flash, request, abort)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, login_required, logout_user, current_user)
from flask_wtf import FlaskForm
from wtforms import (EmailField, PasswordField, StringField, SubmitField)
from wtforms.validators import (DataRequired, Email, Length, ValidationError)
from werkzeug.security import (generate_password_hash, check_password_hash)

# --------------------------------------------------
# Lädt Konfigurationswerte aus der .env-Datei, damit sensible Zugangsdaten nicht im Quellcode gespeichert werden müssen
# --------------------------------------------------

load_dotenv()

# --------------------------------------------------
# Flask App DB Connect
# --------------------------------------------------

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{os.getenv('DB_USER')}:"
    f"{os.getenv('DB_PASSWORD')}@"
    f"{os.getenv('DB_HOST')}/"
    f"{os.getenv('DB_NAME')}"
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Bitte anmelden um diese Seite aufzurufen."
login_manager.login_message_category = "warning"
login_manager.init_app(app)

# --------------------------------------------------
# Datenbankmodelle für Benutzer und Eventbuchungen
# --------------------------------------------------

class User(UserMixin, db.Model):
    # Speichert Kontodaten, Administratorrechte und den aktuellen Abo-Status.
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    payment_status = db.Column(db.String(30), nullable=True, default=None)
    subscription_type = db.Column(db.String(30), nullable=False, default="none")
    subscription_start = db.Column(db.Date, nullable=True)
    subscription_end = db.Column(db.Date, nullable=True)
    event_bookings = db.relationship("EventBooking", backref="user", cascade="all, delete-orphan", lazy=True)

    @property
    def payment_status_label(self):
        # Bereitet den internen Zahlungsstatus für die Anzeige im Frontend auf.
        if self.subscription_type == "none" or not self.payment_status:
            return ""
        if self.payment_status == "paid":
            return "Bezahlt"
        if self.payment_status == "pending":
            return "Pendent"
        return ""

    @property
    def subscription_label(self):
        # Übersetzt die technischen Abo-Werte in verständliche Bezeichnungen.
        labels = {
            "none": "Kein Abo",
            "monthly": "Monatsabo",
            "yearly": "Jahresabo",
            "single": "Einzel-Eintritt",
        }
        return labels.get(self.subscription_type, "Kein Abo")

    @property
    def has_active_subscription(self):
        # Ein Abo ist nur gültig, wenn es bezahlt und noch nicht abgelaufen ist.
        if self.subscription_type not in {"monthly", "yearly"}:
            return False
        if self.payment_status != "paid":
            return False
        if not self.subscription_end:
            return False
        return self.subscription_end >= date.today()

class Event(db.Model):
    # Veranstaltungen mit einer begrenzten Anzahl an Teilnehmerplätzen.
    __tablename__ = "events"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    event_date = db.Column(db.Date, nullable=False)
    max_participants = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    bookings = db.relationship("EventBooking", backref="event", cascade="all, delete-orphan", lazy=True)

    @property
    def booked_count(self):
        # Anzahl der aktuell registrierten Teilnehmer.
        return len(self.bookings)

    @property
    def free_slots(self):
        # Freie Plätze dürfen niemals als negative Zahl angezeigt werden.
        return max(self.max_participants - self.booked_count, 0)

    @property
    def is_full(self):
        # Wird vor einer neuen Eventbuchung zur Kapazitätsprüfung verwendet.
        return self.booked_count >= self.max_participants


class EventBooking(db.Model):
    # Verknüpft einen Benutzer mit einem Event.
    __tablename__ = "event_bookings"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("event_id", "user_id", name="uq_event_booking_user"),
    )

# --------------------------------------------------
# Login
# --------------------------------------------------

@login_manager.user_loader
def load_user(user_id):
    # Flask-Login lädt den Benutzer anhand der gespeicherten User-ID
    return User.query.get(int(user_id))

# --------------------------------------------------
# Forms
# --------------------------------------------------

class RegisterForm(FlaskForm):
    username = StringField(
        "Benutzername",
        validators=[
            DataRequired(),
            Length(min=3, max=32)
        ]
    )

    email = EmailField(
        "E-Mail",
        validators=[
            DataRequired(),
            Email()
        ]
    )

    password = PasswordField(
        "Passwort",
        validators=[
            DataRequired(),
            Length(min=8)
        ]
    )

    submit = SubmitField("Registrieren")

class LoginForm(FlaskForm):
    username = StringField(
        "Benutzername",
        validators=[
            DataRequired(),
            Length(min=3, max=32)
        ]
    )

    password = PasswordField(
        "Passwort",
        validators=[
            DataRequired()
        ]
    )

    submit = SubmitField("Anmelden")


def parse_date(value):
    # Wandelt ein HTML-Datumsfeld sicher in ein Python-Datum um.
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def require_admin_api_key():
    # Schützt die externen Admin-Endpunkte mit dem Schlüssel aus der .env-Datei.
    provided_key = request.headers.get("X-API-Key", "")
    if not ADMIN_API_KEY or not hmac.compare_digest(provided_key, ADMIN_API_KEY):
        return jsonify(error="Ungültiger oder fehlender API-Key."), 401
    return None

# Berechnet das Enddatum eines Monats- oder Jahresabos anhand des Startdatums.
def calculate_subscription_end(start_date, subscription_type):
    if not start_date:
        return None
    if subscription_type == "monthly":
        return start_date + timedelta(days=31)
    if subscription_type == "yearly":
        return start_date + timedelta(days=365)
    return None

# --------------------------------------------------
# Routes
# --------------------------------------------------

@app.route("/")
@login_required
def dashboard():
    # Lädt kommende Events und die Eventanmeldungen des eingeloggten Benutzers.
    events = (
        Event.query
        .filter(Event.event_date >= date.today())
        .order_by(Event.event_date, Event.id)
        .all()
    )

    user_event_bookings = (
        EventBooking.query
        .filter_by(user_id=current_user.id)
        .join(Event)
        .order_by(Event.event_date)
        .all()
    )

    return render_template(
        "dashboard.html",
        events=events,
        user_event_bookings=user_event_bookings,
        today=date.today().isoformat()
    )


@app.route("/admin")
@login_required
def admin_dashboard():
    # Zeigt Admins alle Benutzer, Events und offenen Zahlungen.
    if not current_user.is_admin:
        abort(403)

    events = Event.query.order_by(Event.event_date, Event.id).all()
    event_bookings = EventBooking.query.join(Event).order_by(Event.event_date, EventBooking.id).all()
    users = User.query.order_by(User.username).all()
    pending_payments = User.query.filter_by(payment_status="pending").order_by(User.username).all()
    selected_user = None

    selected_user_id = request.args.get("user_id", type=int)
    if selected_user_id:
        selected_user = User.query.get(selected_user_id)

    return render_template(
        "admin.html",
        events=events,
        event_bookings=event_bookings,
        users=users,
        pending_payments=pending_payments,
        selected_user=selected_user,
        today=date.today().isoformat(),
    )


@app.route("/admin/user/<int:user_id>/update", methods=["POST"])
@login_required
def admin_update_user(user_id):
    # Aktualisiert Passwort, Abo und Zahlungsstatus eines Benutzers.
    if not current_user.is_admin:
        abort(403)

    user = User.query.get_or_404(user_id)
    password = request.form.get("password", "").strip()
    if password:
        user.password_hash = generate_password_hash(password)

    subscription_type = request.form.get("subscription_type", "").strip().lower()
    valid_types = {"none", "monthly", "yearly"}
    if subscription_type in valid_types:
        user.subscription_type = subscription_type

    payment_status = request.form.get("payment_status", "").strip().lower()
    if user.subscription_type == "none":
        user.payment_status = None
    elif payment_status in {"pending", "paid"}:
        user.payment_status = payment_status
    else:
        user.payment_status = "pending"

    if user.subscription_type in {"monthly", "yearly"}:
        subscription_start = parse_date(request.form.get("subscription_start")) or date.today()
        user.subscription_start = subscription_start
        user.subscription_end = calculate_subscription_end(user.subscription_start, user.subscription_type)
    else:
        user.subscription_start = None
        user.subscription_end = None
        user.payment_status = None

    if user.subscription_start and user.subscription_end and user.subscription_end < user.subscription_start:
        flash("Das Abo-Ende darf nicht vor dem Startdatum liegen.", "danger")
        return redirect(url_for("admin_dashboard"))

    db.session.commit()
    flash("Kontodaten wurden gespeichert.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    # Zeigt das eigene Profil und verarbeitet eine Passwortänderung.
    if request.method == "POST":
        new_password = request.form.get("new_password", "").strip()
        if not new_password:
            flash("Bitte ein neues Passwort eingeben.", "danger")
            return redirect(url_for("profile"))

        if len(new_password) < 8:
            flash("Das Passwort muss mindestens 8 Zeichen lang sein.", "danger")
            return redirect(url_for("profile"))

        current_user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash("Passwort wurde erfolgreich geändert.", "success")
        return redirect(url_for("profile"))

    return render_template("profile.html", user=current_user)


@app.route("/admin/event/add", methods=["POST"])
@login_required
def admin_add_event():
    # Prüft die Eingaben und erstellt ein neues Event.
    if not current_user.is_admin:
        abort(403)

    title = (request.form.get("title") or "").strip()
    event_date_str = request.form.get("event_date", "").strip()
    max_participants = request.form.get("max_participants", "1").strip()

    if not title or not event_date_str:
        flash("Titel und Datum sind erforderlich.", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Bitte ein gültiges Datum auswählen.", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        capacity = int(max_participants)
    except ValueError:
        flash("Bitte eine gültige Anzahl Plätze eingeben.", "danger")
        return redirect(url_for("admin_dashboard"))

    if capacity <= 0:
        flash("Die Anzahl Plätze muss größer als 0 sein.", "danger")
        return redirect(url_for("admin_dashboard"))

    event = Event(
        title=title,
        event_date=event_date,
        max_participants=capacity
    )
    db.session.add(event)
    db.session.commit()

    flash("Event wurde erstellt.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/event/<int:event_id>/delete", methods=["POST"])
@login_required
def admin_delete_event(event_id):
    # Löscht ein Event inklusive der zugehörigen Anmeldungen.
    if not current_user.is_admin:
        abort(403)

    event = Event.query.get_or_404(event_id)
    event_title = event.title

    db.session.delete(event)
    db.session.commit()

    flash(f"Event '{event_title}' wurde gelöscht.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/event/book", methods=["POST"])
@login_required
def book_event():
    # Meldet den aktuellen Benutzer für ein Event mit freien Plätzen an.
    event_id = request.form.get("event_id", type=int)
    if event_id is None:
        flash("Bitte ein Event auswählen.", "danger")
        return redirect(url_for("dashboard"))

    event = Event.query.get_or_404(event_id)

    if event.event_date < date.today():
        flash("Dieses Event liegt in der Vergangenheit.", "danger")
        return redirect(url_for("dashboard"))

    if EventBooking.query.filter_by(event_id=event.id, user_id=current_user.id).first():
        flash("Du bist für dieses Event bereits angemeldet.", "warning")
        return redirect(url_for("dashboard"))

    if event.is_full:
        flash("Dieses Event ist bereits ausgebucht.", "warning")
        return redirect(url_for("dashboard"))

    booking = EventBooking(event_id=event.id, user_id=current_user.id)
    db.session.add(booking)
    db.session.commit()

    flash(f"Du hast dich für {event.title} angemeldet.", "success")
    return redirect(url_for("dashboard"))


@app.route("/event/cancel/<int:event_booking_id>")
@login_required
def cancel_event(event_booking_id):
    # Entfernt nur die eigene Anmeldung von einem Event.
    booking = EventBooking.query.filter_by(id=event_booking_id, user_id=current_user.id).first_or_404()
    db.session.delete(booking)
    db.session.commit()
    flash("Deine Anmeldung wurde gelöscht.", "success")
    return redirect(url_for("dashboard"))

# --------------------------------------------------
# Angebot Seite
# --------------------------------------------------

@app.route("/angebot")
def offer():
    # Öffentliche Seite mit den verfügbaren Angeboten.
    return render_template("offer.html")

# --------------------------------------------------
# Registrierung, Login und Logout
# --------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    # Validiert neue Konten und speichert Passwörter ausschliesslich als Hash.

    form = RegisterForm()

    if form.validate_on_submit():

        normalized_username = form.username.data.strip()
        normalized_email = form.email.data.lower().strip()

        existing_user = (
            User.query.filter(
                (User.username == normalized_username) |
                (User.email == normalized_email)
            ).first()
        )

        if existing_user:
            if existing_user.username == normalized_username:
                flash("Benutzername ist bereits registriert.", "danger")
            else:
                flash("E-Mail-Adresse ist bereits registriert.", "danger")
            return render_template("register.html", form=form)

        user = User(
            username=normalized_username,
            email=normalized_email,
            # Passwörter werden nur als Hash gespeichert
            password_hash=generate_password_hash(
                form.password.data
            )
        )

        db.session.add(user)
        db.session.commit()

        flash("Registrierung erfolgreich.", "success")

        return redirect(url_for("login"))

    return render_template(
        "register.html",
        form=form
    )

# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    # Prüft die Anmeldedaten und startet eine Flask-Login-Sitzung.

    form = LoginForm()

    if form.validate_on_submit():
        username = form.username.data.strip()

        user = User.query.filter_by(
            username=username
        ).first()

        if user and check_password_hash(
            user.password_hash,
            form.password.data
        ):
            login_user(user)

            return redirect(
                url_for("dashboard")
            )

        flash(
            "Ungültiger Benutzername oder Passwort.",
            "danger"
        )

    return render_template(
        "login.html",
        form=form
    )

# --------------------------------------------------

@app.route("/logout")
@login_required
def logout():
    # Beendet die aktuelle Benutzersitzung.

    logout_user()

    return redirect(
        url_for("login")
    )


# --------------------------------------------------
# REST API
# --------------------------------------------------

@app.route("/api/admin/users/pending-payments", methods=["GET"])
def api_admin_pending_payments():
    # Liefert Benutzer mit noch nicht bestätigter Zahlung als JSON zurück.
    api_key_error = require_admin_api_key()
    if api_key_error:
        return api_key_error

    users = (
        User.query
        .filter_by(payment_status="pending")
        .order_by(User.username)
        .all()
    )

    return jsonify(
        users=[
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "payment_status": user.payment_status,
                "subscription_type": user.subscription_type,
                "subscription_start": user.subscription_start.isoformat() if user.subscription_start else None,
                "subscription_end": user.subscription_end.isoformat() if user.subscription_end else None,
            }
            for user in users
        ]
    )


@app.route("/api/admin/events", methods=["GET"])
def api_admin_events():
    # Liefert Events und die zugehörigen Teilnehmer für externe Clients.
    api_key_error = require_admin_api_key()
    if api_key_error:
        return api_key_error

    events = Event.query.order_by(Event.event_date, Event.id).all()

    return jsonify(
        events=[
            {
                "id": event.id,
                "title": event.title,
                "event_date": event.event_date.isoformat(),
                "max_participants": event.max_participants,
                "booked_count": event.booked_count,
                "bookings": [
                    {
                        "id": booking.id,
                        "user_id": booking.user_id,
                        "username": booking.user.username,
                        "email": booking.user.email,
                        "created_at": booking.created_at.isoformat(),
                    }
                    for booking in sorted(event.bookings, key=lambda item: item.created_at)
                ],
            }
            for event in events
        ]
    )

