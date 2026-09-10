import os
import uuid
import asyncio
import threading
from datetime import datetime, timezone
from flask import Flask, jsonify, request, send_from_directory
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ============================================================
# NIVA EXCHANGE - CONFIGURATION
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8892058742:AAG8MLSJiXUQKi9qS6FfVsLq9ao7kWLgn5I")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://joyboss556699-byte.github.io/Niva-exchange-/")
SERVER_PORT = int(os.getenv("PORT", os.getenv("SERVER_PORT", "22464")))
ADMIN_IDS = {int(os.getenv("ADMIN_ID", "7294314847"))}

# ============================================================
# FIREBASE
# ============================================================
FIREBASE_CREDENTIALS = {
    "type": "service_account",
    "project_id": os.getenv("FIREBASE_PROJECT_ID", "work-store-12def"),
    "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID", "a889eb47166bb695da41d7bb19630df66fee34f9"),
    "private_key": os.getenv("FIREBASE_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDizMz0OixCoDrO\n2WAZSw8BbbzqvtsuP8PJdXg+Ze+H9UfZs+HzrkTHuljBS1B687xPtxAOUK42Mu1o\nGKMNlWnkEDbukbfD0WOjMXWjlsnghuFPVJOVi6it0FSAM4rMA6b4A9Hk/F51vToI\nEDlTb53r5y0F1U6BgzPt/DmlKmoGWlrf8COxNatkdA91VV+S+3eNBxyr7/UGfIz6\ndxJ2Q9SEFDxC3pT5MHbecxHNC7sB6fy7Rmcn+fJ37AjJTTEy0Q4dtpPAEqsWgdUV\nMNDY6NEiqSXS7/amw0GcRg3gxoPOy5EafBzzg4+BJGErijnHDpJmnZfU1WdbI5ZP\nPavZsvTLAgMBAAECggEAIk1tHu/g0No7esdC3csjQ7PiyQhrzcoZeny4s+CmrVlf\nmsw2UQJbEcWb9e7xBwpFQYiZC5PlUs+PZllPlAGKCKib06fDc6uq67xSeWxthSGG\nrgEclJeRFWo3KvALaUGQ0oiACaen68aJIpNoRY0nWqOA2kCBsAdK5o7pnb2qrTda\nrXkfS78U0J+OJRJbh8JD+jMIN4SA/NbNXfStmOu33MqQWknIY62N96rGHWB3yoDW\nYi0nckFHTu3JKe3QFpwoiopuryOvz8mwGWEDekUBBc8TXdbFPW9KR4ojDnSVypA0\n4C0NstNeIcv2KZnaVVy42ReO7fjks+2Yb5m9xFkkuQKBgQD5OX0aJyCOPWab7JtQ\n3kAj04SWzpVQuQo5v/jkv/uEG1ur+hvSO9LK7McN2L+Fcl2Sm6FZOcWEszXfEfQL\npnEE30pX+pjWtOHRsOhNM+gI4CAgnY7HHJPa8Y9TAzIlztXM6glJDt3Va4Sb/cBb\ncE3bGVw5QnvgiwQeZVg2vDX3EwKBgQDo9z7GJLB/3+uPP1Bc3RZQL/FjBeEZvKh5\ncPXlxNCZbymPmoeFsdXuPF6uvkqnwCWhhH0u5pscQgD30C1ShxzuBGdJQEtj0NF4\nY9HcXYgzvAsv+t+9ULTssx0toiPEyFVXFjbwQRAOnr65ibbpzgPzZr6bh+YSYJPi\n7SrdwkqqaQKBgAPm1ICOUEIpz+ts/tl7QUHOU+sQfOHwo6pXyQu7vbJJw1uj5L+b\n1Cb9IfijhgwOyEw9R39gGimDrLo7S7jK+EX9QOqzr6Tc3BQuUtSylVVePOKF1PBl\nECODWJ0SFbzlyg8VMuQD6ZEnx8GxbUuBLJbbhMgYtFvFkWDwcTsaIzYlAoGBAK2h\nYPLy821LKdjI2o9r5C59nQ4tmpjBCFwCufK3HrXMqRAznyAg7A40hmj8wM2II0Pfa\nCGllCOaefg4+x6QPxqSw5xPxCCvyP9OfmIcf9/3Hetzsn/5/+6OjIevWbNXkGto\nzieAhoQvAn1sS5y0hDNL93IZ9nrp6i7ujs1a+qVJAoGBALJFJEzzGhQOVFqu/RMO\n+Okme1Ursh1o3t9BYbsYDoP5q4t/Kegp2fLQmXcs+B8QU+ma02XqAgddb+mlXYh6\nmwaudfbRzQ05my7R4UvxYeFFdET8nUpeJRPof2Ayr9tmsqdigxyIY+FLhs6u1jVp\nQ01nup5KZ442wWVIAb/UoQ/x\n-----END PRIVATE KEY-----\n"),
    "client_email": os.getenv("FIREBASE_CLIENT_EMAIL", "firebase-adminsdk-fbsvc@work-store-12def.iam.gserviceaccount.com"),
    "client_id": os.getenv("FIREBASE_CLIENT_ID", "107205163723631526842"),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40work-store-12def.iam.gserviceaccount.com",
    "universe_domain": "googleapis.com",
}

