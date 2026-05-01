"""
Orchestrator — Master Agent
Coordinates all sub-agents in sequence.
Emits SSE (Server-Sent Events) status updates for the frontend.
"""

import asyncio
import logging
import time
from typing import AsyncGenerator

from models.schemas import (
    SearchRequest,
    SearchResponse,
    OrderRequest,
    OrderConfirmation,
    AgentStatus,
)
from agents.recognition_agent import RecognitionAgent
from agents.search_agent import SearchAgent
from agents.deal_agent import DealAgent
from agents.filter_agent import FilterAgent
from agents.order_agent import OrderAgent
from agents.email_agent import EmailAgent

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self):
        self.recognition = RecognitionAgent()
        self.search = SearchAgent()
        self.deal = DealAgent()
        self.filter = FilterAgent()
        self.order = OrderAgent()
        self.email = EmailAgent()

    # ─── Search Pipeline ──────────────────────────────────────────────────────

    async def run_search(self, request: SearchRequest) -> SearchResponse:
        """
        Full search pipeline:
        1. Recognize product
        2. Search all platforms in parallel
        3. Fetch coupons & deals
        4. Filter for genuineness
        5. Return top N results
        """
        start = time.monotonic()

        # ── Step 1: Recognition ──
        logger.info("=== STEP 1: Recognition ===")
        recognized = await self.recognition.recognize(
            text=request.query,
            image_base64=request.image_base64,
        )
        logger.info("Recognized: %s (confidence=%.2f)", recognized.normalized_name, recognized.confidence)

        # ── Step 2: Search ──
        logger.info("=== STEP 2: Multi-platform search ===")
        platforms = [p.value for p in request.platforms]
        raw_results = await self.search.search(
            recognized=recognized,
            platforms=platforms,
        )
        logger.info("Raw results: %d", len(raw_results))

        # ── Step 3: Deals & Coupons ──
        logger.info("=== STEP 3: Deal enrichment ===")
        enriched = await self.deal.enrich(raw_results, recognized)

        # ── Step 4: Filter ──
        logger.info("=== STEP 4: Genuineness filter ===")
        filtered = await self.filter.filter(enriched, recognized)
        logger.info("Filtered results: %d", len(filtered))

        # ── Top N results ──
        top = filtered[: request.max_results]
        best = top[0] if top else None

        duration = time.monotonic() - start
        logger.info("=== Search complete in %.2fs ===", duration)

        return SearchResponse(
            recognized=recognized,
            results=top,
            best_deal=best,
            total_platforms_searched=len(platforms),
            search_duration_seconds=round(duration, 2),
        )

    async def run_search_streaming(
        self, request: SearchRequest
    ) -> AsyncGenerator[AgentStatus, None]:
        """
        Search pipeline that yields AgentStatus events for SSE streaming.
        Frontend can display live agent progress.
        """
        yield AgentStatus(agent="recognition", status="running", message="Identifying product...")

        recognized = await self.recognition.recognize(
            text=request.query,
            image_base64=request.image_base64,
        )
        yield AgentStatus(
            agent="recognition",
            status="done",
            message=f"Identified: {recognized.normalized_name}",
        )

        # Emit a status event per platform as each completes
        platform_events: list[AgentStatus] = []

        async def platform_callback(platform: str, status: str):
            platform_events.append(
                AgentStatus(agent=f"search:{platform}", status=status)
            )

        yield AgentStatus(agent="search", status="running", message="Searching all platforms...")
        platforms = [p.value for p in request.platforms]
        raw_results = await self.search.search(recognized, platforms, platform_callback)

        for ev in platform_events:
            yield ev

        yield AgentStatus(agent="deals", status="running", message="Fetching coupons...")
        enriched = await self.deal.enrich(raw_results, recognized)
        yield AgentStatus(agent="deals", status="done", message="Coupons applied")

        yield AgentStatus(agent="filter", status="running", message="Verifying genuineness...")
        filtered = await self.filter.filter(enriched, recognized)
        yield AgentStatus(agent="filter", status="done", message=f"{len(filtered)} genuine results")

        top = filtered[: request.max_results]
        yield AgentStatus(
            agent="complete",
            status="done",
            message=f"Found {len(top)} results",
        )

    # ─── Payment & Order Pipelines ────────────────────────────────────────────

    def create_payment_order(self, request: OrderRequest) -> dict:
        from agents.payment_agent import PaymentAgent
        import uuid
        payment_agent = PaymentAgent()
        receipt = str(uuid.uuid4())[:12]
        amount = request.product.final_price or request.product.price
        return payment_agent.create_order(amount, receipt)

    def verify_payment(self, payment_id: str, order_id: str, signature: str) -> bool:
        from agents.payment_agent import PaymentAgent
        payment_agent = PaymentAgent()
        return payment_agent.verify_signature(payment_id, order_id, signature)

    async def place_order(self, request: OrderRequest, payment_status: str = "pending", transaction_id: str = None) -> OrderConfirmation:
        """
        Full order pipeline:
        1. Place order via platform automation
        2. Send confirmation email
        """
        logger.info("=== ORDER PIPELINE START ===")

        # ── Step 1: Place order ──
        confirmation = await self.order.place_order(
            product=request.product,
            profile=request.profile,
            payment_method=request.payment_method,
            payment_status=payment_status,
            transaction_id=transaction_id
        )
        logger.info("Order placed | order_id=%s", confirmation.order_id)

        # ── Step 2: Send email ──
        email_sent = await self.email.send_confirmation(confirmation)
        if not email_sent:
            logger.warning("Email delivery failed for order %s", confirmation.order_id)

        logger.info("=== ORDER PIPELINE COMPLETE ===")
        return confirmation
