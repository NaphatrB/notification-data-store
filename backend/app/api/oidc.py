import os
import logging
from authlib.integrations.starlette_client import OAuth

logger = logging.getLogger("anla.oidc")

OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET")
OIDC_ISSUER = os.environ.get("OIDC_ISSUER")
OIDC_DISCOVERY_URL = os.environ.get("OIDC_DISCOVERY_URL")

# Synology SSO usually has a well-known endpoint.
# If OIDC_DISCOVERY_URL is not set, try to derive it from OIDC_ISSUER.
if not OIDC_DISCOVERY_URL and OIDC_ISSUER:
    OIDC_DISCOVERY_URL = f"{OIDC_ISSUER.rstrip('/')}/.well-known/openid-configuration"

oauth = OAuth()

if OIDC_CLIENT_ID and OIDC_CLIENT_SECRET and OIDC_DISCOVERY_URL:
    logger.info("OIDC configured with client_id=%s, discovery_url=%s", OIDC_CLIENT_ID, OIDC_DISCOVERY_URL)
    oauth.register(
        name='synology',
        client_id=OIDC_CLIENT_ID,
        client_secret=OIDC_CLIENT_SECRET,
        server_metadata_url=OIDC_DISCOVERY_URL,
        client_kwargs={
            'scope': 'openid profile email',
        }
    )
else:
    logger.warning("OIDC NOT CONFIGURED: Missing client_id, client_secret, or discovery_url.")

def is_oidc_enabled() -> bool:
    return bool(OIDC_CLIENT_ID and OIDC_CLIENT_SECRET and OIDC_DISCOVERY_URL)
