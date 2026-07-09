import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Configuration centralisée de l'application.

    - Charge les variables d'environnement via python-dotenv.
    - Exige explicitement `SECRET_KEY` (sécurité) — ne fournit pas de fallback.
    - Configure la session pour être sécurisée en production.
    """

    # Environnement (dev / production)
    FLASK_ENV = os.environ.get('FLASK_ENV', 'development').lower()

    # Secret (obligatoire). En production, l'absence doit arrêter le démarrage.
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise RuntimeError('La variable SECRET_KEY est requise. Copiez .env.example en .env et définissez SECRET_KEY.')

    # Base de données (sqlite stable pour déploiement simple; DATABASE_URL peut surcharger)
    DATABASE_URL = os.environ.get('DATABASE_URL') or ('sqlite:///' + os.path.join(BASE_DIR, 'app.db'))
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session security
    PERMANENT_SESSION_LIFETIME = timedelta(days=int(os.environ.get('PERMANENT_SESSION_LIFETIME_DAYS', '7')))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    SESSION_COOKIE_SECURE = (FLASK_ENV == 'production')

    # Remember cookie settings (useful if integrating Flask-Login later)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = (FLASK_ENV == 'production')
