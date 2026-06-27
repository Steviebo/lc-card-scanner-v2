import json
import logging
import os
import re
from pathlib import Path
from typing import Set

from ebay.models import Listing

logger = logging.getLogger("lc_card_scanner")

# Anchored to this file's directory (src/) by default, so behavior is
# consistent whether invoked as `python src/main.py` from the repo root
# or `python main.py` from inside src/. Override with SEEN_ITEMS_PATH
# for CI/cache setups that want it somewhere specific.
_DEFAULT_SEEN_FILENAME = Path(__file__).parent.parent / "seen_items.json"
DEFAULT_SEEN_PATH = Path(os.getenv("SEEN_ITEMS_PATH", str(_DEFAULT_SEEN_FILENAME)))

# Catches "reverse", "rev holo", "RH" as a standalone token (e.g. "Charizard RH")
_REVERSE_HOLO_HINTS = ("reverse", "rev holo", "rev. holo")

# The 2002 WOTC Legendary Collection set has 110 cards total, so every
# genuine card number in that set is "<n>/110". This is a much more
# reliable signal than matching the word "Legendary," which also appears
# in unrelated sets (Legendary Treasures, Legendary Shiny Collection,
# generic "Legendary set" listings, etc.) that flood search results.
_LC_CARD_NUMBER_RE = re.compile(r"\b\d{1,3}\s*/\s*110\b")

# Other sets that share the word "Legendary" (or "Collection") with the
# real Legendary Collection, seen flooding search results in practice.
# Title containing any of these is treated as a hard exclusion, even if
# the /110 pattern or "reverse holo" also matches -- these phrases don't
# appear in genuine Legendary Collection listings.
_IMPOSTOR_SET_HINTS = (
    "legendary treasures",
    "shiny collection",
    "treasures reverse",
)


def is_reverse_holo(listing: Listing) -> bool:
    """Best-effort check that a listing title indicates a reverse holo.

    This is a backstop on top of the API-side itemSpecifics filter, not a
    replacement for it -- sellers are inconsistent about how they title
    listings, so this intentionally matches a few common phrasings.
    """
    title = listing.title.lower()
    if any(hint in title for hint in _REVERSE_HOLO_HINTS):
        return True
    # Match "RH" as a standalone word/token, not as a substring of other words
    tokens = title.replace("/", " ").replace("-", " ").split()
    return "rh" in tokens


# Exact phrase match for the genuine set name, allowing "LegendaryCollection"
# (no space) and "Legendary Col Collection" typos seen in real listings.
_LC_PHRASE_RE = re.compile(r"legendary\s*col(?:lection)?\b.{0,20}?collection|legendary\s*collection")


def is_legendary_collection(listing: Listing) -> bool:
    """Check that a listing is actually from the 2002 Legendary Collection
    set, not just a title that happens to contain the word "Legendary."

    Card searches for "Legendary Collection" pull in a lot of unrelated
    sets (Legendary Treasures, Legendary Shiny Collection, etc.) because
    eBay's keyword search isn't an exact-phrase match. This accepts a
    listing if EITHER of two positive signals is present:
      1. The set's distinctive "<n>/110" numbering, or
      2. The literal phrase "Legendary Collection" (not just "Legendary")
    ...and always rejects titles matching a known impostor set, even if
    one of the positive signals above also happens to match.
    """
    title = listing.title.lower()

    if any(hint in title for hint in _IMPOSTOR_SET_HINTS):
        return False

    if _LC_CARD_NUMBER_RE.search(title):
        return True

    return bool(_LC_PHRASE_RE.search(title))


def load_seen_ids(path: Path = DEFAULT_SEEN_PATH) -> Set[str]:
    """Load the set of eBay item IDs we've already alerted on."""
    if not path.exists():
        return set()
    try:
        with open(path) as f:
            data = json.load(f)
        return set(data.get("seen_ids", []))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read seen items file (%s), starting fresh: %s", path, e)
        return set()


def save_seen_ids(seen_ids: Set[str], path: Path = DEFAULT_SEEN_PATH) -> None:
    """Persist the set of seen item IDs, atomically (write-then-rename)."""
    tmp_path = path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w") as f:
            json.dump({"seen_ids": sorted(seen_ids)}, f, indent=2)
        tmp_path.replace(path)
    except OSError as e:
        logger.error("Failed to save seen items file (%s): %s", path, e)
