"""
Agent 6 — Email Agent
Sends a rich HTML confirmation email via SendGrid.
Includes: order ID, product, price, coupon, address, expected delivery, tracking link.
"""

import smtplib
import ssl
import logging
from datetime import datetime
from email.mime.text import MIMEText

from models.schemas import OrderConfirmation
from config.settings import get_settings

logger = logging.getLogger(__name__)


EMAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f0; margin: 0; padding: 0; }}
    .wrapper {{ max-width: 580px; margin: 32px auto; background: #ffffff; border-radius: 12px; overflow: hidden; }}
    .header {{ background: #1D9E75; padding: 28px 32px; }}
    .header h1 {{ color: white; margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.3px; }}
    .header p {{ color: rgba(255,255,255,0.8); margin: 4px 0 0; font-size: 13px; }}
    .body {{ padding: 28px 32px; }}
    .order-id {{ background: #E1F5EE; border-radius: 8px; padding: 12px 16px; margin-bottom: 24px; }}
    .order-id span {{ font-size: 12px; color: #0F6E56; font-weight: 500; display: block; margin-bottom: 2px; }}
    .order-id strong {{ font-size: 18px; color: #085041; letter-spacing: 0.5px; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
    td {{ padding: 10px 0; border-bottom: 0.5px solid #e8e8e4; font-size: 14px; }}
    td:first-child {{ color: #888780; width: 140px; }}
    td:last-child {{ color: #2C2C2A; font-weight: 500; }}
    .total-row td {{ border-bottom: none; padding-top: 14px; font-size: 16px; }}
    .total-row td:last-child {{ color: #1D9E75; }}
    .coupon-badge {{ background: #FAEEDA; color: #633806; border: 0.5px dashed #EF9F27; border-radius: 4px; padding: 2px 8px; font-size: 12px; font-weight: 500; }}
    .tracking-btn {{ display: block; text-align: center; background: #1D9E75; color: white; text-decoration: none; padding: 14px; border-radius: 8px; font-weight: 600; font-size: 15px; margin-top: 24px; }}
    .footer {{ background: #f5f5f0; padding: 20px 32px; font-size: 12px; color: #888780; text-align: center; }}
  </style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <h1>ShopMind AI</h1>
    <p>Your order has been placed successfully</p>
  </div>
  <div class="body">
    <div class="order-id">
      <span>Order ID</span>
      <strong>{order_id}</strong>
    </div>

    <table>
      <tr><td>Product</td><td>{product_title}</td></tr>
      <tr><td>Platform</td><td>{platform_name}</td></tr>
      <tr><td>Amount</td><td>₹{amount_paid:,.0f}</td></tr>
      {coupon_row}
      <tr><td>Deliver to</td><td>{delivery_address}</td></tr>
      <tr><td>Expected by</td><td><strong>{expected_delivery}</strong></td></tr>
      <tr><td>Ordered at</td><td>{timestamp}</td></tr>
      <tr class="total-row"><td>Total paid</td><td>₹{amount_paid:,.0f}</td></tr>
    </table>

    {tracking_section}

    <p style="font-size: 13px; color: #888780; margin-top: 20px; line-height: 1.6;">
      You'll receive shipping updates from <strong>{platform_name}</strong> directly.
      Keep this email for your records. For returns or issues, contact the platform's support.
    </p>
  </div>
  <div class="footer">
    ShopMind AI · Automated product search &amp; ordering · Gurugram, India<br/>
    This is an automated confirmation. Do not reply to this email.
  </div>
</div>
</body>
</html>
"""


class EmailAgent:
    def __init__(self):
        settings = get_settings()
        self.email = settings.email_from
        self.password = settings.email_password  # Gmail App Password

    async def send_confirmation(self, confirmation: OrderConfirmation) -> bool:
        html = self._build_html(confirmation)
        subject = f"Order Confirmed — {confirmation.product_title[:40]} | {confirmation.order_id}"

        msg = MIMEText(html, "html")
        msg["Subject"] = subject
        msg["From"] = self.email
        msg["To"] = confirmation.email_sent_to

        try:
            context = ssl.create_default_context()

            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls(context=context)
                server.login(self.email, self.password)
                server.send_message(msg)

            logger.info("Email sent successfully via SMTP")
            return True

        except Exception as e:
            logger.error("SMTP Email failed: %s", e)
            return False

    def _build_html(self, confirmation: OrderConfirmation) -> str:
        coupon_row = ""
        if confirmation.coupon_applied:
            coupon_row = f"<tr><td>Coupon</td><td><span class='coupon-badge'>{confirmation.coupon_applied}</span></td></tr>"

        tracking_section = ""
        if confirmation.tracking_url:
            tracking_section = f"<a href='{confirmation.tracking_url}' class='tracking-btn'>Track your order</a>"

        return EMAIL_TEMPLATE.format(
            order_id=confirmation.order_id,
            product_title=confirmation.product_title,
            platform_name=confirmation.platform_name,
            amount_paid=confirmation.amount_paid,
            coupon_row=coupon_row,
            delivery_address=confirmation.delivery_address,
            expected_delivery=confirmation.expected_delivery_date,
            timestamp=confirmation.timestamp,
            tracking_section=tracking_section
        )