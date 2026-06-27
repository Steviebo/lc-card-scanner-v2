import logging
import os
import time

import requests

logger = logging.getLogger("lc_card_scanner")

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

MAX_RETRIES = 3


def send_deal(title, price, url, image_url=None, currency="USD"):
    """Post a deal alert to Discord. Returns True on success, False otherwise.

    Never raises -- a Discord outage or rate limit should not crash the scan
    or stop other deals from being processed and recorded as seen.
    """
    if not WEBHOOK_URL:
        raise RuntimeError("Missing DISCORD_WEBHOOK_URL")

    embed = {
        "title": title,
        "url": url,
        "fields": [
            {"name": "Price", "value": f"${price} {currency}".strip(), "inline": True}
        ]
    }

    if image_url:
        embed["image"] = {"url": image_url}

    payload = {"embeds": [embed]}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.post(WEBHOOK_URL, json=payload, timeout=10)
            if r.status_code == 429:
                retry_after = r.json().get("retry_after", 1)
                logger.warning("Discord rate-limited us, retrying in %ss", retry_after)
                time.sleep(retry_after)
                continue
            r.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.warning("Discord webhook failed (attempt %s/%s): %s", attempt, MAX_RETRIES, e)
            time.sleep(1 * attempt)

    logger.error("Giving up sending Discord alert for %r after %s attempts", title, MAX_RETRIES)
    return False
