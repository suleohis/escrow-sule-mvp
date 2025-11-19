import os
import time
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import paystack
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Init clients
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
paystack.secret_key = os.getenv("PAYSTACK_SECRET_KEY")  # Use TEST for now: sk_test_...

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🛒 I Want to Buy USDT", callback_data="role_buyer")],
        [InlineKeyboardButton("💰 I Want to Sell USDT", callback_data="role_seller")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🇳🇬 Welcome to @EscrowSule – Safest P2P Escrow in Nigeria!\n\n"
        "🔒 Money held until you get your USDT.\n"
        "💸 Only 0.5% fee.\n\n"
        "Buying or Selling USDT? Pick below:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "role_buyer":
        await query.edit_message_text("Enter amount in NGN (e.g., 50000):")
        context.user_data['role'] = 'buyer'
        context.user_data['waiting_for'] = 'amount'
    elif query.data == "role_seller":
        await query.edit_message_text(
            "Enter amount in NGN & your bank details:\n"
            "Format: 50000 | Zenith | 1234567890"
        )
        context.user_data['role'] = 'seller'
        context.user_data['waiting_for'] = 'seller_details'
    # Add more callbacks for wallet/bank collection later

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    chat_id = update.message.chat_id

    if context.user_data.get('waiting_for') == 'amount' and context.user_data.get('role') == 'buyer':
        try:
            amount = int(text)
            # Generate Paystack ref
            ref = f"escrow_{chat_id}_{int(time.time())}"
            # Initialize transaction (for payment link)
            response = paystack.transaction.initialize(
                amount=amount * 100,  # Kobo
                email=f"buyer_{user_id}@vaultp2p.com",
                reference=ref,
                callback_url=os.getenv("RAILWAY_URL", "https://your-app.railway.app") + "/webhook"
            )
            if response.get("status"):
                pay_link = response["data"]["authorization_url"]
                # Save pending trade to Supabase
                data = {
                    "chat_id": chat_id,
                    "buyer_id": user_id,
                    "seller_id": None,  # Will match later via group chat or manual
                    "amount_ngn": amount,
                    "status": "pending_payment",
                    "paystack_ref": ref
                }
                supabase.table("trades").insert(data).execute()
                
                keyboard = [[InlineKeyboardButton("💳 Pay Now", url=pay_link)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"Pay ₦{amount:,} to buy USDT.\n"
                    "After payment, share proof with seller. We'll hold funds! 🔒",
                    reply_markup=reply_markup
                )
                context.user_data['trade_ref'] = ref
            else:
                await update.message.reply_text("Payment init failed. Try again.")
        except ValueError:
            await update.message.reply_text("Invalid amount. Enter numbers only.")
        context.user_data['waiting_for'] = None

    # Seller details handler (simplified for MVP – expand to full matching)
    elif context.user_data.get('waiting_for') == 'seller_details':
        parts = text.split('|')
        if len(parts) == 3:
            amount, bank_name, account = parts[0].strip(), parts[1].strip(), parts[2].strip()
            await update.message.reply_text(f"Got it! Amount: ₦{amount:,} | Bank: {bank_name} | Acct: {account}\nShare this ad in Binance groups: 'Selling {amount/1600:.2f} USDT via @EscrowSule'")
            # Save seller info (match to buyer later via /match command or chat_id)
        context.user_data['waiting_for'] = None

async def release(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Fetch active trade for seller
    result = supabase.table("trades").select("*").eq("seller_id", user_id).eq("status", "paid").execute()
    if not result.data:
        await update.message.reply_text("No active trade to release. Use /start.")
        return

    trade = result.data[0]
    amount = trade["amount_ngn"]
    fee = int(amount * 0.005)  # 0.5%
    payout = amount - fee

    # For MVP: Simulate payout (use Paystack Transfer API for live)
    # transfer = Transfer.create(recipient="seller_recipient_code", amount=payout * 100)
    
    # Update status
    supabase.table("trades").update({"status": "released"}).eq("id", trade["id"]).execute()
    
    await update.message.reply_text(
        f"✅ Released! Seller gets ₦{payout:,} (fee: ₦{fee:,}).\n"
        "USDT confirmed? Buyer, rate us! 🚀"
    )
    # Notify buyer
    await context.bot.send_message(trade["chat_id"], "Funds released to seller. Check your USDT! 💸")

# Admin command for disputes (add your Telegram ID)
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_ADMIN_ID:  # Replace with your Telegram user ID
        return
    pending = supabase.table("trades").select("*").eq("status", "paid").gt("created_at", "now() - interval '24 hours'").execute()
    await update.message.reply_text(f"Pending trades: {len(pending.data)}\nUse /release or /refund [id]")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("release", release))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()