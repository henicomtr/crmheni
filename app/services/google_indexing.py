import json
import os
import logging
import httpx
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)
INDEXING_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"

def _get_credentials():
    raw = os.environ.get("GOOGLE_OAUTH_TOKEN")
    if not raw:
        raise RuntimeError("GOOGLE_OAUTH_TOKEN environment variable eksik!")
    data = json.loads(raw)
    creds = Credentials(
        token=None,  # her zaman refresh yap
        refresh_token=data["refresh_token"],
        token_uri=data["token_uri"],
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=data["scopes"]
    )
    creds.refresh(Request())
    return creds

async def notify_google(url: str, action: str = "URL_UPDATED"):
    try:
        creds = _get_credentials()
        headers = {
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json"
        }
        payload = {"url": url, "type": action}
        async with httpx.AsyncClient() as client:
            response = await client.post(INDEXING_ENDPOINT, json=payload, headers=headers)
            response.raise_for_status()
            logger.info(f"Google indexing OK: {url}")
    except Exception as e:
        logger.error(f"Google indexing FAILED: {url} — {e}")