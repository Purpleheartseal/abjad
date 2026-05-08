#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${ROOT_DIR}/github-clean-export"

mkdir -p "${TARGET_DIR}"

rsync -a --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  --exclude 'db.sqlite3' \
  --exclude 'media/' \
  --exclude 'offline/' \
  --exclude 'github-clean-export/' \
  --exclude 'test sample.xlsm' \
  --exclude '~$*.xlsm' \
  --exclude 'file:memorydb_default?mode=memory&cache=shared' \
  --exclude '*.sqlite3' \
  "${ROOT_DIR}/" "${TARGET_DIR}/"

find "${TARGET_DIR}" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "${TARGET_DIR}" -name '.DS_Store' -type f -delete
find "${TARGET_DIR}" -name '*.pyc' -type f -delete
rm -f "${TARGET_DIR}/db.sqlite3"

cat > "${TARGET_DIR}/README-GITHUB-SETUP.md" <<'EOF'
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
EOF

echo "Clean GitHub export synced to: ${TARGET_DIR}"
