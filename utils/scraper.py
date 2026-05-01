"""
Scraper utilities — Playwright-based browser automation.
Robust selectors with multiple fallbacks per platform.
"""

import asyncio
import logging
import re
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext

from config.settings import get_settings, PLATFORMS

logger = logging.getLogger(__name__)
settings = get_settings()


class BrowserPool:
    _browser: Optional[Browser] = None
    _playwright = None

    @classmethod
    async def get_browser(cls) -> Browser:
        if cls._browser is None or not cls._browser.is_connected():
            cls._playwright = await async_playwright().start()
            cls._browser = await cls._playwright.chromium.launch(
                headless=settings.headless,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-web-security",
                ],
            )
            logger.info("Chromium browser launched")
        return cls._browser

    @classmethod
    async def close(cls):
        if cls._browser:
            await cls._browser.close()
        if cls._playwright:
            await cls._playwright.stop()


async def new_context() -> BrowserContext:
    browser = await BrowserPool.get_browser()
    ctx = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        viewport={"width": 1440, "height": 900},
        extra_http_headers={
            "Accept-Language": "en-IN,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
        },
    )
    # Only block media/fonts, keep images for product detection
    await ctx.route(
        "**/*",
        lambda route: route.abort()
        if route.request.resource_type in ("media", "font")
        else route.continue_(),
    )
    return ctx


def _parse_price(text: str) -> float:
    """Extract numeric price from strings like '₹28,999' or '28999.00'"""
    if not text:
        return 0.0
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


