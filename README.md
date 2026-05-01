# ShopMind AI — Multi-Agent Product Search & Order System

## Architecture

```
shopmind/
├── main.py                    # FastAPI app entry point
├── config/
│   └── settings.py            # All env vars and config
├── models/
│   └── schemas.py             # Pydantic data models
├── agents/
│   ├── orchestrator.py        # Master agent — coordinates all sub-agents
│   ├── recognition_agent.py   # Agent 1: Product recognition (text + image)
│   ├── search_agent.py        # Agent 2: Multi-platform parallel search
│   ├── deal_agent.py          # Agent 3: Coupon & deal fetcher
│   ├── filter_agent.py        # Agent 4: Genuineness filter
│   ├── order_agent.py         # Agent 5: Order placement
│   └── email_agent.py         # Agent 6: Confirmation email
├── api/
│   └── routes.py              # FastAPI route handlers
└── utils/
    ├── scraper.py             # Playwright-based scraper helpers
    └── storage.py             # User profile / address store (SQLite)
```

## Setup

```bash
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# Fill in your API keys in .env

uvicorn main:app --reload
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /search | Run full product search pipeline |
| POST | /order | Place order on selected platform |
| GET  | /profile | Get saved delivery profile |
| POST | /profile | Save delivery profile |

## Agent Flow

1. **Recognition Agent** — identifies product from text/image using Claude Vision
2. **Search Agent** — parallel scrapes Amazon, Flipkart, Croma, Zepto, Myntra
3. **Deal Agent** — fetches coupons from CouponDunia, GrabOn, retailer pages
4. **Filter Agent** — scores each result for genuineness (seller rating, GST, returns)
5. **Order Agent** — places order via Playwright browser automation
6. **Email Agent** — sends confirmation email via SendGrid with full details
