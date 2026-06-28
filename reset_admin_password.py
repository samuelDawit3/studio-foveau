"""Local admin password reset helper.

Usage:
    python reset_admin_password.py

This script is disabled by convention in production.
"""

import os
from getpass import getpass

from app import app, init_database, reset_admin_password


def main():
    env = os.environ.get("FLASK_ENV", "development").lower()
    if env == "production":
        print("Outil désactivé en production.")
        return 1

    email = input("Email administrateur: ").strip().lower()
    new_password = getpass("Nouveau mot de passe: ")

    with app.app_context():
        init_database()
        updated = reset_admin_password(email, new_password)

    if updated:
        print("Mot de passe administrateur mis à jour.")
        return 0

    print("Administrateur introuvable.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