db = None

def init_firebase():
    global db
    if firebase_admin._apps:
        db = firestore.client()
        return db
    try:
        cred = credentials.Certificate(FIREBASE_CREDENTIALS)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firebase connected successfully!")
        return db
    except Exception as exc:
        print(" Firebase initialization failed:", exc)
        return None

init_firebase()

# ============================================================
# FILE UPLOADS (order screenshots, coin icons)
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
ORDERS_UPLOAD_DIR = os.path.join(UPLOADS_DIR, "orders")
COINS_UPLOAD_DIR = os.path.join(UPLOADS_DIR, "coins")
PAYMENTS_UPLOAD_DIR = os.path.join(UPLOADS_DIR, "payments")
os.makedirs(ORDERS_UPLOAD_DIR, exist_ok=True)
os.makedirs(COINS_UPLOAD_DIR, exist_ok=True)
os.makedirs(PAYMENTS_UPLOAD_DIR, exist_ok=True)
ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "gif"}

def save_upload(file_storage, folder):
    """Save an uploaded image safely, return its public URL path or None."""
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in ALLOWED_IMAGE_EXT:
        return None
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(os.path.join(folder, filename))
    subfolder = "orders" if folder == ORDERS_UPLOAD_DIR else ("payments" if folder == PAYMENTS_UPLOAD_DIR else "coins")
    return f"/uploads/{subfolder}/{filename}"

# ============================================================
# FLASK APP
# ============================================================
app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")

# The WebApp is commonly hosted on GitHub Pages while this Flask server
# handles the API/uploads. Allow the WebApp origin to call this backend.
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Telegram-User-Id"
    response.headers["Access-Control-Expose-Headers"] = "Content-Type"
    return response

# Register panel blueprint
from panel import panel, set_database, DEFAULT_COINS, DEFAULT_PAYMENT_METHODS, DEFAULT_BRANDING
set_database(db)
app.register_blueprint(panel)

@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")

@app.get("/uploads/<subfolder>/<path:filename>")
def serve_upload(subfolder, filename):
    folder = ORDERS_UPLOAD_DIR if subfolder == "orders" else (PAYMENTS_UPLOAD_DIR if subfolder == "payments" else COINS_UPLOAD_DIR)
    return send_from_directory(folder, filename)

