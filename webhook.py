from flask import Flask, request, abort
import os
import hmac
import hashlib
from paystackapi.paystack import Paystack
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Initialize clients
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
paystack = Paystack(secret_key=os.getenv("PAYSTACK_SECRET_KEY"))

@app.route("/webhook", methods=["POST"])
def paystack_webhook():
    payload = request.get_data(as_text=True)
    signature = request.headers.get("x-paystack-signature")
    secret_key = os.getenv("PAYSTACK_SECRET_KEY")

    # Verify it's really Paystack (manual HMAC per docs)
    expected_sig = hmac.new(
        secret_key.encode(),
        payload.encode(),
        hashlib.sha512
    ).hexdigest()
    
    if not hmac.compare_digest(signature or '', expected_sig):
        print(f"WEBHOOK SIG FAIL: Got {signature}, Expected {expected_sig[:10]}...")
        abort(400)

    event = request.get_json()
    print(f"WEBHOOK EVENT: {event}")  # Debug

    if event["event"] == "charge.success":
        ref = event["data"]["reference"]
        amount_paid = event["data"]["amount"] / 100  # Convert kobo to NGN

        # Mark trade as paid in Supabase
        result = supabase.table("trades")\
            .update({"status": "paid", "paid_at": "now()", "amount_paid": amount_paid})\
            .eq("paystack_ref", ref)\
            .execute()

        if result.data:
            print(f"VAULT LOCKED: {ref} – ₦{amount_paid:,.0f} held safely! 🔒")

    return "", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))