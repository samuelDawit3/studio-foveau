import os
import re
import logging
from html import escape
from datetime import datetime
from functools import wraps
from xml.etree import ElementTree as ET
from werkzeug.security import generate_password_hash

from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
from flask_wtf.csrf import CSRFProtect
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
csrf = CSRFProtect(app)


MESSAGE_STATUS_VALUES = ["Nouveau", "Lu", "Traité"]
RESERVATION_STATUS_VALUES = ["En attente", "Confirmé", "Annulé"]
VERIFIED_SENDER = "Studio Foveau <contact@studiofoveauphoto.fr>"
STUDIO_REPLY_TO = "contact@studiofoveauphoto.fr"
DEFAULT_MAIL_REPLY_TO = "studiofoveau.admin@gmail.com"
ADMIN_NOTIFICATION_EMAIL = "studiofoveau.admin@gmail.com"
SITE_URL = "https://studiofoveauphoto.fr"
BUSINESS_NAME = "Studio Foveau"
BUSINESS_PHONE = "03 21 97 70 20"
BUSINESS_EMAIL = "contact@studiofoveauphoto.fr"
BUSINESS_FACEBOOK = "https://www.facebook.com/studiofoveau/"
BUSINESS_ADDRESS_STREET = "37 Boulevard de l'Égalité"
BUSINESS_ADDRESS_LOCALITY = "Calais"
BUSINESS_ADDRESS_POSTAL_CODE = "62100"
BUSINESS_ADDRESS_COUNTRY = "France"
_resend_module = None
OFFICIAL_LOGO_PATH = "/static/images/ChatGPT-Image-Jul-13_-2026_-06_10_56-PM.svg"

SUPPORTED_LANGUAGES = ("fr", "en")
LANGUAGE_TO_LOCALE = {"fr": "fr-FR", "en": "en-GB"}
LANGUAGE_TO_OG_LOCALE = {"fr": "fr_FR", "en": "en_GB"}

PAGE_PATHS = {
    "home": {"fr": "/", "en": "/en/"},
    "services": {"fr": "/services", "en": "/en/services"},
    "reservation": {"fr": "/reservation", "en": "/en/reservation"},
    "about": {"fr": "/about", "en": "/en/about"},
    "contact": {"fr": "/contact", "en": "/en/contact"},
    "mentions_legales": {"fr": "/mentions-legales", "en": "/en/legal-notice"},
    "politique_confidentialite": {"fr": "/politique-confidentialite", "en": "/en/privacy-policy"},
    "cgu": {"fr": "/cgu", "en": "/en/terms-of-use"},
}

PUBLIC_TEMPLATE_BY_PAGE = {
    "home": {"fr": "home.html", "en": "home_en.html"},
    "services": {"fr": "services.html", "en": "services_en.html"},
    "about": {"fr": "about.html", "en": "about_en.html"},
    "contact": {"fr": "contact.html", "en": "contact_en.html"},
    "reservation": {"fr": "reservation.html", "en": "reservation_en.html"},
    "mentions_legales": {"fr": "mentions-legales.html", "en": "legal-notice.html"},
    "politique_confidentialite": {"fr": "politique-confidentialite.html", "en": "privacy-policy.html"},
    "cgu": {"fr": "cgu.html", "en": "terms-of-use.html"},
}

PUBLIC_ENDPOINTS = set(PAGE_PATHS.keys())

