import json
import logging
import os
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
