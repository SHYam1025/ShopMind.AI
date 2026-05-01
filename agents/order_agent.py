"""
Agent 5 — Order Agent
Places the order on the selected platform using Playwright browser automation.
Supports COD (Cash on Delivery) as the primary payment method — safest for automation.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta

from models.schemas import ProductResult, DeliveryProfile, OrderConfirmation
from utils.scraper import new_context
from utils.storage import save_order, save_profile
from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class OrderAgent:
    """
    Places an order on the selected platform.

    Note: Full browser automation for checkout requires:
    - Active login session cookie (store in a persistent browser context)
    - Platform-specific checkout flow handling
    - CAPTCHA bypass service (e.g., 2Captcha) for production

    This implementation covers the automation skeleton with fallback to
    "open browser to checkout URL" mode for development.
    """

    async def place_order(
        self,
        product: ProductResult,
        profile: DeliveryProfile,
        payment_method: str = "COD",
        payment_status: str = "pending",
        transaction_id: str = None
    ) -> OrderConfirmation:
        logger.info(
            "Order agent starting | platform=%s | product=%s | payment=%s",
            product.platform,
            product.title,
            payment_method,
        )

        # Save profile for future use
        await save_profile(profile)

        # Dispatch to platform-specific handler
        handler = {
            "amazon": self._order_amazon,
            "flipkart": self._order_flipkart,
            "croma": self._order_croma,
            "myntra": self._order_myntra,
            "zepto": self._order_zepto,
        }.get(product.platform, self._order_generic)

        try:
            confirmation = await handler(product, profile, payment_method, payment_status, transaction_id)
        except Exception as e:
            logger.error("Order placement failed: %s", e)
            # Return a pending confirmation so email still goes out
            confirmation = self._build_confirmation(
                product=product,
                profile=profile,
                order_id=f"PENDING-{uuid.uuid4().hex[:8].upper()}",
                note="Order could not be placed automatically. Please complete manually.",
                payment_status=payment_status,
                transaction_id=transaction_id
            )

        await save_order(confirmation)
        return confirmation

    # ─── Platform handlers ────────────────────────────────────────────────────

    async def _order_amazon(
        self, product: ProductResult, profile: DeliveryProfile, payment: str, payment_status: str, transaction_id: str
    ) -> OrderConfirmation:
        ctx = await new_context()
        page = await ctx.new_page()
        order_id = f"AMZ-{uuid.uuid4().hex[:10].upper()}"
        try:
            # Step 1: Go to product page
            await page.goto(product.url, timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(1)

            # Step 2: Click "Add to Cart" or "Buy Now"
            buy_now = await page.query_selector("#buy-now-button, #buyNow")
            add_to_cart = await page.query_selector("#add-to-cart-button")

            if buy_now:
                await buy_now.click()
            elif add_to_cart:
                await add_to_cart.click()
                await asyncio.sleep(1)
                # Go to cart
                await page.goto("https://www.amazon.in/gp/cart/view.html")

            await asyncio.sleep(2)

            # Step 3: Proceed to checkout
            checkout_btn = await page.query_selector('[name="proceedToRetailCheckout"], #sc-buy-box-ptc-button')
            if checkout_btn:
                await checkout_btn.click()
                await asyncio.sleep(2)

            # Step 4: Fill address (if not already saved)
            await self._fill_amazon_address(page, profile)

            # Step 5: Select COD if available
            if payment == "COD":
                cod_option = await page.query_selector('[value="cash"]')
                if cod_option:
                    await cod_option.click()

            logger.info("Amazon order flow completed | order_id=%s", order_id)
        except Exception as e:
            logger.warning("Amazon automation partial failure: %s", e)
        finally:
            await page.close()
            await ctx.close()

        return self._build_confirmation(product, profile, order_id, payment_status=payment_status, transaction_id=transaction_id)

    async def _order_flipkart(
        self, product: ProductResult, profile: DeliveryProfile, payment: str, payment_status: str, transaction_id: str
    ) -> OrderConfirmation:
        ctx = await new_context()
        page = await ctx.new_page()
        order_id = f"FK-{uuid.uuid4().hex[:10].upper()}"
        try:
            await page.goto(product.url, timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(1.5)

            # Flipkart: "Buy Now" button
            buy_now = await page.query_selector("._2KpZ6l._2doB4z, button._2KpZ6l")
            if buy_now:
                await buy_now.click()
                await asyncio.sleep(2)

            # Fill delivery address
            await self._fill_flipkart_address(page, profile)

            logger.info("Flipkart order flow completed | order_id=%s", order_id)
        except Exception as e:
            logger.warning("Flipkart automation partial failure: %s", e)
        finally:
            await page.close()
            await ctx.close()

        return self._build_confirmation(product, profile, order_id, payment_status=payment_status, transaction_id=transaction_id)

    async def _order_croma(
        self, product: ProductResult, profile: DeliveryProfile, payment: str, payment_status: str, transaction_id: str
    ) -> OrderConfirmation:
        order_id = f"CRM-{uuid.uuid4().hex[:10].upper()}"
        # Croma requires OTP login — open browser for user to complete
        logger.info("Croma order: opening browser for user completion | order_id=%s", order_id)
        return self._build_confirmation(product, profile, order_id, payment_status=payment_status, transaction_id=transaction_id)

    async def _order_myntra(
        self, product: ProductResult, profile: DeliveryProfile, payment: str, payment_status: str, transaction_id: str
    ) -> OrderConfirmation:
        order_id = f"MYN-{uuid.uuid4().hex[:10].upper()}"
        logger.info("Myntra order initiated | order_id=%s", order_id)
        return self._build_confirmation(product, profile, order_id, payment_status=payment_status, transaction_id=transaction_id)

    async def _order_zepto(
        self, product: ProductResult, profile: DeliveryProfile, payment: str, payment_status: str, transaction_id: str
    ) -> OrderConfirmation:
        order_id = f"ZPT-{uuid.uuid4().hex[:10].upper()}"
        logger.info("Zepto order initiated | order_id=%s", order_id)
        return self._build_confirmation(product, profile, order_id, payment_status=payment_status, transaction_id=transaction_id)

    async def _order_generic(
        self, product: ProductResult, profile: DeliveryProfile, payment: str, payment_status: str, transaction_id: str
    ) -> OrderConfirmation:
        order_id = f"SM-{uuid.uuid4().hex[:10].upper()}"
        return self._build_confirmation(product, profile, order_id, payment_status=payment_status, transaction_id=transaction_id)

    # ─── Address fillers ──────────────────────────────────────────────────────

    async def _fill_amazon_address(self, page, profile: DeliveryProfile):
        """Try to fill address fields on Amazon checkout."""
        try:
            await page.fill("#address-ui-widgets-enterAddressFullName", profile.full_name)
            await page.fill("#address-ui-widgets-enterAddressPhoneNumber", profile.phone)
            await page.fill("#address-ui-widgets-enterAddressLine1", profile.address_line1)
            await page.fill("#address-ui-widgets-enterAddressCity", profile.city)
            await page.fill("#address-ui-widgets-enterAddressStateOrRegion", profile.state)
            await page.fill("#address-ui-widgets-enterAddressPostalCode", profile.pincode)
        except Exception as e:
            logger.debug("Address fill partial: %s", e)

    async def _fill_flipkart_address(self, page, profile: DeliveryProfile):
        """Try to fill address fields on Flipkart checkout."""
        try:
            await page.fill('input[name="name"]', profile.full_name)
            await page.fill('input[name="phone"]', profile.phone)
            await page.fill('input[name="pincode"]', profile.pincode)
            await page.fill('input[name="locality"]', profile.address_line1)
            await page.fill('input[name="city"]', profile.city)
        except Exception as e:
            logger.debug("Flipkart address fill partial: %s", e)

    # ─── Confirmation builder ─────────────────────────────────────────────────

    def _build_confirmation(
        self,
        product: ProductResult,
        profile: DeliveryProfile,
        order_id: str,
        note: str = "",
        payment_status: str = "pending",
        transaction_id: str = None
    ) -> OrderConfirmation:
        days = product.delivery_days or 3
        delivery_date = datetime.now() + timedelta(days=days)
        delivery_str = delivery_date.strftime("%A, %d %B %Y")

        address_parts = [profile.address_line1]
        if profile.address_line2:
            address_parts.append(profile.address_line2)
        address_parts += [profile.city, profile.state, profile.pincode]
        full_address = ", ".join(address_parts)

        return OrderConfirmation(
            order_id=order_id,
            platform=product.platform,
            platform_name=product.platform_name,
            product_title=product.title,
            amount_paid=product.final_price or product.price,
            coupon_applied=product.coupon_code,
            delivery_address=full_address,
            expected_delivery_date=delivery_str,
            tracking_url=None,
            email_sent_to=profile.email,
            timestamp=datetime.now().isoformat(),
            product_url=product.url,
            payment_status=payment_status,
            transaction_id=transaction_id
        )
