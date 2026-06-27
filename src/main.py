import logging

import yaml
from dotenv import load_dotenv

import discord
from ebay.client import search
from ebay.filters import is_reverse_holo, load_seen_ids, save_seen_ids
from ebay.models import Listing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("lc_card_scanner")


def run():
    load_dotenv()

    with open("src/config/cards.yaml") as f:
        cards = yaml.safe_load(f)["cards"]

    seen_ids = load_seen_ids()
    new_seen_ids = set(seen_ids)
    deals_found = 0

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

            if not is_reverse_holo(listing):
                logger.info("Skipping (not reverse holo): %s", listing.title)
                continue

            if listing.price is None:
                logger.info("Skipping (no price): %s", listing.title)
                continue

            if listing.price < card["max_price"]:
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
            else:
                # Still mark non-deals as seen so we don't re-check them
                # against the title/price filters every single run.
                new_seen_ids.add(listing.item_id)

    save_seen_ids(new_seen_ids)
    logger.info("Scan complete. %s new deal(s) sent.", deals_found)


if __name__ == "__main__":
    run()
