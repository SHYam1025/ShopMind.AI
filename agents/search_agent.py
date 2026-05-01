"""
Agent 2 — Multi-Platform Search
Runs all platform scrapers in parallel using asyncio.gather.
Merges results and sorts by price.
"""

import asyncio
import logging
from typing import Callable

from models.schemas import RecognizedProduct, ProductResult
from utils.scraper import (
    scrape_amazon,
    scrape_flipkart,
    scrape_croma,
    scrape_myntra,
    scrape_zepto,
)
from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# Map platform name → scraper function
SCRAPERS: dict[str, Callable] = {
    "amazon": scrape_amazon,
    "flipkart": scrape_flipkart,
    "croma": scrape_croma,
    "myntra": scrape_myntra,
    "zepto": scrape_zepto,
}


class SearchAgent:
    def __init__(self):
        self.max_per_platform = settings.max_search_results_per_platform

    async def search(
        self,
        recognized: RecognizedProduct,
        platforms: list[str] | None = None,
        status_callback: Callable | None = None,
    ) -> list[ProductResult]:
        """
        Run all platform searches in parallel.
        status_callback(platform, status) is called as each platform completes.
        """
        if platforms is None:
            platforms = list(SCRAPERS.keys())

        # Build per-platform query (recognition agent generated optimized terms)
        platform_list = list(SCRAPERS.keys())
        search_terms = recognized.search_terms

        tasks = []
        for i, platform in enumerate(platforms):
            if platform not in SCRAPERS:
                continue
            # Use platform-specific search term if available, else normalized name
            term = (
                search_terms[platform_list.index(platform)]
                if platform_list.index(platform) < len(search_terms)
                else recognized.normalized_name
            )
            tasks.append(
                self._search_platform(
                    platform=platform,
                    query=term,
                    status_callback=status_callback,
                )
            )

        results_nested = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: list[ProductResult] = []
        for batch in results_nested:
            if isinstance(batch, Exception):
                logger.error("Search task error: %s", batch)
                continue
            all_results.extend(batch)

        # Sort by final_price (after coupon) or price
        all_results.sort(key=lambda r: r.final_price or r.price)

        logger.info("Search complete | total results=%d", len(all_results))
        return all_results

    async def _search_platform(
        self,
        platform: str,
        query: str,
        status_callback: Callable | None,
    ) -> list[ProductResult]:
        """Run one platform scraper and convert raw dicts → ProductResult."""
        logger.info("Searching %s | query=%s", platform, query)

        try:
            raw_results = await SCRAPERS[platform](query, self.max_per_platform)
        except Exception as e:
            logger.error("Platform %s search failed: %s", platform, e)
            if status_callback:
                await status_callback(platform, "error")
            return []

        if status_callback:
            await status_callback(platform, "done")

        models = []
        for r in raw_results:
            try:
                # Calculate discount if original price is available
                discount = None
                if r.get("original_price") and r["original_price"] > r["price"]:
                    discount = round((r["original_price"] - r["price"]) / r["original_price"] * 100)

                models.append(
                    ProductResult(
                        platform=r["platform"],
                        platform_name=r["platform_name"],
                        title=r["title"],
                        price=r["price"],
                        original_price=r.get("original_price"),
                        discount_percent=discount,
                        rating=r.get("rating"),
                        review_count=r.get("review_count"),
                        url=r["url"],
                        image_url=r.get("image_url"),
                        delivery_days=r.get("delivery_days"),
                        delivery_label=r.get("delivery_label", ""),
                        gst_invoice=r.get("gst_invoice", True),
                        return_days=r.get("return_days", 7),
                        final_price=r["price"],  # updated by deal agent
                    )
                )
            except Exception as e:
                logger.debug("Result model build error: %s | raw=%s", e, r)

        return models
