"""
Script de nettoyage : supprime toutes les tables pour repartir de zéro.
Usage : heroku run python reset_db.py --app m-faida-app
"""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db import connection

cursor = connection.cursor()
cursor.execute('SET FOREIGN_KEY_CHECKS = 0;')
cursor.execute('SHOW TABLES;')
tables = [row[0] for row in cursor.fetchall()]
print(f"Tables trouvées : {len(tables)}")
for t in tables:
    cursor.execute(f'DROP TABLE IF EXISTS `{t}`;')
    print(f'  ✓ Supprimée : {t}')
cursor.execute('SET FOREIGN_KEY_CHECKS = 1;')
print("Base de données nettoyée. Vous pouvez relancer migrate.")
