"""Stripe payment endpoints for wallet recharge."""
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel, Field
from typing import Optional
import stripe
import logging
from jose import jwt, JWTError
from datetime import datetime

from core.config import settings
from repositories.wallet_repository import WalletRepository
from clients.mongodb_client import get_database

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = settings.stripe_secret_key

router = APIRouter(prefix="/stripe", tags=["stripe"])


class CreatePaymentIntentRequest(BaseModel):
    """Request model for creating a payment intent."""
    amount: int = Field(..., gt=0, description="Amount in cents (e.g., 1000 = $10.00)")
    currency: str = Field(default="usd", description="Currency code (e.g., usd, mxn)")
    description: Optional[str] = Field(default="Recarga Wallet", description="Payment description")


class CreateRechargeLinkRequest(BaseModel):
    """Request model for creating a recharge payment link."""
    currency: str = Field(default="usd", description="Currency code (e.g., usd, eur)")
    description: str = Field(default="Recarga internacional para Llego Wallet", description="Payment description")


class CreatePaymentIntentResponse(BaseModel):
    """Response model for payment intent creation."""
    client_secret: str
    payment_intent_id: str
    publishable_key: str


class CreateRechargeLinkResponse(BaseModel):
    """Response model for recharge link creation."""
    payment_link: str
    link_id: str
    user_id: str
    expires_at: Optional[str] = None


def verify_token(authorization: Optional[str]) -> str:
    """Verify JWT token and return user_id."""
    if not authorization:
        raise HTTPException(status_code=401, detail="No autorizado: Token no proporcionado")
    
    try:
        # Remove 'Bearer ' prefix
        token = authorization.replace("Bearer ", "")
        
        # Verify JWT
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user_id = payload.get("user_id")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Token inválido: user_id no encontrado")
        
        return user_id
    except JWTError as e:
        logger.error(f"JWT verification failed: {e}")
        raise HTTPException(status_code=401, detail="Token inválido o expirado")


