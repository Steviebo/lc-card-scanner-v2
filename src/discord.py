import os
import requests

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def send_deal(title, price, url, image_url=None):
    if not WEBHOOK_URL:
        raise RuntimeError("Missing DISCORD_WEBHOOK_URL")

    embed = {
        "title": title,
        "url": url,
        "fields": [
            {"name": "Price", "value": f"${price}", "inline": True}
        ]
    }

    if image_url:
        embed["image"] = {"url": image_url}

    payload = {
        "embeds": [embed]
    }

    r = requests.post(WEBHOOK_URL, json=payload)
    r.raise_for_status()