@app.get("/api/system-status")
def get_system_status():
    """Get current system status (enabled/disabled)"""
    try:
        if db:
            doc = db.collection("system").document("status").get()
            if doc.exists:
                return jsonify({"ok": True, "status": doc.to_dict()})
        return jsonify({"ok": True, "status": {"enabled": True}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/api/config")
def get_config():
    """Public config: coin rates, payment methods, and branding.
    Pass ?uid=<telegram id> to apply that user's custom rate override, if any."""
    try:
        coins = DEFAULT_COINS
        payment_methods = DEFAULT_PAYMENT_METHODS
        branding = DEFAULT_BRANDING

        if db:
            coins_doc = db.collection("system").document("coins").get()
            if coins_doc.exists and coins_doc.to_dict().get("list"):
                coins = coins_doc.to_dict()["list"]

            payments_doc = db.collection("system").document("payments").get()
            if payments_doc.exists and payments_doc.to_dict().get("list"):
                payment_methods = payments_doc.to_dict()["list"]

            branding_doc = db.collection("system").document("branding").get()
            if branding_doc.exists:
                branding = {**DEFAULT_BRANDING, **branding_doc.to_dict()}

            uid = request.args.get("uid", "")
            if uid.isdigit():
                user_doc = db.collection("users").document(uid).get()
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    custom_rates = user_data.get("custom_rates") or {}
                    if custom_rates:
                        coins = [
                            {**c, **custom_rates[c["id"]]} if c.get("id") in custom_rates else c
                            for c in coins
                        ]

        # Normalize the admin's simple price/rate format into the WebApp tier format.
        normalized_coins = []
        for coin in coins:
            c = dict(coin)
            unit = float(c.get("unit") or c.get("rate") or 1000)
            c["unit"] = unit
            if not isinstance(c.get("tiers"), list) or not c.get("tiers"):
                c["tiers"] = [{"min": 1, "max": None, "price": float(c.get("price", 0))}]
            c.setdefault("requiresCoupon", False)
            c.setdefault("requiresUsername", not bool(c.get("requiresCoupon")))
            c.setdefault("targetUsername", "")
            normalized_coins.append(c)
        binance_rate = 125.0
        transfer_id = ""
        if db:
            cfg_doc = db.collection("system").document("config").get()
            if cfg_doc.exists:
                cfg = cfg_doc.to_dict() or {}
                try: binance_rate = float(cfg.get("binanceRate", 125.0) or 125.0)
                except Exception: pass
                transfer_id = str(cfg.get("transferId", "") or "")
        return jsonify({"ok": True, "coins": normalized_coins, "paymentMethods": payment_methods, "branding": branding, "binanceRate": binance_rate, "transferId": transfer_id, "sendFee": 0})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/user", methods=["GET", "POST"])
def save_user():
    data = request.get_json(silent=True) or {}
    user = data.get("user") or {}
    user_id = str(user.get("id", "")).strip()
    if not user_id:
        return jsonify({"ok": False, "error": "Telegram user ID required"}), 400

    user_data = {
        "telegram_id": int(user_id),
        "username": user.get("username", ""),
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    blocked = False
    if db:
        existing = db.collection("users").document(user_id).get()
        if existing.exists:
            blocked = bool(existing.to_dict().get("blocked", False))
        if request.method == "POST":
            db.collection("users").document(user_id).set(user_data, merge=True)
        else:
            if existing.exists:
                user_data = {**existing.to_dict(), **user_data}
        pending_count = approved_count = 0
        for od in db.collection("orders").stream():
            o = od.to_dict()
            if str(o.get("user_id", "")) == user_id:
                status = str(o.get("status", "pending"))
                pending_count += status == "pending"
                approved_count += status == "approved"
    else:
        pending_count = approved_count = 0

    return jsonify({"ok": True, "user": user_data, "blocked": blocked, "pending_count": int(pending_count), "approved_count": int(approved_count)})

@app.post("/api/order")
def create_order():
    try:
        data = request.form
        user_id = str(data.get("user_id", ""))

        if db:
            status_doc = db.collection("system").document("status").get()
            if status_doc.exists and not status_doc.to_dict().get("enabled", True):
                return jsonify({"ok": False, "error": "System is currently disabled"}), 403

            if user_id.isdigit():
                user_doc = db.collection("users").document(user_id).get()
                if user_doc.exists and user_doc.to_dict().get("blocked"):
                    return jsonify({"ok": False, "error": "আপনার অ্যাকাউন্টটি ব্লক করা হয়েছে।"}), 403

        screenshot_url = save_upload(request.files.get("screenshot"), ORDERS_UPLOAD_DIR)

        total_amount = float(data.get("total_amount", 0))
        payment_method = str(data.get("payment_method", ""))
        binance_rate = 125.0
        if db:
            cfg_doc = db.collection("system").document("config").get()
            if cfg_doc.exists:
                try: binance_rate = float(cfg_doc.to_dict().get("binanceRate", 125.0) or 125.0)
                except Exception: pass
        usdt_amount = (total_amount / binance_rate) if payment_method == "binance" and binance_rate > 0 else 0

        order_data = {
            "user_id": user_id,
            "username": data.get("username"),
            "instagram_username": data.get("instagram_username"),
            "coin": data.get("coin"),
            "quantity": int(data.get("quantity", 0)),
            "price_per_rate": float(data.get("price_per_rate", 0)),
            "total_amount": total_amount,
            "payment_method": payment_method,
            "binance_rate": binance_rate if payment_method == "binance" else 0,
            "usdt_amount": usdt_amount,
            "account_number": data.get("account_number"),
            "coupon_code": data.get("coupon_code", ""),
            "target_username": data.get("target_username", ""),
            "sender_username": data.get("sender_username", data.get("instagram_username")),
            "screenshot_url": screenshot_url,
            "timestamp": data.get("timestamp"),
            "status": "pending",
        }

        order_id = None
        if db:
            _, doc_ref = db.collection("orders").add(order_data)
            order_id = doc_ref.id

        if order_id:
            notify_admin_new_order(order_id, order_data)

        return jsonify({"ok": True, "message": "Order created successfully", "order_id": order_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ============================================================
# TELEGRAM BOT
# ============================================================
BOT_LOOP = None
BOT_APP = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    keyboard = [[InlineKeyboardButton("💦 OPEN NIVA EXCHANGE", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.message.reply_text(
        "Welcome to NIVA EXCHANGE 💦\n\nOpen the Web App below.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def on_order_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    if not update.effective_user or update.effective_user.id not in ADMIN_IDS:
        await query.answer("Admin only.", show_alert=True)
        return

    try:
        action, order_id = query.data.split(":", 1)
    except ValueError:
        return

    decision = "approved" if action == "order_approve" else "rejected" if action == "order_reject" else None
    if not decision or not order_id:
        return

    process_order_decision(order_id, decision)
    label = "✅ APPROVED" if decision == "approved" else "❌ REJECTED"
    try:
        new_caption = (query.message.caption or query.message.text or "") + f"\n\n{label} by admin"
        if query.message.caption is not None:
            await query.edit_message_caption(caption=new_caption)
        else:
            await query.edit_message_text(text=new_caption)
    except Exception as e:
        print("Edit message error:", e)

def process_order_decision(order_id, decision):
    """Update order status in Firestore and notify the buyer. decision: 'approved' | 'rejected'"""
    if not db:
        return {"ok": False, "error": "Database not connected"}
    try:
        order_ref = db.collection("orders").document(order_id)
        order_doc = order_ref.get()
        if not order_doc.exists:
            return {"ok": False, "error": "Order not found"}

        order_data = order_doc.to_dict()
        order_ref.update({"status": decision})

        user_id = order_data.get("user_id")
        coin = order_data.get("coin", "")
        quantity = order_data.get("quantity", 0)
        total = order_data.get("total_amount", 0)

        if user_id:
            if decision == "approved":
                text = (f"✅ আপনার অর্ডার (কয়েন: {coin}, পরিমাণ: {quantity}, "
                        f"মোট: {total} টাকা) অ্যাডমিন গ্রহণ করেছেন। শীঘ্রই পেমেন্ট পাঠানো হবে।")
            else:
                text = (f"❌ আপনার অর্ডার (কয়েন: {coin}, পরিমাণ: {quantity}) "
                        f"অ্যাডমিন প্রত্যাখ্যান করেছেন। বিস্তারিত জানতে Help Line-এ যোগাযোগ করুন।")
            notify_user(user_id, text)

        return {"ok": True, "status": decision}
    except Exception as e:
        return {"ok": False, "error": str(e)}

async def _send_message(chat_id, text, reply_markup=None):
    if not BOT_APP:
        return
    await BOT_APP.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)

async def _send_photo(chat_id, photo_path, caption, reply_markup=None):
    if not BOT_APP:
        return
    with open(photo_path, "rb") as f:
        await BOT_APP.bot.send_photo(chat_id=chat_id, photo=f, caption=caption, reply_markup=reply_markup)

def _run_coro(coro):
    if not BOT_LOOP:
        print("Bot loop not ready; message not sent.")
        return
    try:
        fut = asyncio.run_coroutine_threadsafe(coro, BOT_LOOP)
        fut.result(timeout=20)
    except Exception as e:
        print("Telegram send error:", e)

def notify_user(telegram_id, text):
    try:
        _run_coro(_send_message(int(telegram_id), text))
    except Exception as e:
        print("notify_user error:", e)

def notify_admin_new_order(order_id, order_data):
    caption = (
        f"🆕 নতুন সেল অর্ডার\n\n"
        f"Order ID: {order_id}\n"
        f"User: @{order_data.get('username') or '—'} (ID: {order_data.get('user_id')})\n"
        f"Instagram: {order_data.get('instagram_username')}\n"
        f"Coin: {order_data.get('coin')}\n"
        f"Quantity: {order_data.get('quantity')}\n"
        f"Total: {order_data.get('total_amount')} টাকা\n"
        f"Payment: {order_data.get('payment_method')} → {order_data.get('account_number')}\n"
        f"Coupon: {order_data.get('coupon_code') or '—'}\n"
        f"Target: {order_data.get('target_username') or '—'}"
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"order_approve:{order_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"order_reject:{order_id}"),
    ]])

    screenshot_url = order_data.get("screenshot_url")
    screenshot_path = None
    if screenshot_url:
        screenshot_path = os.path.join(BASE_DIR, screenshot_url.lstrip("/"))

    for admin_id in ADMIN_IDS:
        try:
            if screenshot_path and os.path.exists(screenshot_path):
                _run_coro(_send_photo(admin_id, screenshot_path, caption, keyboard))
            else:
                _run_coro(_send_message(admin_id, caption, keyboard))
        except Exception as e:
            print("notify_admin_new_order error:", e)

def send_broadcast(text):
    """Send a message to every known user. Returns (sent_count, failed_count)."""
    if not db:
        return 0, 0
    sent, failed = 0, 0
    for doc in db.collection("users").stream():
        uid = doc.to_dict().get("telegram_id")
        if not uid:
            continue
        try:
            _run_coro(_send_message(uid, text))
            sent += 1
        except Exception:
            failed += 1
    return sent, failed

def run_web():
    print(f"🌐 Flask listening on 0.0.0.0:{SERVER_PORT}")
    if WEBAPP_URL:
        print(f"🔗 Telegram Web App URL: {WEBAPP_URL}")
    else:
        print("️ WEBAPP_URL is not configured.")
    app.run(host="0.0.0.0", port=SERVER_PORT, debug=False, use_reloader=False, threaded=True)

async def run_bot():
    global BOT_LOOP, BOT_APP
    if not BOT_TOKEN or BOT_TOKEN == "PUT_BOT_TOKEN_HERE":
        print("⚠️ Set BOT_TOKEN before starting the bot.")
        return

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(on_order_decision, pattern=r"^order_(approve|reject):"))

    BOT_APP = application
    BOT_LOOP = asyncio.get_running_loop()

    print("✅ Telegram bot started")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    try:
        await asyncio.Event().wait()
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

def main():
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(run_bot())

if __name__ == "__main__":
    main()
