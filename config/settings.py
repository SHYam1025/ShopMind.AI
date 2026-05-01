from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Gemini (replaces Anthropic)
    gemini_api_key: str = ""

    # Email
    # Email (SMTP)
    email_from: str = "yourgmail@gmail.com"
    email_password: str = "your_app_password"
    email_from_name: str = "ShopMind AI"
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587

    # Optional search API
    serpapi_key: str = ""

    # Razorpay Payment Gateway
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite+aiosqlite:///./shopmind.db"

    # Scraping
    headless: bool = True
    request_timeout_seconds: int = 20
    max_search_results_per_platform: int = 5

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Platform configs
PLATFORMS = {
    "amazon": {
        "name": "Amazon India",
        "base_url": "https://www.amazon.in",
        "search_url": "https://www.amazon.in/s?k={query}",
        "authorized": True,
        "avg_delivery_days": 2,
        "gst_invoice": True,
        "return_days": 10,
        "selectors": {
            "results": '[data-component-type="s-search-result"]',
            "title": "h2 a span",
            "price": ".a-price-whole",
            "rating": ".a-icon-alt",
            "link": "h2 a",
        },
    },
    "flipkart": {
        "name": "Flipkart",
        "base_url": "https://www.flipkart.com",
        "search_url": "https://www.flipkart.com/search?q={query}",
        "authorized": True,
        "avg_delivery_days": 3,
        "gst_invoice": True,
        "return_days": 7,
        "selectors": {
            "results": "._1AtVbE",
            "title": "._4rR01T, .s1Q9rs",
            "price": "._30jeq3",
            "rating": "._3LWZlK",
            "link": "._1fQZEK, .s1Q9rs",
        },
    },
    "croma": {
        "name": "Croma",
        "base_url": "https://www.croma.com",
        "search_url": "https://www.croma.com/searchB?q={query}",
        "authorized": True,
        "avg_delivery_days": 4,
        "gst_invoice": True,
        "return_days": 7,
        "selectors": {
            "results": ".product-item",
            "title": ".product-title",
            "price": ".amount",
            "rating": ".rating",
            "link": "a.product-title",
        },
    },
    "zepto": {
        "name": "Zepto",
        "base_url": "https://www.zeptonow.com",
        "search_url": "https://www.zeptonow.com/search?query={query}",
        "authorized": True,
        "avg_delivery_days": 0,
        "gst_invoice": True,
        "return_days": 2,
        "selectors": {
            "results": "[data-testid='product-card']",
            "title": "[data-testid='product-card-name']",
            "price": "[data-testid='product-card-price']",
        },
    },
    "myntra": {
        "name": "Myntra",
        "base_url": "https://www.myntra.com",
        "search_url": "https://www.myntra.com/{query}",
        "authorized": True,
        "avg_delivery_days": 5,
        "gst_invoice": True,
        "return_days": 30,
        "selectors": {
            "results": ".product-base",
            "title": ".product-product",
            "price": ".product-discountedPrice",
            "original_price": ".product-strike",
            "link": "a",
        },
    },
}

COUPON_SOURCES = [
    "https://www.coupondunia.in/search?q={store}+{product}",
    "https://www.grabon.in/search/?keyword={store}+{product}",
    "https://www.cashkaro.com/search?q={product}",
]
