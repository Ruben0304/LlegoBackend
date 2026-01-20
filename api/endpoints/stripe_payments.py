"""Stripe payment endpoints for wallet recharge."""
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel, Field
from typing import Optional
import stripe
import logging
from jose import jwt, JWTError

from core.config import settings
from repositories.wallet_repository import WalletRepository

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = settings.stripe_secret_key

router = APIRouter(prefix="/stripe", tags=["stripe"])


class CreatePaymentIntentRequest(BaseModel):
    """Request model for creating a payment intent."""
    amount: int = Field(..., gt=0, description="Amount in cents (e.g., 1000 = $10.00)")
    currency: str = Field(default="usd", description="Currency code (e.g., usd, mxn)")
    description: Optional[str] = Field(default="Recarga Wallet", description="Payment description")


class CreatePaymentIntentResponse(BaseModel):
    """Response model for payment intent creation."""
    client_secret: str
    payment_intent_id: str
    publishable_key: str


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


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhook events.
    
    This endpoint receives notifications from Stripe when payment events occur.
    It verifies the webhook signature and processes the event.
    
    Important events:
    - payment_intent.succeeded: Payment completed successfully
    - payment_intent.payment_failed: Payment failed
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
        user_id = payment_intent["metadata"].get("user_id")
        amount_cents = payment_intent["amount"]
        amount = amount_cents / 100  # Convert cents to dollars
        
        logger.info(f"✅ Payment succeeded: {payment_intent_id} for user {user_id}, amount: ${amount}")
        
        if not user_id:
            logger.error(f"No user_id in payment intent metadata: {payment_intent_id}")
            return
        
        # Update user wallet balance
        wallet_repo = WalletRepository()
        await wallet_repo.add_balance(user_id, amount, "stripe_recharge", payment_intent_id)
        
        logger.info(f"Wallet updated for user {user_id}: +${amount}")
        
    except Exception as e:
        logger.error(f"Error handling payment success: {e}")


async def handle_payment_failure(payment_intent: dict):
    """Handle failed payment."""
    try:
        payment_intent_id = payment_intent["id"]
        user_id = payment_intent["metadata"].get("user_id")
        error = payment_intent.get("last_payment_error", {})
        
        logger.error(f"❌ Payment failed: {payment_intent_id} for user {user_id}")
        logger.error(f"Error: {error.get('message', 'Unknown error')}")
        
        # TODO: Optionally notify user or log to database
        
    except Exception as e:
        logger.error(f"Error handling payment failure: {e}")


@router.get("/config")
async def get_stripe_config():
    """
    Get Stripe publishable key for client-side initialization.
    
    This is safe to expose publicly as it's the publishable key.
    """
    return {
        "publishable_key": settings.stripe_publishable_key
    }