SEO_META = {
    "home": {
        "fr": {
            "title": "Studio Foveau | Photographe à Calais - Photos d'identité, Portraits & Mariages",
            "description": "Studio Foveau, photographe à Calais : photos d'identité ANTS, portraits studio, mariages, développement photo, tirages, albums, cadres et réservation en ligne.",
        },
        "en": {
            "title": "Studio Foveau | Photographer in Calais - ID Photos, Portraits & Weddings",
            "description": "Studio Foveau in Calais offers compliant ID photos in 5 minutes, studio portraits, wedding photography, film development, photo printing and online booking.",
        },
    },
    "services": {
        "fr": {
            "title": "Prestations photo à Calais | Studio Foveau - Identité, Portraits, Mariages",
            "description": "Découvrez les prestations de Studio Foveau à Calais : photos d'identité ANTS, portraits en studio, mariages, tirage photo, développement argentique et borne selfie.",
        },
        "en": {
            "title": "Photography Services | Studio Foveau Calais",
            "description": "Explore Studio Foveau services in Calais: passport and ID photos, studio portraits, wedding photography, event coverage, film development and photo printing.",
        },
    },
    "reservation": {
        "fr": {
            "title": "Réservation photo à Calais | Studio Foveau",
            "description": "Réservez votre séance photo en ligne chez Studio Foveau à Calais pour des photos d'identité, portraits studio, reportages mariage et demandes personnalisées.",
        },
        "en": {
            "title": "Book a Photo Session | Studio Foveau",
            "description": "Book your photo session online with Studio Foveau in Calais for ID photos, studio portraits, weddings and personalised photography services.",
        },
    },
    "about": {
        "fr": {
            "title": "Studio Foveau à Calais | Photographe & Laboratoire Photo depuis 1990",
            "description": "Découvrez l'histoire de Studio Foveau, studio photo à Calais depuis 1990, spécialisé en portraits, photos d'identité, mariages et travaux de laboratoire photo.",
        },
        "en": {
            "title": "About Studio Foveau | Photographer in Calais",
            "description": "Learn about Studio Foveau, a trusted photography studio in Calais since 1990, known for professional quality and friendly service.",
        },
    },
    "contact": {
        "fr": {
            "title": "Contact Studio Foveau | Studio photo à Calais",
            "description": "Contactez Studio Foveau à Calais au 03 21 97 70 20, par email ou via le formulaire pour vos photos d'identité, portraits, mariages et tirages photo.",
        },
        "en": {
            "title": "Contact Studio Foveau | Calais",
            "description": "Contact Studio Foveau in Calais by phone, email or contact form for bookings, quotes and photography enquiries.",
        },
    },
    "mentions_legales": {
        "fr": {
            "title": "Mentions légales | Studio Foveau",
            "description": "Mentions légales du site studiofoveauphoto.fr: éditeur, hébergeur, propriété intellectuelle et informations légales.",
        },
        "en": {
            "title": "Legal Notice | Studio Foveau",
            "description": "Read the legal notice for studiofoveauphoto.fr including publisher details, hosting information and intellectual property terms.",
        },
    },
    "politique_confidentialite": {
        "fr": {
            "title": "Politique de confidentialité | Studio Foveau",
            "description": "Politique de confidentialité et RGPD de Studio Foveau: données collectées, conservation, cookies et droits des utilisateurs.",
        },
        "en": {
            "title": "Privacy Policy | Studio Foveau",
            "description": "Read how Studio Foveau handles personal data, cookies and GDPR rights for visitors using contact and booking forms.",
        },
    },
    "cgu": {
        "fr": {
            "title": "Conditions Générales d'Utilisation | Studio Foveau",
            "description": "Conditions Générales d'Utilisation du site Studio Foveau: accès au service, responsabilités et règles d'usage.",
        },
        "en": {
            "title": "Terms of Use | Studio Foveau",
            "description": "View the terms of use for studiofoveauphoto.fr, including access conditions, user responsibilities and legal information.",
        },
    },
}

