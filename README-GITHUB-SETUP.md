This folder is a sanitized GitHub-ready export of the Abjad project.

What has been removed:
- db.sqlite3 and any local database data
- superuser/user data stored in the database
- virtualenv files
- offline wheelhouse artifacts
- sample Excel data files
- caches and local system files

After cloning/pushing this folder, initialize the app with:

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
