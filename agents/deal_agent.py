"""
Agent 3 — Deal & Coupon Agent
Fetches active coupon codes. Uses Gemini to extract coupons from HTML.
"""

import asyncio
import logging
import json
import google.generativeai as genai
import httpx

from models.schemas import ProductResult, RecognizedProduct
from config.settings import get_settings, COUPON_SOURCES

logger = logging.getLogger(__name__)

COUPON_EXTRACTION_PROMPT = """You are a coupon code extractor for Indian e-commerce.
Given HTML content, extract valid coupon codes.
Return ONLY a JSON array:
[{"code": "CODE", "discount_type": "percent|flat", "discount_value": 10, "min_order": 500, "description": "...", "expiry": "date or null"}]
Return empty array [] if none found. Return JSON only, no markdown."""

KNOWN_COUPONS: dict[str, list[dict]] = {
    "amazon": [
        {"code": "SAVE10", "discount_type": "percent", "discount_value": 10, "min_order": 1000},
        {"code": "HDFC5", "discount_type": "percent", "discount_value": 5, "min_order": 5000},
        {"code": "SBIEMI", "discount_type": "flat", "discount_value": 500, "min_order": 10000},
    ],
    "flipkart": [
        {"code": "FKFIRST", "discount_type": "percent", "discount_value": 10, "min_order": 1000},
        {"code": "AXISBANK", "discount_type": "flat", "discount_value": 250, "min_order": 3000},
    ],
    "croma": [
        {"code": "CROMA500", "discount_type": "flat", "discount_value": 500, "min_order": 5000},
        {"code": "CROMAFEST", "discount_type": "percent", "discount_value": 8, "min_order": 2000},
    ],
    "zepto": [{"code": "ZEPTO100", "discount_type": "flat", "discount_value": 100, "min_order": 500}],
    "myntra": [
        {"code": "MYNTRA200", "discount_type": "flat", "discount_value": 200, "min_order": 1000},
        {"code": "STYLE20", "discount_type": "percent", "discount_value": 20, "min_order": 800},
    ],
}


class DealAgent:
    def __init__(self):
        settings = get_settings()
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=COUPON_EXTRACTION_PROMPT,
        )

    async def enrich(self, results: list[ProductResult], recognized: RecognizedProduct) -> list[ProductResult]:
        tasks = [self._enrich_result(r, recognized) for r in results]
        enriched = await asyncio.gather(*tasks, return_exceptions=True)
        out = []
        for i, r in enumerate(enriched):
            if isinstance(r, Exception):
                logger.error("Deal agent error for result %d: %s", i, r)
                out.append(results[i])
            else:
                out.append(r)
        out.sort(key=lambda r: r.final_price or r.price)
        return out

    async def _enrich_result(self, result: ProductResult, recognized: RecognizedProduct) -> ProductResult:
        coupons = await self._fetch_coupons(result.platform, recognized.normalized_name)
        if not coupons:
            return result
        best_coupon, best_saving = None, 0.0
        for coupon in coupons:
            if result.price < coupon.get("min_order", 0):
                continue
            saving = (result.price * coupon["discount_value"] / 100
                      if coupon["discount_type"] == "percent"
                      else float(coupon["discount_value"]))
            if saving > best_saving:
                best_saving = saving
                best_coupon = coupon
        if best_coupon:
            result.coupon_code = best_coupon["code"]
            result.coupon_discount = best_saving
            result.final_price = max(0, result.price - best_saving)
        return result

    async def _fetch_coupons(self, platform: str, product_name: str) -> list[dict]:
        try:
            live = await self._scrape_coupon_sites(platform, product_name)
            if live:
                return live
        except Exception as e:
            logger.warning("Live coupon scrape failed: %s", e)
        return KNOWN_COUPONS.get(platform, [])

    async def _scrape_coupon_sites(self, platform: str, product: str) -> list[dict]:
        url = f"https://www.coupondunia.in/{platform}"
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ShopMind/1.0)", "Accept": "text/html"})
                if resp.status_code != 200:
                    return []
                html = resp.text[:12000]
        except Exception as e:
            logger.debug("Coupon site fetch failed: %s", e)
            return []
        try:
            response = self.model.generate_content(f"Store: {platform}\nProduct: {product}\n\nHTML:\n{html}")
            raw = response.text.strip().lstrip("```json").rstrip("```").strip()
            return json.loads(raw)
        except Exception:
            return []
