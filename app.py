import os
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from flask import (Flask, jsonify, render_template, redirect, url_for, flash, request, abort)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, login_required, logout_user, current_user)
from flask_jwt_extended import (JWTManager, create_access_token, get_jwt_identity, jwt_required)
from flask_wtf import FlaskForm
from wtforms import (EmailField, PasswordField, SubmitField)
from wtforms.validators import (DataRequired, Email, Length)
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
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{os.getenv('DB_USER')}:"
    f"{os.getenv('DB_PASSWORD')}@"
    f"{os.getenv('DB_HOST')}/"
    f"{os.getenv('DB_NAME')}"
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
jwt = JWTManager(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Bitte anmelden um diese Seite aufzurufen."
login_manager.login_message_category = "warning"
login_manager.init_app(app)

# --------------------------------------------------
# Datenbankmodelle für Benutzer und Trainingsbuchungen
# --------------------------------------------------

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    email = db.Column(
        db.String(255),
        unique=True,
        nullable=False
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    is_admin = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    bookings = db.relationship(
        "Booking",
        backref="user",
        cascade="all, delete-orphan",
        lazy=True
    )

class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    booking_date = db.Column(
        db.Date,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    __table_args__ = (
        # Verhindert, dass ein Benutzer denselben Termin mehrfach bucht
        db.UniqueConstraint(
            "user_id",
            "booking_date",
            name="uq_user_date"
        ),
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
            DataRequired()
        ]
    )

    submit = SubmitField("Anmelden")


def booking_to_dict(booking):
    # Wandelt eine Buchung in ein JSON-kompatibles Objekt für die API um
    return {
        "id": booking.id,
        "booking_date": booking.booking_date.isoformat(),
        "created_at": booking.created_at.isoformat(),
    }

# --------------------------------------------------
# Routes
# --------------------------------------------------

@app.route("/")
@login_required
def dashboard():

    # Benutzer dürfen nur ihre eigenen Buchungen im Dashboard sehen
    bookings = (
        Booking.query
        .filter_by(user_id=current_user.id)
        .order_by(Booking.booking_date)
        .all()
    )

    return render_template(
        "dashboard.html",
        bookings=bookings,
        today=date.today().isoformat()
    )


@app.route("/admin")
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        abort(403)

    bookings = (
        Booking.query
        .join(User)
        .order_by(Booking.booking_date, Booking.id)
        .all()
    )

    return render_template("admin.html", bookings=bookings)

# --------------------------------------------------
# Angebot Seite
# --------------------------------------------------

@app.route("/angebot")
def offer():
    return render_template("offer.html")

# --------------------------------------------------
# Registrierung, Login und Logout
# --------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    form = RegisterForm()

    if form.validate_on_submit():

        existing_user = User.query.filter_by(
            email=form.email.data.lower()
        ).first()

        if existing_user:
            flash("E-Mail-Adresse ist bereits registriert.", "danger")
            return render_template("register.html", form=form)

        user = User(
            email=form.email.data.lower(),
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

    form = LoginForm()

    if form.validate_on_submit():

        user = User.query.filter_by(
            email=form.email.data.lower()
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
            "Ungültige E-Mail oder Passwort.",
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

    logout_user()

    return redirect(
        url_for("login")
    )

# --------------------------------------------------
# REST API
# --------------------------------------------------

@app.route("/api/auth/login", methods=["POST"])
def api_login():
    # Die API verwendet JWT-Tokens anstelle der normalen Browser-Session
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")

    user = User.query.filter_by(email=email).first()

    if not user or not check_password_hash(user.password_hash, password):
        return jsonify(error="Ungültige E-Mail oder Passwort."), 401

    return jsonify(
        access_token=create_access_token(identity=str(user.id)),
        token_type="Bearer"
    )


@app.route("/api/bookings", methods=["GET"])
@jwt_required()
def api_get_bookings():
    user_id = int(get_jwt_identity())

    # Die JWT-Identität begrenzt den Zugriff auf die eigenen Buchungen
    bookings = (
        Booking.query
        .filter_by(user_id=user_id)
        .order_by(Booking.booking_date)
        .all()
    )

    return jsonify(bookings=[booking_to_dict(booking) for booking in bookings])


@app.route("/api/admin/bookings", methods=["GET"])
@jwt_required()
def api_get_all_bookings():
    admin = db.session.get(User, int(get_jwt_identity()))

    if not admin or not admin.is_admin:
        return jsonify(error="Admin-Berechtigung erforderlich."), 403

    bookings = (
        Booking.query
        .join(User)
        .order_by(Booking.booking_date, Booking.id)
        .all()
    )

    return jsonify(
        bookings=[
            {
                **booking_to_dict(booking),
                "user_id": booking.user_id,
                "user_email": booking.user.email,
            }
            for booking in bookings
        ]
    )

# --------------------------------------------------

@app.route("/booking/add", methods=["POST"])
@login_required
def add_booking():

    booking_date_str = request.form.get(
        "booking_date"
    )

    try:
        booking_date = datetime.strptime(
            booking_date_str,
            "%Y-%m-%d"
        ).date()

    except Exception:
        flash("Ungültiges Datum.", "danger")
        return redirect(url_for("dashboard"))

    today = date.today()
    max_date = today + timedelta(days=120)

    # Buchungen sind nur ab heute und höchstens 120 Tage im Voraus möglich
    if booking_date < today:
        flash(
            "Keine Termine in der Vergangenheit erlaubt.",
            "danger"
        )
        return redirect(url_for("dashboard"))

    if booking_date > max_date:
        flash(
            "Termine nur 4 Monate im Voraus erlaubt.",
            "danger"
        )
        return redirect(url_for("dashboard"))

    existing = Booking.query.filter_by(
        user_id=current_user.id,
        booking_date=booking_date
    ).first()

    if existing:
        flash(
            "Dieser Termin wurde bereits gebucht.",
            "warning"
        )
        return redirect(url_for("dashboard"))

    booking = Booking(
        user_id=current_user.id,
        booking_date=booking_date
    )

    db.session.add(booking)
    db.session.commit()

    flash(
        "Termin wurde gespeichert.",
        "success"
    )

    return redirect(
        url_for("dashboard")
    )

# --------------------------------------------------

@app.route("/booking/delete/<int:booking_id>")
@login_required
def delete_booking(booking_id):

    # Die Benutzer-ID verhindert, dass fremde Buchungen gelöscht werden können
    booking = Booking.query.filter_by(
        id=booking_id,
        user_id=current_user.id
    ).first_or_404()

    db.session.delete(booking)
    db.session.commit()

    flash(
        "Termin gelöscht.",
        "success"
    )

    return redirect(
        url_for("dashboard")
    )