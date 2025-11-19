from flask import Flask, request, abort
import os
import paystack  # Just import the whole package
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Set secret key globally (official way)
paystack.secret_key = os.getenv("PAYSTACK_SECRET_KEY")

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("x-paystack-signature")

    # Verify signature (official method)
    if not paystack.webhook.verify_signature(payload, sig_header):
        abort(401)

    event = request.json
    if event.get("event") == "charge.success":
        ref = event["data"]["reference"]
        supabase.table("trades").update({"status": "paid"}).eq("paystack_ref", ref).execute()
        print(f"✅ VaultP2P: Payment confirmed {ref} – ₦ held tight! 🔒")

    return "", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))