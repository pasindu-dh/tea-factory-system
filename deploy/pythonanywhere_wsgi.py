"""PythonAnywhere WSGI configuration (free tier).

On the PythonAnywhere Web tab, open the WSGI file it shows
(/var/www/<username>_pythonanywhere_com_wsgi.py), delete its contents, and
paste this file. Replace:

  * YOUR_USERNAME          -- your PythonAnywhere username
  * PASTE_A_64_CHAR_SECRET -- output of:
        python -c "import secrets; print(secrets.token_hex(32))"

Everything below the substitutions is production-ready: HTTPS is enforced by
the platform, secure cookies are on, demo credentials are off, and the SQLite
file lives outside the source tree in a persistent home-directory folder.

The environment must be configured *before* importing app, because
create_app() validates the production configuration at import time.
"""
import os
import sys
import time

USERNAME = "YOUR_USERNAME"
PROJECT = f"/home/{USERNAME}/tea-factory-system"
DATA = f"/home/{USERNAME}/tea-factory-data"

os.environ["TEA_FACTORY_DB"] = f"{DATA}/tea_factory.sqlite3"
os.environ["TEA_FACTORY_SECRET_KEY"] = "PASTE_A_64_CHAR_SECRET"
os.environ["TEA_FACTORY_PRODUCTION"] = "1"
os.environ["TEA_FACTORY_SECURE_COOKIES"] = "1"
os.environ["TEA_FACTORY_TRUST_PROXY"] = "1"
os.environ["TEA_FACTORY_SHOW_DEMO_CREDENTIALS"] = "0"
os.environ["TZ"] = "Asia/Colombo"
if hasattr(time, "tzset"):  # POSIX only; PythonAnywhere is Linux
    time.tzset()
os.makedirs(DATA, exist_ok=True)

if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

from app import app as application  # noqa: E402  (must follow env setup)
