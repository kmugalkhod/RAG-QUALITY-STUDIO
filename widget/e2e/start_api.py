"""Start an isolated local browser fixture without touching the developer database."""

import os
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from sqlalchemy.engine import make_url
from app.core.config import settings

root = Path(__file__).resolve().parents[2]
url = make_url(settings.database_url).set(database="rag_widget_browser_test")
env = dict(os.environ)
env.update(
    {
        "DATABASE_URL": url.render_as_string(hide_password=False),
        "DEPLOYED_ANSWERS_ENABLED": "true",
        "DEPLOYMENT_ACTIVE_PEPPER": settings.deployment_active_pepper,
        "DEPLOYMENT_KEY_PEPPERS": json.dumps(
            {
                key: value.get_secret_value()
                for key, value in settings.deployment_key_peppers.items()
            }
        ),
        "DEPLOYMENT_PRICING_VERSION": settings.deployment_pricing_version,
        "DEPLOYMENT_APPROVED_PRICES": json.dumps(
            settings.deployment_approved_prices, default=str
        ),
        "OPENROUTER_API_KEY": settings.openrouter_api_key.get_secret_value(),
        "CHAT_MODEL": settings.chat_model,
        "EMBEDDING_MODEL": settings.embedding_model,
        "EMBEDDING_DIMENSIONS": str(settings.embedding_dimensions),
        "AUTH_MODE": "local",
        "DEPLOYMENT_LOCAL_KEYS_ENABLED": "true",
        "WIDGET_ENABLED": "true",
        "WIDGET_FRAME_ORIGIN": "http://127.0.0.1:5274",
        "WIDGET_TOKEN_HASH_KEY": "only-for-isolated-browser-fixture-widget-hashing-1234",
        # Browser journeys share one disposable deployment; production rate boundaries
        # are covered by isolated backend tests and the explicit 429 browser case.
        "DEPLOYMENT_KEY_RPM": "100",
        "DEPLOYMENT_RPM": "200",
        "DEPLOYMENT_ORG_RPM": "1000",
        "WIDGET_VISITOR_RPM": "100",
        "WIDGET_EXCHANGE_RPM": "1000",
        "WIDGET_LOCAL_CONFIG_FILE": str(
            Path(tempfile.gettempdir()) / f"rag-widget-browser-{os.getuid()}.json"
        ),
        "PYTHONPATH": str(root / "backend"),
    }
)
subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    cwd=root / "backend",
    env=env,
    check=True,
)
os.execve(
    sys.executable,
    [sys.executable, str(root / "backend/tests/widget_browser/local_api.py")],
    env,
)