TRANSLATIONS = {
    "fr": {
        "common.skip_to_content": "Aller au contenu principal",
        "nav.main": "Navigation principale",
        "nav.toggle": "Basculer la navigation",
        "nav.home": "Accueil",
        "nav.services": "Prestations",
        "nav.booking": "Réservation",
        "nav.about": "À propos",
        "nav.contact": "Contact",
        "lang.switch.fr": "FR",
        "lang.switch.en": "EN",
        "lang.aria.fr": "Afficher le site en français",
        "lang.aria.en": "View the website in English",
        "footer.location": "Localisation",
        "footer.contact": "Contact",
        "footer.facebook_official": "Facebook officiel",
        "footer.legal_info": "Informations légales",
        "footer.legal_notice": "Mentions légales",
        "footer.privacy": "Politique de confidentialité",
        "footer.terms": "CGU",
        "footer.copyright": "Tous droits réservés.",
        "cookie.aria": "Consentement des cookies",
        "cookie.message": "Nous utilisons uniquement les cookies nécessaires au bon fonctionnement du site.",
        "cookie.accept": "Accepter",
        "cookie.decline": "Refuser",
        "cookie.learn_more": "En savoir plus",
        "common.close": "Fermer",
        "status.open": "🟢 Ouvert",
        "status.closed": "🔴 Fermé",
        "status.sunday": "Dimanche",
        "status.morning": "Matin",
        "status.afternoon": "Après-midi",
        "status.outside": "Hors horaires",
        "flash.contact_success": "Message envoyé ✔",
        "flash.booking_success": "Réservation enregistrée ✔",
        "validation.required": "Merci de remplir tous les champs obligatoires.",
        "validation.invalid_email": "Adresse email invalide.",
        "validation.invalid_phone": "Numéro de téléphone invalide.",
        "validation.invalid_booking": "Les informations de réservation sont invalides.",
        "error.404.title": "Page introuvable (404) - Studio Foveau",
        "error.404.description": "La page demandée est introuvable sur le site Studio Foveau.",
        "error.404.heading": "Page introuvable",
        "error.404.message": "Désolé, la page demandée n'existe pas.",
        "error.500.title": "Erreur serveur (500) - Studio Foveau",
        "error.500.description": "Une erreur technique est survenue sur le site Studio Foveau.",
        "error.500.heading": "Erreur de serveur",
        "error.500.message": "Une erreur est survenue. Merci de réessayer dans quelques instants.",
        "error.back_home": "Retour à l'accueil",
    },
    "en": {
        "common.skip_to_content": "Skip to main content",
        "nav.main": "Main navigation",
        "nav.toggle": "Toggle navigation",
        "nav.home": "Home",
        "nav.services": "Services",
        "nav.booking": "Booking",
        "nav.about": "About",
        "nav.contact": "Contact",
        "lang.switch.fr": "FR",
        "lang.switch.en": "EN",
        "lang.aria.fr": "Afficher le site en français",
        "lang.aria.en": "View the website in English",
        "footer.location": "Location",
        "footer.contact": "Contact",
        "footer.facebook_official": "Official Facebook",
        "footer.legal_info": "Legal information",
        "footer.legal_notice": "Legal notice",
        "footer.privacy": "Privacy policy",
        "footer.terms": "Terms of use",
        "footer.copyright": "All rights reserved.",
        "cookie.aria": "Cookie consent",
        "cookie.message": "We only use cookies required for the website to function properly.",
        "cookie.accept": "Accept",
        "cookie.decline": "Decline",
        "cookie.learn_more": "Learn more",
        "common.close": "Close",
        "status.open": "🟢 Open",
        "status.closed": "🔴 Closed",
        "status.sunday": "Sunday",
        "status.morning": "Morning",
        "status.afternoon": "Afternoon",
        "status.outside": "Outside opening hours",
        "flash.contact_success": "Message sent ✔",
        "flash.booking_success": "Booking request recorded ✔",
        "validation.required": "Please fill in all required fields.",
        "validation.invalid_email": "Invalid email address.",
        "validation.invalid_phone": "Invalid phone number.",
        "validation.invalid_booking": "The booking information is invalid.",
        "error.404.title": "Page not found (404) - Studio Foveau",
        "error.404.description": "The requested page could not be found on the Studio Foveau website.",
        "error.404.heading": "Page not found",
        "error.404.message": "Sorry, the page you requested does not exist.",
        "error.500.title": "Server error (500) - Studio Foveau",
        "error.500.description": "A technical error occurred on the Studio Foveau website.",
        "error.500.heading": "Server error",
        "error.500.message": "An error occurred. Please try again in a few moments.",
        "error.back_home": "Back to home",
    },
}


def normalize_lang(lang):
    if lang in SUPPORTED_LANGUAGES:
        return lang
    return "fr"


def translate(key, lang="fr"):
    normalized_lang = normalize_lang(lang)
    localized_bucket = TRANSLATIONS.get(normalized_lang, {})
    if key in localized_bucket:
        return localized_bucket[key]

    fallback_bucket = TRANSLATIONS["fr"]
    if key in fallback_bucket:
        app.logger.warning("Missing translation key '%s' for lang '%s'. Fallback to fr.", key, normalized_lang)
        return fallback_bucket[key]

    app.logger.warning("Missing translation key '%s' in all locales.", key)
    return key


def normalize_path(path):
    if path in ("/", "/en", "/en/"):
        if path.startswith("/en"):
            return "/en/"
        return path
    return path.rstrip("/")


