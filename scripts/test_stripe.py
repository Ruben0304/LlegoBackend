"""Script to test Stripe configuration."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import stripe
from core.config import settings


def test_stripe_keys():
    """Test if Stripe keys are configured."""
    print("🔍 Testing Stripe Configuration...\n")
    
    # Check if keys are set
    if not settings.stripe_secret_key or settings.stripe_secret_key == "sk_test_your_secret_key_here":
        print("❌ STRIPE_SECRET_KEY not configured")
        print("   Get it from: https://dashboard.stripe.com/apikeys")
        return False
    
    if not settings.stripe_publishable_key or settings.stripe_publishable_key == "pk_test_your_publishable_key_here":
        print("❌ STRIPE_PUBLISHABLE_KEY not configured")
        print("   Get it from: https://dashboard.stripe.com/apikeys")
        return False
    
    print(f"✅ Secret Key: {settings.stripe_secret_key[:12]}...")
    print(f"✅ Publishable Key: {settings.stripe_publishable_key[:12]}...")
    
    # Check key format
    if settings.stripe_secret_key.startswith("sk_test_"):
        print("ℹ️  Using TEST mode keys")
    elif settings.stripe_secret_key.startswith("sk_live_"):
        print("⚠️  Using LIVE mode keys")
    else:
        print("❌ Invalid Secret Key format")
        return False
    
    return True


async def test_stripe_api():
    """Test Stripe API connection."""
    print("\n🔍 Testing Stripe API Connection...\n")
    
    try:
        stripe.api_key = settings.stripe_secret_key
        
        # Try to create a test payment intent
        payment_intent = stripe.PaymentIntent.create(
            amount=1000,  # $10.00
            currency="usd",
            description="Test payment intent",
            metadata={
                "test": "true"
            },
            automatic_payment_methods={
                "enabled": True,
            },
        )
        
        print(f"✅ Payment Intent created: {payment_intent.id}")
        print(f"   Amount: ${payment_intent.amount / 100:.2f}")
        print(f"   Status: {payment_intent.status}")
        print(f"   Client Secret: {payment_intent.client_secret[:20]}...")
        
        # Cancel the test payment intent
        stripe.PaymentIntent.cancel(payment_intent.id)
        print(f"✅ Test Payment Intent cancelled")
        
        return True
        
    except stripe.error.AuthenticationError as e:
        print(f"❌ Authentication Error: {e}")
        print("   Check your STRIPE_SECRET_KEY")
        return False
    except stripe.error.StripeError as e:
        print(f"❌ Stripe Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        return False


def test_webhook_secret():
    """Test webhook secret configuration."""
    print("\n🔍 Testing Webhook Configuration...\n")
    
    if not settings.stripe_webhook_secret or settings.stripe_webhook_secret == "whsec_your_webhook_secret_here":
        print("⚠️  STRIPE_WEBHOOK_SECRET not configured")
        print("   This is optional for testing but required for production")
        print("   Get it from: https://dashboard.stripe.com/webhooks")
        return False
    
    print(f"✅ Webhook Secret: {settings.stripe_webhook_secret[:15]}...")
    return True


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Stripe Configuration Test")
    print("=" * 60)
    
    # Test 1: Keys configuration
    keys_ok = test_stripe_keys()
    
    if not keys_ok:
        print("\n❌ Configuration incomplete. Please set up your Stripe keys.")
        print("\nSteps:")
        print("1. Go to https://dashboard.stripe.com/apikeys")
        print("2. Copy your Secret Key and Publishable Key")
        print("3. Add them to your .env file:")
        print("   STRIPE_SECRET_KEY=sk_test_...")
        print("   STRIPE_PUBLISHABLE_KEY=pk_test_...")
        return
    
    # Test 2: API connection
    api_ok = await test_stripe_api()
    
    # Test 3: Webhook secret
    webhook_ok = test_webhook_secret()
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Keys Configuration: {'✅' if keys_ok else '❌'}")
    print(f"API Connection: {'✅' if api_ok else '❌'}")
    print(f"Webhook Secret: {'✅' if webhook_ok else '⚠️  (optional for testing)'}")
    
    if keys_ok and api_ok:
        print("\n✅ Stripe is configured correctly!")
        print("\nNext steps:")
        print("1. Start your backend: uvicorn main:app --reload")
        print("2. Test the endpoint: POST /stripe/create-payment-intent")
        print("3. Configure webhook: https://dashboard.stripe.com/webhooks")
    else:
        print("\n❌ Please fix the errors above")


if __name__ == "__main__":
    asyncio.run(main())
