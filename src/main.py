import yaml
from ebay.client import search
from dotenv import load_dotenv

load_dotenv()

with open("src/config/cards.yaml") as f:
    cards = yaml.safe_load(f)["cards"]

for card in cards:
    results = search(card["query"])
    for item in results:
        price = float(item["currentBidPrice"]["value"])
        if price <= card["max_price"]:
            print(f"[DEAL] {item['title']} — ${price}")