import logging
from pathlib import Path

import yaml
from dotenv import load_dotenv

import discord
from ebay.client import search
from ebay.filters import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    is_reverse_holo,
    legendary_collection_confidence,
    load_seen_ids,
    save_seen_ids,
)
from ebay.models import Listing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("lc_card_scanner")

# Resolve relative to this file, not the caller's cwd -- so `python src/main.py`
# from the repo root and `python main.py` from inside src/ both work the same.
CARDS_CONFIG_PATH = Path(__file__).parent / "config" / "cards.yaml"


def run():
    load_dotenv()

    with open(CARDS_CONFIG_PATH) as f:
        cards = yaml.safe_load(f)["cards"]

    seen_ids = load_seen_ids()
    new_seen_ids = set(seen_ids)
    deals_found = 0
    low_confidence_candidates = []  # collected across all cards, sent as one batch at the end

    for card in cards:
        name = card.get("name", card["query"])
        try:
            raw_items = search(card["query"])
        except Exception as e:
            logger.error("Search failed for %s: %s", name, e)
            continue  # don't let one bad card kill the whole scan

        for raw_item in raw_items:
            listing = Listing.from_item_summary(raw_item)

            if not listing.item_id:
                logger.warning("Skipping listing with no itemId: %r", listing.title)
                continue

            if listing.item_id in seen_ids:
                continue  # already alerted on this one in a previous run

            confidence = legendary_collection_confidence(listing)
            if confidence == "none":
                logger.info("Skipping (not actually Legendary Collection): %s", listing.title)
                continue

            if not is_reverse_holo(listing):
                logger.info("Skipping (not reverse holo): %s", listing.title)
                continue

            if listing.price is None:
                logger.info("Skipping (no price): %s", listing.title)
                continue

            if listing.price >= card["max_price"]:
                # Still mark non-deals as seen so we don't re-check them
                # against the title/price filters every single run.
                new_seen_ids.add(listing.item_id)
                continue

            if confidence == CONFIDENCE_HIGH:
                logger.info(
                    "[DEAL] %s -- $%s -- %s -- %s",
                    listing.title, listing.price, listing.buying_options, listing.url
                )
                sent = discord.send_deal(
                    title=listing.title,
                    price=listing.price,
                    url=listing.url,
                    image_url=listing.image_url,
                    currency=listing.currency or "USD",
                )
                if sent:
                    deals_found += 1
                    # Only mark as seen if we actually managed to alert on it,
                    # so a Discord outage doesn't silently swallow a deal.
                    new_seen_ids.add(listing.item_id)
            else:  # CONFIDENCE_LOW
                logger.info(
                    "[LOW-CONFIDENCE] %s -- $%s -- %s",
                    listing.title, listing.price, listing.url
                )
                low_confidence_candidates.append(listing)

    if low_confidence_candidates:
        sent_listings = discord.send_low_confidence_batch(low_confidence_candidates)
        for listing in sent_listings:
            # Only mark as seen the ones that actually made it to Discord,
            # same reasoning as high-confidence deals above.
            new_seen_ids.add(listing.item_id)
        deals_found += len(sent_listings)

    save_seen_ids(new_seen_ids)
    logger.info("Scan complete. %s new deal(s) sent.", deals_found)


if __name__ == "__main__":
    run()
