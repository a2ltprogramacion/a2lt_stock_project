"""
ASGI config for a2lt_stock_project project.

It exposes the ASGI callable as a module-level variable named ``application``.
"""
import os
from pathlib import Path


def _load_dotenv():
    env_path = Path(__file__).resolve().parent.parent / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()

from django.core.asgi import get_asgi_application  # noqa: E402

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'a2lt_stock_project.settings')

application = get_asgi_application()
