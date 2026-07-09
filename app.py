import os
import re
import logging
from html import escape
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash

from flask import Flask, render_template, request, redirect, url_for, flash, session
from sqlalchemy import or_
from email_validator import validate_email, EmailNotValidError

from config import Config
from models import db


# =========================
# APP SETUP
# =========================
app = Flask(__name__, instance_relative_config=True)
app.config.from_object(Config)

# safer Flask standard usage
app.config['SECRET_KEY'] = Config.SECRET_KEY

os.makedirs(app.instance_path, exist_ok=True)
db.init_app(app)


MESSAGE_STATUS_VALUES = ["Nouveau", "Lu", "Traité"]
RESERVATION_STATUS_VALUES = ["En attente", "Confirmé", "Annulé"]
VERIFIED_SENDER = "Studio Foveau <contact@studiofoveauphoto.fr>"
STUDIO_REPLY_TO = "contact@studiofoveauphoto.fr"
ADMIN_NOTIFICATION_EMAIL = "studiofoveau.admin@gmail.com"


def setup_logging():
    """Configure la journalisation locale sans dépendance externe."""
    log_path = os.path.join(app.instance_path, "studiofoveau.log")
    os.makedirs(app.instance_path, exist_ok=True)

    if not any(getattr(handler, "baseFilename", None) == log_path for handler in app.logger.handlers):
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        app.logger.addHandler(file_handler)

    app.logger.setLevel(logging.INFO)


def log_mail_runtime_config():
    """Journalise la configuration email effectivement lue au runtime."""
    raw_resend_api_key = os.environ.get("RESEND_API_KEY") or ""
    resend_key_state = "present" if raw_resend_api_key else "missing"
    masked_resend_api_key = "" if not raw_resend_api_key else "*" * 8

    mail_config = {
        "RESEND_API_KEY": masked_resend_api_key,
        "RESEND_API_KEY_STATE": resend_key_state,
        "MAIL_DEFAULT_SENDER": os.environ.get("MAIL_DEFAULT_SENDER") or "",
        "MAIL_RECIPIENT": os.environ.get("MAIL_RECIPIENT") or "",
        "ADMIN_EMAIL": os.environ.get("ADMIN_EMAIL") or "",
    }

    app.logger.info("Email runtime config: %s", mail_config)


from models import ContactMessage, Booking, AdminUser
from forms import LoginForm


