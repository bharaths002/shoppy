"""
Razorpay integration utilities.
In TEST MODE — uses Razorpay's test API keys (free, no real money moves).
Switch to LIVE keys later — no code changes needed, just .env values change.
"""
import razorpay
from django.conf import settings


def get_razorpay_client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_razorpay_order(amount_in_rupees, receipt_id):
    """
    Creates a Razorpay order. Amount must be in paise (1 rupee = 100 paise).
    Returns the Razorpay order object.
    """
    client = get_razorpay_client()
    amount_in_paise = int(amount_in_rupees * 100)

    razorpay_order = client.order.create({
        "amount": amount_in_paise,
        "currency": "INR",
        "receipt": receipt_id,
        "payment_capture": 1  # auto-capture payment
    })
    return razorpay_order


def verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
    """
    Verifies the payment signature sent back by Razorpay after checkout.
    This MUST be done server-side — never trust frontend claims of payment success.
    """
    client = get_razorpay_client()
    params_dict = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature
    }
    try:
        client.utility.verify_payment_signature(params_dict)
        return True
    except razorpay.errors.SignatureVerificationError:
        return False