@router.post("/create-payment-intent", response_model=CreatePaymentIntentResponse)
async def create_payment_intent(
    request: CreatePaymentIntentRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Create a Stripe Payment Intent for wallet recharge.
    
    This endpoint:
    1. Verifies user authentication via JWT
    2. Creates a Payment Intent with Stripe
    3. Returns the client secret for the iOS app to complete payment
    
    The amount should be in cents (e.g., 1000 = $10.00).
    """
    try:
        # Verify authentication
        user_id = verify_token(authorization)
        
        logger.info(f"Creating payment intent for user {user_id}, amount: {request.amount} {request.currency}")
        
        # Create Payment Intent
        payment_intent = stripe.PaymentIntent.create(
            amount=request.amount,
            currency=request.currency.lower(),
            description=request.description,
            metadata={
                "user_id": user_id,
                "type": "wallet_recharge"
            },
            # Enable automatic payment methods (includes Apple Pay, Google Pay, cards)
            automatic_payment_methods={
                "enabled": True,
            },
        )
        
        logger.info(f"Payment intent created: {payment_intent.id}")
        
        return CreatePaymentIntentResponse(
            client_secret=payment_intent.client_secret,
            payment_intent_id=payment_intent.id,
            publishable_key=settings.stripe_publishable_key
        )
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(status_code=400, detail=f"Error de Stripe: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error creating payment intent: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post("/create-recharge-link", response_model=CreateRechargeLinkResponse)
async def create_recharge_link(
    request: CreateRechargeLinkRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Create a Stripe Payment Link for international wallet recharge.
    
    This endpoint:
    1. Verifies user authentication via JWT
    2. Creates a Product and Price in Stripe with custom amount enabled
    3. Creates a Payment Link that can be shared with family/friends abroad
    4. Saves the link to database for tracking
    
    The link allows the payer to choose the amount (min $5, max $1000).
    """
    try:
        # Verify authentication
        user_id = verify_token(authorization)
        
        # Get user details for personalization
        db = get_database()
        user = await db.users.find_one({"_id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        user_name = user.get("name", "Usuario")
        user_email = user.get("email", "")
        user_username = user.get("username", "")
        
        logger.info(f"Creating recharge link for user {user_id} ({user_email})")
        
        # Create a Product for this user
        product = stripe.Product.create(
            name=f"Recarga Wallet - {user_name}",
            description=f"Recarga internacional para {user_email}",
            metadata={
                "user_id": user_id,
                "user_email": user_email,
                "username": user_username,
                "type": "wallet_recharge"
            }
        )
        
        logger.info(f"Created Stripe product: {product.id}")
        
        # Create a Price with custom amount enabled
        price = stripe.Price.create(
            product=product.id,
            currency=request.currency.lower(),
            unit_amount=2000,  # $20 USD as default suggestion (in cents)
            custom_unit_amount={
                "enabled": True,
                "minimum": 500,      # Minimum $5 USD
                "maximum": 100000,   # Maximum $1000 USD
                "preset": 2000       # Suggested amount $20 USD
            }
        )
        
        logger.info(f"Created Stripe price: {price.id}")
        
        # Create the Payment Link
        payment_link = stripe.PaymentLink.create(
            line_items=[{
                "price": price.id,
                "quantity": 1,
                "adjustable_quantity": {
                    "enabled": False  # Don't allow changing quantity, only amount
                }
            }],
            after_completion={
                "type": "hosted_confirmation",
                "hosted_confirmation": {
                    "custom_message": f"¡Gracias! El dinero ha sido enviado a {user_name} exitosamente."
                }
            },
            allow_promotion_codes=False,
            billing_address_collection="auto",
            phone_number_collection={
                "enabled": False
            },
            metadata={
                "user_id": user_id,
                "user_email": user_email,
                "username": user_username,
                "type": "wallet_recharge",
                "created_at": datetime.utcnow().isoformat()
            }
        )
        
        logger.info(f"Created payment link: {payment_link.id}")
        
        # Save the link to database for tracking
        await save_payment_link_to_db(
            user_id=user_id,
            link_id=payment_link.id,
            url=payment_link.url,
            product_id=product.id,
            price_id=price.id,
            currency=request.currency
        )
        
        return CreateRechargeLinkResponse(
            payment_link=payment_link.url,
            link_id=payment_link.id,
            user_id=user_id,
            expires_at=None  # Payment Links don't expire by default
        )
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(status_code=400, detail=f"Error de Stripe: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating recharge link: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhook events.
    
    This endpoint receives notifications from Stripe when payment events occur.
    It verifies the webhook signature and processes the event.
    
    Important events:
    - payment_intent.succeeded: Payment completed successfully (Payment Intents)
    - payment_intent.payment_failed: Payment failed
    - checkout.session.completed: Payment Link checkout completed
    """
    try:
        # Get the webhook signature
        sig_header = request.headers.get("stripe-signature")
        if not sig_header:
            raise HTTPException(status_code=400, detail="Missing stripe-signature header")
        
        # Get raw body
        payload = await request.body()
        
        # Verify webhook signature
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.stripe_webhook_secret
            )
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Webhook signature verification failed: {e}")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        # Handle the event
        event_type = event["type"]
        logger.info(f"Received webhook event: {event_type}")
        
        if event_type == "payment_intent.succeeded":
            payment_intent = event["data"]["object"]
            await handle_payment_success(payment_intent)
            
        elif event_type == "payment_intent.payment_failed":
            payment_intent = event["data"]["object"]
            await handle_payment_failure(payment_intent)
        
        elif event_type == "checkout.session.completed":
            session = event["data"]["object"]
            await handle_checkout_session_completed(session)
        
        else:
            logger.info(f"Unhandled event type: {event_type}")
        
        return {"received": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Error processing webhook")


async def handle_payment_success(payment_intent: dict):
    """Handle successful payment."""
    try:
        payment_intent_id = payment_intent["id"]
        metadata = payment_intent.get("metadata", {})
        user_id = metadata.get("user_id")
        payment_type = metadata.get("type", "wallet_recharge")
        amount_cents = payment_intent["amount"]
        amount = amount_cents / 100  # Convert cents to dollars

        logger.info(f"✅ Payment succeeded: {payment_intent_id} for user {user_id}, amount: ${amount}, type: {payment_type}")

        if not user_id:
            logger.error(f"No user_id in payment intent metadata: {payment_intent_id}")
            return

        # Handle based on payment type
        if payment_type == "order_payment":
            # This is an order payment - use PaymentService
            from services.payments_service import payment_service
            await payment_service.handle_stripe_webhook(
                payment_intent_id,
                "payment_intent.succeeded"
            )
            logger.info(f"Order payment processed: {payment_intent_id}")
        else:
            # This is a wallet recharge
            wallet_repo = WalletRepository()
            await wallet_repo.add_balance(user_id, amount, "stripe_recharge", payment_intent_id)
            logger.info(f"Wallet updated for user {user_id}: +${amount}")

    except Exception as e:
        logger.error(f"Error handling payment success: {e}")


async def handle_payment_failure(payment_intent: dict):
    """Handle failed payment."""
    try:
        payment_intent_id = payment_intent["id"]
        metadata = payment_intent.get("metadata", {})
        user_id = metadata.get("user_id")
        payment_type = metadata.get("type", "wallet_recharge")
        error = payment_intent.get("last_payment_error", {})

        logger.error(f"❌ Payment failed: {payment_intent_id} for user {user_id}, type: {payment_type}")
        logger.error(f"Error: {error.get('message', 'Unknown error')}")

        # Handle based on payment type
        if payment_type == "order_payment":
            # This is an order payment - use PaymentService
            from services.payments_service import payment_service
            await payment_service.handle_stripe_webhook(
                payment_intent_id,
                "payment_intent.payment_failed"
            )
            logger.info(f"Order payment failure processed: {payment_intent_id}")

        # TODO: Optionally notify user

    except Exception as e:
        logger.error(f"Error handling payment failure: {e}")


async def handle_checkout_session_completed(session: dict):
    """Handle successful Payment Link checkout."""
    try:
        session_id = session["id"]
        metadata = session.get("metadata", {})
        user_id = metadata.get("user_id")
        
        if not user_id:
            logger.error(f"⚠️ No user_id in metadata for session: {session_id}")
            return
        
        # Get the amount paid (in cents)
        amount_total = session.get("amount_total", 0)
        currency = session.get("currency", "usd")
        payment_intent_id = session.get("payment_intent")
        
        # Convert from cents to dollars
        amount = amount_total / 100
        
        logger.info(f"✅ Checkout session completed: {session_id} for user {user_id}, amount: ${amount} {currency.upper()}")
        
        # Update user wallet balance
        wallet_repo = WalletRepository()
        await wallet_repo.add_balance(
            user_id=user_id,
            amount=amount,
            transaction_type="stripe_payment_link",
            reference_id=payment_intent_id or session_id
        )
        
        logger.info(f"Wallet updated for user {user_id}: +${amount} {currency.upper()}")
        
        # Update payment link usage stats
        await update_payment_link_usage(session_id, amount)
        
        # TODO: Send push notification to user
        # await send_push_notification(
        #     user_id=user_id,
        #     title="¡Recarga recibida!",
        #     body=f"Has recibido ${amount:.2f} {currency.upper()} en tu Wallet"
        # )
        
    except Exception as e:
        logger.error(f"Error handling checkout session: {e}")


async def save_payment_link_to_db(
    user_id: str,
    link_id: str,
    url: str,
    product_id: str,
    price_id: str,
    currency: str
):
    """Save payment link to database for tracking."""
    try:
        db = get_database()
        
        payment_link_data = {
            "_id": link_id,
            "userId": user_id,
            "url": url,
            "productId": product_id,
            "priceId": price_id,
            "currency": currency,
            "isActive": True,
            "totalReceived": 0.0,
            "usageCount": 0,
            "createdAt": datetime.utcnow(),
            "lastUsedAt": None
        }
        
        await db.stripe_payment_links.insert_one(payment_link_data)
        logger.info(f"Saved payment link {link_id} to database")
        
    except Exception as e:
        logger.error(f"Error saving payment link to database: {e}")
        # Don't raise - this is not critical


async def update_payment_link_usage(session_id: str, amount: float):
    """Update payment link usage statistics."""
    try:
        db = get_database()
        
        # Get the session to find the payment link
        session = stripe.checkout.Session.retrieve(session_id)
        metadata = session.get("metadata", {})
        
        # Update the payment link record
        await db.stripe_payment_links.update_one(
            {"userId": metadata.get("user_id")},
            {
                "$inc": {
                    "totalReceived": amount,
                    "usageCount": 1
                },
                "$set": {
                    "lastUsedAt": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"Updated payment link usage for session {session_id}")
        
    except Exception as e:
        logger.error(f"Error updating payment link usage: {e}")
        # Don't raise - this is not critical


@router.get("/config")
async def get_stripe_config():
    """
    Get Stripe publishable key for client-side initialization.
    
    This is safe to expose publicly as it's the publishable key.
    """
    return {
        "publishable_key": settings.stripe_publishable_key
    }
