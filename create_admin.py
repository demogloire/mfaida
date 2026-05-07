"""
Crée le superuser initial sur Heroku.
Usage : heroku run python create_admin.py --app m-faida-app
"""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from utilisateur.models import Profil

username = 'admin'
email = 'admin@mfaida.com'
password = 'Admin@2026!'

if Profil.objects.filter(username=username).exists():
    print(f"L'utilisateur '{username}' existe déjà.")
else:
    Profil.objects.create_superuser(username=username, email=email, password=password)
    print(f"Superuser '{username}' créé avec succès.")
    print(f"Email    : {email}")
    print(f"Mot de passe : {password}")
    print("PENSEZ À CHANGER LE MOT DE PASSE APRÈS LA PREMIÈRE CONNEXION !")