def get_request_lang(default="fr"):
    path = request.path or ""
    if path == "/en" or path == "/en/" or path.startswith("/en/"):
        session["site_lang"] = "en"
        return "en"

    if default in SUPPORTED_LANGUAGES:
        session["site_lang"] = default
        return default

    stored = session.get("site_lang", "fr")
    return normalize_lang(stored)


def endpoint_url(endpoint, lang="fr", **kwargs):
    normalized_lang = normalize_lang(lang)
    if endpoint in PUBLIC_ENDPOINTS:
        return url_for(endpoint, lang=normalized_lang, **kwargs)
    return url_for(endpoint, **kwargs)


def template_for_page(page_key, lang):
    return PUBLIC_TEMPLATE_BY_PAGE[page_key][normalize_lang(lang)]


def render_public_page(page_key, lang, **context):
    normalized_lang = normalize_lang(lang)
    meta = SEO_META[page_key][normalized_lang]
    template_name = template_for_page(page_key, normalized_lang)
    return render_template(
        template_name,
        meta_title=meta["title"],
        meta_description=meta["description"],
        page_key=page_key,
        **context,
    )


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


def get_resend_module():
    """Charge et met en cache le SDK Resend pour éviter les imports répétés."""
    global _resend_module
    if _resend_module is None:
        import resend
        _resend_module = resend
    return _resend_module


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


def validate_contact_payload(form_data, lang="fr"):
    """Valide les champs du formulaire de contact avant sauvegarde."""
    name = form_data.get("name", "").strip()
    email = form_data.get("email", "").strip()
    phone = form_data.get("phone", "").strip()
    service = form_data.get("service", "").strip()
    message = form_data.get("message", "").strip()

    if not name or not email or not phone or not service or not message:
        return None, translate("validation.required", lang)

    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError:
        return None, translate("validation.invalid_email", lang)

    if not re.fullmatch(r"[0-9+().\s-]{8,20}", phone):
        return None, translate("validation.invalid_phone", lang)

    return {
        "name": name,
        "email": email.lower(),
        "phone": phone,
        "service": service,
        "message": message,
    }, None


def validate_booking_payload(form_data, lang="fr"):
    """Valide les champs de réservation avant sauvegarde."""
    name = form_data.get("name", "").strip()
    email = form_data.get("email", "").strip()
    phone = form_data.get("phone", "").strip()
    service = form_data.get("service", "").strip()
    requested_date = form_data.get("requested_date", "").strip()
    requested_time = form_data.get("requested_time", "").strip()
    message = form_data.get("message", "").strip()

    if not name or not email or not phone or not service or not requested_date or not requested_time:
        return None, translate("validation.required", lang)

    try:
        validate_email(email, check_deliverability=False)
        datetime.strptime(requested_date, "%Y-%m-%d")
        datetime.strptime(requested_time, "%H:%M")
    except (EmailNotValidError, ValueError):
        return None, translate("validation.invalid_booking", lang)

    if not re.fullmatch(r"[0-9+().\s-]{8,20}", phone):
        return None, translate("validation.invalid_phone", lang)

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
        resend = get_resend_module()
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
    sender = os.environ.get("MAIL_DEFAULT_SENDER") or "Studio Foveau <contact@studiofoveauphoto.fr>"
    resolved_reply_to = os.environ.get("MAIL_REPLY_TO") or DEFAULT_MAIL_REPLY_TO

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


