import json
import logging
import httpx
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

# Docker container içindeki token dosyası yolu
TOKEN_FILE = "/app/secrets/oauth_token.json"
INDEXING_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"


def _get_credentials():
    # Token dosyasını oku ve Credentials nesnesi oluştur
    with open(TOKEN_FILE) as f:
        data = json.load(f)
    creds = Credentials(
        token=data["token"],
        refresh_token=data["refresh_token"],
        token_uri=data["token_uri"],
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=data["scopes"]
    )
    if not creds.valid:
        # Token süresi dolmuşsa yenile ve dosyaya kaydet
        creds.refresh(Request())
        data["token"] = creds.token
        with open(TOKEN_FILE, "w") as f:
            json.dump(data, f, indent=2)
    return creds


async def notify_google(url: str, action: str = "URL_UPDATED"):
    # Google Indexing API'ye URL güncelleme bildirimi gönder
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
