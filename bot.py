import os
import asyncio
import threading
from datetime import datetime, timezone
from flask import Flask, jsonify, request, send_from_directory
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================================
# NIVA EXCHANGE
# ============================================================
BOT_TOKEN = "8892058742:AAG8MLSJiXUQKi9qS6FfVsLq9ao7kWLgn5I"
# Telegram Web App must use a trusted HTTPS URL.
# Set WEBAPP_URL in Bot-Hosting Environment Variables to your HTTPS domain.
# Example:
#   WEBAPP_URL=https://your-domain.example
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip().rstrip("/")

# Internal port supplied by the hosting environment.
# Bot-Hosting's app server should listen on 0.0.0.0:$PORT.
SERVER_PORT = int(os.getenv("PORT", os.getenv("SERVER_PORT", "8080")))
ADMIN_IDS = {7294314847}

# ============================================================
# FIREBASE
# ============================================================
FIREBASE_CREDENTIALS = {
    "type": "service_account",
    "project_id": "work-store-12def",
    "private_key_id": "a889eb47166bb695da41d7bb19630df66fee34f9",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDizMz0OixCoDrO\n2WAZSw8BbbzqvtsuP8PJdXg+Ze+H9UfZs+HzrkTHuljBS1B687xPtxAOUK42Mu1o\nGKMNlWnkEDbukbfD0WOjMXWjlsnghuFPVJOVi6it0FSAM4rMA6b4A9Hk/F51vToI\nEDlTb53r5y0F1U6BgzPt/DmlKmoGWlrf8COxNatkdA91VV+S+3eNBxyr7/UGfIz6\ndxJ2Q9SEFDxC3pT5MHbecxHNC7sB6fy7Rmcn+fJ37AjJTTEy0Q4dtpPAEqsWgdUV\nMNDY6NEiqSXS7/amw0GcRg3gxoPOy5EafBzzg4+BJGErijnHDpJmnZfU1WdbI5ZP\nPavZsvTLAgMBAAECggEAIk1tHu/g0No7esdC3csjQ7PiyQhrzcoZeny4s+CmrVlf\nmsw2UQJbEcWb9e7xBwpFQYiZC5PlUs+PZllPlAGKCKib06fDc6uq67xSeWxthSGG\nrgEclJeRFWo3KvALaUGQ0oiACaen68aJIpNoRY0nWqOA2kCBsAdK5o7pnb2qrTda\nrXkfS78U0J+OJRJbh8JD+jMIN4SA/NbNXfStmOu33MqQWknIY62N96rGHWB3yoDW\nYi0nckFHTu3JKe3QFpwoiopuryOvz8mwGWEDekUBBc8TXdbFPW9KR4ojDnSVypA0\n4C0NstNeIcv2KZnaVVy42ReO7fjks+2Yb5m9xFkkuQKBgQD5OX0aJyCOPWab7JtQ\n3kAj04SWzpVQuQo5v/jkv/uEG1ur+hvSO9LK7McN2L+Fcl2Sm6FZOcWEszXfEfQL\npnEE30pX+pjWtOHRsOhNM+gI4CAgnY7HHJPa8Y9TAzIlztXM6glJDt3Va4Sb/cBb\ncE3bGVw5QnvgiwQeZVg2vDX3EwKBgQDo9z7GJLB/3+uPP1Bc3RZQL/FjBeEZvKh5\ncPXlxNCZbymPmoeFsdXuPF6uvkqnwCWhhH0u5pscQgD30C1ShxzuBGdJQEtj0NF4\nY9HcXYgzvAsv+t+9ULTssx0toiPEyFVXFjbwQRAOnr65ibbpzgPzZr6bh+YSYJPi\n7SrdwkqqaQKBgAPm1ICOUEIpz+ts/tl7QUHOU+sQfOHwo6pXyQu7vbJJw1uj5L+b\n1Cb9IfijhgwOyEw9R39gGimDrLo7S7jK+EX9QOqzr6Tc3BQuUtSylVVePOKF1PBl\nECODWJ0SFbzlyg8VMuQD6ZEnx8GxbUuBLJbbhMgYtFvFkWDwcTsaIzYlAoGBAK2h\nYPLy821LKdjI2o9r5C59nQ4tmpjBCFwCufK3HrXMqRAznyAg7A40hmj8wM2II0Pfa\nCGllCOaefg4+x6QPxqSw5xPxCCvyP9OfmIcf9/3Hetzsn/5/+6OjIevWbNXkGto\nzieAhoQvAn1sS5y0hDNL93IZ9nrp6i7ujs1a+qVJAoGBALJFJEzzGhQOVFqu/RMO\n+Okme1Ursh1o3t9BYbsYDoP5q4t/Kegp2fLQmXcs+B8QU+ma02XqAgddb+mlXYh6\nmwaudfbRzQ05my7R4UvxYeFFdET8nUpeJRPof2Ayr9tmsqdigxyIY+FLhs6u1jVp\nQ01nup5KZ442wWVIAb/UoQ/x\n-----END PRIVATE KEY-----\n",
    "client_email": "firebase-adminsdk-fbsvc@work-store-12def.iam.gserviceaccount.com",
    "client_id": "107205163723631526842",
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
        print("❌ Firebase initialization failed:", exc)
        return None

init_firebase()

# ============================================================
# FLASK APP
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")

# Register panel blueprint
from panel import panel, set_database
set_database(db)
app.register_blueprint(panel)

@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")

@app.get("/api/config")
def api_config():
    return jsonify({"app_name": "NIVA EXCHANGE 💦", "firebase_ready": db is not None, "webapp_url_configured": WEBAPP_URL.startswith("https://")})

@app.post("/api/user")
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
    if db:
        db.collection("users").document(user_id).set(user_data, merge=True)
    return jsonify({"ok": True, "user": user_data})

@app.get("/api/coins")
def get_coins():
    default_coins = [
        {"id": "top", "name": "TOP COIN", "icon": "💗", "online": True},
        {"id": "ns", "name": "NS COIN", "icon": "🧑‍💻", "online": True},
        {"id": "niva", "name": "NIVA COIN", "icon": "", "online": True},
    ]
    if not db:
        return jsonify(default_coins)
    try:
        result = []
        for doc in db.collection("coins").stream():
            item = doc.to_dict()
            item["id"] = doc.id
            result.append(item)
        return jsonify(result or default_coins)
    except Exception as exc:
        print("Coin read error: ", exc)
        return jsonify(default_coins)

# ============================================================
# TELEGRAM BOT
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    keyboard = [[InlineKeyboardButton("💦 OPEN NIVA EXCHANGE", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.message.reply_text(
        "Welcome to NIVA EXCHANGE 💦\n\nOpen the Web App below.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def run_web():
    print(f"🌐 Flask listening on 0.0.0.0:{SERVER_PORT}")
    if WEBAPP_URL:
        print(f"🔗 Telegram Web App URL: {WEBAPP_URL}")
    else:
        print("⚠️ WEBAPP_URL is not configured.")
    app.run(
        host="0.0.0.0",
        port=SERVER_PORT,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


async def run_bot():
    if not BOT_TOKEN or BOT_TOKEN == "PUT_BOT_TOKEN_HERE":
        print("⚠️ Set BOT_TOKEN before starting the bot.")
        return
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
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