def build_email_html_layout(title, intro, content_html, lang="fr"):
    """Construit une base HTML responsive noir/blanc pour tous les emails."""
    html_lang = "en" if normalize_lang(lang) == "en" else "fr"
    return f"""<!doctype html>
<html lang=\"{html_lang}\">
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
                Email: {BUSINESS_EMAIL}<br /><br />
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


def send_customer_contact_confirmation(payload, lang="fr"):
    """Envoie un accusé de réception HTML après un contact."""
    try:
        normalized_lang = normalize_lang(lang)
        if normalized_lang == "en":
            subject = "We have received your message - Studio Foveau"
            title = "Message received"
            intro = "Your contact request has been received."
            greeting = f"Hello {payload['name']},"
            message_1 = "Thank you for contacting Studio Foveau."
            message_2 = "Your request has been received. Our team will reply as soon as possible."
            service_label = "Requested service"
            customer_message_label = "Your message"
            studio_contact_label = "Studio contact"
            text_body = (
                f"Hello {payload['name']},\n\n"
                "Thank you for contacting Studio Foveau.\n"
                "Your request has been received and we will reply as soon as possible.\n\n"
                f"Requested service: {payload['service']}\n"
                f"Your message: {payload['message']}\n"
                f"Studio contact: {BUSINESS_EMAIL}\n\n"
                "Studio Foveau\n"
                "Calais\n"
                f"Email: {BUSINESS_EMAIL}\n\n"
                "This is an automated email."
            )
        else:
            subject = "Nous avons bien reçu votre message - Studio Foveau"
            title = "Message bien reçu"
            intro = "Votre demande de contact est enregistrée."
            greeting = f"Bonjour {payload['name']},"
            message_1 = "Merci d'avoir contacté Studio Foveau."
            message_2 = "Votre demande a bien été reçue. Notre équipe vous répondra dans les plus brefs délais."
            service_label = "Service demandé"
            customer_message_label = "Votre message"
            studio_contact_label = "Contact studio"
            text_body = (
                f"Bonjour {payload['name']},\n\n"
                "Merci d'avoir contacté Studio Foveau.\n"
                "Votre demande a bien été reçue et nous vous répondrons dès que possible.\n\n"
                f"Service demandé: {payload['service']}\n"
                f"Votre message: {payload['message']}\n"
                f"Contact studio: {BUSINESS_EMAIL}\n\n"
                "Studio Foveau\n"
                "Calais\n"
                f"Email: {BUSINESS_EMAIL}\n\n"
                "Ceci est un email automatique."
            )
        customer_message_html = escape(payload.get("message", "")).replace("\n", "<br />")
        content_html = f"""
                <div class=\"card\">
                    <p>{escape(greeting)}</p>
                    <p>{escape(message_1)}</p>
                    <p>{escape(message_2)}</p>
                    <div class=\"row\"><span class=\"label\">{escape(service_label)}:</span> {escape(payload['service'])}</div>
                    <div class=\"row\"><span class=\"label\">{escape(customer_message_label)}:</span><br />{customer_message_html}</div>
                    <div class=\"row\"><span class=\"label\">{escape(studio_contact_label)}:</span> {BUSINESS_EMAIL}</div>
                </div>
                """
        html_body = build_email_html_layout(
            title=title,
            intro=intro,
            content_html=content_html,
            lang=normalized_lang,
        )
        return send_notification_email(
            subject=subject,
            body=text_body,
            recipient=payload["email"],
            html_body=html_body,
        )
    except Exception:
        app.logger.exception("Échec de préparation de l'email client (contact)")
        return False


def send_customer_reservation_confirmation(payload, lang="fr"):
    """Envoie un accusé de réception HTML après une réservation."""
    try:
        reservation_message = (payload.get("message") or "").strip()
        normalized_lang = normalize_lang(lang)
        if normalized_lang == "en":
            subject = "Your booking request has been received - Studio Foveau"
            title = "Booking request received"
            intro = "Your request is being processed."
            greeting = f"Hello {payload['name']},"
            message_1 = "Your booking request has been received. It is not yet confirmed."
            message_2 = "Studio Foveau will contact you shortly to confirm your appointment."
            service_label = "Requested service"
            date_label = "Preferred date"
            time_label = "Preferred time"
            customer_message_label = "Your message"
            text_body = (
                f"Hello {payload['name']},\n\n"
                "Your booking request has been received. It is not yet confirmed. "
                "Studio Foveau will contact you shortly to confirm your appointment.\n\n"
                "Summary:\n"
                f"- Requested service: {payload['service']}\n"
                f"- Preferred date: {payload['requested_date']}\n"
                f"- Preferred time: {payload['requested_time']}\n"
                + (f"- Your message: {reservation_message}\n" if reservation_message else "")
                + "\n"
                "Studio Foveau\n"
                "Calais\n"
                f"Email: {BUSINESS_EMAIL}\n\n"
                "This is an automated email."
            )
        else:
            subject = "Votre demande de réservation a bien été reçue - Studio Foveau"
            title = "Réservation reçue"
            intro = "Votre demande est en cours de traitement."
            greeting = f"Bonjour {payload['name']},"
            message_1 = "Votre demande de réservation a bien été reçue. Elle n'est pas encore confirmée."
            message_2 = "Studio Foveau vous contactera rapidement pour confirmer le rendez-vous."
            service_label = "Service demandé"
            date_label = "Date demandée"
            time_label = "Heure demandée"
            customer_message_label = "Votre message"
            text_body = (
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
                "Calais\n"
                f"Email: {BUSINESS_EMAIL}\n\n"
                "Ceci est un email automatique."
            )
        reservation_message_html = escape(reservation_message).replace("\n", "<br />")
        reservation_message_row = ""
        if reservation_message:
            reservation_message_row = (
                f'<div class="row"><span class="label">{escape(customer_message_label)}:</span><br />{reservation_message_html}</div>'
            )

        content_html = f"""
                <div class=\"card\">
                    <p>{escape(greeting)}</p>
                    <p>{escape(message_1)}</p>
                    <p>{escape(message_2)}</p>
                    <div class=\"row\"><span class=\"label\">{escape(service_label)}:</span> {escape(payload['service'])}</div>
                    <div class=\"row\"><span class=\"label\">{escape(date_label)}:</span> {escape(payload['requested_date'])}</div>
                    <div class=\"row\"><span class=\"label\">{escape(time_label)}:</span> {escape(payload['requested_time'])}</div>
                    {reservation_message_row}
                </div>
                """
        html_body = build_email_html_layout(
            title=title,
            intro=intro,
            content_html=content_html,
            lang=normalized_lang,
        )
        return send_notification_email(
            subject=subject,
            body=text_body,
            recipient=payload["email"],
            html_body=html_body,
        )
    except Exception:
        app.logger.exception("Échec de préparation de l'email client (réservation)")
        return False


@app.after_request
def set_security_headers(response):
    """Ajoute des en-têtes HTTP de sécurité compatibles avec le site actuel."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


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
def get_studio_status(lang="fr"):
    normalized_lang = normalize_lang(lang)
    now = datetime.now()
    day = now.weekday()
    time_now = now.time()

    if day == 6:
        return False, translate("status.closed", normalized_lang), translate("status.sunday", normalized_lang)

    open_morning = datetime.strptime("09:00", "%H:%M").time()
    close_morning = datetime.strptime("12:00", "%H:%M").time()
    open_afternoon = datetime.strptime("14:00", "%H:%M").time()
    close_evening = datetime.strptime(
        "18:00" if day == 5 else "19:00", "%H:%M"
    ).time()

    if open_morning <= time_now < close_morning:
        return True, translate("status.open", normalized_lang), translate("status.morning", normalized_lang)
    if open_afternoon <= time_now < close_evening:
        return True, translate("status.open", normalized_lang), translate("status.afternoon", normalized_lang)

    return False, translate("status.closed", normalized_lang), translate("status.outside", normalized_lang)


