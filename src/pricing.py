import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger("lc_card_scanner")

API_BASE_URL = "https://www.pokemonpricetracker.com/api/v2"
PARSE_TITLE_ENDPOINT = f"{API_BASE_URL}/parse-title"

MAX_RETRIES = 2  # keep this low -- pricing is a nice-to-have, not worth blocking the scan over
RETRY_BACKOFF_SECONDS = 2

# The API returns a ranked list of candidate matches, not a single
# guaranteed-correct answer -- in testing, unrelated cards (different sets
# entirely) regularly showed up alongside the right one. We only trust a
# match if its own setName is actually "Legendary Collection", rather than
# blindly taking the top-ranked match by matchScore.
_EXPECTED_SET_NAME = "legendary collection"


@dataclass
class PriceLookupResult:
    """Result of looking up market price for a listing title.

    `market_price` is None whenever we can't confidently provide one --
    missing API key, no match in the expected set, API error, or rate
    limit hit. This is the expected/normal case for some listings, not
    just an error path, so callers should treat None as "no comparison
    available" rather than a failure to handle specially.
    """
    market_price: Optional[float]
    matched_card_name: Optional[str] = None
    matched_set_name: Optional[str] = None


def get_market_price(title: str) -> PriceLookupResult:
    """Look up the market price for a card based on a raw eBay listing title.

    Never raises. If the API key is missing, the request fails, or no
    match with setName == "Legendary Collection" is found among the
    candidates returned, returns a PriceLookupResult with
    market_price=None so the caller can simply omit the comparison.
    """
    api_key = os.getenv("POKEMON_PRICE_TRACKER_API_KEY")
    if not api_key:
        logger.debug("No POKEMON_PRICE_TRACKER_API_KEY set, skipping price lookup")
        return PriceLookupResult(market_price=None)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {"title": title}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.post(PARSE_TITLE_ENDPOINT, headers=headers, json=body, timeout=10)

            if r.status_code == 429:
                wait = RETRY_BACKOFF_SECONDS * attempt
                logger.warning("PokemonPriceTracker rate-limited us, retrying in %ss", wait)
                time.sleep(wait)
                continue

            if r.status_code == 401:
                logger.error("PokemonPriceTracker API key rejected (401) -- check the secret value")
                return PriceLookupResult(market_price=None)

            r.raise_for_status()
            data = r.json()
            return _parse_response(data, title)

        except requests.RequestException as e:
            logger.warning("PokemonPriceTracker lookup failed (attempt %s/%s) for %r: %s",
                            attempt, MAX_RETRIES, title, e)
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
        except (ValueError, KeyError) as e:
            # Malformed/unexpected JSON shape -- log and treat as no match,
            # rather than crashing the scan over a pricing nice-to-have.
            logger.warning("Unexpected PokemonPriceTracker response shape for %r: %s", title, e)
            return PriceLookupResult(market_price=None)

    logger.warning("Giving up on price lookup for %r after %s attempts", title, MAX_RETRIES)
    return PriceLookupResult(market_price=None)


def _parse_response(response_json: dict, title: str) -> PriceLookupResult:
    matches = (response_json.get("data") or {}).get("matches") or []

    if not matches:
        logger.info("No price matches returned for %r", title)
        return PriceLookupResult(market_price=None)

    # Matches are ranked by matchScore but NOT guaranteed correct -- in
    # testing, unrelated cards from other sets showed up ranked highly
    # alongside the right one. Only trust a match whose own setName is
    # actually Legendary Collection, scanning in ranked order so we take
    # the best candidate that clears that bar (not necessarily matches[0]).
    for match in matches:
        set_name = (match.get("setName") or "").strip().lower()
        if set_name != _EXPECTED_SET_NAME:
            continue

        market = (match.get("prices") or {}).get("market")
        if market is None:
            continue

        try:
            market_price = float(market)
        except (TypeError, ValueError):
            continue

        return PriceLookupResult(
            market_price=market_price,
            matched_card_name=match.get("name"),
            matched_set_name=match.get("setName"),
        )

    logger.info("No Legendary Collection match among %s candidate(s) for %r", len(matches), title)
    return PriceLookupResult(market_price=None)