def ensure_sqlite_schema_compatibility():
    """Ajoute les colonnes manquantes sur les bases SQLite existantes.

    Cette fonction évite les crashes liés à une base locale déjà créée avant
    l'ajout de nouvelles colonnes non nulles avec valeur par défaut.
    """
    if not app.config.get('SQLALCHEMY_DATABASE_URI', '').startswith('sqlite'):
        return

    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    compatibility_map = {
        'admin_user': ('created_at', 'updated_at'),
        'contact_message': ('created_at', 'updated_at'),
        'booking': ('created_at', 'updated_at'),
    }

    for table_name, desired_columns in compatibility_map.items():
        if table_name not in table_names:
            continue

        columns = {column['name'] for column in inspector.get_columns(table_name)}
        for column_name in desired_columns:
            if column_name not in columns:
                with db.engine.begin() as connection:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} DATETIME"))

        with db.engine.begin() as connection:
            if 'created_at' in columns and 'updated_at' not in columns:
                connection.execute(text(f"UPDATE {table_name} SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP) WHERE updated_at IS NULL"))
            if 'created_at' not in columns:
                connection.execute(text(f"UPDATE {table_name} SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
            connection.execute(text(f"UPDATE {table_name} SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP) WHERE updated_at IS NULL"))


def normalize_message_status(status_value):
    """Normalise les statuts des messages vers une valeur canonique."""
    normalized = (status_value or "").strip().lower()
    mapping = {
        "nouveau": "Nouveau",
        "new": "Nouveau",
        "lu": "Lu",
        "read": "Lu",
        "traite": "Traité",
        "traité": "Traité",
        "processed": "Traité",
    }
    return mapping.get(normalized, "Toutes")


def normalize_reservation_status(status_value):
    """Normalise les statuts des réservations vers une valeur canonique."""
    normalized = (status_value or "").strip().lower()
    mapping = {
        "en attente": "En attente",
        "pending": "En attente",
        "confirmé": "Confirmé",
        "confirme": "Confirmé",
        "confirmed": "Confirmé",
        "annulé": "Annulé",
        "annule": "Annulé",
        "cancelled": "Annulé",
        "canceled": "Annulé",
    }
    return mapping.get(normalized, "Toutes")


def validate_contact_payload(form_data):
    """Valide les champs du formulaire de contact avant sauvegarde."""
    name = form_data.get("name", "").strip()
    email = form_data.get("email", "").strip()
    phone = form_data.get("phone", "").strip()
    service = form_data.get("service", "").strip()
    message = form_data.get("message", "").strip()

    if not name or not email or not phone or not service or not message:
        return None, "Merci de remplir tous les champs obligatoires."

    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError:
        return None, "Adresse email invalide."

    if not re.fullmatch(r"[0-9+().\s-]{8,20}", phone):
        return None, "Numéro de téléphone invalide."

    return {
        "name": name,
        "email": email.lower(),
        "phone": phone,
        "service": service,
        "message": message,
    }, None


def validate_booking_payload(form_data):
    """Valide les champs de réservation avant sauvegarde."""
    name = form_data.get("name", "").strip()
    email = form_data.get("email", "").strip()
    phone = form_data.get("phone", "").strip()
    service = form_data.get("service", "").strip()
    requested_date = form_data.get("requested_date", "").strip()
    requested_time = form_data.get("requested_time", "").strip()
    message = form_data.get("message", "").strip()

    if not name or not email or not phone or not service or not requested_date or not requested_time:
        return None, "Merci de remplir tous les champs obligatoires."

    try:
        validate_email(email, check_deliverability=False)
        datetime.strptime(requested_date, "%Y-%m-%d")
        datetime.strptime(requested_time, "%H:%M")
    except (EmailNotValidError, ValueError):
        return None, "Les informations de réservation sont invalides."

    if not re.fullmatch(r"[0-9+().\s-]{8,20}", phone):
        return None, "Numéro de téléphone invalide."

    return {
        "name": name,
        "email": email.lower(),
        "phone": phone,
        "service": service,
        "requested_date": requested_date,
        "requested_time": requested_time,
        "message": message,
    }, None


def send_notification_email(subject, body, reply_to=None, recipient=None, html_body=None):
    """Envoie une notification email via Resend API si configuré."""
    resend_api_key = os.environ.get("RESEND_API_KEY")
    if not resend_api_key:
        app.logger.info("Email ignored: RESEND_API_KEY missing")
        return False

    try:
        import resend
    except Exception:
        app.logger.exception("Resend package unavailable")
        return False

    resend.api_key = resend_api_key
    configured_recipient = (
        recipient
        or os.environ.get("MAIL_RECIPIENT")
        or os.environ.get("ADMIN_EMAIL")
        or ADMIN_NOTIFICATION_EMAIL
    )
    sender = os.environ.get("MAIL_DEFAULT_SENDER") or VERIFIED_SENDER
    resolved_reply_to = STUDIO_REPLY_TO

    if not configured_recipient or not sender:
        app.logger.info("Notification email ignorée: configuration Resend incomplète.")
        return False

    payload = {
        "from": sender,
        "to": [configured_recipient],
        "subject": subject,
        "html": html_body or body.replace("\n", "<br>"),
        "text": body,
        "reply_to": resolved_reply_to,
    }

    try:
        resend.Emails.send(payload)
        app.logger.info(
            "Email sent successfully via Resend: subject=%s to=%s",
            subject,
            configured_recipient,
        )
        return True
    except Exception:
        app.logger.exception(
            "Échec d'envoi de notification email via Resend: subject=%s to=%s sender=%s",
            subject,
            configured_recipient,
            sender,
        )
        return False


def build_email_html_layout(title, intro, content_html):
        """Construit une base HTML responsive noir/blanc pour tous les emails."""
        return f"""<!doctype html>
<html lang=\"fr\">
    <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
        <title>{title}</title>
        <style>
            body {{
                margin: 0;
                padding: 24px 12px;
                background: #f4f4f4;
                color: #111111;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            }}
            .container {{
                max-width: 620px;
                margin: 0 auto;
                background: #ffffff;
                border: 1px solid #e5e5e5;
                border-radius: 14px;
                overflow: hidden;
            }}
            .logo-area {{
                background: #111111;
                color: #ffffff;
                text-align: center;
                padding: 14px 16px;
                font-size: 12px;
                letter-spacing: 1.5px;
                text-transform: uppercase;
            }}
            .content {{
                padding: 24px;
            }}
            h1 {{
                margin: 0 0 8px 0;
                font-size: 22px;
                line-height: 1.3;
            }}
            p {{
                margin: 0 0 14px 0;
                line-height: 1.6;
                color: #222222;
            }}
            .card {{
                background: #fafafa;
                border: 1px solid #ebebeb;
                border-radius: 10px;
                padding: 14px;
            }}
            .row {{
                margin: 8px 0;
            }}
            .label {{
                font-weight: 600;
            }}
            .footer {{
                border-top: 1px solid #efefef;
                padding: 16px 24px 20px 24px;
                font-size: 12px;
                color: #555555;
                line-height: 1.5;
            }}
            @media (max-width: 640px) {{
                body {{
                    padding: 12px 8px;
                }}
                .content {{
                    padding: 18px;
                }}
                h1 {{
                    font-size: 20px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class=\"container\">
            <div class=\"logo-area\">Studio Foveau</div>
            <div class=\"content\">
                <h1>{title}</h1>
                <p>{intro}</p>
                {content_html}
            </div>
            <div class=\"footer\">
                Studio Foveau<br />
                Calais<br />
                Email: studiofoveau.admin@gmail.com<br /><br />
                Ceci est un email automatique.
            </div>
        </div>
    </body>
</html>"""


def send_admin_contact_email(payload):
        """Envoie à l'admin la notification HTML du formulaire de contact."""
        try:
                received_at = datetime.now().strftime("%d/%m/%Y à %H:%M")
                subject = "Nouveau message de contact - Studio Foveau"
                content_html = f"""
                <div class=\"card\">
                    <div class=\"row\"><span class=\"label\">Nom:</span> {escape(payload['name'])}</div>
                    <div class=\"row\"><span class=\"label\">Email:</span> {escape(payload['email'])}</div>
                    <div class=\"row\"><span class=\"label\">Téléphone:</span> {escape(payload['phone'])}</div>
                    <div class=\"row\"><span class=\"label\">Service sélectionné:</span> {escape(payload['service'])}</div>
                    <div class=\"row\"><span class=\"label\">Message:</span><br />{escape(payload['message']).replace(chr(10), '<br />')}</div>
                    <div class=\"row\"><span class=\"label\">Date de réception:</span> {received_at}</div>
                </div>
                """
                html_body = build_email_html_layout(
                        title="Nouveau message de contact",
                        intro="Un nouveau message a été envoyé depuis le site Studio Foveau.",
                        content_html=content_html,
                )
                body = (
                        "Nouveau message de contact - Studio Foveau\n\n"
                        f"Nom: {payload['name']}\n"
                        f"Email: {payload['email']}\n"
                        f"Téléphone: {payload['phone']}\n"
                        f"Service sélectionné: {payload['service']}\n"
                        f"Message: {payload['message']}\n"
                        f"Date de réception: {received_at}\n"
                )
                recipient = os.environ.get("MAIL_RECIPIENT") or ADMIN_NOTIFICATION_EMAIL
                return send_notification_email(
                        subject=subject,
                        body=body,
                        reply_to=payload["email"],
                        recipient=recipient,
                        html_body=html_body,
                )
        except Exception:
                app.logger.exception("Échec de préparation de l'email admin (contact)")
                return False


def send_admin_reservation_email(payload):
        """Envoie à l'admin la notification HTML de nouvelle réservation."""
        try:
                submitted_at = datetime.now().strftime("%d/%m/%Y à %H:%M")
                subject = "Nouvelle réservation - Studio Foveau"
                content_html = f"""
                <div class=\"card\">
                    <div class=\"row\"><span class=\"label\">Nom:</span> {escape(payload['name'])}</div>
                    <div class=\"row\"><span class=\"label\">Email:</span> {escape(payload['email'])}</div>
                    <div class=\"row\"><span class=\"label\">Téléphone:</span> {escape(payload['phone'])}</div>
                    <div class=\"row\"><span class=\"label\">Service:</span> {escape(payload['service'])}</div>
                    <div class=\"row\"><span class=\"label\">Date demandée:</span> {escape(payload['requested_date'])}</div>
                    <div class=\"row\"><span class=\"label\">Heure demandée:</span> {escape(payload['requested_time'])}</div>
                    <div class=\"row\"><span class=\"label\">Message:</span><br />{escape(payload['message']).replace(chr(10), '<br />')}</div>
                    <div class=\"row\"><span class=\"label\">Date de soumission:</span> {submitted_at}</div>
                </div>
                """
                html_body = build_email_html_layout(
                        title="Nouvelle réservation",
                        intro="Une nouvelle demande de réservation a été envoyée depuis le site.",
                        content_html=content_html,
                )
                body = (
                        "Nouvelle réservation - Studio Foveau\n\n"
                        f"Nom: {payload['name']}\n"
                        f"Email: {payload['email']}\n"
                        f"Téléphone: {payload['phone']}\n"
                        f"Service: {payload['service']}\n"
                        f"Date demandée: {payload['requested_date']}\n"
                        f"Heure demandée: {payload['requested_time']}\n"
                        f"Message: {payload['message']}\n"
                        f"Date de soumission: {submitted_at}\n"
                )
                recipient = os.environ.get("MAIL_RECIPIENT") or ADMIN_NOTIFICATION_EMAIL
                return send_notification_email(
                        subject=subject,
                        body=body,
                        reply_to=payload["email"],
                        recipient=recipient,
                        html_body=html_body,
                )
        except Exception:
                app.logger.exception("Échec de préparation de l'email admin (réservation)")
                return False


def send_customer_contact_confirmation(payload):
        """Envoie un accusé de réception HTML après un contact."""
        try:
                subject = "Nous avons bien reçu votre message - Studio Foveau"
                customer_message_html = escape(payload.get("message", "")).replace("\n", "<br />")
                content_html = f"""
                <div class=\"card\">
                    <p>Bonjour {escape(payload['name'])},</p>
                    <p>Merci d'avoir contacté Studio Foveau.</p>
                    <p>Votre demande a bien été reçue. Notre équipe vous répondra dans les plus brefs délais.</p>
                    <div class=\"row\"><span class=\"label\">Service demandé:</span> {escape(payload['service'])}</div>
                    <div class=\"row\"><span class=\"label\">Votre message:</span><br />{customer_message_html}</div>
                    <div class=\"row\"><span class=\"label\">Contact studio:</span> studiofoveau.admin@gmail.com</div>
                </div>
                """
                html_body = build_email_html_layout(
                        title="Message bien reçu",
                        intro="Votre demande de contact est enregistrée.",
                        content_html=content_html,
                )
                body = (
                        f"Bonjour {payload['name']},\n\n"
                        "Merci d'avoir contacté Studio Foveau.\n"
                    "Votre demande a bien été reçue et nous vous répondrons dès que possible.\n\n"
                    f"Service demandé: {payload['service']}\n"
                    f"Votre message: {payload['message']}\n"
                    "Contact studio: studiofoveau.admin@gmail.com\n\n"
                        "Studio Foveau\n"
                        "Calais\n"
                        "Email: studiofoveau.admin@gmail.com\n\n"
                        "Ceci est un email automatique."
                )
                return send_notification_email(
                        subject=subject,
                        body=body,
                        recipient=payload["email"],
                        html_body=html_body,
                )
        except Exception:
                app.logger.exception("Échec de préparation de l'email client (contact)")
                return False


def send_customer_reservation_confirmation(payload):
        """Envoie un accusé de réception HTML après une réservation."""
        try:
                subject = "Votre demande de réservation a bien été reçue - Studio Foveau"
                reservation_message = (payload.get("message") or "").strip()
                reservation_message_html = escape(reservation_message).replace("\n", "<br />")
                reservation_message_row = ""
                if reservation_message:
                        reservation_message_row = (
                                f'<div class="row"><span class="label">Votre message:</span><br />{reservation_message_html}</div>'
                        )

                content_html = f"""
                <div class=\"card\">
                    <p>Bonjour {escape(payload['name'])},</p>
                    <p>Votre demande de réservation a bien été reçue. Elle n’est pas encore confirmée.</p>
                    <p>Studio Foveau vous contactera rapidement pour confirmer le rendez-vous.</p>
                    <div class=\"row\"><span class=\"label\">Service demandé:</span> {escape(payload['service'])}</div>
                    <div class=\"row\"><span class=\"label\">Date demandée:</span> {escape(payload['requested_date'])}</div>
                    <div class=\"row\"><span class=\"label\">Heure demandée:</span> {escape(payload['requested_time'])}</div>
                    {reservation_message_row}
                </div>
                """
                html_body = build_email_html_layout(
                        title="Réservation reçue",
                        intro="Votre demande est en cours de traitement.",
                        content_html=content_html,
                )
                body = (
                        f"Bonjour {payload['name']},\n\n"
                        "Votre demande de réservation a bien été reçue. Elle n'est pas encore confirmée. "
                        "Studio Foveau vous contactera rapidement pour confirmer le rendez-vous.\n\n"
                        "Récapitulatif:\n"
                        f"- Service demandé: {payload['service']}\n"
                        f"- Date demandée: {payload['requested_date']}\n"
                        f"- Heure demandée: {payload['requested_time']}\n"
                        + (f"- Votre message: {reservation_message}\n" if reservation_message else "")
                        + "\n"
                        "Studio Foveau\n"
                        "Calais\n\n"
                        "Ceci est un email automatique."
                )
                return send_notification_email(
                        subject=subject,
                        body=body,
                        recipient=payload["email"],
                        html_body=html_body,
                )
        except Exception:
                app.logger.exception("Échec de préparation de l'email client (réservation)")
                return False


# =========================
# DATABASE INITIALIZATION
# =========================
def init_database():
    """Initialise la base SQLite et crée l'admin initial si nécessaire.

    Cette fonction est idempotente:
    - crée les tables manquantes
    - conserve les données existantes
    - crée l'administrateur par défaut uniquement s'il n'existe pas
    """
    database_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    db_file_exists = False
    if database_uri.startswith("sqlite:///"):
        db_path = database_uri.replace("sqlite:///", "", 1)
        db_file_exists = os.path.exists(db_path)

    if db_file_exists:
        app.logger.info("Existing database detected")

    try:
        db.create_all()
        ensure_sqlite_schema_compatibility()
        app.logger.info("Database initialized")

        existing_admin = AdminUser.query.first()
        if existing_admin:
            app.logger.info("Default admin already exists")
            db.session.commit()
            return

        admin_email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
        admin_password = os.getenv("ADMIN_PASSWORD") or ""
        env = app.config.get("FLASK_ENV", "development")

        if not admin_email or not admin_password:
            if env == "production":
                raise RuntimeError("ADMIN_EMAIL et ADMIN_PASSWORD requis en production.")

            app.logger.warning("Admin not created due to missing env vars")
            db.session.commit()
            return

        new_user = AdminUser(
            email=admin_email,
            password_hash=generate_password_hash(admin_password),
        )
        db.session.add(new_user)
        db.session.commit()
        app.logger.info("Default admin created")
    except Exception:
        db.session.rollback()
        app.logger.exception("Database initialization failed")
        raise


def reset_admin_password(email, new_password):
    """Réinitialise le mot de passe d'un administrateur existant.

    Le mot de passe est toujours hashé avant stockage.
    """
    with app.app_context():
        admin = AdminUser.query.filter_by(email=email.strip().lower()).first()
        if not admin:
            return False

        admin.set_password(new_password)
        db.session.commit()
        return True


setup_logging()
log_mail_runtime_config()


with app.app_context():
    init_database()


# =========================
# STUDIO STATUS
# =========================
def get_studio_status():
    now = datetime.now()
    day = now.weekday()
    time_now = now.time()

    if day == 6:
        return False, "🔴 Fermé", "Dimanche"

    open_morning = datetime.strptime("09:00", "%H:%M").time()
    close_morning = datetime.strptime("12:00", "%H:%M").time()
    open_afternoon = datetime.strptime("14:00", "%H:%M").time()
    close_evening = datetime.strptime(
        "18:00" if day == 5 else "19:00", "%H:%M"
    ).time()

    if open_morning <= time_now < close_morning:
        return True, "🟢 Ouvert", "Matin"
    if open_afternoon <= time_now < close_evening:
        return True, "🟢 Ouvert", "Après-midi"

    return False, "🔴 Fermé", "Hors horaires"


@app.context_processor
def inject_status():
    is_open, label, detail = get_studio_status()
    return dict(
        is_open=is_open,
        status_label=label,
        status_detail=detail,
        status=label
    )


# =========================
# AUTH DECORATOR
# =========================
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_user"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


# =========================
# PUBLIC ROUTES
# =========================
@app.route("/")
def home():
    return render_template("home.html")


@app.route("/services")
def services():
    return render_template("services.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        payload, error_message = validate_contact_payload(request.form)
        if error_message:
            flash(error_message, "danger")
            return redirect(url_for("contact"))

        db.session.add(ContactMessage(**payload))
        db.session.commit()

        send_admin_contact_email(payload)
        # Customer confirmations are disabled until studiofoveau.fr is verified in Resend.

        flash("Message envoyé ✔", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html")


@app.route("/reservation", methods=["GET", "POST"])
def reservation():
    if request.method == "POST":
        payload, error_message = validate_booking_payload(request.form)
        if error_message:
            flash(error_message, "danger")
            return redirect(url_for("reservation"))

        db.session.add(Booking(**payload))
        db.session.commit()

        send_admin_reservation_email(payload)
        # Customer confirmations are disabled until studiofoveau.fr is verified in Resend.

        flash("Réservation enregistrée ✔", "success")
        return redirect(url_for("reservation"))

    return render_template("reservation.html")


# =========================
# ADMIN AUTH
# =========================
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    form = LoginForm()

    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = AdminUser.query.filter_by(email=email).first()

        if user and user.check_password(form.password.data):
            session.clear()
            session["admin_user"] = user.email
            session.permanent = True
            app.logger.info("Connexion admin réussie pour %s depuis %s", user.email, request.remote_addr)
            flash("Connexion réussie ✔", "success")
            return redirect(url_for("admin_dashboard"))

        app.logger.warning(
            "Échec de connexion admin pour %s depuis %s",
            email,
            request.remote_addr,
        )
        flash("Identifiants invalides", "danger")

    return render_template("admin/login.html", form=form)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("Déconnecté", "info")
    return redirect(url_for("admin_login"))


# =========================
# ADMIN DASHBOARD
# =========================
@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    total_messages = ContactMessage.query.count()
    total_reservations = Booking.query.count()

    today = datetime.utcnow().date().isoformat()

    reservations_today = Booking.query.filter(
        Booking.requested_date == today
    ).count()

    new_messages = ContactMessage.query.filter_by(status="Nouveau").count()
    pending = Booking.query.filter_by(status="En attente").count()

    return render_template(
        "admin/dashboard.html",
        total_messages=total_messages,
        total_reservations=total_reservations,
        reservations_today=reservations_today,
        new_messages=new_messages,
        pending_reservations=pending,
    )


# =========================
# MESSAGES
# =========================
@app.route("/admin/messages")
@login_required
def admin_messages():
    status_filter = normalize_message_status(request.args.get("status", "Toutes"))
    search_query = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)

    query = ContactMessage.query.order_by(ContactMessage.created_at.desc())

    if status_filter in MESSAGE_STATUS_VALUES:
        query = query.filter_by(status=status_filter)

    if search_query:
        like_pattern = f"%{search_query}%"
        query = query.filter(
            or_(
                ContactMessage.name.ilike(like_pattern),
                ContactMessage.email.ilike(like_pattern),
                ContactMessage.service.ilike(like_pattern),
                ContactMessage.message.ilike(like_pattern),
            )
        )

    pagination = query.paginate(page=page, per_page=10, error_out=False)

    return render_template(
        "admin/messages.html",
        messages=pagination.items,
        pagination=pagination,
        status_filter=status_filter,
        search_query=search_query,
    )


@app.route("/admin/messages/<int:message_id>")
@login_required
def admin_message_view(message_id):
    message = ContactMessage.query.get_or_404(message_id)
    return render_template("admin/message_view.html", message=message)


@app.route("/admin/messages/<int:message_id>/action/<string:action>")
@login_required
def admin_message_action(message_id, action):
    message = ContactMessage.query.get_or_404(message_id)

    if action == "mark-lu":
        message.status = "Lu"
        app.logger.info("Message %s marqué Lu", message.id)
    elif action == "mark-traite":
        message.status = "Traité"
        app.logger.info("Message %s marqué Traité", message.id)
    elif action == "delete":
        db.session.delete(message)
        db.session.commit()
        flash("Message supprimé", "warning")
        app.logger.info("Message %s supprimé", message.id)
        return redirect(url_for("admin_messages"))

    db.session.commit()
    return redirect(url_for("admin_messages"))


# =========================
# RESERVATIONS
# =========================
@app.route("/admin/reservations")
@login_required
def admin_reservations():
    status = normalize_reservation_status(request.args.get("status", "Toutes"))
    search_query = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)

    query = Booking.query.order_by(Booking.created_at.desc())

    if status in RESERVATION_STATUS_VALUES:
        query = query.filter_by(status=status)

    if search_query:
        like_pattern = f"%{search_query}%"
        query = query.filter(
            or_(
                Booking.name.ilike(like_pattern),
                Booking.email.ilike(like_pattern),
                Booking.service.ilike(like_pattern),
                Booking.requested_date.ilike(like_pattern),
            )
        )

    pagination = query.paginate(page=page, per_page=10, error_out=False)

    return render_template(
        "admin/reservations.html",
        reservations=pagination.items,
        pagination=pagination,
        status_filter=status,
        search_query=search_query,
    )


@app.route("/admin/reservations/<int:reservation_id>/action/<string:action>")
@login_required
def admin_reservation_action(reservation_id, action):
    reservation = Booking.query.get_or_404(reservation_id)

    if action == "confirm":
        reservation.status = "Confirmé"
        app.logger.info("Réservation %s confirmée", reservation.id)
    elif action == "cancel":
        reservation.status = "Annulé"
        app.logger.info("Réservation %s annulée", reservation.id)
    elif action == "delete":
        db.session.delete(reservation)
        db.session.commit()
        flash("Réservation supprimée", "warning")
        app.logger.info("Réservation %s supprimée", reservation.id)
        return redirect(url_for("admin_reservations"))

    db.session.commit()
    return redirect(url_for("admin_reservations"))


# =========================
# ERROR HANDLERS
# =========================
@app.errorhandler(404)
def not_found(e):
    app.logger.info("404: %s", request.path)
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    app.logger.exception("Erreur serveur sur %s", request.path)
    return render_template("500.html"), 500


def validate_admin_template_routes():
    """Vérifie au démarrage que les templates admin ne référencent aucun endpoint absent."""
    admin_templates_dir = os.path.join(app.root_path, "templates", "admin")
    missing_routes = []

    for root, _, files in os.walk(admin_templates_dir):
        for filename in files:
            if not filename.endswith(".html"):
                continue

            template_path = os.path.join(root, filename)
            with open(template_path, "r", encoding="utf-8") as template_file:
                content = template_file.read()

            endpoints = re.findall(r"url_for\(\s*['\"](admin_[^'\"]+)['\"]", content)
            for endpoint in endpoints:
                if endpoint not in app.view_functions:
                    missing_routes.append(f"{filename}: {endpoint}")

    if missing_routes:
        raise RuntimeError(
            "Routes admin manquantes détectées dans les templates : "
            + ", ".join(missing_routes)
        )


# =========================
# START
# =========================
if __name__ == "__main__":
    app.run()