import os
import uuid
from operator import itemgetter  # For sorting
from paystackapi.paystack import Paystack
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# Initialize
app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
paystack = Paystack(secret_key=os.getenv("PAYSTACK_SECRET_KEY"))
WEBHOOK_URL = os.getenv("RAILWAY_URL") + "/webhook" if os.getenv("RAILWAY_URL") else "https://your-railway-url.up.railway.app/webhook"  # Fallback for local

# States
user_state = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("Buy USDT", callback_data="buy")],
        [InlineKeyboardButton("Sell USDT", callback_data="sell")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Welcome to @EscrowSule – Nigeria's Safest P2P Escrow 🔒\n\n"
        "100% Funds held until delivery.\n0.5% fee only on release.\n\nChoose:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "buy":
        user_state[user_id] = "awaiting_amount"
        await query.edit_message_text("How much NGN do you want to spend?\n\nExample: 50000")

    elif query.data == "sell":
        user_state[user_id] = "awaiting_wallet"
        await query.edit_message_text("Share your USDT wallet address for buyers to send to.\n\nExample: 0x742d35Cc...")

    elif query.data == "release":
        # Fetch pending paid trades for this seller
        trades = supabase.table("trades")\
            .select("*")\
            .eq("seller_id", user_id)\
            .eq("status", "paid")\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute().data

        if not trades:
            await query.edit_message_text("No paid trade ready for release. Check /start.")
            return

        trade = trades[0]
        amount = trade["amount"]

        # Update status to released
        supabase.table("trades").update({"status": "released"}).eq("id", trade["id"]).execute()

        fee = amount * 0.005
        net = amount - fee

        await query.edit_message_text(
            f"Funds Released! 🎉\n\n"
            f"₦{amount:,.0f} payout sent (bank transfer queued).\n"
            f"Escrow Fee (0.5%): ₦{fee:,.0f}\n"
            f"You Net: ₦{net:,.0f}\n\n"
            f"Thanks for trusting @EscrowSule!"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in user_state:
        await update.message.reply_text("Use /start first!")
        return

    if user_state[user_id] == "awaiting_amount":
        try:
            amount = float(text.replace(",", ""))
            if amount < 5000:
                await update.message.reply_text("Minimum is ₦5,000")
                return
        except ValueError:
            await update.message.reply_text("Send a valid number e.g. 50000")
            return

        # Simple seller match: Find first available seller (expand to real matching later)
        sellers = supabase.table("sellers").select("id, wallet").eq("available", True).limit(1).execute().data
        if not sellers:
            await update.message.reply_text("No sellers available right now. Try later!")
            user_state.pop(user_id, None)
            return
        seller = sellers[0]
        seller_id = seller["id"]
        wallet = seller["wallet"]

        # Generate unique reference
        ref = f"escrow_{user_id}_{uuid.uuid4().hex[:8]}"

        # Save trade
        trade_data = {
            "buyer_id": user_id,
            "seller_id": seller_id,
            "amount": amount,
            "paystack_ref": ref,
            "seller_wallet": wallet,
            "status": "pending"
        }
        supabase.table("trades").insert(trade_data).execute()

        # Initialize Paystack payment
        response = paystack.transaction.initialize(
            amount=int(amount * 100),  # kobo
            email=f"buyer_{user_id}@escrowsule.com",
            reference=ref,
            callback_url=WEBHOOK_URL
        )

        if response.get("status"):
            pay_url = response["data"]["authorization_url"]
            keyboard = [[InlineKeyboardButton("Pay Now 💳", url=pay_url)]]
            await update.message.reply_text(
                f"Trade Matched! Seller Wallet: `{wallet}`\n\n"
                f"Amount: ₦{amount:,.0f}\n"
                f"Reference: {ref}\n\n"
                f"Pay below – funds held until USDT sent to wallet above 🔒",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            user_state.pop(user_id, None)
        else:
            await update.message.reply_text(f"Payment setup failed: {response.get('message', 'Try again.')}")

    elif user_state[user_id] == "awaiting_wallet":
        # Save seller wallet (assume table 'sellers' exists; create if not)
        supabase.table("sellers").upsert({"id": user_id, "wallet": text, "available": True}).execute()
        keyboard = [[InlineKeyboardButton("Release Funds", callback_data="release")]]
        await update.message.reply_text(
            f"Wallet saved: `{text}`\n\n"
            "Awaiting buyer matches. Use /release when paid.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        user_state.pop(user_id, None)

# Commands
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("EscrowSule Bot Running... @EscrowSule")
app.run_polling()