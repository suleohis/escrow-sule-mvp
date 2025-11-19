from flask import Flask, request, abort
import os
from paystackapi.event import Event
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("x-paystack-signature")
    event = Event.verify_signature(payload, sig_header, PAYSTACK_SECRET)

    if event["event"] == "charge.success":
        ref = event["data"]["reference"]
        # Update trade status
        superbase.table("trades").update({"status": "paid"}).eq("paystack_ref", ref).execute()
        # Notify seller/buyer (add bot.send_message here if integrated)
        print(f"Payment confirmed: {ref} - Fund held! 🔒")
    
    return "", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))