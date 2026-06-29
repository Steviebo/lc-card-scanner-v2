from dataclasses import dataclass
from typing import Optional


@dataclass
class Listing:
    """A normalized eBay listing, safe to build even from incomplete API data."""

    item_id: str
    title: str
    url: str
    price: Optional[float]
    currency: Optional[str]
    buying_options: str
    image_url: Optional[str]
    market_price: Optional[float] = None  # populated later via pricing.get_market_price(), if available

    @classmethod
    def from_item_summary(cls, item: dict) -> "Listing":
        """Build a Listing from a raw eBay Browse API itemSummary dict.

        Uses .get() throughout so a missing field never crashes the scan --
        worst case we end up with None/defaults for that field.
        """
        price_block = item.get("price") or {}
        raw_price = price_block.get("value")
        price = None
        if raw_price is not None:
            try:
                price = float(raw_price)
            except (TypeError, ValueError):
                price = None

        image_url = None
        if item.get("image"):
            image_url = item["image"].get("imageUrl")

        return cls(
            item_id=item.get("itemId", ""),
            title=item.get("title", "Untitled listing"),
            url=item.get("itemWebUrl", ""),
            price=price,
            currency=price_block.get("currency"),
            buying_options=", ".join(item.get("buyingOptions", [])) or "UNKNOWN",
            image_url=image_url,
        )
