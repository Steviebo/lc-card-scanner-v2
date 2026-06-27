import base64
import logging
import os
import time

import requests

logger = logging.getLogger("lc_card_scanner")

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
TOKEN_CACHE = {
    "token": None,
    "expires_at": 0
}

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2


def get_access_token():
    now = time.time()
    if TOKEN_CACHE["token"] and now < TOKEN_CACHE["expires_at"]:
        return TOKEN_CACHE["token"]

    client_id = os.getenv("EBAY_CLIENT_ID")
    client_secret = os.getenv("EBAY_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError("Missing EBAY_CLIENT_ID or EBAY_CLIENT_SECRET")

    creds = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(creds.encode()).decode()

    headers = {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope",
    }

    r = requests.post(TOKEN_URL, headers=headers, data=data, timeout=15)
    r.raise_for_status()

    payload = r.json()
    TOKEN_CACHE["token"] = payload["access_token"]
    TOKEN_CACHE["expires_at"] = now + payload["expires_in"] - 60

    return TOKEN_CACHE["token"]


def search(query, limit=200, max_pages=1):
    """
    Search eBay for listings matching query, filtered to Reverse Holo
    Trading Card Singles.

    Paginates up to max_pages (each page up to `limit`, eBay's max is 200).
    Retries on rate-limit (429) and transient server errors (5xx) with
    backoff. Raises requests.HTTPError if a request ultimately fails.

    Returns a combined list of itemSummary dicts.
    """
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}"
    }

    all_items = []
    offset = 0

    for page in range(max_pages):
        params = {
            "q": query,
            "category_ids": "183454",  # Trading Card Singles
            "filter": "itemSpecifics:{name=Rarity,value=Reverse Holo}",
            "limit": limit,
            "offset": offset,
        }

        response_json = _get_with_retries(headers, params)
        items = response_json.get("itemSummaries", [])
        all_items.extend(items)

        total = response_json.get("total", 0)
        offset += len(items)
        if len(items) < limit or offset >= total:
            break  # no more pages available

    return all_items


def _get_with_retries(headers, params):
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(BROWSE_URL, headers=headers, params=params, timeout=15)
            if r.status_code == 429:
                wait = RETRY_BACKOFF_SECONDS * attempt
                logger.warning("eBay rate-limited us (429), retrying in %ss", wait)
                time.sleep(wait)
                continue
            if 500 <= r.status_code < 600:
                wait = RETRY_BACKOFF_SECONDS * attempt
                logger.warning("eBay server error %s, retrying in %ss", r.status_code, wait)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            last_exc = e
            logger.warning("eBay request failed (attempt %s/%s): %s", attempt, MAX_RETRIES, e)
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    if last_exc:
        raise last_exc
    raise RuntimeError(f"eBay search failed after {MAX_RETRIES} attempts for query={params.get('q')!r}")