@app.context_processor
def inject_status():
    current_lang = get_request_lang()
    is_open, label, detail = get_studio_status(current_lang)
    canonical_path = normalize_path(request.path)
    canonical_url = SITE_URL if canonical_path == "/" else f"{SITE_URL}{canonical_path}"

    normalized_path = normalize_path(request.path)
    page_key = None
    for candidate_key, localized_paths in PAGE_PATHS.items():
        if normalized_path in {normalize_path(localized_paths["fr"]), normalize_path(localized_paths["en"])}:
            page_key = candidate_key
            break

    if page_key:
        alternate_paths = PAGE_PATHS[page_key]
    else:
        alternate_paths = {"fr": "/", "en": "/en/"}

    alternate_urls = {
        "fr": SITE_URL if alternate_paths["fr"] == "/" else f"{SITE_URL}{alternate_paths['fr']}",
        "en": f"{SITE_URL}{alternate_paths['en']}",
    }

    switch_lang = "en" if current_lang == "fr" else "fr"
    switch_lang_url = alternate_urls[switch_lang]

    local_business_schema = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": BUSINESS_NAME,
        "url": SITE_URL,
        "telephone": BUSINESS_PHONE,
        "email": BUSINESS_EMAIL,
        "image": f"{SITE_URL}{OFFICIAL_LOGO_PATH}",
        "logo": f"{SITE_URL}{OFFICIAL_LOGO_PATH}",
        "sameAs": [BUSINESS_FACEBOOK],
        "address": {
            "@type": "PostalAddress",
            "streetAddress": BUSINESS_ADDRESS_STREET,
            "addressLocality": BUSINESS_ADDRESS_LOCALITY,
            "postalCode": BUSINESS_ADDRESS_POSTAL_CODE,
            "addressCountry": BUSINESS_ADDRESS_COUNTRY,
        },
        "areaServed": [
            {"@type": "City", "name": "Calais"},
            {"@type": "AdministrativeArea", "name": "Pas-de-Calais"},
            {"@type": "AdministrativeArea", "name": "Hauts-de-France"},
        ],
        "inLanguage": LANGUAGE_TO_LOCALE[current_lang],
        "priceRange": "EUR",
    }

    return dict(
        t=lambda key: translate(key, current_lang),
        lang=current_lang,
        og_locale=LANGUAGE_TO_OG_LOCALE[current_lang],
        html_lang="fr" if current_lang == "fr" else "en",
        current_locale=LANGUAGE_TO_LOCALE[current_lang],
        alternate_urls=alternate_urls,
        switch_lang=switch_lang,
        switch_lang_url=switch_lang_url,
        page_key=page_key,
        is_open=is_open,
        status_label=label,
        status_detail=detail,
        status=label,
        site_url=SITE_URL,
        canonical_url=canonical_url,
        business_name=BUSINESS_NAME,
        business_phone=BUSINESS_PHONE,
        business_email=BUSINESS_EMAIL,
        business_facebook=BUSINESS_FACEBOOK,
        business_address_street=BUSINESS_ADDRESS_STREET,
        business_address_locality=BUSINESS_ADDRESS_LOCALITY,
        business_address_postal_code=BUSINESS_ADDRESS_POSTAL_CODE,
        business_address_country=BUSINESS_ADDRESS_COUNTRY,
        local_business_schema=local_business_schema,
        google_site_verification=os.environ.get("GOOGLE_SITE_VERIFICATION", ""),
        current_year=datetime.utcnow().year,
        lang_url=lambda endpoint, **kwargs: endpoint_url(endpoint, current_lang, **kwargs),
        url_for=lambda endpoint, **kwargs: endpoint_url(endpoint, current_lang, **kwargs),
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
@app.route("/", defaults={"lang": "fr"})
@app.route("/en", defaults={"lang": "en"})
@app.route("/en/", defaults={"lang": "en"})
def home(lang):
    return render_public_page("home", lang)


@app.route("/services", defaults={"lang": "fr"})
@app.route("/en/services", defaults={"lang": "en"})
def services(lang):
    return render_public_page("services", lang)


@app.route("/about", defaults={"lang": "fr"})
@app.route("/en/about", defaults={"lang": "en"})
def about(lang):
    return render_public_page("about", lang)


@app.route("/mentions-legales", defaults={"lang": "fr"})
@app.route("/en/legal-notice", defaults={"lang": "en"})
def mentions_legales(lang):
    return render_public_page("mentions_legales", lang)


@app.route("/politique-confidentialite", defaults={"lang": "fr"})
@app.route("/en/privacy-policy", defaults={"lang": "en"})
def politique_confidentialite(lang):
    return render_public_page("politique_confidentialite", lang)


@app.route("/cgu", defaults={"lang": "fr"})
@app.route("/en/terms-of-use", defaults={"lang": "en"})
def cgu(lang):
    return render_public_page("cgu", lang)


@app.route("/contact", methods=["GET", "POST"], defaults={"lang": "fr"})
@app.route("/en/contact", methods=["GET", "POST"], defaults={"lang": "en"})
def contact(lang):
    normalized_lang = normalize_lang(lang)
    if request.method == "POST":
        payload, error_message = validate_contact_payload(request.form, normalized_lang)
        if error_message:
            flash(error_message, "danger")
            return redirect(endpoint_url("contact", normalized_lang))

        db.session.add(ContactMessage(**payload))
        db.session.commit()

        admin_result = send_admin_contact_email(payload)
        app.logger.info("Admin contact email result: %s", admin_result)
        customer_result = send_customer_contact_confirmation(payload, normalized_lang)
        app.logger.info("Customer contact email result: %s", customer_result)

        flash(translate("flash.contact_success", normalized_lang), "success")
        return redirect(endpoint_url("contact", normalized_lang))

    return render_public_page("contact", normalized_lang)


@app.route("/reservation", methods=["GET", "POST"], defaults={"lang": "fr"})
@app.route("/en/reservation", methods=["GET", "POST"], defaults={"lang": "en"})
def reservation(lang):
    normalized_lang = normalize_lang(lang)
    if request.method == "POST":
        payload, error_message = validate_booking_payload(request.form, normalized_lang)
        if error_message:
            flash(error_message, "danger")
            return redirect(endpoint_url("reservation", normalized_lang))

        db.session.add(Booking(**payload))
        db.session.commit()

        admin_result = send_admin_reservation_email(payload)
        app.logger.info("Admin reservation email result: %s", admin_result)
        customer_result = send_customer_reservation_confirmation(payload, normalized_lang)
        app.logger.info("Customer reservation email result: %s", customer_result)

        flash(translate("flash.booking_success", normalized_lang), "success")
        return redirect(endpoint_url("reservation", normalized_lang))

    return render_public_page("reservation", normalized_lang)


@app.route("/sitemap.xml")
def sitemap_xml():
    pages = [
        ("home", 1.0),
        ("services", 0.9),
        ("reservation", 0.9),
        ("about", 0.8),
        ("contact", 0.8),
        ("mentions_legales", 0.4),
        ("politique_confidentialite", 0.4),
        ("cgu", 0.4),
    ]

    xml_lines = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\" xmlns:xhtml=\"http://www.w3.org/1999/xhtml\">",
    ]

    seen_urls = set()
    for page_key, priority in pages:
        fr_path = PAGE_PATHS[page_key]["fr"]
        en_path = PAGE_PATHS[page_key]["en"]

        fr_url = f"{SITE_URL}/" if fr_path == "/" else f"{SITE_URL}{fr_path}"
        en_url = f"{SITE_URL}{en_path}"

        # Keep multilingual alternates while ensuring each canonical URL is unique.
        for canonical in (fr_url, en_url):
            if canonical in seen_urls:
                continue
            seen_urls.add(canonical)

            escaped_canonical = escape(canonical, quote=True)
            escaped_fr = escape(fr_url, quote=True)
            escaped_en = escape(en_url, quote=True)

            xml_lines.extend(
                [
                    "  <url>",
                    f"    <loc>{escaped_canonical}</loc>",
                    f"    <xhtml:link rel=\"alternate\" hreflang=\"fr\" href=\"{escaped_fr}\" />",
                    f"    <xhtml:link rel=\"alternate\" hreflang=\"en\" href=\"{escaped_en}\" />",
                    f"    <xhtml:link rel=\"alternate\" hreflang=\"x-default\" href=\"{escaped_fr}\" />",
                    "    <changefreq>weekly</changefreq>",
                    f"    <priority>{priority:.1f}</priority>",
                    "  </url>",
                ]
            )

    xml_lines.append("</urlset>")
    xml_content = "\n".join(xml_lines)

    # Validate XML before returning it to avoid malformed sitemap responses.
    ET.fromstring(xml_content)

    return Response(xml_content, content_type="application/xml")


