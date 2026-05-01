"""
Agent 4 — Genuineness Filter
Scores each result for authenticity using heuristics + Gemini reasoning.
"""

import logging
import json
import google.generativeai as genai

from models.schemas import ProductResult, RecognizedProduct
from config.settings import get_settings

logger = logging.getLogger(__name__)

FILTER_PROMPT = """You are a product authenticity analyst for an Indian e-commerce platform.
Given a product listing, score its genuineness from 0.0 to 1.0.
Return ONLY JSON:
{
  "score": 0.95,
  "flags": ["price seems low for brand"],
  "recommendation": "safe|caution|avoid"
}
Return JSON only, no markdown."""

PLATFORM_BASE_SCORES = {"amazon": 0.85, "flipkart": 0.82, "croma": 0.95, "myntra": 0.88, "zepto": 0.80}
SUSPICION_PRICE_RATIO = 0.4


class FilterAgent:
    def __init__(self):
        settings = get_settings()
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=FILTER_PROMPT,
        )

    async def filter(self, results: list[ProductResult], recognized: RecognizedProduct) -> list[ProductResult]:
        if not results:
            return results
        prices = [r.price for r in results if r.price > 0]
        median_price = sorted(prices)[len(prices) // 2] if prices else 0
        scored = []
        for result in results:
            score = await self._score_result(result, recognized, median_price)
            result.genuineness_score = score
            if score >= 0.5:
                scored.append(result)
            else:
                logger.warning("Filtered out | platform=%s | score=%.2f", result.platform, score)
        scored.sort(key=lambda r: (-r.genuineness_score, r.final_price or r.price))
        return scored

    async def _score_result(self, result: ProductResult, recognized: RecognizedProduct, median_price: float) -> float:
        base = PLATFORM_BASE_SCORES.get(result.platform, 0.70)
        if median_price > 0 and result.price < median_price * SUSPICION_PRICE_RATIO:
            base -= 0.3
        if result.review_count is not None and result.review_count < 10:
            base -= 0.1
        if result.rating and result.rating >= 4.0 and (result.review_count or 0) > 100:
            base += 0.05
        if recognized.brand and recognized.brand.lower() not in result.title.lower():
            base -= 0.15
        if 0.4 <= base <= 0.75:
            base = await self._gemini_score(result, recognized, median_price, base)
        return min(1.0, max(0.0, base))

    async def _gemini_score(self, result: ProductResult, recognized: RecognizedProduct,
                             median_price: float, heuristic_score: float) -> float:
        prompt = (
            f"Product: {recognized.normalized_name}\n"
            f"Expected price: ₹{median_price * 0.7:.0f}–₹{median_price * 1.3:.0f}\n"
            f"Platform: {result.platform_name}\n"
            f"Title: {result.title}\n"
            f"Price: ₹{result.price:.0f}\n"
            f"Rating: {result.rating or 'N/A'} ({result.review_count or 0} reviews)\n"
        )
        import asyncio
        response = None
        for attempt in range(5):
            try:
                response = await self.model.generate_content_async(prompt)
                break
            except Exception as e:
                msg = str(e)
                if ("429" in msg or "exhausted" in msg.lower()) and attempt < 4:
                    delay = 2 ** attempt
                    logger.warning("Gemini filter rate limited. Retrying in %ds...", delay)
                    await asyncio.sleep(delay)
                else:
                    logger.warning("Gemini filter scoring failed: %s", e)
                    return heuristic_score
                    
        if not response:
            return heuristic_score

        try:
            raw = response.text.strip().lstrip("```json").rstrip("```").strip()
            # fallback if multiple markdown blocks are found, etc.
            if "{" in raw and "}" in raw:
                start = raw.find("{")
                end = raw.rfind("}") + 1
                raw = raw[start:end]
            
            import json
            data = json.loads(raw)
            claude_score = float(data.get("score", heuristic_score))
            return (heuristic_score + claude_score) / 2
        except Exception as e:
            logger.warning("Gemini filter parsing failed: %s | raw: %s", e, raw[:100] if response else "none")
            return heuristic_score
