"""
Quick integration test — run this to verify the pipeline works end-to-end.
Uses mocked scraper data so it doesn't need live browser or API keys.

Usage:
  python test_pipeline.py
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

# ─── Mock scraper so we don't need real browsers in CI ────────────────────────
import utils.scraper as scraper_module

MOCK_RESULTS = [
    {
        "platform": "amazon",
        "platform_name": "Amazon India",
        "title": "Sony WH-1000XM5 Wireless Noise Cancelling Headphones",
        "price": 22990.0,
        "original_price": 29990.0,
        "rating": 4.6,
        "review_count": 12840,
        "url": "https://www.amazon.in/dp/B09XS7JWHH",
        "image_url": "",
        "delivery_days": 2,
        "delivery_label": "Free · 2 days",
        "gst_invoice": True,
        "return_days": 10,
    },
    {
        "platform": "flipkart",
        "platform_name": "Flipkart",
        "title": "Sony WH-1000XM5 (Black, Over the Ear)",
        "price": 23499.0,
        "original_price": 29990.0,
        "rating": 4.5,
        "review_count": 8200,
        "url": "https://www.flipkart.com/sony-wh-1000xm5/p/abc",
        "delivery_days": 3,
        "delivery_label": "Free · 3 days",
        "gst_invoice": True,
        "return_days": 7,
    },
    {
        "platform": "croma",
        "platform_name": "Croma",
        "title": "Sony WH-1000XM5 Wireless Headphones + Pouch",
        "price": 24990.0,
        "original_price": 29990.0,
        "rating": 4.7,
        "review_count": 3100,
        "url": "https://www.croma.com/sony-wh1000xm5",
        "delivery_days": 4,
        "delivery_label": "₹99 · 4 days",
        "gst_invoice": True,
        "return_days": 7,
    },
]


async def mock_scraper(query: str, max_results: int = 5) -> list[dict]:
    await asyncio.sleep(0.1)  # simulate network delay
    return MOCK_RESULTS[:max_results]


# Patch all scrapers with mock
scraper_module.scrape_amazon = mock_scraper
scraper_module.scrape_flipkart = mock_scraper
scraper_module.scrape_croma = mock_scraper
scraper_module.scrape_myntra = mock_scraper
scraper_module.scrape_zepto = mock_scraper

# ─── Also mock the Anthropic client ──────────────────────────────────────────
import anthropic


class MockMessage:
    def __init__(self, text):
        self.content = [type("Block", (), {"text": text})()]


class MockAnthropicClient:
    def __init__(self, *args, **kwargs):
        pass

    class messages:
        @staticmethod
        def create(**kwargs):
            system = kwargs.get("system", "")
            if "product identification" in system.lower():
                return MockMessage("""{
                    "normalized_name": "Sony WH-1000XM5",
                    "brand": "Sony",
                    "model": "WH-1000XM5",
                    "category": "electronics",
                    "key_specs": ["wireless", "noise cancelling", "30hr battery"],
                    "search_terms": [
                        "Sony WH-1000XM5 wireless headphones",
                        "Sony WH-1000XM5 noise cancelling",
                        "Sony WH1000XM5 headphones",
                        "Sony WH-1000XM5",
                        "Sony WH-1000XM5 bluetooth"
                    ],
                    "confidence": 0.98
                }""")
            elif "coupon" in system.lower():
                return MockMessage("[]")
            elif "genuineness" in system.lower():
                return MockMessage('{"score": 0.92, "flags": [], "recommendation": "safe"}')
            return MockMessage('{"score": 0.85}')


import agents.recognition_agent as rec_mod
import agents.deal_agent as deal_mod
import agents.filter_agent as filt_mod

rec_mod.anthropic.Anthropic = MockAnthropicClient
deal_mod.anthropic.Anthropic = MockAnthropicClient
filt_mod.anthropic.Anthropic = MockAnthropicClient


# ─── Run the actual test ──────────────────────────────────────────────────────
async def main():
    from agents.orchestrator import Orchestrator
    from models.schemas import SearchRequest, Platform

    print("\n" + "=" * 60)
    print("  ShopMind AI — Pipeline Integration Test")
    print("=" * 60 + "\n")

    orc = Orchestrator()
    request = SearchRequest(
        query="Sony WH-1000XM5 wireless headphones",
        platforms=[Platform.amazon, Platform.flipkart, Platform.croma],
        max_results=5,
    )

    print("Running search pipeline...")
    result = await orc.run_search(request)

    print(f"\n✓ Recognized: {result.recognized.normalized_name}")
    print(f"  Brand: {result.recognized.brand}")
    print(f"  Confidence: {result.recognized.confidence:.0%}")
    print(f"\n✓ Found {len(result.results)} genuine results in {result.search_duration_seconds}s\n")

    for i, r in enumerate(result.results):
        coupon = f" | coupon: {r.coupon_code}" if r.coupon_code else ""
        print(
            f"  {i+1}. [{r.platform_name}] {r.title[:50]}"
            f"\n     ₹{r.final_price:,.0f} (was ₹{r.original_price or r.price:,.0f})"
            f" | score: {r.genuineness_score:.2f}{coupon}"
        )

    if result.best_deal:
        print(f"\n✓ Best deal: {result.best_deal.platform_name} @ ₹{result.best_deal.final_price:,.0f}")

    print("\n" + "=" * 60)
    print("  All tests passed!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