@app.route("/robots.txt")
def robots_txt():
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        f"Sitemap: {SITE_URL}/sitemap.xml\n"
    )
    return Response(content, mimetype="text/plain")


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
    lang = get_request_lang()
    return render_template(
        "404.html",
        meta_title=translate("error.404.title", lang),
        meta_description=translate("error.404.description", lang),
    ), 404


@app.errorhandler(500)
def server_error(e):
    app.logger.exception("Erreur serveur sur %s", request.path)
    lang = get_request_lang()
    return render_template(
        "500.html",
        meta_title=translate("error.500.title", lang),
        meta_description=translate("error.500.description", lang),
    ), 500


@app.route("/<lang>/", defaults={"subpath": ""})
@app.route("/<lang>/<path:subpath>")
def fallback_unknown_language(lang, subpath):
    if lang in SUPPORTED_LANGUAGES:
        return redirect(endpoint_url("home", lang))

    stripped_subpath = (subpath or "").strip("/")
    fallback_map = {
        "legal-notice": "mentions-legales",
        "privacy-policy": "politique-confidentialite",
        "terms-of-use": "cgu",
    }
    fallback_subpath = fallback_map.get(stripped_subpath, stripped_subpath)
    fallback_target = f"/{fallback_subpath}" if fallback_subpath else "/"
    return redirect(fallback_target)


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


validate_admin_template_routes()


# =========================
# START
# =========================
if __name__ == "__main__":
    app.run()