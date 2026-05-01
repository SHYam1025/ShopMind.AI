"""
Agent 1 — Product Recognition
Uses Gemini to extract normalized product name, brand, model, specs.
"""

import json
import logging
import base64
import google.generativeai as genai

from models.schemas import RecognizedProduct
from config.settings import get_settings

logger = logging.getLogger(__name__)

RECOGNITION_PROMPT = """You are a product identification expert for an Indian e-commerce search engine.
Analyze the user's input and extract structured product information.
Return ONLY a valid JSON object with no extra text:
{
  "normalized_name": "Brand Model full name",
  "brand": "Brand name or null",
  "model": "Model number/name or null",
  "category": "electronics|clothing|footwear|home|beauty|sports|other",
  "key_specs": ["spec1", "spec2"],
  "search_terms": [
    "term optimized for Amazon India",
    "term optimized for Flipkart",
    "term optimized for Croma",
    "term optimized for Zepto",
    "term optimized for Myntra"
  ],
  "confidence": 0.95
}
Return JSON only. No markdown. No explanation."""


class RecognitionAgent:
    def __init__(self):
        settings = get_settings()
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=RECOGNITION_PROMPT,
        )

    async def recognize(self, text: str | None = None, image_base64: str | None = None) -> RecognizedProduct:
        logger.info("Recognition agent | text=%s | has_image=%s", text, bool(image_base64))
        content = self._build_content(text, image_base64)
        
        fallback = RecognizedProduct(
            raw_query=text or "unknown",
            normalized_name=text or "unknown",
            search_terms=[text or ""] * 5,
            confidence=0.3,
        )

        import asyncio
        response = None
        for attempt in range(5):
            try:
                response = await self.model.generate_content_async(content)
                break
            except Exception as e:
                msg = str(e)
                if ("429" in msg or "exhausted" in msg.lower()) and attempt < 4:
                    delay = 2 ** attempt
                    logger.warning("Gemini recognition rate limited. Retrying in %ds...", delay)
                    await asyncio.sleep(delay)
                else:
                    logger.error("Gemini recognition error: %s", e)
                    return fallback

        if not response:
            return fallback

        try:
            raw = response.text.strip()
        except Exception as e:
            logger.error("Gemini text extraction error: %s", e)
            return fallback

        # Strip markdown fences
        if "```" in raw:
            parts = raw.split("```")
            for part in parts:
                if "{" in part:
                    raw = part.lstrip("json").strip()
                    break

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error("Recognition JSON parse error: %s | raw=%s", e, raw[:200])
            # Try to extract JSON from the response
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(raw[start:end])
                except Exception:
                    return RecognizedProduct(
                        raw_query=text or "unknown",
                        normalized_name=text or "unknown",
                        search_terms=[text or ""] * 5,
                        confidence=0.3,
                    )
            else:
                return RecognizedProduct(
                    raw_query=text or "unknown",
                    normalized_name=text or "unknown",
                    search_terms=[text or ""] * 5,
                    confidence=0.3,
                )

        logger.info("Recognized: %s (confidence=%.2f)", data.get("normalized_name"), data.get("confidence", 0.8))
        raw_search_terms = data.get("search_terms", [text or ""] * 5)
        clean_search_terms = [t if isinstance(t, str) else (text or "") for t in raw_search_terms]

        return RecognizedProduct(
            raw_query=text or "image_input",
            normalized_name=data.get("normalized_name", text or ""),
            brand=data.get("brand"),
            model=data.get("model"),
            category=data.get("category"),
            key_specs=data.get("key_specs", []),
            search_terms=clean_search_terms,
            confidence=float(data.get("confidence", 0.8)),
        )

    def _build_content(self, text: str | None, image_base64: str | None):
        parts = []
        if image_base64:
            media_type = self._detect_media_type(image_base64)
            parts.append({"inline_data": {"mime_type": media_type, "data": image_base64}})
            parts.append({"text": f"Additional context: {text}" if text else "Identify this product for Indian e-commerce search. What is this product?"})
        else:
            parts.append({"text": text or ""})
        return parts

    def _detect_media_type(self, b64: str) -> str:
        try:
            header = base64.b64decode(b64[:16])
            if header[:4] in (b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1"):
                return "image/jpeg"
            if header[:8] == b"\x89PNG\r\n\x1a\n":
                return "image/png"
        except Exception:
            pass
        return "image/jpeg"