async def scrape_amazon(query: str, max_results: int = 5) -> list[dict]:
    if not query:
        return []
    url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
    ctx = await new_context()
    page = await ctx.new_page()
    results = []
    try:
        await page.goto(url, timeout=25000, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Multiple selector strategies
        items = []
        for selector in [
            '[data-component-type="s-search-result"]',
            '[data-asin]:not([data-asin=""])',
            '.s-result-item[data-asin]',
        ]:
            items = await page.query_selector_all(selector)
            if items:
                break

        for item in items[:max_results]:
            try:
                # Title — multiple fallbacks
                title_el = await item.query_selector("h2 a span, h2 span, .a-size-medium")
                title = (await title_el.inner_text()).strip() if title_el else ""
                if not title or len(title) < 5:
                    continue

                # Price
                price_el = await item.query_selector(".a-price-whole, .a-price .a-offscreen")
                price_text = (await price_el.inner_text()).strip() if price_el else "0"
                price = _parse_price(price_text)

                # Link
                link_el = await item.query_selector("h2 a, a.a-link-normal")
                href = await link_el.get_attribute("href") if link_el else ""
                url_full = f"https://www.amazon.in{href}" if href and href.startswith("/") else href

                # Rating
                rating_el = await item.query_selector(".a-icon-star-small .a-icon-alt, .a-icon-alt")
                rating_text = (await rating_el.inner_text()).strip() if rating_el else ""
                rating = float(rating_text.split()[0]) if rating_text and rating_text[0].isdigit() else None

                # Review count
                review_el = await item.query_selector(".a-size-small .a-size-base, [aria-label*='stars'] + span")
                review_text = (await review_el.inner_text()).strip() if review_el else "0"
                review_count = int(re.sub(r"[^\d]", "", review_text)) if review_text else 0

                # Image
                img_el = await item.query_selector("img.s-image")
                img_url = await img_el.get_attribute("src") if img_el else None

                if price > 0 or url_full:
                    results.append({
                        "platform": "amazon",
                        "platform_name": "Amazon India",
                        "title": title,
                        "price": price or 999,
                        "rating": rating,
                        "review_count": review_count or None,
                        "url": url_full or url,
                        "image_url": img_url,
                        "delivery_days": 2,
                        "delivery_label": "Free delivery",
                        "gst_invoice": True,
                        "return_days": 10,
                    })
            except Exception as e:
                logger.debug("Amazon item parse error: %s", e)

        logger.info("Amazon scraped %d results for '%s'", len(results), query)
    except Exception as e:
        logger.warning("scrape_amazon failed: %s", e)
    finally:
        await page.close()
        await ctx.close()
    return results


async def scrape_flipkart(query: str, max_results: int = 5) -> list[dict]:
    if not query:
        return []
    url = f"https://www.flipkart.com/search?q={query.replace(' ', '+')}&otracker=search"
    ctx = await new_context()
    page = await ctx.new_page()
    results = []
    try:
        # Dismiss login popup
        await page.goto(url, timeout=25000, wait_until="domcontentloaded")
        await asyncio.sleep(1.5)
        try:
            close_btn = await page.query_selector('button._2KpZ6l._2doB4z._3AWRsL, button[class*="close"]')
            if close_btn:
                await close_btn.click()
        except Exception:
            pass

        # Multiple selector strategies for Flipkart
        items = []
        for selector in [
            "._1AtVbE",
            "._13oc-S",
            '[data-id]',
            "._2kHMtA",
            ".CXW8mj",
            "._75nlfW",
        ]:
            items = await page.query_selector_all(selector)
            valid = [i for i in items if await i.query_selector("a")]
            if len(valid) >= 2:
                items = valid
                break

        for item in items[:max_results * 2]:
            try:
                # Title
                title_el = await item.query_selector(
                    "._4rR01T, .s1Q9rs, .IRpwTa, ._2WkVRV, a[title], .KzDlHZ"
                )
                title = (await title_el.inner_text()).strip() if title_el else ""
                if not title or len(title) < 5:
                    continue

                # Price
                price_el = await item.query_selector("._30jeq3, ._1_WHN1, .Nx9bqj")
                price_text = (await price_el.inner_text()).strip() if price_el else "0"
                price = _parse_price(price_text)

                # Original price
                orig_el = await item.query_selector("._3I9_wc, ._3auQ3N")
                orig_text = (await orig_el.inner_text()).strip() if orig_el else ""
                orig_price = _parse_price(orig_text) if orig_text else None

                # Link
                link_el = await item.query_selector("a._1fQZEK, a.s1Q9rs, a[href*='/p/']")
                href = await link_el.get_attribute("href") if link_el else ""
                url_full = f"https://www.flipkart.com{href}" if href and href.startswith("/") else href

                # Rating
                rating_el = await item.query_selector("._3LWZlK, .XQDdHH")
                rating_text = (await rating_el.inner_text()).strip() if rating_el else ""
                rating = float(rating_text) if rating_text and rating_text.replace(".", "").isdigit() else None

                if title:
                    results.append({
                        "platform": "flipkart",
                        "platform_name": "Flipkart",
                        "title": title,
                        "price": price or 999,
                        "original_price": orig_price,
                        "rating": rating,
                        "url": url_full or url,
                        "delivery_days": 3,
                        "delivery_label": "Free delivery",
                        "gst_invoice": True,
                        "return_days": 7,
                    })
                    if len(results) >= max_results:
                        break
            except Exception as e:
                logger.debug("Flipkart item error: %s", e)

        logger.info("Flipkart scraped %d results for '%s'", len(results), query)
    except Exception as e:
        logger.warning("scrape_flipkart failed: %s", e)
    finally:
        await page.close()
        await ctx.close()
    return results


async def scrape_croma(query: str, max_results: int = 5) -> list[dict]:
    if not query:
        return []
    url = f"https://www.croma.com/searchB?q={query.replace(' ', '%20')}&inStockOnly=false"
    ctx = await new_context()
    page = await ctx.new_page()
    results = []
    try:
        await page.goto(url, timeout=25000, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        items = []
        for selector in [
            ".product-item",
            "li.product-item",
            '[class*="product-item"]',
            ".cp-card",
            'article[class*="product"]',
        ]:
            items = await page.query_selector_all(selector)
            if items:
                break

        for item in items[:max_results]:
            try:
                title_el = await item.query_selector(
                    "h3.product-title, .product-title a, h3 a, .cp-product-title"
                )
                title = (await title_el.inner_text()).strip() if title_el else ""
                if not title or len(title) < 5:
                    continue

                price_el = await item.query_selector(".amount, .new-price, .pdpPrice, [class*='price']")
                price_text = (await price_el.inner_text()).strip() if price_el else "0"
                price = _parse_price(price_text)

                link_el = await item.query_selector("a")
                href = await link_el.get_attribute("href") if link_el else ""
                url_full = f"https://www.croma.com{href}" if href and href.startswith("/") else href

                results.append({
                    "platform": "croma",
                    "platform_name": "Croma",
                    "title": title,
                    "price": price or 999,
                    "url": url_full or url,
                    "delivery_days": 4,
                    "delivery_label": "Free delivery",
                    "gst_invoice": True,
                    "return_days": 7,
                })
            except Exception as e:
                logger.debug("Croma item error: %s", e)

        logger.info("Croma scraped %d results for '%s'", len(results), query)
    except Exception as e:
        logger.warning("scrape_croma failed: %s", e)
    finally:
        await page.close()
        await ctx.close()
    return results


async def scrape_zepto(query: str, max_results: int = 5) -> list[dict]:
    if not query:
        return []
    url = f"https://www.zeptonow.com/search?query={query.replace(' ', '%20')}"
    ctx = await new_context()
    page = await ctx.new_page()
    results = []
    try:
        await page.goto(url, timeout=25000, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        items = []
        for selector in [
            "[data-testid='product-card']",
            "[data-testid='plp-product-card']",
            '.product-card',
            '[class*="ProductCard"]',
            'a[href*="/pn/"]',
        ]:
            items = await page.query_selector_all(selector)
            if items:
                break

        for item in items[:max_results]:
            try:
                title_el = await item.query_selector(
                    "[data-testid='product-card-name'], [data-testid='plp-product-name'], h4, h3, [class*='name']"
                )
                title = (await title_el.inner_text()).strip() if title_el else ""
                if not title or len(title) < 3:
                    continue

                price_el = await item.query_selector(
                    "[data-testid='product-card-price'], [class*='price'], [class*='Price']"
                )
                price_text = (await price_el.inner_text()).strip() if price_el else "0"
                price = _parse_price(price_text)

                link_el = await item.query_selector("a")
                href = await link_el.get_attribute("href") if link_el else ""
                url_full = f"https://www.zeptonow.com{href}" if href and href.startswith("/") else href

                results.append({
                    "platform": "zepto",
                    "platform_name": "Zepto",
                    "title": title,
                    "price": price or 99,
                    "url": url_full or url,
                    "delivery_days": 0,
                    "delivery_label": "10-minute delivery",
                    "gst_invoice": True,
                    "return_days": 2,
                })
            except Exception as e:
                logger.debug("Zepto item error: %s", e)

        logger.info("Zepto scraped %d results for '%s'", len(results), query)
    except Exception as e:
        logger.warning("scrape_zepto failed: %s", e)
    finally:
        await page.close()
        await ctx.close()
    return results


async def scrape_myntra(query: str, max_results: int = 5) -> list[dict]:
    if not query:
        return []
    # Myntra uses a different URL format — search via the search path
    search_query = query.replace(" ", "-").lower()
    url = f"https://www.myntra.com/search?rawQuery={query.replace(' ', '%20')}"
    ctx = await new_context()
    page = await ctx.new_page()
    results = []
    try:
        await page.goto(url, timeout=25000, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        items = []
        for selector in [
            ".product-base",
            "li.product-base",
            "[class*='product-base']",
            ".results-base li",
        ]:
            items = await page.query_selector_all(selector)
            if items:
                break

        for item in items[:max_results]:
            try:
                # Brand + product name
                brand_el = await item.query_selector(".product-brand, h3.product-brand")
                brand = (await brand_el.inner_text()).strip() if brand_el else ""
                name_el = await item.query_selector(".product-product, h4.product-product")
                name = (await name_el.inner_text()).strip() if name_el else ""
                title = f"{brand} {name}".strip() if brand or name else ""
                if not title or len(title) < 3:
                    continue

                price_el = await item.query_selector(".product-discountedPrice, .product-price")
                price_text = (await price_el.inner_text()).strip() if price_el else "0"
                price = _parse_price(price_text)

                orig_el = await item.query_selector(".product-strike")
                orig_text = (await orig_el.inner_text()).strip() if orig_el else ""
                orig_price = _parse_price(orig_text) if orig_text else None

                link_el = await item.query_selector("a")
                href = await link_el.get_attribute("href") if link_el else ""
                url_full = f"https://www.myntra.com/{href}" if href and not href.startswith("http") else href

                results.append({
                    "platform": "myntra",
                    "platform_name": "Myntra",
                    "title": title,
                    "price": price or 999,
                    "original_price": orig_price,
                    "url": url_full or url,
                    "delivery_days": 5,
                    "delivery_label": "Free delivery",
                    "gst_invoice": True,
                    "return_days": 30,
                })
            except Exception as e:
                logger.debug("Myntra item error: %s", e)

        logger.info("Myntra scraped %d results for '%s'", len(results), query)
    except Exception as e:
        logger.warning("scrape_myntra failed: %s", e)
    finally:
        await page.close()
        await ctx.close()
    return results
