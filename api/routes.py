"""
API Routes — FastAPI route definitions.
"""

import json
import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from models.schemas import (
    SearchRequest,
    SearchResponse,
    OrderRequest,
    OrderConfirmation,
    DeliveryProfile,
    PaymentCreateResponse,
    PaymentVerifyRequest,
)
from agents.orchestrator import Orchestrator
from utils.storage import save_profile, get_profile, get_orders

logger = logging.getLogger(__name__)
router = APIRouter()

# Single orchestrator instance (shared across requests)
_orchestrator = Orchestrator()


def get_orchestrator() -> Orchestrator:
    return _orchestrator


# ─── Search ───────────────────────────────────────────────────────────────────

@router.post("/search", response_model=SearchResponse, summary="Run full product search pipeline")
async def search(
    request: SearchRequest,
    orc: Orchestrator = Depends(get_orchestrator),
):
    """
    Accepts a text description and/or base64 image.
    Returns top 5 verified results across Amazon, Flipkart, Croma, Zepto, Myntra
    with coupon codes and genuineness scores.
    """
    if not request.query and not request.image_base64:
        raise HTTPException(status_code=400, detail="Provide at least 'query' or 'image_base64'")

    result = await orc.run_search(request)
    return result


@router.post("/search/stream", summary="Stream agent status via SSE")
async def search_stream(
    request: SearchRequest,
    orc: Orchestrator = Depends(get_orchestrator),
):
    """
    Same as /search but streams agent status events as Server-Sent Events.
    Each event is a JSON-encoded AgentStatus.
    Frontend can use EventSource to show live progress.
    """
    if not request.query and not request.image_base64:
        raise HTTPException(status_code=400, detail="Provide at least 'query' or 'image_base64'")

    async def event_generator():
        async for status in orc.run_search_streaming(request):
            yield f"data: {status.model_dump_json()}\n\n"
        yield "data: {\"agent\": \"done\", \"status\": \"done\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── Payment & Order ──────────────────────────────────────────────────────────

@router.post("/payment/create", response_model=PaymentCreateResponse, summary="Create Razorpay Order")
async def create_payment_order(
    request: OrderRequest,
    orc: Orchestrator = Depends(get_orchestrator),
):
    from config.settings import get_settings
    settings = get_settings()
    order_data = orc.create_payment_order(request)
    return PaymentCreateResponse(
        razorpay_order_id=order_data["id"],
        amount=order_data["amount"],
        currency="INR",
        key_id=settings.razorpay_key_id or "mock_key_id"
    )

@router.post("/payment/verify", response_model=OrderConfirmation, summary="Verify Payment & Place Order")
async def verify_payment(
    request: PaymentVerifyRequest,
    orc: Orchestrator = Depends(get_orchestrator),
):
    is_valid = orc.verify_payment(request.razorpay_payment_id, request.razorpay_order_id, request.razorpay_signature)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid payment signature")
    
    confirmation = await orc.place_order(request.order_request, payment_status="success", transaction_id=request.razorpay_payment_id)
    return confirmation

@router.post("/order", response_model=OrderConfirmation, summary="Place COD order directly")
async def place_order(
    request: OrderRequest,
    orc: Orchestrator = Depends(get_orchestrator),
):
    """
    Places the order directly via COD on the selected platform.
    Sends a confirmation email and saves the delivery profile.
    """
    confirmation = await orc.place_order(request, payment_status="pending")
    return confirmation


@router.get("/orders/{email}", response_model=list[OrderConfirmation], summary="Get order history")
async def get_order_history(email: str):
    """Return all past orders for an email address."""
    return await get_orders(email)


# ─── Delivery Profile ────────────────────────────────────────────────────────

@router.get("/profile/{email}", response_model=DeliveryProfile, summary="Get saved delivery profile")
async def get_delivery_profile(email: str):
    """Return the saved delivery profile for an email."""
    profile = await get_profile(email)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.post("/profile", response_model=DeliveryProfile, summary="Save delivery profile")
async def save_delivery_profile(profile: DeliveryProfile):
    """Save or update a delivery profile."""
    await save_profile(profile)
    return profile


# ─── Health ──────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok", "service": "ShopMind AI"}
