import razorpay
import logging
from config.settings import get_settings

logger = logging.getLogger(__name__)

class PaymentAgent:
    def __init__(self):
        settings = get_settings()
        self.key_id = settings.razorpay_key_id
        self.key_secret = settings.razorpay_key_secret
        if self.key_id and self.key_secret:
            self.client = razorpay.Client(auth=(self.key_id, self.key_secret))
        else:
            self.client = None
            logger.warning("Razorpay credentials missing. Payment Agent will run in mock mode.")

    def create_order(self, amount_in_inr: float, receipt: str) -> dict:
        if not self.client:
            return {"id": f"order_{receipt}", "amount": int(amount_in_inr*100), "currency":"INR"}
        
        amount_in_paise = int(amount_in_inr * 100)
        data = {
            "amount": amount_in_paise,
            "currency": "INR",
            "receipt": receipt,
            "payment_capture": "1"
        }
        order = self.client.order.create(data=data)
        return order

    def verify_signature(self, payment_id: str, order_id: str, signature: str) -> bool:
        if not self.client:
            return True # Mock success
        try:
            self.client.utility.verify_payment_signature({
                'razorpay_payment_id': payment_id,
                'razorpay_order_id': order_id,
                'razorpay_signature': signature
            })
            return True
        except razorpay.errors.SignatureVerificationError:
            return False
