from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from enum import Enum


class Platform(str, Enum):
    amazon = "amazon"
    flipkart = "flipkart"
    croma = "croma"
    zepto = "zepto"
    myntra = "myntra"


class ProductResult(BaseModel):
    platform: str
    platform_name: str
    title: str
    price: float
    original_price: Optional[float] = None
    discount_percent: Optional[int] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    url: str
    image_url: Optional[str] = None
    delivery_days: Optional[int] = None
    delivery_label: str = ""
    gst_invoice: bool = True
    return_days: int = 7
    genuineness_score: float = 1.0          # 0–1 from filter agent
    coupon_code: Optional[str] = None
    coupon_discount: Optional[float] = None
    final_price: Optional[float] = None     # after coupon


class RecognizedProduct(BaseModel):
    raw_query: str
    normalized_name: str                    # e.g. "Sony WH-1000XM5"
    brand: Optional[str] = None
    model: Optional[str] = None
    category: Optional[str] = None
    key_specs: list[str] = []
    search_terms: list[str] = []            # platform-optimized search strings
    confidence: float = 1.0


class SearchRequest(BaseModel):
    query: Optional[str] = None
    image_base64: Optional[str] = None     # base64-encoded product image
    platforms: list[Platform] = list(Platform)
    max_results: int = 5

    @field_validator("query", "image_base64")
    @classmethod
    def at_least_one(cls, v, info):
        return v


class DeliveryProfile(BaseModel):
    full_name: str
    phone: str
    email: EmailStr
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state: str
    pincode: str
    country: str = "India"


class OrderRequest(BaseModel):
    product: ProductResult
    profile: DeliveryProfile
    payment_method: str = "COD"             # COD | UPI | CARD


class OrderConfirmation(BaseModel):
    order_id: str
    platform: str
    platform_name: str
    product_title: str
    amount_paid: float
    coupon_applied: Optional[str] = None
    delivery_address: str
    expected_delivery_date: str
    tracking_url: Optional[str] = None
    email_sent_to: str
    timestamp: str
    product_url: Optional[str] = None
    payment_status: str = "pending"
    transaction_id: Optional[str] = None

class PaymentCreateResponse(BaseModel):
    razorpay_order_id: str
    amount: int
    currency: str = "INR"
    key_id: str

class PaymentVerifyRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str
    order_request: OrderRequest


class SearchResponse(BaseModel):
    recognized: RecognizedProduct
    results: list[ProductResult]
    best_deal: Optional[ProductResult] = None
    total_platforms_searched: int
    search_duration_seconds: float


class AgentStatus(BaseModel):
    agent: str
    status: str                             # running | done | error
    message: str = ""
