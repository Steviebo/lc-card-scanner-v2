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


def send_deal(title, price, url, image_url=None, currency="USD", market_price=None):
    """Post a single high-confidence deal alert to Discord, with image.

    If market_price is provided (not None), adds a "Market Price" field
    showing the comparison and percent savings, e.g. "$400.00 ~25% Savings!"
    If the listing price is actually >= market price, shows the delta
    plainly instead of claiming a (false) savings.

    Never raises -- a Discord outage or rate limit should not crash the scan
    or stop other deals from being processed and recorded as seen.
    """
    if not WEBHOOK_URL:
        raise RuntimeError("Missing DISCORD_WEBHOOK_URL")

    fields = [
        {"name": "Price", "value": f"${price} {currency}".strip(), "inline": True}
    ]

    market_field = _format_market_price_field(price, market_price, currency)
    if market_field:
        fields.append(market_field)

    embed = {
        "title": title,
        "url": url,
        "fields": fields,
    }

    if image_url:
        embed["image"] = {"url": image_url}

    return _post_with_retries({"embeds": [embed]}, label=title)


def _format_market_price_field(listing_price, market_price, currency):
    """Build the 'Market Price' embed field, or None if we have nothing to show."""
    if market_price is None or market_price <= 0:
        return None

    diff_pct = (market_price - listing_price) / market_price * 100

    if diff_pct > 0:
        value = f"${market_price:.2f} {currency} (~{diff_pct:.0f}% Savings!)"
    elif diff_pct < 0:
        value = f"${market_price:.2f} {currency} ({abs(diff_pct):.0f}% above market)"
    else:
        value = f"${market_price:.2f} {currency} (at market price)"

    return {"name": "Market Price", "value": value, "inline": True}


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
            suffix = ""
            if listing.market_price and listing.market_price > 0:
                diff_pct = (listing.market_price - listing.price) / listing.market_price * 100
                if diff_pct > 0:
                    suffix = f" -- market ~${listing.market_price:.2f} ({diff_pct:.0f}% savings)"
                else:
                    suffix = f" -- market ~${listing.market_price:.2f}"
            lines.append(f"[{listing.title}]({listing.url}) -- {price_str}{suffix}")

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
