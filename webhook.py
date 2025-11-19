from flask import Flask, request, abort
import os
import hmac
import hashlib
from paystack import Transaction, Event  # Official import – Event is top-level
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")  # sk_test_... or live

@app.route("/webhook", methods=["POST"])
def webhook():
    # Get raw payload for signature verification
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("x-paystack-signature")

    # Verify it's from Paystack (prevents fakes)
    try:
        Event.verify_signature(payload, sig_header, PAYSTACK_SECRET)
    except Exception:
        abort(401)  # Unauthorized – kill bad requests

    # Parse event
    event = request.json
    if event["event"] == "charge.success":
        ref = event["data"]["reference"]
        # Update Supabase trade status
        supabase.table("trades").update({"status": "paid"}).eq("paystack_ref", ref).execute()
        print(f"✅ Payment confirmed: {ref} – Funds held in vault! 🔒")
        # TODO: Notify buyer/seller via bot (add asyncio bot.send_message later)

    return "", 200  # Ack to Paystack – no retry

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))