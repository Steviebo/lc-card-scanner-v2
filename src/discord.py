import logging
import os
import time

import requests

logger = logging.getLogger("lc_card_scanner")

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

MAX_RETRIES = 3

# Discord hard limits we need to respect when batching text into one embed.
_EMBED_DESCRIPTION_LIMIT = 4096
_MAX_LINES_PER_BATCH = 20  # keep batches readable even well under the char limit


def send_deal(title, price, url, image_url=None, currency="USD"):
    """Post a single high-confidence deal alert to Discord, with image.

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

    return _post_with_retries({"embeds": [embed]}, label=title)


def send_low_confidence_batch(listings):
    """Post a batch of lower-confidence listings as compact title+price+link
    lines in a single embed (no images), so they don't crowd the channel
    the way one full embed per listing would.

    `listings` is an iterable of Listing objects. Splits into multiple
    messages if needed to stay under Discord's embed description limit.
    Returns the list of listings that were successfully sent (so the
    caller can mark exactly those as seen).
    """
    if not WEBHOOK_URL:
        raise RuntimeError("Missing DISCORD_WEBHOOK_URL")

    listings = list(listings)
    if not listings:
        return []

    sent = []
    for batch_start in range(0, len(listings), _MAX_LINES_PER_BATCH):
        batch = listings[batch_start:batch_start + _MAX_LINES_PER_BATCH]

        lines = []
        for listing in batch:
            price_str = f"${listing.price} {listing.currency or 'USD'}".strip()
            lines.append(f"[{listing.title}]({listing.url}) -- {price_str}")

        description = "\n".join(lines)
        if len(description) > _EMBED_DESCRIPTION_LIMIT:
            description = description[:_EMBED_DESCRIPTION_LIMIT - 3] + "..."

        embed = {
            "title": f"🔎 {len(batch)} lower-confidence listing(s) to review",
            "description": description,
        }

        if _post_with_retries({"embeds": [embed]}, label=f"low-confidence batch of {len(batch)}"):
            sent.extend(batch)

    return sent


def _post_with_retries(payload, label):
    """Shared retry/backoff logic for any webhook payload. Never raises."""
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
            logger.warning("Discord webhook failed (attempt %s/%s) for %r: %s", attempt, MAX_RETRIES, label, e)
            time.sleep(1 * attempt)

    logger.error("Giving up sending Discord message for %r after %s attempts", label, MAX_RETRIES)
    return False
