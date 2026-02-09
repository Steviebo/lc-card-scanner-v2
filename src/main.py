import yaml
from ebay.client import search
from dotenv import load_dotenv
from discord import send_deal

load_dotenv()

with open("src/config/cards.yaml") as f:
    cards = yaml.safe_load(f)["cards"]

for card in cards:
    results = search(card["query"])
    for item in results.get("itemSummaries", []):
        # Normalize price
        price = item.get("price", {}).get("value")
        if not price:
            price = "N/A"

        if "reverse" not in item.get("title", "").lower():
            print("Skipping because not reverse holo")
            continue
        
        image_url = None
        if item.get("image"):
            image_url = item["image"].get("imageUrl")

        # Get buying options
        buying_options = ", ".join(item.get("buyingOptions", [])) or "UNKNOWN"
        if price != "N/A" and float(price) < card["max_price"]:
            print(f"[DEAL] {item['title']} — ${price} — {buying_options} — {item['itemWebUrl']}")
            if image_url:
                print(f"Image: {image_url}")
            print("\n")
            send_deal(
                title=item["title"],
                price=price,
                url=item["itemWebUrl"],
                image_url=image_url
            )