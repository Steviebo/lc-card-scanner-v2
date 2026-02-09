import os
import base64
import time
import requests

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
TOKEN_CACHE = {
    "token": None,
    "expires_at": 0
}

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

    r = requests.post(TOKEN_URL, headers=headers, data=data)
    r.raise_for_status()

    payload = r.json()
    TOKEN_CACHE["token"] = payload["access_token"]
    TOKEN_CACHE["expires_at"] = now + payload["expires_in"] - 60

    return TOKEN_CACHE["token"]

def search(query, limit=200):
    """
    Search eBay for listings matching query (auctions only)
    Returns a list of item summaries
    """
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}"
    }
    params = {
        "q": query,
        "category_ids": "183454",  # Trading Card Singles
        "filter": (
        "itemSpecifics:{name=Rarity,value=Reverse Holo}"
        ),
        "limit": limit
    }

    r = requests.get(BROWSE_URL, headers=headers, params=params)
    r.raise_for_status()
    return r.json()