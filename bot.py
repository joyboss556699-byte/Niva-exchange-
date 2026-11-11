# bot.py - Social Media Task Bot
# SPEED OPTIMIZED BUILD — cache↑ middleware↓ polling fast webhook ready

import os
import hashlib
import logging
import asyncio
import re
import random
import string
import csv
import io
import json
import time
from datetime import datetime
from functools import wraps
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import ParseMode


# ==================== লগিং ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== বট কনফিগারেশন ====================
API_TOKEN = (
    os.getenv("BOT_TOKEN")
    or os.getenv("API_TOKEN")
    or os.getenv("TELEGRAM_BOT_TOKEN")
)
if not API_TOKEN:
    raise RuntimeError(
        "Telegram bot token missing. Set BOT_TOKEN in Render Environment Variables."
    )

ADMIN_ID = int(os.getenv("ADMIN_ID", "7294314847"))

# ==================== SPEED: Simple in-memory cache ====================
class SimpleCache:
    """Very lightweight TTL cache. Avoids repeated Firestore reads."""
    def __init__(self):
        self._store = {}

    def get(self, key, default=None):
        item = self._store.get(key)
        if item is None:
            return default
        value, expires = item
        if expires and time.time() > expires:
            self._store.pop(key, None)
            return default
        return value

    def set(self, key, value, ttl=120):
        expires = time.time() + ttl if ttl else None
        self._store[key] = (value, expires)

    def delete(self, key):
        self._store.pop(key, None)

    def clear(self):
        self._store.clear()

cache = SimpleCache()

def escape_md(s):
    """Escape Telegram legacy Markdown special characters."""
    s = str(s or "")
    for ch in ["\\", "`", "*", "_", "[", "]"]:
        s = s.replace(ch, "\\" + ch)
    return s

async def safe_answer(message, text, reply_markup=None, parse_mode=ParseMode.MARKDOWN):
    """Send message; if Markdown fails, retry without parse_mode."""
    try:
        return await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        logger.warning(f"safe_answer markdown fail: {e}")
        try:
            # strip common markdown markers for plain fallback
            plain = str(text or "").replace("**", "").replace("__", "").replace("`", "")
            return await message.answer(plain, reply_markup=reply_markup, parse_mode=None)
        except Exception as e2:
            logger.error(f"safe_answer plain fail: {e2}")
            return None

async def safe_edit(message, text, reply_markup=None, parse_mode=ParseMode.MARKDOWN):
    try:
        return await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        logger.warning(f"safe_edit markdown fail: {e}")
        try:
            plain = str(text or "").replace("**", "").replace("__", "").replace("`", "")
            return await message.edit_text(plain, reply_markup=reply_markup, parse_mode=None)
        except Exception as e2:
            logger.error(f"safe_edit plain fail: {e2}")
            return None

# ইন-মেমোরি: 2FA অপেক্ষমাণ ইউজার (Firestore read কমায়)
PENDING_TASK_USERS = set()
BOT_USERNAME_CACHE = {"value": None}

def mark_pending_task(user_id):
    PENDING_TASK_USERS.add(user_id)

def clear_pending_task(user_id):
    PENDING_TASK_USERS.discard(user_id)
    # ব্যাকগ্রাউন্ডে ডিলিট — রেসপন্স ব্লক করবে না
    def _bg_del():
        try:
            db.collection('temp_tasks').document(str(user_id)).delete()
            db.collection('temp_2fa').document(str(user_id)).delete()
        except Exception:
            pass
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(asyncio.to_thread(_bg_del))
    except Exception:
        try:
            _bg_del()
        except Exception:
            pass

# ==================== Firebase সেটআপ ====================
import firebase_admin
from firebase_admin import credentials, firestore

FIREBASE_SERVICE_ACCOUNT = {
    'type': 'service_account',
    'project_id': 'social-media-task-88c67',
    'private_key_id': 'b26508ca424fc852a3e387c4b1679e9772687547',
    'private_key': '-----BEGIN PRIVATE KEY-----\nMIIEuwIBADANBgkqhkiG9w0BAQEFAASCBKUwggShAgEAAoIBAQDwQLQzjbCaAvQT\n1kh5EBvCsY6Eawmni/R8lo3PVF+5RITDwFjc8Bw0jTqJMwZV8jaw3NZLXOwanIUv\nDg95/tfknqWYWX2ebME+OLJZ1HddU2jesemAncjDKzqt2IWdbYdxFcTm/0HUp0FW\n9evkua10zgPdRc4i17AeiRk0KQrRItRK7jW11AeOcHa1/gVzqQb9TAekThp5fvp1\nwvDkxRE7kpntcBUgwzpSFJi6ZwwvVW6CP9ECnFqYq6FDNdQBsT6Tb8T2cm0tBrfQ\nXHkFwJJX7Z0Q7/jJuCSyMpWw/G9aqBJoztEXMgCZGBrUmzd9BUuWi1Rvm26KDp9V\n+DlmAS0XAgMBAAECgf9nO2YywK8hfiNiYrDBVCqZfbG/ND7xvzFOV2KXs6lt8gMa\nGYwVYxa7ffOpAEO4qlrVpA5wU30f8iFIFsKPqPEbSw/cZpeTeyeNlM8Nyj1/3Fcz\nWT78BNA/DFQqXt8KxgVske4JU6T1uuhYdVLm9OGTTvJaIaRxVDxY4o/x2bDMK1Xs\ncIVIRnm9GRJ1A35GUvYwdkxS4Qd0MCPK5hyVVm5K7ETzHH3QqPHeUD22x4xtS19J\nzTDATDgxIOyiIM7Q5Jg9ckS26QiKMjPRX11HadAemQnGYg7TUtTFbEgvvfLzl6nP\nAXviQbIwG7do9F9rXSnGW8rpFrVH8GgFTmHY/KECgYEA+H+UDB/C7D0qyO4L6oqN\nHPA9jcO1+ai25zuq/dZbCuG46d2RZhYw81L6Q03b/klQoM5vOl9oMfsIGwZoVtgC\nLietvXK3oNlsfANZbyyOsQerfo+UTBip81jEyw2oPJ5ZhoERouPZ+mmFprK39h4m\ny6JUKEzsAX1Fw25cRav5Gv8CgYEA94FnF52GCKqzgEVrPSYLEr9FMjryEhPEXb6o\ndpate5M1eIEFOIWQgkaltxsKcX2oLhd7sUdN07HGKbNfFJDHtVkLUZzp7jAozA8q\nLZGRFZnGaBxOGZaRUbXtqvcOEIosiKUEpSX76TlWKsfjwtPYfU3D0L7jg3ZVORbS\n3mxfZekCgYBOqryodemUNez0fP+CuWfg0GD8HwfdyD5Wx3njL9fUgw6x4nWkFsRa\nU1tssRpCztzae1+U4B0xLWIshAPF8k4GZINI5ScioZIJVFocqsNlYaM1xqhQysIK\nioCKM4Gd5xc6UGPP6EfaUUuBMTSxkmv/rRztQSS5d/n821QUrlOG6wKBgQCWouRq\nxA3CkpojNJzbH59Xrp/fvW59QBigcZy4aGZ3spW1nNjfmLLmBzdupP+LKU5FlzdK\nIzqj4CvaT3hL3P4fSm2QI29g72C1KXmjOFhUDD5sOOXzvub9EzvudOTTfjUyiTS1\nitOyE5p0+SmO9z5orP7Duppf9ZJS56g5hT3emQKBgHJjG/5rOUvtAdr15EYyX1dq\nLvfyR/a0J97OvS5W96ktxM15+WdmWKBayW+hsU49rkz+Ru6uBSyGoW9grT3+Zd+O\n8NiRJ/RKsid99ONDmX+r02l06sfqiFmYqtNwAGAcNRSnTQyal5ewqojAmyrcU2yy\nrbm497rYfiMro+x3eBaP\n-----END PRIVATE KEY-----\n',
    'client_email': 'firebase-adminsdk-fbsvc@social-media-task-88c67.iam.gserviceaccount.com',
    'client_id': '105355804467417364326',
    'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
    'token_uri': 'https://oauth2.googleapis.com/token',
    'auth_provider_x509_cert_url': 'https://www.googleapis.com/oauth2/v1/certs',
    'client_x509_cert_url': 'https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40social-media-task-88c67.iam.gserviceaccount.com',
    'universe_domain': 'googleapis.com',
}

cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT)
firebase_admin.initialize_app(cred)
db = firestore.client()

print("✅ Firebase Connected!")

# ==================== Google Sheets সেটআপ ====================
import gspread
from google.oauth2.service_account import Credentials

GSHEETS_CRED_PATH = "credentials.json"
SHEET_ID = os.getenv("SHEET_ID", "1Oa3STRM-wtkqTg30NkMGqQiSaNRHi3uFMx4CQWd6IzA")

GOOGLE_SERVICE_ACCOUNT = FIREBASE_SERVICE_ACCOUNT

_gsheet_client = None
_gsheet_last_init = 0

def get_google_sheet():
    """Cache the gspread client for a few minutes to avoid re-auth every time."""
    global _gsheet_client, _gsheet_last_init
    try:
        now = time.time()
        if _gsheet_client is None or (now - _gsheet_last_init) > 1800:
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = Credentials.from_service_account_info(GOOGLE_SERVICE_ACCOUNT, scopes=scope)
            client = gspread.authorize(creds)
            _gsheet_client = client.open_by_key(SHEET_ID).sheet1
            _gsheet_last_init = now
        return _gsheet_client
    except Exception as e:
        logger.error(f"Google Sheets Error: {type(e).__name__}: {e}")
        _gsheet_client = None
        return None

# ==================== ডেটা সেভ সেটিংস (Google Sheet / Local CSV আলাদাভাবে ON/OFF) ====================

SETTINGS_FILE = "bot_settings.json"
CSV_FILE = "task_data.csv"
CSV_HEADERS = ["Serial", "User ID", "Username", "Full Name", "Password", "Cookies", "2FA Key", "Task Type", "Reward", "Status", "Time"]

def load_settings():
    default = {"sheet_sync_enabled": True, "csv_sync_enabled": True}
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default.update(data)
    except Exception as e:
        logger.error(f"Settings Load Error: {e}")
    return default

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Settings Save Error: {e}")

bot_settings = load_settings()

def is_sheet_sync_enabled():
    return bot_settings.get("sheet_sync_enabled", True)

def is_csv_sync_enabled():
    return bot_settings.get("csv_sync_enabled", True)

def toggle_sheet_sync():
    bot_settings["sheet_sync_enabled"] = not is_sheet_sync_enabled()
    save_settings(bot_settings)
    return bot_settings["sheet_sync_enabled"]

def toggle_csv_sync():
    bot_settings["csv_sync_enabled"] = not is_csv_sync_enabled()
    save_settings(bot_settings)
    return bot_settings["csv_sync_enabled"]

def _ensure_csv_file():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            writer.writerow(CSV_HEADERS)

def save_to_csv(user_id, username, password, full_name, twofa_key, twofa_code, task_type, reward=0, cookies=""):
    try:
        _ensure_csv_file()
        with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
            row_count = sum(1 for _ in f)
        serial = row_count
        safe_cookies = str(cookies).replace("\r", " ").replace("\n", " ") if cookies else ""
        # শুধু 2FA Key সেভ — code জেনারেট/অ্যাপেন্ড নয়
        safe_2fa = str(twofa_key or "").replace("\r", " ").replace("\n", " ")
        safe_password = str(password or "").replace("\r", " ").replace("\n", " ")
        row = [
            f"#{serial:03d}",
            str(user_id),
            str(username or ""),
            str(full_name or ""),
            safe_password,
            safe_cookies,
            safe_2fa,
            str(task_type or ""),
            str(reward),
            "pending",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ]
        with open(CSV_FILE, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL, escapechar='\\')
            writer.writerow(row)
        return f"#{serial:03d}"
    except Exception as e:
        logger.error(f"CSV Save Error: {type(e).__name__}: {e}")
        return "#001"

def reset_csv_data():
    try:
        with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            writer.writerow(CSV_HEADERS)
        return True
    except Exception as e:
        logger.error(f"CSV Reset Error: {e}")
        return False


def rebuild_csv_from_firestore(force=False):
    """
    Render/VPS restart-এ local CSV মুছে গেলে Firestore থেকে আবার বানায়।
    force=False হলে শুধু CSV খালি/নেই হলে rebuild করে।
    """
    try:
        existing_count = 0
        if os.path.exists(CSV_FILE) and not force:
            try:
                with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
                    existing_count = max(0, sum(1 for _ in f) - 1)
            except Exception:
                existing_count = 0
            if existing_count > 0:
                logger.info(f"CSV already has {existing_count} rows — skip rebuild")
                return existing_count

        rows = []
        seen = set()
        for status in ("pending", "approved", "cancelled", "rejected"):
            try:
                stream = db.collection("submissions").where("status", "==", status).limit(500).stream()
            except Exception as e:
                logger.warning(f"rebuild CSV stream {status}: {e}")
                continue
            for d in stream:
                s = d.to_dict() or {}
                uid_val = str(s.get("uid") or s.get("username") or "")
                user_id = str(s.get("user_id") or "")
                key = (user_id, uid_val, str(s.get("password") or ""), str(s.get("status") or status))
                if key in seen:
                    continue
                seen.add(key)
                submitted = s.get("submitted_at")
                if hasattr(submitted, "strftime"):
                    time_str = submitted.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    time_str = str(submitted or "")
                rows.append({
                    "User ID": user_id,
                    "Username": uid_val,
                    "Full Name": str(s.get("full_name") or ""),
                    "Password": str(s.get("password") or ""),
                    "Cookies": str(s.get("cookies") or "").replace("\r", " ").replace("\n", " "),
                    "2FA Key": str(s.get("twofa_key") or ""),
                    "Task Type": str(s.get("task_type") or s.get("task_id") or ""),
                    "Reward": str(s.get("reward") or 0),
                    "Status": str(s.get("status") or status),
                    "Time": time_str,
                })

        with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL, escapechar='\\')
            writer.writerow(CSV_HEADERS)
            for i, r in enumerate(rows, 1):
                writer.writerow([
                    f"#{i:03d}",
                    r["User ID"],
                    r["Username"],
                    r["Full Name"],
                    r["Password"],
                    r["Cookies"],
                    r["2FA Key"],
                    r["Task Type"],
                    r["Reward"],
                    r["Status"],
                    r["Time"],
                ])
        logger.info(f"✅ CSV rebuilt from Firestore: {len(rows)} rows")
        return len(rows)
    except Exception as e:
        logger.error(f"rebuild_csv_from_firestore error: {e}")
        _ensure_csv_file()
        return 0


def save_task_submission(user_id, username, password, full_name, twofa_key, twofa_code, task_type, reward=0, cookies=""):
    """
    ২টা সিস্টেম আলাদাভাবে on/off — Google Sheet আর Local CSV।
    Sheet-এ লেখা ব্যাকগ্রাউন্ডে (fire-and-forget) হয়, তাই বট স্লো হয় না।
    সিরিয়াল নম্বর CSV থেকে (দ্রুততম, লোকাল) রিটার্ন করা হয়।
    সবসময় Firestore submissions-এও থাকে (restart-safe)।
    """
    serial = "#001"
    # CSV সবসময় অন রাখার চেষ্টা — ডেটা হারানো কমাতে
    if is_csv_sync_enabled():
        serial = save_to_csv(user_id, username, password, full_name, twofa_key, twofa_code, task_type, reward, cookies)
    else:
        # csv off থাকলেও serial দরকার
        serial = f"#{datetime.now().strftime('%H%M%S')}"
    if is_sheet_sync_enabled():
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                asyncio.to_thread(save_to_google_sheets, user_id, username, password, full_name, twofa_key, twofa_code, task_type, reward, cookies)
            )
        except Exception:
            try:
                asyncio.create_task(
                    asyncio.to_thread(save_to_google_sheets, user_id, username, password, full_name, twofa_key, twofa_code, task_type, reward, cookies)
                )
            except Exception:
                pass
    return serial

# ==================== বট ইনিশিয়ালাইজ ====================
# ===== SPEED: Telegram HTTP session tuned =====
try:
    from aiogram.bot.api import TelegramAPIServer
except Exception:
    TelegramAPIServer = None
try:
    from aiogram.bot.session import BaseSession
except Exception:
    pass

bot = Bot(token=API_TOKEN, parse_mode=None)
# Larger timeout budget only for long ops; default sends stay snappy
try:
    bot.session.timeout = 12
except Exception:
    pass
dp = Dispatcher(bot)
# LoggingMiddleware disabled for SPEED (less overhead per update)

# ===== INSTANT BUTTON FEEDBACK (no spinning loader) =====
try:
    from aiogram.dispatcher.middlewares import BaseMiddleware
except Exception:
    BaseMiddleware = object

class InstantCallbackMiddleware(BaseMiddleware):
    """Answer every callback immediately so Telegram stops the loading spinner."""
    async def on_pre_process_callback_query(self, callback_query, data):
        data["cb_answered"] = False
        # If handler needs show_alert, it should answer itself first with alert.
        # We only pre-answer when data does not look like copy/alert-only shortcuts.
        raw = (callback_query.data or "")
        # Let copy alert & permission alerts answer themselves first with text
        if raw.startswith("cp2fa_"):
            return
        try:
            await callback_query.answer()
            data["cb_answered"] = True
            # mark on object for handlers
            try:
                callback_query.conf = getattr(callback_query, "conf", {}) or {}
            except Exception:
                pass
            callback_query._answered = True
        except Exception:
            data["cb_answered"] = False


async def cb_answer(callback, text=None, show_alert=False):
    """Safe answer — skip if already answered (unless alert needed and not answered)."""
    if getattr(callback, "_answered", False) and not show_alert:
        return
    if getattr(callback, "_answered", False) and show_alert:
        # already answered empty — send a chat message instead of alert
        if text:
            try:
                await callback.message.answer(text)
            except Exception:
                pass
        return
    try:
        await callback.answer(text=text, show_alert=show_alert)
        callback._answered = True
    except Exception:
        if show_alert and text:
            try:
                await callback.message.answer(text)
            except Exception:
                pass

try:
    dp.middleware.setup(InstantCallbackMiddleware())
except Exception as e:
    print("InstantCallbackMiddleware setup failed:", e)


# ==================== ইউজার স্টেট ====================
user_states = {}
temp_data = {}

# ==================== গ্লোবাল ভেরিয়েবল ====================
WITHDRAW_METHODS = ["বিকাশ", "নগদ", "রকেট", "ব্যাংক"]
MIN_WITHDRAW = 50.0
WITHDRAW_GROUP = ""
# Binance USDT: 126 BDT = 1 USDT (display + convert)
USDT_RATE_BDT = 126.0

FORCE_CHANNELS = []
REFERRAL_COMMISSION_PERCENT = 10.0
SUPPORT_CONTACT = "@admin_username"
SUPPORT_ADMIN_LINK = ""
SUPPORT_CHANNEL_LINK = ""
PASSWORD_LENGTH = 8
PASSWORD_SIMPLE = True
FIXED_PASSWORD = ""
GUIDE_VIDEO = ""
GUIDE_BUTTONS = []
ADMIN_LIST = [ADMIN_ID]

# মেনু বাটন টেক্সট — state চলাকালীন চাপলে state ক্লিয়ার হবে
MENU_BUTTON_TEXTS = {
    "📱 কাজ", "📋 Tasks ▸", "📊 আমার রিপোর্ট", "📊 Report", "👤 Profile", "👤 প্রোফাইল",
    "💸 টাকা উত্তোলন", "💸 Withdraw", "🔗 রেফারেল", "🔗 Referral",
    "🛠 সাপোর্ট", "🛠 Support", "🌐 Language / ভাষা",
    "🎛️ অ্যাডমিন প্যানেল", "🎛️ Admin Panel", "❌ প্রধান মেনু", "❌ Main Menu",
    "Admin Panel", "অ্যাডমিন প্যানেল", "Tasks ▸", "Report", "Profile", "প্রোফাইল", "Withdraw",
    "Referral", "Support", "Language / ভাষা",
}

# ==================== অটো ইউজারনেম জেনারেটর ====================

def generate_username():
    first_names = ['kiara', 'elizabeth', 'sophia', 'olivia', 'emma', 'mia', 'chloe', 'zara', 'luna', 'ella',
                   'liam', 'noah', 'oliver', 'elijah', 'james', 'william', 'benjamin', 'lucas', 'henry', 'alexander']
    last_names = ['thomas', 'rocha', 'smith', 'johnson', 'williams', 'brown', 'jones', 'miller', 'wilson', 'moore',
                  'taylor', 'anderson', 'thompson', 'white', 'harris', 'martin', 'jackson', 'lee', 'perez', 'roberts']
    
    first = random.choice(first_names)
    last = random.choice(last_names)
    number = random.randint(10, 999)
    username = f"{first}_{last}{number}".lower()
    
    # Firestore uniqueness skip — collision অত্যন্ত কম; writeও skip (speed)
    return username

def generate_password(task_fixed_password=""):
    # টাস্ক-নির্দিষ্ট password আগে, তারপর গ্লোবাল FIXED_PASSWORD
    if task_fixed_password:
        return str(task_fixed_password)
    if FIXED_PASSWORD:
        return FIXED_PASSWORD
    if PASSWORD_SIMPLE:
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(PASSWORD_LENGTH))
    letters = string.ascii_letters
    digits = string.digits
    special = "!@#$%^&*"
    all_chars = letters + digits + special
    password = ''.join(random.choice(all_chars) for _ in range(PASSWORD_LENGTH))
    while not (any(c.isupper() for c in password) and any(c.islower() for c in password) and any(c.isdigit() for c in password) and any(c in special for c in password)):
        password = ''.join(random.choice(all_chars) for _ in range(PASSWORD_LENGTH))
    return password

def generate_full_name():
    first_names = ['Kiara', 'Elizabeth', 'Sophia', 'Olivia', 'Emma', 'Mia', 'Chloe', 'Zara', 'Luna', 'Ella',
                   'Liam', 'Noah', 'Oliver', 'Elijah', 'James', 'William', 'Benjamin', 'Lucas', 'Henry', 'Alexander']
    last_names = ['Thomas', 'Rocha', 'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Miller', 'Wilson', 'Moore',
                  'Taylor', 'Anderson', 'Thompson', 'White', 'Harris', 'Martin', 'Jackson', 'Lee', 'Perez', 'Roberts']
    return f"{random.choice(first_names)} {random.choice(last_names)}"

def generate_vietnamese_full_name():
    """Threads টাস্কের জন্য ভিয়েতনামি নাম (diacritics সহ)"""
    names = [
        "Nguyễn Văn An", "Trần Minh Đức", "Lê Hoàng Nam", "Phạm Quốc Huy", "Hoàng Gia Bảo",
        "Nguyễn Thị Linh", "Trần Ngọc Anh", "Lê Thị Mai", "Phạm Thu Hà", "Võ Minh Khang",
        "Nguyễn Hoàng Long", "Trần Văn Đức", "Lê Minh Anh", "Phạm Gia Huy", "Hoàng Thị Lan",
        "Nguyễn Ngọc Bảo", "Trần Thu Hà", "Lê Quốc Bảo", "Phạm Minh Châu", "Vũ Hoàng Nam",
        "Nguyễn Thị Hoa", "Trần Gia Bảo", "Lê Văn Khoa", "Phạm Ngọc Linh", "Hoàng Minh Đức",
        "Đặng Văn An", "Bùi Thị Mai", "Đỗ Hoàng Nam", "Ngô Minh Khang", "Dương Ngọc Anh",
        "Nguyễn Quốc Huy", "Trần Hoàng Long", "Lê Thị Hương", "Phạm Văn Tùng", "Hoàng Thu Trang",
        "Võ Thị Yến", "Nguyễn Minh Châu", "Trần Quốc Bảo", "Lê Gia Huy", "Phạm Hoàng Nam",
    ]
    return random.choice(names)

# ==================== অ্যাডমিন লিস্ট (CACHED) ====================

def load_admins():
    global ADMIN_LIST
    try:
        doc = db.collection('settings').document('admins').get()
        if doc.exists:
            ADMIN_LIST = doc.to_dict().get('list', [ADMIN_ID])
        cache.set("admins", ADMIN_LIST, ttl=300)
    except Exception:
        pass

load_admins()

def get_admins():
    cached = cache.get("admins")
    if cached is not None:
        return cached
    load_admins()
    return ADMIN_LIST

def is_admin(user_id):
    return user_id in get_admins()

def add_admin(user_id):
    admins = get_admins()
    if user_id not in admins:
        admins.append(user_id)
        db.collection('settings').document('admins').set({'list': admins})
        cache.set("admins", admins, ttl=300)
        return True
    return False

def remove_admin(user_id):
    admins = get_admins()
    if user_id in admins and user_id != ADMIN_ID:
        admins.remove(user_id)
        db.collection('settings').document('admins').set({'list': admins})
        cache.set("admins", admins, ttl=300)
        return True
    return False

# ==================== উইথড্র সেটিংস (CACHED) ====================

WITHDRAW_ENABLED = True

def load_withdraw_settings():
    global MIN_WITHDRAW, WITHDRAW_METHODS, WITHDRAW_GROUP, WITHDRAW_ENABLED, USDT_RATE_BDT
    try:
        doc = db.collection('settings').document('withdraw').get()
        if doc.exists:
            data = doc.to_dict()
            MIN_WITHDRAW = data.get('min_withdraw', 50.0)
            WITHDRAW_METHODS = data.get('methods', ["বিকাশ", "নগদ", "রকেট", "ব্যাংক"])
            WITHDRAW_GROUP = data.get('group', "")
            WITHDRAW_ENABLED = data.get('enabled', True)
            USDT_RATE_BDT = float(data.get('usdt_rate_bdt', USDT_RATE_BDT) or 126.0)
        cache.set("withdraw_settings", True, ttl=600)
    except Exception:
        pass

def save_withdraw_settings():
    try:
        db.collection('settings').document('withdraw').set({
            'min_withdraw': MIN_WITHDRAW,
            'methods': WITHDRAW_METHODS,
            'group': WITHDRAW_GROUP,
            'enabled': WITHDRAW_ENABLED,
            'usdt_rate_bdt': USDT_RATE_BDT
        })
        cache.delete("withdraw_settings")
    except Exception:
        pass

load_withdraw_settings()

# ==================== ফোর্স জয়েন (CACHED) ====================

def normalize_channel(ch):
    """
    যেকোনো ফরম্যাট → Telegram API-র জন্য চ্যাট রেফ:
    https://t.me/xxx  /  t.me/xxx  /  @xxx  /  xxx  → @xxx
    """
    s = str(ch or "").strip()
    if not s:
        return s
    s = re.sub(r'^https?://', '', s, flags=re.I)
    s = re.sub(r'^t\.me/', '', s, flags=re.I)
    s = s.split('?')[0].split('/')[0].strip()
    if not s:
        return str(ch).strip()
    if s.lstrip("-").isdigit():
        return s
    return f"@{s.lstrip('@')}"


def channel_join_url(ch):
    n = normalize_channel(ch)
    if not n:
        return None
    if n.lstrip("-").isdigit():
        return None
    return f"https://t.me/{n.lstrip('@')}"


def load_force_channels():
    global FORCE_CHANNELS
    try:
        doc = db.collection('settings').document('force_join').get()
        if doc.exists:
            raw = doc.to_dict().get('channels', []) or []
            # পুরনো URL ফরম্যাট অটো ঠিক
            FORCE_CHANNELS = []
            seen = set()
            for ch in raw:
                n = normalize_channel(ch)
                if n and n not in seen:
                    seen.add(n)
                    FORCE_CHANNELS.append(n)
        cache.set("force_channels", FORCE_CHANNELS, ttl=300)
    except Exception:
        pass

def save_force_channels():
    try:
        # সেভের আগে নরমালাইজ
        cleaned = []
        seen = set()
        for ch in FORCE_CHANNELS:
            n = normalize_channel(ch)
            if n and n not in seen:
                seen.add(n)
                cleaned.append(n)
        FORCE_CHANNELS[:] = cleaned
        db.collection('settings').document('force_join').set({'channels': FORCE_CHANNELS})
        cache.set("force_channels", FORCE_CHANNELS, ttl=300)
    except Exception:
        pass

load_force_channels()

# ==================== এক্সট্রা সেটিংস (CACHED) ====================

def load_extra_settings():
    global REFERRAL_COMMISSION_PERCENT, SUPPORT_CONTACT, SUPPORT_ADMIN_LINK, SUPPORT_CHANNEL_LINK
    global PASSWORD_LENGTH, PASSWORD_SIMPLE, FIXED_PASSWORD, GUIDE_VIDEO
    try:
        doc = db.collection('settings').document('extra').get()
        if doc.exists:
            data = doc.to_dict()
            REFERRAL_COMMISSION_PERCENT = data.get('referral_commission', 10.0)
            SUPPORT_CONTACT = data.get('support_contact', "@admin_username")
            SUPPORT_ADMIN_LINK = data.get('support_admin_link', "")
            SUPPORT_CHANNEL_LINK = data.get('support_channel_link', "")
            PASSWORD_LENGTH = data.get('password_length', 8)
            PASSWORD_SIMPLE = data.get('password_simple', True)
            FIXED_PASSWORD = data.get('fixed_password', "")
            GUIDE_VIDEO = data.get('guide_video', "")
        cache.set("extra_settings", True, ttl=600)
    except Exception:
        pass

def save_extra_settings():
    try:
        db.collection('settings').document('extra').set({
            'referral_commission': REFERRAL_COMMISSION_PERCENT,
            'support_contact': SUPPORT_CONTACT,
            'support_admin_link': SUPPORT_ADMIN_LINK,
            'support_channel_link': SUPPORT_CHANNEL_LINK,
            'password_length': PASSWORD_LENGTH,
            'password_simple': PASSWORD_SIMPLE,
            'fixed_password': FIXED_PASSWORD,
            'guide_video': GUIDE_VIDEO
        })
        cache.delete("extra_settings")
    except Exception:
        pass

load_extra_settings()

# ==================== কাস্টম গাইড বাটন (মাল্টি ভিডিও) ====================

def load_guide_buttons():
    global GUIDE_BUTTONS
    try:
        doc = db.collection('settings').document('guide_buttons').get()
        if doc.exists:
            GUIDE_BUTTONS = doc.to_dict().get('buttons', [])
        cache.set("guide_buttons", GUIDE_BUTTONS, ttl=600)
    except Exception:
        pass

def save_guide_buttons():
    try:
        db.collection('settings').document('guide_buttons').set({'buttons': GUIDE_BUTTONS})
        cache.set("guide_buttons", GUIDE_BUTTONS, ttl=600)
    except Exception:
        pass

load_guide_buttons()

PENDING_GUIDE_BUTTON = {}

async def check_force_join(user_id, force_refresh=False):
    channels = cache.get("force_channels")
    if channels is None:
        load_force_channels()
        channels = FORCE_CHANNELS
    if not channels:
        return True
    if is_admin(user_id):
        return True
    ck = f"force_join:{user_id}"
    if not force_refresh:
        cached = cache.get(ck)
        if cached is not None:
            return cached

    async def _one(ch):
        chat_ref = normalize_channel(ch)
        try:
            member = await bot.get_chat_member(chat_ref, user_id)
            return member.status not in ('left', 'kicked')
        except Exception as e:
            logger.warning(f"Force join check fail ({chat_ref}): {e}")
            # চ্যাট রেফ ভুল হলে ইউজারকে ব্লক না করে False — join মেসেজ দেখাবে
            return False

    results = await asyncio.gather(*[_one(ch) for ch in channels], return_exceptions=True)
    ok = all(r is True for r in results)
    cache.set(ck, ok, ttl=30)
    return ok


async def require_force_join(message, user_id):
    """প্রতি ক্লিকে ফ্রেশ চেক — ছেড়ে দিলে সঙ্গে সঙ্গে Join চাইবে"""
    try:
        cache.delete(f"force_join:{user_id}")
        if await check_force_join(user_id, force_refresh=True):
            return True
    except Exception as e:
        logger.error(f"require_force_join check error: {e}")

    # লিংক টেক্সট নয় — শুধু নির্দেশ + বাটন
    text = (
        "⚠️ **বট ব্যবহার করতে আগে চ্যানেলে জয়েন করুন**\n\n"
        "1️⃣ **Join Channel** বাটনে জয়েন করুন\n"
        "2️⃣ তারপর **✅ Verify** চাপুন"
    )
    kb = get_force_join_keyboard()
    try:
        await message.answer(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        try:
            await message.answer(
                "⚠️ বট ব্যবহার করতে আগে চ্যানেলে জয়েন করুন\n\n"
                "1) Join Channel বাটনে জয়েন করুন\n"
                "2) তারপর Verify চাপুন",
                reply_markup=kb
            )
        except Exception as e2:
            logger.error(f"require_force_join send error: {e2}")
    return False


def get_force_join_keyboard():
    """শুধু Join + Verify বাটন — লিংক হাইড, রঙিন"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    channels = FORCE_CHANNELS or []
    if not channels:
        load_force_channels()
        channels = FORCE_CHANNELS or []
    for idx, ch in enumerate(channels):
        url = channel_join_url(ch)
        label = "📢 Join Channel" if len(channels) == 1 else f"📢 Join Channel {idx + 1}"
        try:
            if url:
                keyboard.add(colored_button(label, url=url, style="primary"))
            else:
                keyboard.add(colored_button(label, callback_data="force_join_info", style="primary"))
        except Exception:
            try:
                if url:
                    keyboard.add(InlineKeyboardButton(label, url=url))
                else:
                    keyboard.add(InlineKeyboardButton(label, callback_data="force_join_info"))
            except Exception:
                pass
    try:
        keyboard.add(colored_button("✅ Verify / যাচাই করুন", callback_data="force_join_verify", style="success"))
    except Exception:
        keyboard.add(InlineKeyboardButton("✅ Verify / যাচাই করুন", callback_data="force_join_verify"))
    return keyboard


def get_force_join_message(user_id):
    """Force join মেসেজ — লিংক ছাড়া শুধু নির্দেশ"""
    return (
        "⚠️ **বট ব্যবহার করতে আগে চ্যানেলে জয়েন করুন**\n\n"
        "1️⃣ **Join Channel** বাটনে জয়েন করুন\n"
        "2️⃣ তারপর **✅ Verify** চাপুন"
    )

# ==================== Firebase ফাংশন (CACHED + FAST) ====================

def get_user(user_id):
    """Cache user data – biggest speed win."""
    key = f"user:{user_id}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        doc = db.collection('users').document(str(user_id)).get()
        if doc.exists:
            data = doc.to_dict()
            cache.set(key, data, ttl=180)
            return data
    except Exception as e:
        logger.error(f"Get User Error: {e}")
    return None

def invalidate_user_cache(user_id):
    cache.delete(f"user:{user_id}")


def get_user_display(user_id, user=None):
    """@username দেখাবে; না থাকলে নাম, শেষে ID — newline/স্পেস ক্লিন"""
    if user is None:
        user = get_user(user_id) or {}
    uname = user.get('username')
    if uname and str(uname).strip() and str(uname).strip() != str(user_id):
        clean = str(uname).replace("\n", "").replace("\r", "").replace("\\n", "").strip().lstrip("@")
        if clean:
            return f"@{clean}"
    name = user.get('first_name')
    if name and str(name).strip():
        return str(name).replace("\n", "").replace("\r", "").replace("\\n", "").strip()
    return str(user_id)

def create_user(user_id, username, first_name, lang='bn'):
    user_data = {
        'user_id': user_id,
        'username': username or str(user_id),
        'first_name': first_name,
        'balance': 0.0,
        'pending_balance': 0.0,
        'total_earned': 0.0,
        'total_tasks': 0,
        'approved_tasks': 0,
        'pending_tasks': 0,
        'rejected_tasks': 0,
        'referral_code': f"REF_{user_id}",
        'referred_by': None,
        'ref_notify': True,
        'total_refers': 0,
        'refer_income': 0.0,
        'is_banned': False,
        'lang': lang,
        'joined_at': firestore.SERVER_TIMESTAMP
    }
    db.collection('users').document(str(user_id)).set(user_data)
    cache.set(f"user:{user_id}", user_data, ttl=300)
    return user_data

def update_balance(user_id, amount):
    try:
        user_ref = db.collection('users').document(str(user_id))
        user_ref.update({
            'balance': firestore.Increment(amount),
            'total_earned': firestore.Increment(amount) if amount > 0 else firestore.Increment(0)
        })
        invalidate_user_cache(user_id)
        return True
    except Exception as e:
        logger.error(f"Update Balance Error: {e}")
        return False

async def credit_task_approval(target_id, base_reward):
    user = get_user(target_id) or {}
    # Personal fixed base (Tk) for ALL tasks — e.g. 1 means always Tk 1
    custom_base = user.get("custom_base_reward", None)
    if custom_base is not None:
        try:
            cb = float(custom_base)
            if cb >= 0:
                actual_reward = cb
            else:
                actual_reward = float(base_reward or 0)
        except (TypeError, ValueError):
            actual_reward = float(base_reward or 0)
    else:
        # Legacy percent rate (100 = normal)
        try:
            custom_rate = float(user.get("custom_rate", 100) or 100)
        except (TypeError, ValueError):
            custom_rate = 100.0
        actual_reward = float(base_reward or 0) * (custom_rate / 100.0)
    update_balance(target_id, actual_reward)
    
    referrer_id = (user or {}).get('referred_by')
    if referrer_id:
        commission = actual_reward * (REFERRAL_COMMISSION_PERCENT / 100.0)
        if commission > 0:
            try:
                db.collection('users').document(str(referrer_id)).update({
                    'balance': firestore.Increment(commission),
                    'refer_income': firestore.Increment(commission)
                })
                invalidate_user_cache(referrer_id)
                try:
                    ref_user = get_user(referrer_id) or {}
                    if ref_user.get("ref_notify", True) is not False:
                        await bot.send_message(
                            referrer_id,
                            "🎉 আপনার রেফার করা একজনের টাস্ক অ্যাপ্রুভ হয়েছে!" + chr(10) +
                            f"💵 কমিশন পেয়েছেন: Tk {commission:.2f}"
                        )
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Referral Commission Credit Error: {e}")
    
    return actual_reward

def get_balance(user_id):
    user = get_user(user_id)
    return user['balance'] if user else 0.0

def get_active_tasks():
    """Cache active tasks – tasks rarely change."""
    cached = cache.get("active_tasks")
    if cached is not None:
        return cached
    try:
        docs = db.collection('tasks').where('is_active', '==', True).stream()
        tasks = [doc.to_dict() for doc in docs]
        tasks.sort(key=lambda t: t.get('created_at') or datetime.min)
        cache.set("active_tasks", tasks, ttl=120)
        return tasks
    except Exception as e:
        logger.error(f"Get Active Tasks Error: {e}")
        return []


def normalize_fb_uid(uid):
    """Facebook UID normalize — only digits/letters kept, strip spaces."""
    s = str(uid or "").strip()
    s = s.replace(" ", "").replace("\n", "").replace("\r", "")
    return s


def normalize_report_username(value):
    s = str(value or "").strip().lstrip("@").lower()
    s = s.replace(" ", "").replace("\n", "").replace("\r", "")
    return s


def get_task_account_name(sub_data=None, csv_username=None, extra=None):
    """
    টাস্ক অ্যাকাউন্টের username/UID — কখনোই Telegram name নয়।
    Priority: csv_username → submission uid → submission username → extra
    """
    candidates = []
    if csv_username:
        candidates.append(csv_username)
    if isinstance(sub_data, dict):
        candidates.append(sub_data.get("uid"))
        candidates.append(sub_data.get("username"))
    if extra:
        candidates.append(extra)
    for c in candidates:
        s = str(c or "").strip().lstrip("@")
        # skip empty / pure telegram-looking fallback markers
        if not s:
            continue
        if s.lower() in ("none", "n/a", "null"):
            continue
        return s
    return "account"


def is_username_already_reported(username):
    """Username already used in a previous Upload Report."""
    uname = normalize_report_username(username)
    if not uname or len(uname) < 2:
        return False
    try:
        doc = db.collection("reported_usernames").document(uname[:150]).get()
        if doc.exists:
            return True
    except Exception as e:
        logger.warning(f"reported_usernames check: {e}")
    return False

def mark_username_reported(username, meta=None):
    uname = normalize_report_username(username)
    if not uname:
        return
    try:
        data = {
            "username": uname,
            "reported_at": firestore.SERVER_TIMESTAMP,
        }
        if meta:
            data.update(meta)
        db.collection("reported_usernames").document(uname[:150]).set(data, merge=True)
    except Exception as e:
        logger.warning(f"mark reported username: {e}")

def is_facebook_uid_used(uid):
    """True if this Facebook UID was already submitted (any user/status)."""
    uid = normalize_fb_uid(uid)
    if not uid or len(uid) < 5:
        return False
    try:
        docs = list(
            db.collection("submissions")
            .where("uid", "==", uid)
            .limit(1)
            .stream()
        )
        if docs:
            return True
    except Exception as e:
        logger.warning(f"uid used query: {e}")
    # also try as int if pure digits
    if uid.isdigit():
        try:
            docs = list(
                db.collection("submissions")
                .where("uid", "==", int(uid))
                .limit(1)
                .stream()
            )
            if docs:
                return True
        except Exception:
            pass
    # CSV fallback
    try:
        if os.path.exists(CSV_FILE):
            with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    row_uid = normalize_fb_uid(row.get("Username") or row.get("UID") or "")
                    # Username column often stores FB uid in this bot
                    if row_uid and row_uid == uid:
                        return True
    except Exception as e:
        logger.warning(f"uid csv check: {e}")
    return False

def get_task(task_id, allow_inactive=False):
    """Return task only if active (unless allow_inactive=True). Deleted/inactive → None."""
    if not task_id:
        return None
    key = f"task:{task_id}"
    cached = cache.get(key)
    data = None

    # Tombstone cache (deleted) → always re-check Firestore (task may be re-added)
    if cached is not None and not (isinstance(cached, dict) and cached.get("deleted") is True):
        data = cached
    else:
        try:
            doc = db.collection('tasks').document(str(task_id)).get()
            if doc.exists:
                data = doc.to_dict() or {}
                data["task_id"] = data.get("task_id") or task_id
                # clear any old tombstone
                cache.set(key, data, ttl=300)
            else:
                # truly missing — short tombstone only
                cache.set(key, {"task_id": task_id, "deleted": True, "is_active": False}, ttl=60)
                data = None
        except Exception as e:
            logger.error(f"Get Task Error: {e}")
            return None

    if not data:
        return None
    if allow_inactive:
        return data
    if data.get("deleted") is True:
        return None
    if data.get("is_active") is False:
        return None
    return data

def invalidate_tasks_cache():
    cache.delete("active_tasks")


def clear_task_cache(task_id):
    """Call after add/edit/delete task so list + get_task stay correct."""
    if task_id:
        cache.delete(f"task:{task_id}")
    cache.delete("active_tasks")

def save_to_google_sheets(user_id, username, password, full_name, twofa_key, twofa_code, task_type, reward=0, cookies=""):
    """get_all_values() বাদ — খুব স্লো ছিল; সরাসরি append"""
    try:
        sheet = get_google_sheet()
        if not sheet:
            return "#001"
        serial = int(time.time()) % 1000000
        safe_cookies = str(cookies).replace("\r", " ").replace("\n", " ") if cookies else ""
        safe_2fa = str(twofa_key or "").replace("\r", " ").replace("\n", " ")
        safe_password = str(password or "").replace("\r", " ").replace("\n", " ")
        row = [
            f"#{serial:06d}",
            str(user_id),
            str(username or ""),
            str(full_name or ""),
            safe_password,
            safe_cookies,
            safe_2fa,
            str(task_type or ""),
            str(reward),
            "pending",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ]
        sheet.append_row(row, value_input_option="RAW")
        return f"#{serial:06d}"
    except Exception as e:
        logger.error(f"Google Sheet Error: {type(e).__name__}: {e}")
        return "#001"

# ==================== ল্যাঙ্গুয়েজ ====================

LANG = {
    'bn': {
        'welcome': "🌟 **স্বাগতম, {name}!** 🌟\n\n🤝 **Social Media Task Bot**-এ আপনাকে স্বাগতম।\n\n📋 আপনার পছন্দের টাস্ক বেছে নিন, কাজ সম্পন্ন করুন এবং অ্যাপ্রুভ হলে আপনার ব্যালেন্সে রিওয়ার্ড যোগ হবে।\n\n🚀 **শুরু করতে নিচের `📋 Tasks ▸` বাটনে চাপ দিন।**\n💡 সাহায্য লাগলে `🛠 Support` ব্যবহার করুন।",
        'balance': "💰 **ব্যালেন্স**\n\n🆔 **ইউজার আইডি:** {user_id}\n💰 **বর্তমান ব্যালেন্স:** Tk {balance:.2f}\n⏳ **পেন্ডিং ব্যালেন্স:** Tk {pending:.2f}\n📊 **মোট আয়:** Tk {total:.2f}\n📋 **মোট টাস্ক:** {tasks}\n✅ **অ্যাপ্রুভড:** {approved}\n⏳ **পেন্ডিং:** {pending_tasks}\n❌ **রিজেক্টেড:** {rejected}\n⬇️ **মিনিমাম উইথড্র:** Tk {min_withdraw:.2f}",
        'withdraw': "💸 **টাকা উত্তোলন**\n\n💰 **বর্তমান ব্যালেন্স:** Tk {balance:.2f}\n⬇️ **মিনিমাম উইথড্র:** Tk {min_withdraw:.2f}\n\n📌 **উইথড্রয়াল পদ্ধতি নির্বাচন করুন:**",
        'referral': "🎁 **রেফারেল প্রোগ্রাম**\n\n👋 বন্ধুদের আমন্ত্রণ জানান!\n🚀 আপনার রেফার করা কেউ টাস্ক করে অ্যাপ্রুভ পেলে, আপনি তার রিওয়ার্ডের {commission:.0f}% কমিশন পাবেন।\n\n🔗 **আপনার রেফারেল লিংক:**\n`{link}`\n\n👤 **মোট রেফার:** {total}\n💰 **রেফার ইনকাম:** {income:.2f} টাকা",
        'report': "📊 **আমার রিপোর্ট**\n\n💰 **ব্যালেন্স:** Tk {balance:.2f}\n📋 **মোট সাবমিট করা টাস্ক:** {tasks}\n📅 **আজ জমা দিয়েছেন:** {today} টি\n✅ **অ্যাপ্রুভড:** {approved}\n⏳ **মোট পেন্ডিং (এখনো অ্যাপ্রুভ হয়নি):** {pending} টি\n❌ **রিজেক্টেড:** {rejected}\n\n📌 **সর্বশেষ ১০ টাস্ক:**\n{tasks_list}",
        'support': "🧑‍💻 **Customer Support Center**\n\n━━━━━━━━━━━━━━━━━━━━\n\nপ্রিয় সদস্য,\nযেকোনো প্রশ্ন বা সমস্যার জন্য আমাদের সাপোর্ট টিমের সাথে যোগাযোগ করুন। আমরা দ্রুত সাহায্য করব।\n\n⚠️ **নোট:** স্প্যাম মেসেজ এড়িয়ে চলুন।\nধন্যবাদ!",
        'task_submit_ok': "✅✅ **আপনার টাস্ক সাবমিট হয়েছে সঠিক ভাবে!**\n\n⏳ আপনার টাস্কটি অ্যাডমিন রিভিউয়ের অপেক্ষায় রয়েছে। 🔍 অ্যাডমিন যাচাই করার পর টাকা ব্যালেন্সে যোগ করা হবে।",
        'no_tasks': "❌ বর্তমানে কোনো টাস্ক নেই!",
        'task_ready': "🆕 **Create Account**\n\n🔥 **টাস্ক:** {emoji} {name}\n\n💵 **মূল্য:** Tk {reward:.2f}\n📝 **নাম:** `{full_name}`\n👤 **ইউজারনেম:** `{username}`\n🔐 **পাসওয়ার্ড:** `{password}`\n\n📢 {instructions}",
        'ask_2fa': "📌 **2FA Key পাঠান:**\n\n:",
        '2fa_received': "✅ **Key সফলভাবে গ্রহণ করা হয়েছে!**\n\n📌 **সিরিয়াল:** {serial}\n🔢 **2FA Code:** `{twofa_code}`\n⏰ ভ্যালিডিটি: ৩০ সেকেন্ড\n\n⏰ আপনার টাস্ক পেন্ডিং আছে। অ্যাডমিন চেক করবে।",
        'task_cancelled': "❌ টাস্ক বাতিল করা হয়েছে।",
        'withdraw_amount': "📝 **উইথড্র অ্যামাউন্ট লিখুন:**\n\n💰 আপনার ব্যালেন্স: Tk {balance:.2f}\n⬇️ মিনিমাম: {min_withdraw:.2f} টাকা",
        'withdraw_method': "📝 **আপনার {method} অ্যাকাউন্ট নম্বর লিখুন:**",
        'withdraw_confirm': "✅ **উইথড্র রিকোয়েস্ট সাবমিট হয়েছে!**\n\n🧾 রিকোয়েস্ট আইডি: {req_id}\n💰 অ্যামাউন্ট: {amount} টাকা\n📱 মেথড: {method}\n🔢 অ্যাকাউন্ট: {account}",
        'withdraw_disabled': "❌ উইথড্র বর্তমানে বন্ধ আছে।",
        'insufficient_balance': "❌ আপনার ব্যালেন্স অপর্যাপ্ত!\n💰 আপনার ব্যালেন্স: {balance:.2f} টাকা\n⬇️ প্রয়োজন: {min_withdraw:.2f} টাকা",
        'admin_panel': "🎛️ **অ্যাডমিন প্যানেল**\n\n📊 মোট টাস্ক: {tasks}\n✅ সক্রিয়: {active}\n👥 ইউজার: {users}\n📋 টাস্ক লিস্ট:\n{task_list}",
        'task_added': "✅ '{name}' টাস্ক যোগ করা হয়েছে!",
        'task_updated': "✅ '{name}' টাস্ক আপডেট হয়েছে!",
        'task_deleted': "✅ '{name}' টাস্ক ডিলিট করা হয়েছে!",
        'user_not_found': "❌ ইউজার পাওয়া যায়নি!",
        'balance_updated': "✅ ব্যালেন্স আপডেট হয়েছে! নতুন ব্যালেন্স: {balance:.2f} টাকা",
        'file_uploaded': "✅ ফাইল আপলোড হয়েছে! {count} টি ইউজার প্রসেস হয়েছে।",
        'broadcast_sent': "✅ ব্রডকাস্ট পাঠানো হয়েছে! {count} জন পেয়েছে।",
        'force_join': "⚠️ **বট ব্যবহার করতে নিচের চ্যানেল/গ্রুপে জয়েন করুন:**\n\n{channels}\n\n1️⃣ প্রথমে **Join Channel** বাটনে ক্লিক করে জয়েন করুন\n2️⃣ তারপর নিচের **✅ Verify** বাটনে চাপুন",
        'join_check': "✅ আপনি জয়েন করেছেন! এখন বট ব্যবহার করতে পারবেন।",
        'language_changed': "✅ ভাষা পরিবর্তন করা হয়েছে!",
        'withdraw_group': "💸 **নতুন উইথড্র রিকোয়েস্ট!**\n\n👤 ইউজার: {user}\n💰 অ্যামাউন্ট: {amount} টাকা\n📱 মেথড: {method}\n🔢 অ্যাকাউন্ট: {account}\n🧾 রিকোয়েস্ট আইডি: {req_id}",
        'withdraw_approved': "✅ আপনার {amount} টাকা উইথড্র অনুমোদিত হয়েছে!",
        'withdraw_rejected': "❌ আপনার {amount} টাকা উইথড্র বাতিল করা হয়েছে।",
        'admin_added': "✅ নতুন অ্যাডমিন যোগ করা হয়েছে!",
        'admin_removed': "✅ অ্যাডমিন সরানো হয়েছে!",
        'admin_list': "👥 **অ্যাডমিন লিস্ট:**\n\n{admins}",
        'user_banned': "🚫 ইউজার ব্লক করা হয়েছে!",
        'user_unbanned': "✅ ইউজার আনব্লক করা হয়েছে!",
        'user_balance': "💰 **ইউজার ব্যালেন্স**\n\n🆔 {user_id}\n💰 ব্যালেন্স: {balance:.2f} টাকা\n📊 মোট আয়: {total:.2f} টাকা",
        'back_button': "🔙 পিছনে"
    },
    'en': {
        'welcome': "🌟 **Welcome, {name}!** 🌟\n\n🤝 Welcome to **Social Media Task Bot**.\n\n📋 Choose a task, complete it, and your reward will be added after approval.\n\n🚀 **Tap `📋 Tasks ▸` below to get started.**\n💡 Need help? Use `🛠 Support`.",
        'balance': "💰 **Balance**\n\n🆔 **User ID:** {user_id}\n💰 **Balance:** Tk {balance:.2f}\n⏳ **Pending:** Tk {pending:.2f}\n📊 **Total Earned:** Tk {total:.2f}\n📋 **Total Tasks:** {tasks}\n✅ **Approved:** {approved}\n⏳ **Pending Tasks:** {pending_tasks}\n❌ **Rejected:** {rejected}\n⬇️ **Min Withdraw:** Tk {min_withdraw:.2f}",
        'withdraw': "💸 **Withdraw**\n\n💰 **Balance:** Tk {balance:.2f}\n⬇️ **Min Withdraw:** Tk {min_withdraw:.2f}\n\n📌 **Select withdrawal method:**",
        'referral': "🎁 **Referral Program**\n\n👋 Invite friends!\n🚀 When someone you refer completes a task and gets approved, you earn {commission:.0f}% commission of their reward.\n\n🔗 **Your Referral Link:**\n`{link}`\n\n👤 **Total Referrals:** {total}\n💰 **Referral Income:** {income:.2f} TK",
        'report': "📊 **Report**\n\n💰 **Balance:** Tk {balance:.2f}\n📋 **Total Submitted Tasks:** {tasks}\n📅 **Submitted today:** {today}\n✅ **Approved:** {approved}\n⏳ **Total Pending (not yet approved):** {pending}\n❌ **Rejected:** {rejected}\n\n📌 **Last 10 Tasks:**\n{tasks_list}",
        'support': "🧑‍💻 **Customer Support Center**\n\n━━━━━━━━━━━━━━━━━━━━\n\nDear Member,\nFor any inquiries or issues, please contact our support team. We will assist you promptly.\n\n⚠️ **Note:** Avoid spam messages.\nThank you!",
        'task_submit_ok': "✅✅ **Your task has been submitted successfully!**\n\n⏳ Your task is waiting for admin review. 🔍 After admin verification, the reward will be added to your balance.",
        'no_tasks': "❌ No tasks available!",
        'task_ready': "🆕 **Create Account**\n\n🔥 **Task:** {emoji} {name}\n\n💵 **Price:** Tk {reward:.2f}\n📝 **Name:** `{full_name}`\n👤 **Username:** `{username}`\n🔐 **Password:** `{password}`\n\n📢 {instructions}",
        'ask_2fa': "📌 **Send me the 2FA Key:**\n\n:",
        '2fa_received': "✅ **Key received successfully!**\n\n🔢 **2FA Code:** `{twofa_code}`\n⏰ Valid for 30 seconds\n\n⏰ Your task is pending. Admin will check it.",
        'task_cancelled': "❌ Task cancelled.",
        'withdraw_amount': "📝 **Enter withdrawal amount:**\n\n💰 Your balance: Tk {balance:.2f}\n⬇️ Minimum: {min_withdraw:.2f} TK",
        'withdraw_method': "📝 **Enter your {method} account number:**",
        'withdraw_confirm': "✅ **Withdrawal request submitted!**\n\n🧾 Request ID: {req_id}\n💰 Amount: {amount} TK\n📱 Method: {method}\n🔢 Account: {account}",
        'withdraw_disabled': "❌ Withdrawals are currently disabled.",
        'insufficient_balance': "❌ Insufficient balance!\n💰 Your balance: {balance:.2f} TK\n⬇️ Required: {min_withdraw:.2f} TK",
        'admin_panel': "🎛️ **Admin Panel**\n\n📊 Total Tasks: {tasks}\n✅ Active: {active}\n👥 Users: {users}\n📋 Task List:\n{task_list}",
        'task_added': "✅ '{name}' task added!",
        'task_updated': "✅ '{name}' task updated!",
        'task_deleted': "✅ '{name}' task deleted!",
        'user_not_found': "❌ User not found!",
        'balance_updated': "✅ Balance updated! New balance: {balance:.2f} TK",
        'file_uploaded': "✅ File uploaded! {count} users processed.",
        'broadcast_sent': "✅ Broadcast sent! {count} received.",
        'force_join': "⚠️ **Please join the following channels to use the bot:**\n\n{channels}\n\n1️⃣ First tap **Join Channel** and join\n2️⃣ Then press the **✅ Verify** button below",
        'join_check': "✅ You have joined! Now you can use the bot.",
        'language_changed': "✅ Language changed!",
        'withdraw_group': "💸 **New Withdrawal Request!**\n\n👤 User: {user}\n💰 Amount: {amount} TK\n📱 Method: {method}\n🔢 Account: {account}\n🧾 Request ID: {req_id}",
        'withdraw_approved': "✅ Your {amount} TK withdrawal has been approved!",
        'withdraw_rejected': "❌ Your {amount} TK withdrawal has been rejected.",
        'admin_added': "✅ New admin added!",
        'admin_removed': "✅ Admin removed!",
        'admin_list': "👥 **Admin List:**\n\n{admins}",
        'user_banned': "🚫 User banned!",
        'user_unbanned': "✅ User unbanned!",
        'user_balance': "💰 **User Balance**\n\n🆔 {user_id}\n💰 Balance: {balance:.2f} TK\n📊 Total Earned: {total:.2f} TK",
        'back_button': "🔙 Back"
    }
}

def get_text(user_id, key, **kwargs):
    user = get_user(user_id)
    lang = user.get('lang', 'bn') if user else 'bn'
    text = LANG.get(lang, LANG['bn']).get(key, LANG['bn'].get(key, key))
    try:
        return text.format(**kwargs)
    except Exception:
        return text


# ==================== Telegram Button Color/Style Logic ====================
_DANGER_WORDS = (
    "cancel", "reject", "delete", "remove", "back", "close", "reset", "block", "ban",
    "বাতিল", "ডিলিট", "মুছ", "পিছনে", "বন্ধ", "রিসেট", "ব্লক", "কাটুন", "রিজেক্ট",
)
_SUCCESS_WORDS = (
    "approve", "done", "submit", "confirm", "success", "add", "save", "upload", "download",
    "unblock", "unban", "yes", "start",
    "জমা", "সাবমিট", "অ্যাপ্রুভ", "যোগ", "আপলোড", "সেভ", "হ্যাঁ", "আনব্লক", "নিশ্চিত",
)

def _auto_button_style(label):
    low = label.lower()
    if "✅ on" in low:
        return "success"
    if "❌ off" in low:
        return "danger"
    stripped = label.lstrip()
    if stripped.startswith(("❌", "🔙", "🗑", "🚫", "➖")):
        return "danger"
    if stripped.startswith(("✅", "➕")):
        return "success"
    if any(w in low for w in _DANGER_WORDS):
        return "danger"
    if any(w in low for w in _SUCCESS_WORDS):
        return "success"
    styles = ("primary", "success")
    return styles[int(hashlib.sha256(label.encode("utf-8")).hexdigest(), 16) % len(styles)]


def colored_button(text, callback_data=None, url=None, style=None, **kwargs):
    label = str(text or "")
    if style not in ("primary", "success", "danger"):
        style = _auto_button_style(label)

    button_kwargs = dict(kwargs)
    button_kwargs.pop("api_kwargs", None)
    button_kwargs["style"] = style
    if callback_data is not None:
        button_kwargs["callback_data"] = callback_data
    if url is not None:
        button_kwargs["url"] = url
    return InlineKeyboardButton(label, **button_kwargs)

def copy_text_button(label, text_to_copy, style=None):
    """Telegram native copy button; fallback to callback alert."""
    code = str(text_to_copy or "")[:256]
    try:
        kwargs = {"text": label, "copy_text": {"text": code}}
        if style in ("primary", "success", "danger"):
            kwargs["style"] = style
        return InlineKeyboardButton(**kwargs)
    except Exception:
        pass
    # Fallback — callback shows code in alert (user can long-press copy)
    return colored_button(label, callback_data=f"cp2fa_{code}", style=style or "primary")


def build_2fa_code_keyboard(user_id, twofa_code):
    """Row1: NEW CODE | COPY CODE — Row2: Submit — Row3: Cancel"""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(
        colored_button("🔄 NEW CODE", callback_data=f"refresh_2fa_{user_id}", style="primary"),
        copy_text_button("📋 COPY CODE", twofa_code, style="primary"),
    )
    kb.add(colored_button("✅ সাবমিট করুন", callback_data=f"submit_2fa_{user_id}", style="success"))
    kb.add(colored_button("❌ বাতিল", callback_data=f"cancel_2fa_{user_id}", style="danger"))
    return kb



# ==================== মেনু ====================

def get_language_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.row(
        colored_button("🇧🇩 বাংলা", callback_data="select_lang_bn", style="primary"),
        colored_button("🇬🇧 English", callback_data="select_lang_en", style="primary")
    )
    keyboard.row(colored_button("🔙 পিছনে", callback_data="lang_back"))
    return keyboard


def get_main_menu(user_id):
    user = get_user(user_id)
    lang = user.get('lang') if user else None
    admin = is_admin(user_id)

    keyboard = ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=False
    )

    if lang == 'en':
        keyboard.row(
            KeyboardButton("📋 Tasks ▸", style="primary")
        )
        keyboard.row(
            KeyboardButton("👤 Profile", style="primary"),
            KeyboardButton("💸 Withdraw", style="danger")
        )
        keyboard.row(
            KeyboardButton("🔗 Referral", style="success"),
            KeyboardButton("🛠 Support", style="primary")
        )
        keyboard.row(KeyboardButton("🌐 Language / ভাষা", style="primary"))
        if admin:
            keyboard.row(
                KeyboardButton("🎛️ Admin Panel", style="danger")
            )
    else:
        keyboard.row(
            KeyboardButton("📱 কাজ", style="primary")
        )
        keyboard.row(
            KeyboardButton("👤 প্রোফাইল", style="primary"),
            KeyboardButton("💸 টাকা উত্তোলন", style="danger")
        )
        keyboard.row(
            KeyboardButton("🔗 রেফারেল", style="success"),
            KeyboardButton("🛠 সাপোর্ট", style="primary")
        )
        keyboard.row(KeyboardButton("🌐 Language / ভাষা", style="primary"))
        if admin:
            keyboard.row(
                KeyboardButton("🎛️ অ্যাডমিন প্যানেল", style="danger")
            )

    return keyboard


# ==================== Main Menu Callback Bridge ====================
class _MainMenuMessageProxy:
    def __init__(self, message, user):
        self._message = message
        self.from_user = user
        self.chat = message.chat

    async def reply(self, *args, **kwargs):
        return await self._message.reply(*args, **kwargs)

    async def answer(self, *args, **kwargs):
        return await self._message.answer(*args, **kwargs)


@dp.callback_query_handler(lambda c: c.data in (
    "main_task", "main_withdraw", "main_report",
    "main_referral", "main_support", "main_admin"
))
async def main_menu_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data

    if data == "main_admin" and not is_admin(user_id):
        await cb_answer(callback, "❌ আপনি অ্যাডমিন নন!", show_alert=True)
        return

    await cb_answer(callback)
    proxy = _MainMenuMessageProxy(callback.message, callback.from_user)

    try:
        if data == "main_task":
            await show_tasks(proxy)
        elif data == "main_withdraw":
            await show_withdraw(proxy)
        elif data == "main_report":
            await show_report(proxy)
        elif data == "main_referral":
            await show_referral(proxy)
        elif data == "main_support":
            await show_support(proxy)
        elif data == "main_admin":
            await admin_panel(proxy)
    except Exception as e:
        logger.error(f"Main Menu Callback Error: {e}")
        try:
            await callback.message.answer("❌ অনুরোধটি সম্পন্ন করা যায়নি।")
        except Exception:
            pass


# ==================== /start ====================

async def _process_referral_start(user_id, name, args):
    if not args or not args.startswith('ref_'):
        return
    try:
        referrer_id = int(args.split('_')[1])
        if referrer_id != user_id:
            referrer = get_user(referrer_id)
            if referrer:
                db.collection('users').document(str(user_id)).update({'referred_by': referrer_id})
                db.collection('users').document(str(referrer_id)).update({
                    'total_refers': firestore.Increment(1)
                })
                invalidate_user_cache(user_id)
                invalidate_user_cache(referrer_id)
                await bot.send_message(
                    referrer_id,
                    f"🎉 নতুন রেফারেল! {name} আপনার লিংক দিয়ে জয়েন করেছে!\n"
                    f"💡 এই ইউজারের কোনো টাস্ক অ্যাপ্রুভ হলেই আপনি "
                    f"{REFERRAL_COMMISSION_PERCENT:.0f}% কমিশন পাবেন।"
                )
    except Exception as e:
        logger.error(f"Referral Start Error: {e}")


@dp.message_handler(commands=['start'])
async def welcome(message: types.Message):
    user_id = message.from_user.id
    name = message.from_user.first_name
    username = message.from_user.username or str(user_id)

    user = get_user(user_id)
    is_new_user = not user

    if is_new_user:
        create_user(user_id, username, name, lang=None)
        user = get_user(user_id)
    else:
        # username/name আপডেট রাখা — সব জায়গায় @username দেখাতে
        try:
            updates = {}
            if user.get('username') != username:
                updates['username'] = username
            if name and user.get('first_name') != name:
                updates['first_name'] = name
            if updates:
                db.collection('users').document(str(user_id)).update(updates)
                invalidate_user_cache(user_id)
        except Exception:
            pass

    args = message.get_args()

    if is_new_user and args and args.startswith('ref_'):
        await _process_referral_start(user_id, name, args)

    user = get_user(user_id)
    if not user or not user.get('lang'):
        await message.answer(
            "🌐 **Choose your language / ভাষা নির্বাচন করুন**\n\n"
            "Please select your preferred language.\n"
            "আপনার পছন্দের ভাষা নির্বাচন করুন।",
            reply_markup=get_language_menu(),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if not await require_force_join(message, user_id):
        return

    await message.answer(
        get_text(user_id, 'welcome', name=name),
        reply_markup=get_main_menu(user_id),
        parse_mode=ParseMode.MARKDOWN
    )


@dp.callback_query_handler(lambda c: c.data == "lang_back")
async def language_back(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "force_join_info")
async def force_join_info(callback: types.CallbackQuery):
    """Chat ID টাইপ চ্যানেলের জন্য — লিংক না থাকলে নির্দেশ"""
    await callback.answer(
        "এই চ্যানেল/গ্রুপে ম্যানুয়ালি জয়েন করুন, তারপর ✅ Verify চাপুন।",
        show_alert=True
    )


@dp.callback_query_handler(lambda c: c.data == "force_join_verify")
async def force_join_verify(callback: types.CallbackQuery):
    """Verify বাটন — সদস্যপদ যাচাই করে মেনু দেখায়"""
    user_id = callback.from_user.id
    # ক্যাশ মুছে নতুন করে চেক
    cache.delete(f"force_join:{user_id}")
    ok = await check_force_join(user_id, force_refresh=True)
    if ok:
        try:
            await callback.message.edit_text(
                get_text(user_id, 'join_check'),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            try:
                await callback.message.answer(get_text(user_id, 'join_check'), parse_mode=ParseMode.MARKDOWN)
            except Exception:
                pass
        await callback.message.answer(
            get_text(user_id, 'welcome', name=callback.from_user.first_name),
            reply_markup=get_main_menu(user_id),
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer("✅ যাচাই সফল!")
    else:
        await callback.answer(
            "❌ এখনও সব চ্যানেলে জয়েন করেননি!\nJoin করে আবার Verify চাপুন।",
            show_alert=True
        )
        # পুরনো মেসেজ আপডেট করে আবার বাটন দেখানো
        try:
            await callback.message.edit_text(
                get_force_join_message(user_id),
                reply_markup=get_force_join_keyboard(),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass


@dp.callback_query_handler(lambda c: c.data in ("select_lang_bn", "select_lang_en"))
async def select_language(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = "bn" if callback.data == "select_lang_bn" else "en"

    try:
        user_ref = db.collection('users').document(str(user_id))
        user_ref.update({'lang': lang})
        invalidate_user_cache(user_id)
    except Exception as e:
        logger.error(f"Language Save Error: {e}")
        await callback.answer("❌ Language save failed.", show_alert=True)
        return

    invalidate_user_cache(user_id)
    await callback.answer("বাংলা নির্বাচিত হয়েছে ✅" if lang == "bn" else "English selected ✅")

    # পুরো মেনু ও টেক্সট নতুন ভাষায় — mixed থাকবে না (gap মেসেজ নেই)
    welcome = get_text(user_id, 'welcome', name=callback.from_user.first_name)
    menu = get_main_menu(user_id)
    try:
        await callback.message.edit_text(welcome, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        pass
    try:
        await callback.message.answer(welcome, reply_markup=menu, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Language Welcome Error: {e}")
        await callback.message.answer(welcome, reply_markup=menu, parse_mode=None)

    if not await check_force_join(user_id):
        await callback.message.answer(
            get_force_join_message(user_id),
            reply_markup=get_force_join_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )


# ==================== গাইড মেনু ====================

def get_guide_menu(lang):
    keyboard = InlineKeyboardMarkup(row_width=1)
    if lang == 'bn':
        keyboard.add(
            colored_button("💸 কিভাবে উইথড্র করবেন", callback_data="guide_withdraw"),
            colored_button("📱 কিভাবে টাস্ক করবেন", callback_data="guide_task"),
            colored_button("🔗 কিভাবে লিংক শেয়ার করবেন", callback_data="guide_share")
        )
    else:
        keyboard.add(
            colored_button("💸 How to Withdraw", callback_data="guide_withdraw"),
            colored_button("📱 How Tasks Work", callback_data="guide_task"),
            colored_button("🔗 How to Share Your Link", callback_data="guide_share")
        )
    for btn in GUIDE_BUTTONS:
        keyboard.add(colored_button(btn['title'], callback_data=f"gbtn_{btn['id']}"))
    return keyboard

GUIDE_TEXTS = {
    'bn': {
        'menu': "🎥 **বট ওয়ার্ক সিস্টেম**\n\nবট কিভাবে ব্যবহার করবেন তা জানতে নিচের যেকোনো একটা অপশনে ক্লিক করুন:",
        'withdraw': (
            "💸 **কিভাবে উইথড্র করবেন**\n\n"
            "১️⃣ মেনু থেকে 💸 টাকা উত্তোলন বাটনে ক্লিক করুন\n"
            "২️⃣ আপনার পেমেন্ট মেথড বেছে নিন\n"
            "৩️⃣ কত টাকা তুলবেন তা লিখুন\n"
            "৪️⃣ আপনার অ্যাকাউন্ট নম্বর লিখুন\n"
            "৫️⃣ রিকোয়েস্ট জমা হয়ে যাবে, অ্যাডমিন অ্যাপ্রুভ করলেই টাকা পাবেন"
        ),
        'task': (
            "📱 **কিভাবে টাস্ক করবেন**\n\n"
            "১️⃣ মেনু থেকে 📱 কাজ বাটনে ক্লিক করুন\n"
            "২️⃣ পছন্দমতো একটা প্ল্যাটফর্ম বেছে নিন\n"
            "৩️⃣ বট অটো ইউজারনেম, পাসওয়ার্ড জেনারেট করবে\n"
            "৪️⃣ কাজ শেষে ✅ Done বাটনে ক্লিক করুন\n"
            "৫️⃣ 2FA Key টাইপ করে পাঠান\n"
            "৬️⃣ অ্যাডমিন অ্যাপ্রুভ করলেই টাকা যোগ হবে"
        ),
        'share': (
            "🔗 **কিভাবে লিংক শেয়ার করবেন**\n\n"
            "১️⃣ মেনু থেকে 🔗 রেফারেল বাটনে ক্লিক করুন\n"
            "২️⃣ আপনার রেফারেল লিংক দেখতে পাবেন\n"
            "৩️⃣ 📤 শেয়ার করুন বাটনে ক্লিক করে শেয়ার করুন\n"
            "৪️⃣ কেউ জয়েন করলে আপনি কমিশন পাবেন"
        )
    },
    'en': {
        'menu': "🎥 **Bot Work System**\n\nTap any option below to learn how to use the bot:",
        'withdraw': (
            "💸 **How to Withdraw**\n\n"
            "1️⃣ Tap 💸 Withdraw from the menu\n"
            "2️⃣ Choose your payment method\n"
            "3️⃣ Enter the amount you want to withdraw\n"
            "4️⃣ Enter your account number\n"
            "5️⃣ Your request is submitted — you'll get paid once admin approves it"
        ),
        'task': (
            "📱 **How Tasks Work**\n\n"
            "1️⃣ Tap 📋 Tasks ▸ from the menu\n"
            "2️⃣ Pick a platform\n"
            "3️⃣ The bot auto-generates username/password\n"
            "4️⃣ Tap ✅ Done once finished\n"
            "5️⃣ Send the 2FA Key\n"
            "6️⃣ You get paid once admin approves it"
        ),
        'share': (
            "🔗 **How to Share Your Link**\n\n"
            "1️⃣ Tap 🔗 Referral from the menu\n"
            "2️⃣ You'll see your unique referral link\n"
            "3️⃣ Tap 📤 Share to send it\n"
            "4️⃣ When your referral gets approved, you earn commission"
        )
    }
}

# ==================== কাজ — ক্যাটাগরি মেনু ====================

# প্ল্যাটফর্ম ক্যাটাগরি (task_id / name ম্যাচ)
TASK_CATEGORIES = [
    ("facebook",  "📘 Facebook",  ("fb", "facebook")),
    ("instagram", "📸 Instagram", ("insta", "instagram")),
    ("threads",   "🧵 Threads",   ("threads", "thread", "theads")),
    ("tiktok",    "🎵 TikTok",    ("tiktok", "tik tok")),
    ("twitter",   "🐦 Twitter/X", ("twitter", "tweet", "x_2fa")),
    ("youtube",   "▶️ YouTube",   ("youtube", "yt_")),
    ("other",     "📱 Other",     ()),
]

def get_task_category_id(task):
    tid = f"{task.get('task_id', '')} {task.get('name', '')}".lower()
    for cat_id, _label, keywords in TASK_CATEGORIES:
        if cat_id == "other":
            continue
        if any(k in tid for k in keywords):
            return cat_id
    return "other"

def group_tasks_by_category(tasks):
    groups = {}
    for t in tasks:
        cid = get_task_category_id(t)
        groups.setdefault(cid, []).append(t)
    return groups

def _cat_label(cat_id, lang='bn'):
    for cid, label, _ in TASK_CATEGORIES:
        if cid == cat_id:
            return label
    return "📱 Other"

async def show_task_categories(message: types.Message, user_id=None):
    """
    মেইন টাস্ক মেনু:
    - ক্যাটাগরিতে ২+ টাস্ক → ফোল্ডার বাটন (ভিতরে সাব-বাটন)
    - ক্যাটাগরিতে ১টা টাস্ক → সরাসরি সিঙ্গেল টাস্ক বাটন
    """
    user_id = user_id or message.from_user.id
    tasks = get_active_tasks()
    if not tasks:
        await message.answer(get_text(user_id, 'no_tasks'))
        return

    groups = group_tasks_by_category(tasks)
    user = get_user(user_id)
    lang = (user or {}).get('lang', 'bn')
    back_label = "❌ Main Menu" if lang == 'en' else "❌ প্রধান মেনু"
    text = (
        "✏️ **Select a task / platform**"
        if lang == 'en' else
        "✏️ **টাস্ক বা প্ল্যাটফর্ম সিলেক্ট করুন**"
    )

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False, row_width=1)
    cat_map = {}       # folder button text → cat_id
    name_map = {}      # single task button text → task_id
    folder_count = 0
    single_count = 0

    task_groups_store = {}
    for cat_id, label, _ in TASK_CATEGORIES:
        tlist = groups.get(cat_id) or []
        if not tlist:
            continue
        packed = [
            {
                'task_id': t.get('task_id', ''),
                'name': t.get('name', 'Unknown'),
                'emoji': t.get('emoji', '📱'),
                'reward': t.get('reward', 0),
            }
            for t in tlist
        ]
        task_groups_store[cat_id] = packed

        if len(tlist) == 1:
            # সিঙ্গেল টাস্ক — সরাসরি বাটন
            t = tlist[0]
            btn = f"{t.get('emoji', '📱')} {t.get('name', 'Unknown')}"
            keyboard.add(KeyboardButton(btn, style="primary"))
            name_map[btn] = t.get('task_id', '')
            single_count += 1
        else:
            # একাধিক টাস্ক — ফোল্ডার বাটন
            btn = f"{label} ({len(tlist)}) ▸"
            keyboard.add(KeyboardButton(btn, style="primary"))
            cat_map[btn] = cat_id
            folder_count += 1

    keyboard.add(KeyboardButton(back_label, style="danger"))
    MENU_BUTTON_TEXTS.add(back_label)

    if user_id not in temp_data or not isinstance(temp_data.get(user_id), dict):
        temp_data[user_id] = {}
    temp_data[user_id]['task_cat_map'] = cat_map
    temp_data[user_id]['task_groups'] = task_groups_store
    # সিঙ্গেল টাস্ক সরাসরি সিলেক্ট করা যাবে
    temp_data[user_id]['task_name_map'] = name_map
    # level: category তেও সিঙ্গেল টাস্ক কাজ করবে
    temp_data[user_id]['task_menu_level'] = 'category'

    await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


async def show_category_tasks(message: types.Message, user_id, cat_id):
    """একটা ক্যাটাগরির ভিতরের টাস্ক লিস্ট"""
    user = get_user(user_id)
    lang = (user or {}).get('lang', 'bn')
    groups = (temp_data.get(user_id) or {}).get('task_groups') or {}
    tasks = groups.get(cat_id) or []

    # ক্যাশ মিস হলে আবার লোড
    if not tasks:
        all_tasks = get_active_tasks()
        groups = group_tasks_by_category(all_tasks)
        tasks = [
            {
                'task_id': t.get('task_id', ''),
                'name': t.get('name', 'Unknown'),
                'emoji': t.get('emoji', '📱'),
                'reward': t.get('reward', 0),
            }
            for t in groups.get(cat_id, [])
        ]

    if not tasks:
        await message.answer(get_text(user_id, 'no_tasks'))
        return

    cat_label = _cat_label(cat_id, lang)
    text = (
        f"📂 **{cat_label}**\n\n✏️ Select a task:"
        if lang == 'en' else
        f"📂 **{cat_label}**\n\n✏️ একটি টাস্ক সিলেক্ট করুন:"
    )
    back_cat = "🔙 Categories" if lang == 'en' else "🔙 ক্যাটাগরি"
    back_main = "❌ Main Menu" if lang == 'en' else "❌ প্রধান মেনু"

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False, row_width=1)
    name_map = {}
    for t in tasks:
        label = f"{t.get('emoji', '📱')} {t.get('name', 'Unknown')}"
        keyboard.add(KeyboardButton(label, style="primary"))
        name_map[label] = t.get('task_id', '')

    keyboard.add(KeyboardButton(back_cat, style="primary"))
    keyboard.add(KeyboardButton(back_main, style="danger"))
    MENU_BUTTON_TEXTS.add(back_cat)
    MENU_BUTTON_TEXTS.add(back_main)

    if user_id not in temp_data or not isinstance(temp_data.get(user_id), dict):
        temp_data[user_id] = {}
    temp_data[user_id]['task_name_map'] = name_map
    temp_data[user_id]['task_menu_level'] = 'tasks'
    temp_data[user_id]['current_category'] = cat_id

    await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


@dp.message_handler(lambda message: message.text in ["📱 কাজ", "📋 Tasks ▸"])
async def show_tasks(message: types.Message):
    user_id = message.from_user.id
    if not await require_force_join(message, user_id):
        return
    await show_task_categories(message, user_id)


@dp.message_handler(lambda message: message.text in ["🔙 ক্যাটাগরি", "🔙 Categories"])
async def back_to_categories(message: types.Message):
    if not await require_force_join(message, message.from_user.id):
        return
    await show_task_categories(message, message.from_user.id)


@dp.message_handler(lambda message: (
    message.from_user.id in temp_data
    and isinstance(temp_data.get(message.from_user.id), dict)
    and temp_data.get(message.from_user.id, {}).get('task_menu_level') == 'category'
    and message.text in temp_data.get(message.from_user.id, {}).get('task_cat_map', {})
))
async def handle_category_select(message: types.Message):
    """ক্যাটাগরি বাটন — ভিতরের টাস্ক দেখায়"""
    user_id = message.from_user.id
    if not await require_force_join(message, user_id):
        return
    cat_id = temp_data[user_id]['task_cat_map'].get(message.text, '')
    if not cat_id:
        await message.answer("❌ ক্যাটাগরি পাওয়া যায়নি!")
        return
    await show_category_tasks(message, user_id, cat_id)

# ==================== টাস্ক হ্যান্ডলার ====================

def get_verification_mode(task_id):
    """
    Task ID অনুযায়ী verification mode:
    - fb_cookies / fb_cokies / cookies     → শুধু UID + Cookies
    - fb_2fa_cookies                       → UID + 2FA Key + Cookies
    - fb_2fa / facebook (explicit fb)      → UID + 2FA Key
    - insta_2fa / threads_2fa / অন্য       → Username + Password + 2FA Key
    """
    tid = (task_id or "").lower()
    has_cookie = ("cookie" in tid) or ("cokies" in tid) or ("cookies" in tid)
    is_threads = "threads" in tid or "theads" in tid or "thread" in tid
    is_fb = ("fb" in tid or "facebook" in tid) and not is_threads

    # শুধু explicit 2fa + cookie হলেই fb_2fa_cookies; fb_cookies = pure cookie
    if has_cookie and "2fa" in tid:
        return "fb_2fa_cookies"
    if has_cookie:
        return "cookie"
    # Facebook only → UID + 2FA; Threads/Instagram → normal (username+password+2FA)
    if is_fb:
        return "fb_2fa"
    return "normal"

def after_submit_keyboard(task_id=""):
    """টাস্ক সাবমিটের পর ২টা বাটন"""
    kb = InlineKeyboardMarkup(row_width=1)
    if task_id:
        kb.add(colored_button("🔄 আবার এই টাস্ক", callback_data=f"task_{task_id}", style="primary"))
    kb.add(colored_button("📋 অন্য টাস্ক", callback_data="main_task", style="success"))
    return kb

async def send_task_credentials(callback_message, user_id, task_id, edit=True):
    task = get_task(task_id)
    if not task:
        # cache tombstone থাকলে একবার রিফ্রেশ
        clear_task_cache(task_id)
        task = get_task(task_id)
    if not task:
        try:
            await callback_message.answer("❌ এই টাস্ক নেই বা ডিলিট করা হয়েছে। আর সাবমিট করা যাবে না।")
        except Exception:
            try:
                await callback_message.edit_text("❌ এই টাস্ক নেই বা ডিলিট করা হয়েছে। আর সাবমিট করা যাবে না।")
            except Exception:
                pass
        return
    
    mode = get_verification_mode(task_id)
    password = generate_password(task.get("fixed_password", "") or "")
    # threads_2fa → ভিয়েতনামি নাম; বাকি সব English
    _tid = (task_id or "").lower()
    if "threads" in _tid or "theads" in _tid or "thread" in _tid:
        full_name = generate_vietnamese_full_name()
    else:
        full_name = generate_full_name()
    reward = task.get('reward', 4.0)
    name = task.get('name', 'Unknown')
    emoji = task.get('emoji', '📱')
    instructions = task.get('instructions', '')
    
    if mode == "normal":
        username = generate_username()
        db.collection('temp_tasks').document(str(user_id)).set({
            'task_id': task_id,
            'username': username,
            'password': password,
            'full_name': full_name,
            'reward': reward,
            'mode': mode
        })
        mark_pending_task(user_id)
        text = get_text(user_id, 'task_ready',
            emoji=emoji, name=name, reward=reward, username=username, password=password,
            full_name=full_name, instructions=instructions
        )
        refresh_label = "🔄 নতুন Username/Password"
    else:
        db.collection('temp_tasks').document(str(user_id)).set({
            'task_id': task_id,
            'password': password,
            'full_name': full_name,
            'reward': reward,
            'mode': mode
        })
        mark_pending_task(user_id)
        # Create Account — name/password 1-tap copy (`code`)
        instr = f"\n\n📢 {instructions}" if instructions else ""
        text = (
            f"🆕 **Create Account**\n\n"
            f"🔥 **টাস্ক:** {emoji} {name}\n\n"
            f"💵 **মূল্য:** Tk {reward:.2f}\n"
            f"📝 **নাম:** `{full_name}`\n"
            f"🔐 **পাসওয়ার্ড:** `{password}`"
            f"{instr}"
        )
        refresh_label = "🔄 নতুন Password"
    
    keyboard = InlineKeyboardMarkup(row_width=2).add(
        colored_button("✅ Done", callback_data=f"task_done_{task_id}"),
        colored_button(refresh_label, callback_data=f"task_refresh_{task_id}"),
        colored_button("❌ Cancel", callback_data="task_cancel")
    )
    # edit=False → answer (quote/mark নেই); edit=True → আগে edit_text চেষ্টা
    async def _send(parse_mode=ParseMode.MARKDOWN):
        if edit:
            try:
                await callback_message.edit_text(text, reply_markup=keyboard, parse_mode=parse_mode)
                return True
            except Exception:
                pass
        # answer = নতুন মেসেজ, ইউজারের বাটন মেসেজ quote করবে না
        try:
            await callback_message.answer(text, reply_markup=keyboard, parse_mode=parse_mode)
            return True
        except Exception:
            try:
                await callback_message.answer(text, reply_markup=keyboard, parse_mode=None)
                return True
            except Exception:
                return False

    try:
        ok = await _send(ParseMode.MARKDOWN)
        if not ok:
            await _send(None)
    except Exception as e:
        logger.error(f"Task Ready Send Error: {e}")

@dp.message_handler(lambda message: message.text in ("❌ প্রধান মেনু", "❌ Main Menu"))
async def back_to_main_menu(message: types.Message):
    user_id = message.from_user.id
    user_states.pop(user_id, None)
    await message.answer(
        get_text(user_id, 'welcome', name=message.from_user.first_name),
        reply_markup=get_main_menu(user_id),
        parse_mode=ParseMode.MARKDOWN
    )

async def restore_main_keyboard(message: types.Message, user_id: int):
    """টাস্ক লিস্ট বাটন সরিয়ে মেইন মেনু বসায় — লোডিং ইমোজি ছাড়া"""
    try:
        tmp = await message.answer("\u200b", reply_markup=get_main_menu(user_id))
        try:
            await tmp.delete()
        except Exception:
            pass
    except Exception:
        pass

@dp.message_handler(lambda message: (
    message.from_user.id in temp_data
    and isinstance(temp_data.get(message.from_user.id), dict)
    and 'task_name_map' in temp_data.get(message.from_user.id, {})
    and message.text in temp_data.get(message.from_user.id, {}).get('task_name_map', {})
))
async def handle_task_from_reply_kb(message: types.Message):
    """ReplyKeyboard থেকে টাস্ক সিলেক্ট — reply/quote mark ছাড়া"""
    user_id = message.from_user.id
    if not await require_force_join(message, user_id):
        return
    task_id = temp_data[user_id]['task_name_map'].get(message.text, '')
    if not task_id:
        # map মিস হলে active tasks থেকে rebuild
        tasks = get_active_tasks()
        name_map = {f"{t.get('emoji', '📱')} {t.get('name', 'Unknown')}": t.get('task_id', '') for t in tasks}
        task_id = name_map.get(message.text, '')
        if user_id not in temp_data or not isinstance(temp_data.get(user_id), dict):
            temp_data[user_id] = {}
        temp_data[user_id]['task_name_map'] = name_map
    if not task_id:
        await message.answer("❌ টাস্ক পাওয়া যায়নি!")
        return
    # Stale "deleted" cache clear — re-added task same ID কাজ করবে
    clear_task_cache(task_id)
    try:
        await restore_main_keyboard(message, user_id)
    except Exception:
        pass
    try:
        await send_task_credentials(message, user_id, task_id, edit=False)
    except Exception as e:
        logger.error(f"Task select send error: {e}")
        await message.answer(f"❌ টাস্ক লোড সমস্যা: {e}")

@dp.callback_query_handler(lambda c: c.data.startswith("task_") and not c.data.startswith("task_done_") and not c.data.startswith("task_refresh_") and c.data != "task_cancel")
async def handle_task(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    cache.delete(f"force_join:{user_id}")
    if not await check_force_join(user_id, force_refresh=True):
        await callback.answer("❌ দয়া করে চ্যানেলে জয়েন করে Verify করুন!", show_alert=True)
        try:
            await callback.message.answer(
                get_force_join_message(user_id),
                reply_markup=get_force_join_keyboard(),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass
        return
    
    task_id = callback.data.replace("task_", "", 1)
    await send_task_credentials(callback.message, user_id, task_id)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("task_refresh_"))
async def task_refresh(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    task_id = callback.data.replace("task_refresh_", "", 1)
    await send_task_credentials(callback.message, user_id, task_id)
    await callback.answer("🔄 নতুন Username/Password জেনারেট হয়েছে!")

# ==================== Done ====================

def task_cancel_keyboard():
    return InlineKeyboardMarkup(row_width=1).add(
        colored_button("❌ Cancel", callback_data="task_cancel")
    )

@dp.callback_query_handler(lambda c: c.data.startswith("task_done_"))
async def task_done(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await cb_answer(callback)
    task_id = callback.data.replace("task_done_", "", 1)
    if not get_task(task_id):
        try:
            await callback.message.edit_text("❌ এই টাস্ক ডিলিট করা হয়েছে। আর সাবমিট করা যাবে না।")
        except Exception:
            await callback.message.answer("❌ এই টাস্ক ডিলিট করা হয়েছে। আর সাবমিট করা যাবে না।")
        clear_pending_task(user_id)
        try:
            db.collection('temp_tasks').document(str(user_id)).delete()
        except Exception:
            pass
        return
    mode = get_verification_mode(task_id)
    if mode == "normal":
        await callback.message.edit_text(get_text(user_id, 'ask_2fa'), reply_markup=task_cancel_keyboard(), parse_mode=ParseMode.MARKDOWN)
    else:
        user_states[user_id] = "awaiting_uid"
        await callback.message.edit_text(
            "🆔 **আপনার তৈরি করা Facebook অ্যাকাউন্টের UID লিখুন:**",
            reply_markup=task_cancel_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
    await callback.answer()

# ==================== Facebook UID রিসিভ ====================

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "awaiting_uid")
async def receive_uid(message: types.Message):
    user_id = message.from_user.id
    uid = normalize_fb_uid(message.text)
    if not uid:
        await message.answer("❌ সঠিক UID দিন!", reply_markup=task_cancel_keyboard())
        return

    # Same Facebook UID only once (global)
    try:
        used = await asyncio.to_thread(is_facebook_uid_used, uid)
    except Exception:
        used = is_facebook_uid_used(uid)
    if used:
        await message.answer(
            "❌ এই Facebook UID **আগেই সাবমিট** করা হয়েছে!" + chr(10) + chr(10) +
            f"🆔 UID: `{uid}`" + chr(10) +
            "অন্য UID দিয়ে আবার চেষ্টা করুন।",
            reply_markup=task_cancel_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    doc_ref = db.collection('temp_tasks').document(str(user_id))
    doc = doc_ref.get()
    if not doc.exists:
        await message.answer("❌ টাস্ক ডেটা পাওয়া যায়নি!")
        del user_states[user_id]
        return
    
    data = doc.to_dict()
    task_id = data.get('task_id', '')
    mode = get_verification_mode(task_id)
    doc_ref.update({'uid': uid})
    
    if mode == "cookie":
        user_states[user_id] = "awaiting_cookies"
        await message.answer("🍪 **এখন আপনার Facebook Cookies পেস্ট করুন:**", reply_markup=task_cancel_keyboard(), parse_mode=ParseMode.MARKDOWN)
    else:
        # fb_2fa + fb_2fa_cookies: 2FA Key নেবে → code জেনারেট হবে (sheet-এ code যাবে না)
        del user_states[user_id]
        await message.answer(get_text(user_id, 'ask_2fa'), reply_markup=task_cancel_keyboard(), parse_mode=ParseMode.MARKDOWN)

# ==================== Facebook Cookies রিসিভ ====================

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "awaiting_cookies")
async def receive_cookies(message: types.Message):
    user_id = message.from_user.id
    cookies = message.text.strip()
    if not cookies:
        await message.answer("❌ Cookies দিন!", reply_markup=task_cancel_keyboard())
        return
    
    doc = db.collection('temp_tasks').document(str(user_id)).get()
    if not doc.exists:
        await message.answer("❌ টাস্ক ডেটা পাওয়া যায়নি!")
        del user_states[user_id]
        return
    
    data = doc.to_dict()
    task_id = data.get('task_id', '')
    password = data.get('password', '')
    full_name = data.get('full_name', '')
    reward = data.get('reward', 4.0)
    uid = data.get('uid', '')
    twofa_key = data.get('twofa_key', '')
    twofa_code = data.get('twofa_code', '')
    
    task = get_task(task_id)
    if not task:
        user_states.pop(user_id, None)
        clear_pending_task(user_id)
        await message.answer("❌ এই টাস্ক ডিলিট করা হয়েছে। সাবমিট করা যাবে না।")
        return
    uid = normalize_fb_uid(uid)
    if uid:
        try:
            used = await asyncio.to_thread(is_facebook_uid_used, uid)
        except Exception:
            used = is_facebook_uid_used(uid)
        if used:
            await message.answer(
                "❌ এই Facebook UID **আগেই সাবমিট** করা হয়েছে!" + chr(10) +
                f"🆔 `{uid}`" + chr(10) + "অন্য UID দিয়ে চেষ্টা করুন।",
                parse_mode=ParseMode.MARKDOWN
            )
            return
    task_type = task.get('name', 'Unknown') if task else 'Unknown'
    
    task_data = {
        'task_id': task_id,
        'user_id': user_id,
        'uid': uid,
        'username': '',
        'password': password,
        'full_name': full_name,
        'cookies': cookies,
        'twofa_key': twofa_key,
        'twofa_code': twofa_code,
        'task_type': task_type,
        'reward': reward,
        'status': 'pending',
        'submitted_at': firestore.SERVER_TIMESTAMP
    }
    db.collection('submissions').add(task_data)
    
    serial = save_task_submission(user_id, uid, password, full_name, twofa_key, twofa_code, task_type, reward, cookies=cookies)
    
    clear_pending_task(user_id)
    db.collection('users').document(str(user_id)).update({
        'pending_tasks': firestore.Increment(1),
        'total_tasks': firestore.Increment(1)
    })
    invalidate_user_cache(user_id)
    
    user_states.pop(user_id, None)
    
    await message.answer(
        get_text(user_id, 'task_submit_ok'),
        reply_markup=after_submit_keyboard(task_id),
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== 2FA রিসিভ ====================

async def is_awaiting_2fa(message: types.Message):
    txt = (message.text or "").strip()
    if not txt or len(txt) < 10:
        return False
    if txt in MENU_BUTTON_TEXTS or txt.startswith("/"):
        return False
    uid = message.from_user.id
    if uid in user_states:
        return False
    # শুধু মেমোরি — প্রতি মেসেজে Firestore read নয় (super fast)
    return uid in PENDING_TASK_USERS

@dp.message_handler(is_awaiting_2fa)
async def receive_2fa(message: types.Message):
    user_id = message.from_user.id
    raw = (message.text or "").strip()
    if raw in MENU_BUTTON_TEXTS or raw.startswith("/"):
        return
    twofa_key = raw
    
    twofa_key = re.sub(r'[\s\-\._]+', '', twofa_key.upper())
    
    original_key = twofa_key
    twofa_key = twofa_key.replace('0', 'O').replace('1', 'I').replace('8', 'B').replace('9', 'G')
    
    if twofa_key != original_key:
        await message.answer(
            f"✅ **Key টি ফরম্যাট করা হয়েছে!**\n\n"
            f"🔑 নতুন Key: `{twofa_key}`\n\n"
            f"📌 0→O, 1→I, 8→B, 9→G কনভার্ট করা হয়েছে।\n"
            f"🔄 OTP জেনারেট করা হচ্ছে...",
            parse_mode=ParseMode.MARKDOWN
        )
    
    if len(twofa_key) < 10:
        await message.answer(
            "❌ **2FA Key খুব ছোট!**\n\n"
            "🔑 কমপক্ষে ১০ ক্যারেক্টার হতে হবে।\n"
            "📝 আবার চেষ্টা করুন:",
            reply_markup=task_cancel_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if not re.match(r'^[A-Z2-7]+$', twofa_key):
        await message.answer(
            "❌ **ভুল 2FA Key!**\n\n"
            "🔑 Instagram/Facebook এর 2FA Key তে শুধু থাকে:\n"
            "✅ A-Z (বড় হাতের)\n"
            "✅ 2, 3, 4, 5, 6, 7\n"
            "❌ 0, 1, 8, 9 (এগুলো Base32 তে নেই)\n\n"
            "আবার সঠিক Key টাইপ করুন:",
            reply_markup=task_cancel_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        import pyotp
        totp = pyotp.TOTP(twofa_key)
        twofa_code = totp.now()
        
        if len(twofa_code) != 6 or not twofa_code.isdigit():
            raise ValueError("Invalid OTP")
            
    except Exception as e:
        await message.answer(
            f"❌ **2FA Key টি সঠিক নয়!**\n\n"
            f"🔑 সমস্যা: `{str(e)}`\n\n"
            f"📝 ইনস্টাগ্রাম/ফেসবুক থেকে সঠিক Key কপি করুন।\n"
            f"⚠️ স্পেস বা ড্যাশ ছাড়া লিখুন।",
            reply_markup=task_cancel_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    doc = db.collection('temp_tasks').document(str(user_id)).get()
    if not doc.exists:
        await message.answer("❌ টাস্ক ডেটা পাওয়া যায়নি!")
        return
    
    data = doc.to_dict()
    task_id = data.get('task_id', '')
    username = data.get('username', '')
    password = data.get('password', '')
    full_name = data.get('full_name', '')
    reward = data.get('reward', 4.0)
    uid = data.get('uid', '')
    
    db.collection('temp_2fa').document(str(user_id)).set({
        'twofa_key': twofa_key,
        'task_id': task_id,
        'username': username,
        'uid': uid,
        'password': password,
        'full_name': full_name,
        'reward': reward,
        'created_at': firestore.SERVER_TIMESTAMP
    })
    
    keyboard = build_2fa_code_keyboard(user_id, twofa_code)
    
    await message.answer(
        f"🔢 ** Your 2FA Code:** `{twofa_code}`\n"
        f"⏰ **ভ্যালিডিটি:** ৩০ সেকেন্ড\n\n",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== 2FA বাতিল কলব্যাক ====================

@dp.callback_query_handler(lambda c: c.data.startswith("cancel_2fa_"))
async def cancel_2fa_code(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await cb_answer(callback)
    def _del():
        try:
            db.collection('temp_2fa').document(str(user_id)).delete()
            db.collection('temp_tasks').document(str(user_id)).delete()
        except Exception:
            pass
    try:
        asyncio.get_event_loop().create_task(asyncio.to_thread(_del))
    except Exception:
        _del()
    try:
        await callback.message.edit_text("❌ বাতিল করা হয়েছে।")
    except Exception:
        pass

# ==================== 2FA রিফ্রেশ কলব্যাক ====================


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("cp2fa_"))
async def copy_2fa_alert(callback: types.CallbackQuery):
    """Fallback when native copy_text unsupported — show code in alert."""
    code = callback.data.replace("cp2fa_", "", 1)
    await callback.answer(f"2FA Code: {code}", show_alert=True)

@dp.callback_query_handler(lambda c: c.data.startswith("refresh_2fa_"))
async def refresh_2fa_code(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await cb_answer(callback)

    def _work():
        doc = db.collection('temp_2fa').document(str(user_id)).get()
        if not doc.exists:
            return None, "missing"
        data = doc.to_dict() or {}
        key = data.get('twofa_key', '')
        try:
            import pyotp
            code = pyotp.TOTP(key).now()
            if len(code) != 6 or not code.isdigit():
                return None, "badotp"
            return code, key
        except Exception as e:
            return None, str(e)

    code, info = await asyncio.to_thread(_work)
    if not code:
        msg = "❌ 2FA ডেটা পাওয়া যায়নি! আবার Key দিন।" if info == "missing" else f"❌ 2FA Key ত্রুটিপূর্ণ! আবার Key দিন।"
        try:
            await callback.message.edit_text(msg)
        except Exception:
            try:
                await callback.message.answer(msg)
            except Exception:
                pass
        return

    # firestore touch in background
    def _touch():
        try:
            db.collection('temp_2fa').document(str(user_id)).update({'updated_at': firestore.SERVER_TIMESTAMP})
        except Exception:
            pass
    try:
        asyncio.get_event_loop().create_task(asyncio.to_thread(_touch))
    except Exception:
        pass

    keyboard = build_2fa_code_keyboard(user_id, code)
    body = f"🔢 ** Your 2FA Code:** `{code}`\n⏰ **ভ্যালিডিটি:** ৩০ সেকেন্ড\n\n"
    body = "🔢 ** Your 2FA Code:** `" + str(code) + "`" + chr(10) + "⏰ **ভ্যালিডিটি:** ৩০ সেকেন্ড" + chr(10) + chr(10)
    try:
        await callback.message.edit_text(body, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        try:
            await callback.message.reply(body, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass


@dp.callback_query_handler(lambda c: c.data.startswith("submit_2fa_"))
async def submit_2fa_code(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await cb_answer(callback)

    doc = db.collection('temp_2fa').document(str(user_id)).get()
    if not doc.exists:
        await callback.message.edit_text(
            "❌ 2FA ডেটা পাওয়া যায়নি! আবার Key দিন।",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
        return
    
    data = doc.to_dict()
    twofa_key = data.get('twofa_key', '')
    task_id = data.get('task_id', '')
    if not get_task(task_id):
        try:
            await callback.message.edit_text("❌ এই টাস্ক ডিলিট করা হয়েছে। সাবমিট করা যাবে না।")
        except Exception:
            await callback.message.answer("❌ এই টাস্ক ডিলিট করা হয়েছে। সাবমিট করা যাবে না।")
        clear_pending_task(user_id)
        try:
            db.collection('temp_2fa').document(str(user_id)).delete()
            db.collection('temp_tasks').document(str(user_id)).delete()
        except Exception:
            pass
        return
    username = data.get('username', '')
    uid = normalize_fb_uid(data.get('uid', ''))
    if uid:
        try:
            used = await asyncio.to_thread(is_facebook_uid_used, uid)
        except Exception:
            used = is_facebook_uid_used(uid)
        if used:
            try:
                await callback.message.edit_text(
                    "❌ এই Facebook UID আগেই সাবমিট করা হয়েছে!" + chr(10) +
                    f"🆔 `{uid}`" + chr(10) + "অন্য UID দিয়ে নতুন টাস্ক করুন।"
                )
            except Exception:
                await callback.message.answer(
                    "❌ এই Facebook UID আগেই সাবমিট করা হয়েছে! অন্য UID ব্যবহার করুন।"
                )
            return
    password = data.get('password', '')
    full_name = data.get('full_name', '')
    reward = data.get('reward', 4.0)
    
    try:
        import pyotp
        totp = pyotp.TOTP(twofa_key)
        twofa_code = totp.now()
    except Exception as e:
        await callback.message.edit_text(
            f"❌ 2FA Key ত্রুটিপূর্ণ! আবার Key দিন।\n\nএরর: {e}",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
        return
    
    mode = get_verification_mode(task_id)

    # fb_2fa_cookies: code দেখাবে, তারপর Cookies চাইবে — sheet-এ শুধু Key যাবে
    if mode == "fb_2fa_cookies":
        try:
            db.collection('temp_tasks').document(str(user_id)).update({
                'twofa_key': twofa_key,
                'twofa_code': twofa_code,
                'uid': uid or data.get('uid', ''),
            })
        except Exception:
            db.collection('temp_tasks').document(str(user_id)).set({
                'task_id': task_id,
                'password': password,
                'full_name': full_name,
                'reward': reward,
                'mode': mode,
                'uid': uid or data.get('uid', ''),
                'twofa_key': twofa_key,
                'twofa_code': twofa_code,
            }, merge=True)
        user_states[user_id] = "awaiting_cookies"
        await callback.message.edit_text(
            f"✅ **2FA Code জেনারেট হয়েছে!**\n\n"
            f"🔢 **2FA Code:** `{twofa_code}`\n"
            f"(এই code sheet/CSV তে সেভ হবে না — শুধু Key সেভ হবে)\n\n"
            f"🍪 **এখন আপনার Facebook Cookies পেস্ট করুন:**",
            reply_markup=task_cancel_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer("✅ Code OK — এখন Cookies দিন")
        return

    task = get_task(task_id)
    task_type = task.get('name', 'Unknown') if task else 'Unknown'
    
    task_data = {
        'task_id': task_id,
        'user_id': user_id,
        'username': username,
        'uid': uid,
        'password': password,
        'full_name': full_name,
        'twofa_key': twofa_key,
        'twofa_code': twofa_code,
        'task_type': task_type,
        'reward': reward,
        'status': 'pending',
        'submitted_at': firestore.SERVER_TIMESTAMP
    }
    db.collection('submissions').add(task_data)
    
    serial = save_task_submission(
        user_id, (username or uid), password, full_name, 
        twofa_key, twofa_code, task_type, reward
    )
    
    clear_pending_task(user_id)
    
    db.collection('users').document(str(user_id)).update({
        'pending_tasks': firestore.Increment(1),
        'total_tasks': firestore.Increment(1)
    })
    invalidate_user_cache(user_id)
    
    await callback.message.edit_text(
        get_text(user_id, 'task_submit_ok'),
        reply_markup=after_submit_keyboard(task_id),
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer("✅ সাবমিট হয়েছে!")

# ==================== Cancel ====================

@dp.callback_query_handler(lambda c: c.data == "task_cancel")
async def task_cancel(callback: types.CallbackQuery):
    clear_pending_task(callback.from_user.id)
    user_states.pop(callback.from_user.id, None)
    await callback.message.edit_text(get_text(callback.from_user.id, 'task_cancelled'))
    await callback.answer()

# ==================== রেফারেল ====================

@dp.message_handler(lambda message: message.text in ["🔗 রেফারেল", "🔗 Referral"])
async def show_referral(message: types.Message):
    user_id = message.from_user.id
    if not await require_force_join(message, user_id):
        return
    user = get_user(user_id)
    if not user:
        user = create_user(user_id, message.from_user.username, message.from_user.first_name)
    if not BOT_USERNAME_CACHE["value"]:
        bot_info = await bot.get_me()
        BOT_USERNAME_CACHE["value"] = bot_info.username
    ref_link = f"https://t.me/{BOT_USERNAME_CACHE['value']}?start=ref_{user_id}"
    notify_on = user.get("ref_notify", True) is not False
    if notify_on:
        notify_btn = colored_button("🔔 Notification: ON", callback_data="ref_notify_off", style="success")
        note = "\n\n🔔 কমিশন নোটিফিকেশন চালু — অ্যাপ্রুভ হলে মেসেজ পাবেন।"
    else:
        notify_btn = colored_button("🔕 Notification: OFF", callback_data="ref_notify_on", style="danger")
        note = "\n\n🔕 কমিশন নোটিফিকেশন বন্ধ — মেসেজ যাবে না, কমিশন balance-এ যোগ হবে।"
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(colored_button("📤 শেয়ার করুন", switch_inline_query=ref_link))
    kb.add(notify_btn)
    body = get_text(user_id, 'referral',
        link=ref_link, total=user.get('total_refers', 0), income=user.get('refer_income', 0), commission=REFERRAL_COMMISSION_PERCENT
    )
    # note already has escaped - fix:
    note = ("\n\n" if False else chr(10)+chr(10)) + (
        "🔔 কমিশন নোটিফিকেশন চালু — অ্যাপ্রুভ হলে মেসেজ পাবেন।" if notify_on
        else "🔕 কমিশন নোটিফিকেশন বন্ধ — মেসেজ যাবে না, কমিশন balance-এ যোগ হবে।"
    )
    await message.answer(body + note, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

@dp.callback_query_handler(lambda c: c.data.startswith("copy_"))
async def copy_referral_link(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not BOT_USERNAME_CACHE["value"]:
        bot_info = await bot.get_me()
        BOT_USERNAME_CACHE["value"] = bot_info.username
    ref_link = f"https://t.me/{BOT_USERNAME_CACHE['value']}?start=ref_{user_id}"
    await callback.answer(f"লিংক কপি করতে নিচের মেসেজে থাকা লিংকে ট্যাপ করুন:\n{ref_link}", show_alert=True)


@dp.callback_query_handler(lambda c: c.data in ("ref_notify_on", "ref_notify_off"))
async def toggle_ref_notify(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    turn_on = callback.data == "ref_notify_on"
    try:
        db.collection("users").document(str(user_id)).update({"ref_notify": turn_on})
        invalidate_user_cache(user_id)
    except Exception as e:
        logger.error(f"ref_notify update error: {e}")
        await callback.answer("❌ সেভ করতে সমস্যা", show_alert=True)
        return
    user = get_user(user_id) or {}
    if not BOT_USERNAME_CACHE["value"]:
        try:
            bot_info = await bot.get_me()
            BOT_USERNAME_CACHE["value"] = bot_info.username
        except Exception:
            BOT_USERNAME_CACHE["value"] = "bot"
    ref_link = f"https://t.me/{BOT_USERNAME_CACHE['value']}?start=ref_{user_id}"
    notify_on = turn_on
    if notify_on:
        notify_btn = colored_button("🔔 Notification: ON", callback_data="ref_notify_off", style="success")
    else:
        notify_btn = colored_button("🔕 Notification: OFF", callback_data="ref_notify_on", style="danger")
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(colored_button("📤 শেয়ার করুন", switch_inline_query=ref_link))
    kb.add(notify_btn)
    note = (chr(10)+chr(10)) + (
        "🔔 কমিশন নোটিফিকেশন চালু — অ্যাপ্রুভ হলে মেসেজ পাবেন।" if notify_on
        else "🔕 কমিশন নোটিফিকেশন বন্ধ — মেসেজ যাবে না, কমিশন balance-এ যোগ হবে।"
    )
    body = get_text(user_id, "referral",
        link=ref_link, total=user.get("total_refers", 0), income=user.get("refer_income", 0),
        commission=REFERRAL_COMMISSION_PERCENT)
    try:
        await callback.message.edit_text(body + note, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        try:
            await callback.message.edit_text(body + note, reply_markup=kb)
        except Exception:
            pass
    await callback.answer("🔔 নোটিফিকেশন চালু" if notify_on else "🔕 নোটিফিকেশন বন্ধ")


# ==================== প্রোফাইল (পুরনো Report) ====================

@dp.message_handler(lambda message: message.text in [
    "📊 রিপোর্ট", "📊 Report", "📊 আমার রিপোর্ট", "👤 Profile", "👤 প্রোফাইল"
])
async def show_report(message: types.Message):
    """Fast accurate Profile: live counts + last 5 (account name) + pending IDs"""
    user_id = message.from_user.id
    if not await require_force_join(message, user_id):
        return
    user = get_user(user_id)
    if not user:
        await message.answer("❌ আপনার কোনো ডেটা নেই!")
        return

    lang = (user or {}).get("lang", "bn")
    en = lang == "en"

    def _fetch_fast():
        """Fetch submissions — int + string user_id, no composite index."""
        by_id = {}
        for uid_q in (user_id, str(user_id)):
            try:
                for d in db.collection("submissions").where("user_id", "==", uid_q).limit(40).stream():
                    by_id[d.id] = d.to_dict() or {}
            except Exception as e:
                logger.warning(f"profile subs fetch ({uid_q}): {e}")
        subs = list(by_id.values())
        subs.sort(key=lambda s: s.get("submitted_at") or datetime.min, reverse=True)
        return subs

    try:
        subs = await asyncio.to_thread(_fetch_fast)
    except Exception as e:
        logger.error(f"Profile fetch error: {e}")
        subs = []

    # Live counts from real submissions (not stale user fields alone)
    live_pending = 0
    live_approved = 0
    live_rejected = 0
    live_cancelled = 0
    for s in subs:
        st = str(s.get("status") or "pending").lower()
        if st == "pending":
            live_pending += 1
        elif st == "approved":
            live_approved += 1
        elif st.startswith("cancel"):
            live_cancelled += 1
        else:
            live_rejected += 1

    # Prefer higher of live vs stored (stored may include older beyond limit)
    total_tasks = max(int(user.get("total_tasks", 0) or 0), len(subs))
    approved_n = max(int(user.get("approved_tasks", 0) or 0), live_approved)
    pending_n = max(int(user.get("pending_tasks", 0) or 0), live_pending)
    rejected_n = max(int(user.get("rejected_tasks", 0) or 0), live_rejected)

    # Last 5 — 1 line, with TASK ACCOUNT name (not Telegram)
    last5_lines = []
    for s in subs[:5]:
        st = str(s.get("status") or "pending").lower()
        if st == "approved":
            em, stt = "✅", "Approved"
        elif st == "pending":
            em, stt = "⏳", "Pending"
        elif st.startswith("cancel"):
            em, stt = "🗑", "Cancelled"
        else:
            em, stt = "❌", "Rejected"
        ttype = str(s.get("task_type") or s.get("task_id") or "N/A").replace("\n", " ").strip()
        if len(ttype) > 28:
            ttype = ttype[:28] + "…"
        reward = float(s.get("reward", 0) or 0)
        acc = get_task_account_name(s)
        if acc and acc != "account":
            last5_lines.append(f"{em} {ttype} > {reward:.2f} Tk | `{acc}` ({stt})")
        else:
            last5_lines.append(f"{em} {ttype} > {reward:.2f} Tk ({stt})")

    # Pending IDs — only real pending + task account uid/username
    pending_id_lines = []
    for s in subs:
        st = str(s.get("status") or "pending").lower()
        if st != "pending":
            continue
        acc = get_task_account_name(s)
        if not acc or acc == "account":
            continue
        ttype = str(s.get("task_type") or s.get("task_id") or "").replace("\n", " ").strip()
        if len(ttype) > 22:
            ttype = ttype[:22] + "…"
        reward = float(s.get("reward", 0) or 0)
        pending_id_lines.append(f"⏳ {ttype} > {reward:.2f} Tk — `{acc}`")
        if len(pending_id_lines) >= 10:
            break

    if not last5_lines:
        last5_lines.append("└── " + ("No tasks yet" if en else "কোনো টাস্ক নেই"))
    if not pending_id_lines:
        pending_id_lines.append("└── " + ("No pending" if en else "কোনো pending নেই"))

    bal = float(user.get("balance", 0) or 0)
    nl = chr(10)

    if en:
        body = (
            f"📊 **Report**{nl}{nl}"
            f"💰 Balance: Tk {bal:.2f}{nl}"
            f"📋 Total Submitted: {total_tasks}{nl}"
            f"✅ Approved: {approved_n}{nl}"
            f"⏳ Pending: {pending_n}{nl}"
            f"❌ Rejected: {rejected_n}{nl}{nl}"
            f"📌 **Last 5 Tasks:**{nl}"
            + nl.join(last5_lines)
            + f"{nl}{nl}🆔 **Pending IDs:**{nl}"
            + nl.join(pending_id_lines)
        )
    else:
        body = (
            f"📊 **রিপোর্ট**{nl}{nl}"
            f"💰 ব্যালেন্স: Tk {bal:.2f}{nl}"
            f"📋 মোট সাবমিট: {total_tasks}{nl}"
            f"✅ অ্যাপ্রুভ: {approved_n}{nl}"
            f"⏳ পেন্ডিং: {pending_n}{nl}"
            f"❌ রিজেক্ট: {rejected_n}{nl}{nl}"
            f"📌 **শেষ ৫টা টাস্ক:**{nl}"
            + nl.join(last5_lines)
            + f"{nl}{nl}🆔 **Pending IDs:**{nl}"
            + nl.join(pending_id_lines)
        )

    if len(body) > 3900:
        body = body[:3850] + nl + "…"

    try:
        await message.answer(body, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await message.answer(body.replace("**", "").replace("`", ""))


# ==================== Language button ====================

@dp.message_handler(lambda message: message.text == "🌐 Language / ভাষা")
async def show_language_button(message: types.Message):
    await message.answer(
        "🌐 **Choose your language / ভাষা নির্বাচন করুন**",
        reply_markup=get_language_menu(),
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== সাপোর্ট ====================

@dp.message_handler(lambda message: message.text in ["🛠 সাপোর্ট", "🛠 Support"])
async def show_support(message: types.Message):
    user_id = message.from_user.id
    if not await require_force_join(message, user_id):
        return
    text = get_text(user_id, 'support', contact=SUPPORT_CONTACT)
    keyboard = InlineKeyboardMarkup(row_width=1)
    admin_link = SUPPORT_ADMIN_LINK or (f"https://t.me/{SUPPORT_CONTACT.lstrip('@')}" if SUPPORT_CONTACT else "")
    if admin_link:
        keyboard.add(InlineKeyboardButton("👨‍💼 Admin Support", url=admin_link))
    if SUPPORT_CHANNEL_LINK:
        keyboard.add(InlineKeyboardButton("📢 Official Channel", url=SUPPORT_CHANNEL_LINK))
    try:
        await message.answer(text, reply_markup=keyboard if keyboard.inline_keyboard else None, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Show Support Markdown Error: {e}")
        await message.answer(text, reply_markup=keyboard if keyboard.inline_keyboard else None, parse_mode=None)



def normalize_withdraw_chat(chat):
    """@channel / t.me link / -100id → Telegram chat target."""
    s = str(chat or "").strip()
    if not s:
        return ""
    s = s.replace("https://t.me/", "").replace("http://t.me/", "").replace("t.me/", "")
    s = s.split("?")[0].strip()
    if s.lstrip("-").isdigit():
        try:
            return int(s)
        except Exception:
            return s
    if not s.startswith("@"):
        s = "@" + s
    return s

async def notify_withdraw_request(group_text, keyboard, req_id):
    """Always try withdraw channel first; fallback plain text; also ping admins if channel fails."""
    global WITHDRAW_GROUP
    chat = normalize_withdraw_chat(WITHDRAW_GROUP)
    sent = False
    errors = []

    if chat:
        for parse in (ParseMode.MARKDOWN, None):
            try:
                await bot.send_message(chat, group_text if parse else group_text.replace("**", "").replace("`", ""),
                                       reply_markup=keyboard, parse_mode=parse)
                sent = True
                logger.info(f"Withdraw {req_id} sent to channel {chat}")
                break
            except Exception as e:
                errors.append(f"channel/{parse}: {e}")
                logger.error(f"Withdraw Group Notify Error ({chat}, {parse}): {e}")

    # Always also try admins if channel failed (so request never lost)
    if not sent:
        for admin_id in get_admins():
            try:
                await bot.send_message(admin_id, group_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
                sent = True
            except Exception:
                try:
                    await bot.send_message(admin_id, group_text.replace("**", "").replace("`", ""), reply_markup=keyboard)
                    sent = True
                except Exception as e:
                    errors.append(f"admin {admin_id}: {e}")
                    logger.error(f"Withdraw Admin DM Error: {e}")

    if not sent:
        logger.error(f"Withdraw {req_id} NOTIFY FAILED: {errors}")
    return sent

def is_binance_method(method):
    m = str(method or "").lower()
    return "binance" in m or "usdt" in m or "বিinance" in m

def bdt_to_usdt(bdt):
    rate = float(USDT_RATE_BDT or 126) or 126.0
    return float(bdt or 0) / rate

def usdt_to_bdt(usdt):
    rate = float(USDT_RATE_BDT or 126) or 126.0
    return float(usdt or 0) * rate

# ==================== উইথড্র ====================

@dp.message_handler(lambda message: message.text in ["💸 টাকা উত্তোলন", "💸 Withdraw"])
async def show_withdraw(message: types.Message):
    user_id = message.from_user.id

    if not WITHDRAW_ENABLED:
        await message.answer(get_text(user_id, 'withdraw_disabled'))
        return
    
    if not await require_force_join(message, user_id):
        return
    
    balance = get_balance(user_id)
    if balance < MIN_WITHDRAW:
        await message.answer(get_text(user_id, 'insufficient_balance', balance=balance, min_withdraw=MIN_WITHDRAW))
        return
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    for method in WITHDRAW_METHODS:
        keyboard.add(colored_button(method, callback_data=f"withdraw_{method}"))
    keyboard.add(colored_button("❌ বাতিল", callback_data="withdraw_cancel"))
    
    await message.answer(get_text(user_id, 'withdraw', balance=balance, min_withdraw=MIN_WITHDRAW), reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

@dp.callback_query_handler(lambda c: c.data.startswith("withdraw_"))
async def handle_withdraw(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await cb_answer(callback)
    data = callback.data
    if data == "withdraw_cancel":
        user_states.pop(user_id, None)
        temp_data.pop(user_id, None)
        try:
            await callback.message.edit_text("❌ উইথড্র বাতিল করা হয়েছে।")
        except Exception:
            pass
        return
    method = data.replace("withdraw_", "", 1)
    user_states[user_id] = f"withdraw_amount_{method}"
    balance = get_balance(user_id)
    temp_data[user_id] = {'method': method, 'is_usdt': is_binance_method(method)}
    cancel_kb = InlineKeyboardMarkup().add(colored_button("❌ বাতিল", callback_data="withdraw_cancel"))
    if is_binance_method(method):
        usdt_bal = bdt_to_usdt(balance)
        usdt_min = bdt_to_usdt(MIN_WITHDRAW)
        rate = float(USDT_RATE_BDT or 126)
        msg = (
            f"📝 **Enter withdrawal amount (USDT):**\n\n"
            f"💰 Your balance: **${usdt_bal:.2f} USDT**\n"
            f"   (Tk {balance:.2f} ÷ {rate:.0f})\n"
            f"⬇️ Minimum: **${usdt_min:.2f} USDT**\n"
            f"📌 Rate: {rate:.0f} Tk = 1 USDT\n\n"
            f"USDT অ্যামাউন্ট লিখুন (উদাহরণ: `1` বা `0.5`)"
        )
        # use real newlines
        msg = (
            "📝 **Enter withdrawal amount (USDT):**" + chr(10) + chr(10) +
            f"💰 Your balance: **${usdt_bal:.2f} USDT**" + chr(10) +
            f"   (Tk {balance:.2f} ÷ {rate:.0f})" + chr(10) +
            f"⬇️ Minimum: **${usdt_min:.2f} USDT**" + chr(10) +
            f"📌 Rate: {rate:.0f} Tk = 1 USDT" + chr(10) + chr(10) +
            "USDT অ্যামাউন্ট লিখুন (উদাহরণ: 1 বা 0.5)"
        )
        await callback.message.edit_text(msg, reply_markup=cancel_kb, parse_mode=ParseMode.MARKDOWN)
    else:
        await callback.message.edit_text(
            get_text(user_id, 'withdraw_amount', balance=balance, min_withdraw=MIN_WITHDRAW),
            reply_markup=cancel_kb, parse_mode=ParseMode.MARKDOWN
        )
    await callback.answer()

@dp.message_handler(lambda message: (
    message.from_user.id in user_states
    and str(user_states.get(message.from_user.id, "")).startswith("withdraw_amount_")
    and (message.text or "").strip() not in MENU_BUTTON_TEXTS
))
async def withdraw_amount(message: types.Message):
    user_id = message.from_user.id
    state = user_states[user_id]
    method = state.replace("withdraw_amount_", "")
    try:
        raw_amount = float(message.text.strip().replace("$", "").replace(",", ""))
        balance = get_balance(user_id)
        is_usdt = is_binance_method(method) or (temp_data.get(user_id) or {}).get("is_usdt")

        if is_usdt:
            usdt_amount = raw_amount
            amount_bdt = usdt_to_bdt(usdt_amount)
            usdt_bal = bdt_to_usdt(balance)
            usdt_min = bdt_to_usdt(MIN_WITHDRAW)
            if usdt_amount < usdt_min - 1e-9:
                await message.answer(
                    f"❌ মিনিমাম ${usdt_min:.2f} USDT (Tk {MIN_WITHDRAW:.2f})" + chr(10) +
                    "আবার USDT অ্যামাউন্ট দিন:"
                )
                return
            if usdt_amount > usdt_bal + 1e-9:
                await message.answer(
                    f"❌ ব্যালেন্স অপর্যাপ্ত!" + chr(10) +
                    f"💰 Available: ${usdt_bal:.2f} USDT (Tk {balance:.2f})" + chr(10) +
                    "আবার USDT অ্যামাউন্ট দিন:"
                )
                return
            if user_id not in temp_data:
                temp_data[user_id] = {}
            temp_data[user_id]["amount"] = amount_bdt
            temp_data[user_id]["usdt_amount"] = usdt_amount
            temp_data[user_id]["is_usdt"] = True
            user_states[user_id] = f"withdraw_account_{method}"
            cancel_kb = InlineKeyboardMarkup().add(colored_button("❌ বাতিল", callback_data="withdraw_cancel"))
            await message.answer(
                "📝 **আপনার Binance UID / Address লিখুন:**" + chr(10) + chr(10) +
                f"💵 USDT: ${usdt_amount:.2f}" + chr(10) +
                f"💰 BDT: Tk {amount_bdt:.2f}",
                reply_markup=cancel_kb,
                parse_mode=ParseMode.MARKDOWN
            )
            return

        amount = raw_amount
        if amount < MIN_WITHDRAW:
            await message.answer(f"❌ মিনিমাম উইথড্র {MIN_WITHDRAW} টাকা!" + chr(10) + "আবার অ্যামাউন্ট দিন:")
            return
        if amount > balance:
            await message.answer(f"❌ আপনার ব্যালেন্স অপর্যাপ্ত! ব্যালেন্স: {balance:.2f} টাকা" + chr(10) + "আবার অ্যামাউন্ট দিন:")
            return
        if user_id not in temp_data:
            temp_data[user_id] = {}
        temp_data[user_id]["amount"] = amount
        temp_data[user_id]["is_usdt"] = False
        user_states[user_id] = f"withdraw_account_{method}"
        cancel_kb = InlineKeyboardMarkup().add(colored_button("❌ বাতিল", callback_data="withdraw_cancel"))
        await message.answer(get_text(user_id, "withdraw_method", method=method), reply_markup=cancel_kb, parse_mode=ParseMode.MARKDOWN)
    except ValueError:
        await message.answer("❌ সঠিক অ্যামাউন্ট দিন!")

@dp.message_handler(lambda message: (
    message.from_user.id in user_states
    and str(user_states.get(message.from_user.id, "")).startswith("withdraw_account_")
    and (message.text or "").strip() not in MENU_BUTTON_TEXTS
))
async def withdraw_account(message: types.Message):
    user_id = message.from_user.id
    state = user_states.pop(user_id, "")
    data = temp_data.pop(user_id, {})
    method = state.replace("withdraw_account_", "")
    account = message.text.strip()
    amount = data.get('amount', 0)
    usdt_amount = data.get('usdt_amount')
    is_usdt = data.get('is_usdt') or is_binance_method(method)
    req_id = f"WD{datetime.now().strftime('%Y%m%d%H%M%S')}{user_id % 1000}"
    update_balance(user_id, -amount)
    wd_doc = {
        'user_id': user_id, 'amount': amount, 'method': method,
        'account': account, 'status': 'pending', 'req_id': req_id,
        'created_at': firestore.SERVER_TIMESTAMP
    }
    if is_usdt and usdt_amount is not None:
        wd_doc['usdt_amount'] = usdt_amount
        wd_doc['usdt_rate'] = float(USDT_RATE_BDT or 126)
    db.collection('withdrawals').document(req_id).set(wd_doc)
    if is_usdt and usdt_amount is not None:
        confirm = (
            f"✅ **উইথড্র রিকোয়েস্ট সাবমিট হয়েছে!**\n\n"
            f"🧾 রিকোয়েস্ট আইডি: {req_id}\n"
            f"💵 USDT: ${float(usdt_amount):.2f}\n"
            f"💰 BDT: Tk {float(amount):.2f}\n"
            f"📱 মেথড: {method}\n"
            f"🔢 Account: {account}"
        )
        await message.answer(confirm, parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(get_text(user_id, 'withdraw_confirm',
            req_id=req_id, amount=amount, method=method, account=account
        ), parse_mode=ParseMode.MARKDOWN)
    
    user = get_user(user_id)
    # Include USDT info in channel message when applicable
    extra = ""
    if is_usdt and usdt_amount is not None:
        extra = f"\n💵 USDT: ${float(usdt_amount):.2f} (rate {float(USDT_RATE_BDT or 126):.0f})"
    try:
        group_text = get_text(user_id, 'withdraw_group',
            user=get_user_display(user_id, user),
            amount=amount, method=method, account=account, req_id=req_id
        )
        if extra and extra not in group_text:
            group_text = group_text + extra.replace("\\n", chr(10))
    except Exception:
        group_text = (
            f"💸 নতুন উইথড্র রিকোয়েস্ট!" + chr(10) + chr(10) +
            f"👤 User: {get_user_display(user_id, user)}" + chr(10) +
            f"💰 Amount: Tk {amount}" + chr(10) +
            f"📱 Method: {method}" + chr(10) +
            f"🔢 Account: {account}" + chr(10) +
            f"🧾 ID: {req_id}"
        )
        if is_usdt and usdt_amount is not None:
            group_text += chr(10) + f"💵 USDT: ${float(usdt_amount):.2f}"

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        colored_button("✅ Approve", callback_data=f"wd_approve_{req_id}"),
        colored_button("❌ Reject", callback_data=f"wd_reject_{req_id}")
    )
    try:
        notified = await notify_withdraw_request(group_text, keyboard, req_id)
        if not notified:
            await message.answer(
                "⚠️ রিকোয়েস্ট সেভ হয়েছে, কিন্তু চ্যানেলে পাঠানো যায়নি।" + chr(10) +
                "Admin: Withdraw Group ID ঠিক আছে কিনা ও বট চ্যানেলে Admin কিনা চেক করুন।"
            )
    except Exception as e:
        logger.error(f"Withdraw notify fatal: {e}")
        await message.answer("⚠️ রিকোয়েস্ট সেভ হয়েছে। চ্যানেল নোটিফাইতে সমস্যা হয়েছে — অ্যাডমিন চেক করুন।")

@dp.callback_query_handler(lambda c: c.data.startswith("wd_"))
async def withdraw_approve(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("❌ আপনি অ্যাডমিন নন!", show_alert=True)
        return
    data = callback.data
    req_id = data.replace("wd_approve_", "").replace("wd_reject_", "")
    action = "approve" if "approve" in data else "reject"
    doc = db.collection('withdrawals').document(req_id).get()
    if not doc.exists:
        await callback.answer("❌ রিকোয়েস্ট পাওয়া যায়নি!", show_alert=True)
        return
    wd_data = doc.to_dict()
    target_user_id = wd_data.get('user_id')
    amount = wd_data.get('amount', 0)
    if action == "approve":
        db.collection('withdrawals').document(req_id).update({'status': 'approved'})
        await bot.send_message(target_user_id, get_text(target_user_id, 'withdraw_approved', amount=amount))
        await callback.message.edit_text(f"✅ {req_id} অ্যাপ্রুভ করা হয়েছে!")
    else:
        update_balance(target_user_id, amount)
        db.collection('withdrawals').document(req_id).update({'status': 'rejected'})
        await bot.send_message(target_user_id, get_text(target_user_id, 'withdraw_rejected', amount=amount))
        await callback.message.edit_text(f"❌ {req_id} রিজেক্ট করা হয়েছে!")
    await callback.answer()

# ==================== অ্যাডমিন প্যানেল ====================

@dp.callback_query_handler(lambda c: c.data == "admin_panel_back")
async def admin_panel_back(callback: types.CallbackQuery):
    await cb_answer(callback)
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("❌ আপনি অ্যাডমিন নন!", show_alert=True)
        return
    try:
        text, keyboard = build_admin_panel_content(user_id)
    except Exception as e:
        logger.error(f"admin_panel_back build error: {e}")
        await callback.answer("❌ Panel load failed", show_alert=True)
        return
    await safe_edit(callback.message, text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    await callback.answer()

def build_admin_panel_content(user_id):
    # SPEED: use cached active tasks + light counts
    tasks = get_active_tasks()
    
    # Cache admin panel counts for 20 seconds
    counts = cache.get("admin_counts")
    if counts is None:
        try:
            all_tasks_count = len(list(db.collection('tasks').limit(200).stream()))
            users_count = len(list(db.collection('users').limit(500).stream()))
            pending_subs = len(list(db.collection('submissions').where('status', '==', 'pending').limit(100).stream()))
            pending_wd = len(list(db.collection('withdrawals').where('status', '==', 'pending').limit(50).stream()))
            counts = {
                "tasks": all_tasks_count,
                "users": users_count,
                "pending_subs": pending_subs,
                "pending_wd": pending_wd
            }
            cache.set("admin_counts", counts, ttl=60)
        except Exception:
            counts = {"tasks": 0, "users": 0, "pending_subs": 0, "pending_wd": 0}
    
    task_list = ""
    for task in tasks[:5]:
        tname = escape_md(task.get('name', 'N/A'))
        temoji = str(task.get('emoji', '') or '')
        try:
            reward = float(task.get('reward', 0) or 0)
        except Exception:
            reward = 0.0
        task_list += f"• {temoji} {tname} (Tk {reward:.2f})\n"
    if not task_list:
        task_list = "• কোনো টাস্ক নেই"
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        colored_button(f"📥 সাবমিশন ({counts['pending_subs']})", callback_data="admin_submissions"),
        colored_button(f"💸 উইথড্র রিকোয়েস্ট ({counts['pending_wd']})", callback_data="admin_withdrawals"),
        colored_button("➕ টাস্ক যোগ", callback_data="admin_add_task"),
        colored_button("✏️ টাস্ক এডিট", callback_data="admin_edit_task"),
        colored_button("🗑️ টাস্ক ডিলিট", callback_data="admin_delete_task"),
        colored_button("📋 সব টাস্ক", callback_data="admin_all_tasks"),
        colored_button("👥 ইউজার লিস্ট", callback_data="admin_users"),
        colored_button("📢 ব্রডকাস্ট", callback_data="admin_broadcast"),
        colored_button("🏆 লিডারবোর্ড", callback_data="admin_leaderboard"),
        colored_button("⚙️ সেটিংস", callback_data="admin_settings"),
        colored_button("👑 অ্যাডমিন ম্যানেজ", callback_data="admin_manage"),
        colored_button("👤 ইউজার ম্যানেজ", callback_data="admin_user_manage"),
        colored_button("🔍 User Pending ID", callback_data="admin_user_pending"),
        colored_button("🎥 বট ওয়ার্ক সিস্টেম", callback_data="admin_folder_guide"),
        colored_button("📊 ডাটা ও শিট ম্যানেজমেন্ট", callback_data="admin_folder_data"),
        colored_button("❌ বন্ধ করুন", callback_data="admin_close")
    )
    text = get_text(user_id, 'admin_panel',
        tasks=counts["tasks"], active=len(tasks), users=counts["users"], task_list=task_list
    )
    return text, keyboard

def build_guide_folder_content():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        colored_button("🎥 ভিডিও সেট করুন", callback_data="admin_set_video"),
        colored_button("➕ কাস্টম বাটন যোগ", callback_data="admin_add_gbtn"),
        colored_button("🗑️ কাস্টম বাটন ডিলিট", callback_data="admin_del_gbtn"),
        colored_button("🔙 পিছনে", callback_data="admin_panel_back")
    )
    text = (
        "🎥 **বট ওয়ার্ক সিস্টেম**\n\n"
        "এখানে \"🎥 বট ওয়ার্ক সিস্টেম\" মেনুর মেইন ভিডিও এবং কাস্টম বাটন (কয়েন ইনকাম, Instagram 2FA ইত্যাদি) ম্যানেজ করুন।"
    )
    return text, keyboard

def build_data_folder_content():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        colored_button("📤 Upload Report", callback_data="admin_upload_report"),
        colored_button("✅ Report Ready", callback_data="admin_report_ready", style="success"),
        colored_button("🗑️ Delete Report", callback_data="admin_delete_report"),
        colored_button("📥 Download Report", callback_data="admin_download_report"),
        colored_button("🔙 পিছনে", callback_data="admin_panel_back"),
    )
    text = (
        "📊 **ডাটা ও শিট ম্যানেজমেন্ট**\n\n"
        "রিপোর্ট Upload, Delete/Reset এবং task-wise Download এখান থেকে করুন।"
    )
    return text, keyboard

def _saved_task_names():
    """Task names from local CSV + Firestore (so data survives Render restart)."""
    names = []
    seen = set()

    def _add(name):
        name = (name or "").strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)

    # 1) Local CSV (fast)
    try:
        _ensure_csv_file()
        with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                _add(row.get("Task Type") or "")
    except Exception as e:
        logger.error(f"Task name CSV read error: {e}")

    # 2) Firestore submissions (persistent — survives restart)
    try:
        for status in ("pending", "approved", "cancelled", "rejected"):
            try:
                for d in db.collection("submissions").where("status", "==", status).limit(300).stream():
                    s = d.to_dict() or {}
                    _add(s.get("task_type") or s.get("task_id") or "")
            except Exception as e:
                logger.warning(f"task names firestore ({status}): {e}")
    except Exception as e:
        logger.error(f"Task name Firestore error: {e}")

    return names


def _load_task_rows(task_name):
    """Load all rows for a task from CSV + Firestore. Deduped."""
    task_name = (task_name or "").strip()
    rows = []
    seen = set()  # (user_id, username, password, status)

    def _key(r):
        return (
            str(r.get("User ID") or ""),
            str(r.get("Username") or ""),
            str(r.get("Password") or ""),
            str(r.get("Status") or ""),
        )

    # CSV first
    try:
        _ensure_csv_file()
        with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if (r.get("Task Type") or "").strip() != task_name:
                    continue
                k = _key(r)
                if k in seen:
                    continue
                seen.add(k)
                rows.append(r)
    except Exception as e:
        logger.error(f"load task CSV: {e}")

    # Firestore (source of truth after restart)
    try:
        for status in ("pending", "approved", "cancelled", "rejected"):
            try:
                stream = db.collection("submissions").where("status", "==", status).limit(400).stream()
            except Exception:
                continue
            for d in stream:
                s = d.to_dict() or {}
                ttype = str(s.get("task_type") or s.get("task_id") or "").strip()
                if ttype != task_name:
                    continue
                submitted = s.get("submitted_at")
                if hasattr(submitted, "strftime"):
                    time_str = submitted.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    time_str = str(submitted or "")
                uid_val = s.get("uid") or s.get("username") or ""
                row = {
                    "Serial": "",
                    "User ID": str(s.get("user_id") or ""),
                    "Username": str(uid_val),
                    "Full Name": str(s.get("full_name") or ""),
                    "Password": str(s.get("password") or ""),
                    "Cookies": str(s.get("cookies") or "").replace("\r", " ").replace("\n", " "),
                    "2FA Key": str(s.get("twofa_key") or ""),
                    "Task Type": ttype,
                    "Reward": str(s.get("reward") or 0),
                    "Status": str(s.get("status") or status),
                    "Time": time_str,
                }
                k = _key(row)
                if k in seen:
                    continue
                seen.add(k)
                rows.append(row)
    except Exception as e:
        logger.error(f"load task Firestore: {e}")

    # Serial numbers
    for i, r in enumerate(rows, 1):
        r["Serial"] = f"#{i:03d}"
    return rows


def _safe_task_filename(task_name):
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in task_name)[:50] or "task"
    return f"{safe_name}_task_data.csv"

def _write_task_file(task_name, rows=None):
    if rows is None:
        rows = _load_task_rows(task_name)
    safe_headers = ["Serial", "User ID", "Username", "Full Name", "Password", "Cookies", "2FA Key", "Task Type", "Reward", "Status", "Time"]
    path = _safe_task_filename(task_name)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=safe_headers, quoting=csv.QUOTE_ALL, escapechar='\\')
        writer.writeheader()
        for row in rows:
            writer.writerow({h: row.get(h, "") for h in safe_headers})
    return path

def build_submissions_page(page=0, page_size=8):
    docs = db.collection('submissions').where('status', '==', 'pending').limit(80).stream()
    subs = [(d.id, d.to_dict()) for d in docs]
    subs.sort(key=lambda s: s[1].get('submitted_at') or datetime.min)
    total = len(subs)
    
    if total == 0:
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("🔄 Reset Submissions", callback_data="admin_reset_subs_ask", style="danger"))
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
        return "📥 **পেন্ডিং সাবমিশন**" + chr(10) + chr(10) + "✅ কোনো পেন্ডিং সাবমিশন নেই! (০)", keyboard
    
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    page_subs = subs[start:start + page_size]
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for sub_id, s in page_subs:
        label = f"🔸 {s.get('task_type', 'N/A')} | 🆔 {s.get('user_id', 'N/A')}"
        keyboard.add(colored_button(label, callback_data=f"subview_{sub_id}_{page}"))
    
    nav_row = []
    if page > 0:
        nav_row.append(colored_button("⬅️ আগের পেজ", callback_data=f"subpage_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(colored_button("পরের পেজ ➡️", callback_data=f"subpage_{page + 1}"))
    if nav_row:
        keyboard.row(*nav_row)
    keyboard.add(colored_button("🔄 Reset All Pending (→ 0)", callback_data="admin_reset_subs_ask", style="danger"))
    keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
    
    text = (
        f"📥 **পেন্ডিং সাবমিশন (মোট {total}টি) — পেজ {page + 1}/{total_pages}**"
        + chr(10) + chr(10)
        + "নিচে থেকে সিলেক্ট করে Approve/Reject করুন।"
        + chr(10)
        + "🔄 Reset চাপলে সব pending সাবমিশন → ০ হবে।"
    )
    return text, keyboard

def build_withdrawals_page(page=0, page_size=5):
    docs = db.collection('withdrawals').where('status', '==', 'pending').limit(40).stream()
    wds = [(d.id, d.to_dict()) for d in docs]
    wds.sort(key=lambda w: w[1].get('created_at') or datetime.min)
    total = len(wds)
    
    if total == 0:
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
        return "💸 **পেন্ডিং উইথড্র রিকোয়েস্ট**\n\n✅ কোনো পেন্ডিং রিকোয়েস্ট নেই!", keyboard
    
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    page_wds = wds[start:start + page_size]
    
    lines = [f"💸 **পেন্ডিং উইথড্র রিকোয়েস্ট (মোট {total}টি) — পেজ {page + 1}/{total_pages}**\n"]
    keyboard = InlineKeyboardMarkup(row_width=2)
    for req_id, w in page_wds:
        uid = w.get('user_id', 'N/A')
        amount = w.get('amount', 0)
        method = w.get('method', 'N/A')
        account = w.get('account', 'N/A')
        lines.append(f"🧾 `{req_id}`\n👤 ইউজার: `{uid}`\n💰 {amount:.2f} টাকা | 📱 {method}\n🔢 অ্যাকাউন্ট: `{account}`\n")
        keyboard.add(
            colored_button(f"✅ {req_id}", callback_data=f"wd_approve_{req_id}"),
            colored_button(f"❌ {req_id}", callback_data=f"wd_reject_{req_id}")
        )
    
    nav_row = []
    if page > 0:
        nav_row.append(colored_button("⬅️ আগের পেজ", callback_data=f"wdpage_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(colored_button("পরের পেজ ➡️", callback_data=f"wdpage_{page + 1}"))
    if nav_row:
        keyboard.row(*nav_row)
    keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
    
    return "\n".join(lines), keyboard

def _is_admin_panel_text(txt):
    t = (txt or "").strip()
    if not t:
        return False
    # emoji vary by client — match by core label
    low = t.lower()
    return (
        "admin panel" in low
        or "অ্যাডমিন প্যানেল" in t
        or "অ্যাডমিন প্যানেল" in t
        or t in ("🎛️ অ্যাডমিন প্যানেল", "🎛️ Admin Panel", "Admin Panel", "অ্যাডমিন প্যানেল")
    )

@dp.message_handler(lambda message: _is_admin_panel_text(message.text))
async def admin_panel(message: types.Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("❌ আপনি অ্যাডমিন নন!\nআপনার ID: `{}`".format(user_id))
        return
    # টাস্ক/2FA state ক্লিয়ার — Admin Panel চাপলে 2FA চাইবে না
    user_states.pop(user_id, None)
    temp_data.pop(user_id, None)
    clear_pending_task(user_id)
    try:
        text, keyboard = build_admin_panel_content(user_id)
    except Exception as e:
        logger.error(f"build_admin_panel_content error: {e}")
        await message.answer(f"❌ Admin panel load error:\n{type(e).__name__}: {e}")
        return
    await safe_answer(message, text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

# ==================== অ্যাডমিন কলব্যাক ====================

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("admin_"))
async def admin_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await cb_answer(callback, "❌ আপনি অ্যাডমিন নন!", show_alert=True)
        return
    await cb_answer(callback)
    data = callback.data
    
    if data == "admin_report_ready":
        user_states[user_id] = "admin_report_ready_task"
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(colored_button("🔙 পিছনে", callback_data="admin_folder_data"))
        # show some task names
        names = []
        try:
            names = _saved_task_names()[:15]
        except Exception:
            names = []
        tip = ""
        if names:
            tip = chr(10) + "উদাহরণ টাস্ক: " + ", ".join(f"`{n}`" for n in names[:8])
        await callback.message.edit_text(
            "✅ **Report Ready**" + chr(10) + chr(10) +
            "যে টাস্কের রিপোর্ট বানাবেন, তার **Task Type / নাম** লিখুন।" + chr(10) +
            "উদাহরণ: `Facebook 2FA` বা `fb_2fa`" + tip + chr(10) + chr(10) +
            "পরে OK Username গুলোর CSV আপলোড করবেন।",
            reply_markup=kb,
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
        return

    if data == "admin_upload_report":

        user_states[user_id] = "admin_report_upload"
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_folder_data"))
        msg = """📤 **Upload Report**

এখন CSV অথবা XLSX রিপোর্ট ফাইল পাঠান।

📋 **নিয়ম:**
• `User ID` কলাম জরুরি
• **Reward** আছে (০ এর বেশি) → ইউজারের balance যোগ (Approve)
• Reward নেই / ০ → **Cancel** (pending সরে যাবে, balance হবে না)

উদাহরণ: `User ID, Username, Reward`"""
        await callback.message.edit_text(msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()

    elif data == "admin_delete_report":
        task_names = _saved_task_names()
        keyboard = InlineKeyboardMarkup(row_width=1)
        if not task_names:
            keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_folder_data"))
            await callback.message.edit_text(
                "🗑️ **Delete Report**\n\n❌ কোনো saved task পাওয়া যায়নি।",
                reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
            return
        for idx, name in enumerate(task_names[:50]):
            keyboard.add(colored_button(
                f"📌 {name.replace(chr(10), ' ')[:45]}",
                callback_data=f"admin_delete_task_{idx}"
            ))
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_folder_data"))
        await callback.message.edit_text(
            "🗑️ **Delete Report**\n\nসব জমা হওয়া task দেখানো হচ্ছে। যে task manage করতে চান সেটি select করুন:",
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

    elif data.startswith("admin_delete_task_"):
        try:
            idx = int(data.rsplit("_", 1)[1])
            task_names = _saved_task_names()
            task_name = task_names[idx]
        except Exception:
            await callback.answer("❌ Task পাওয়া যায়নি। আবার চেষ্টা করুন।", show_alert=True)
            return
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            colored_button("🗑️ Delete File", callback_data=f"admin_delete_file_{idx}"),
            colored_button("🔄 Restart File", callback_data=f"admin_restart_file_{idx}"),
            colored_button("🔙 পিছনে", callback_data="admin_delete_report")
        )
        await callback.message.edit_text(
            f"📌 **Task:** `{task_name}`\n\nযে কাজটি করতে চান সেটি নির্বাচন করুন:",
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

    elif data.startswith("admin_delete_file_") or data.startswith("admin_restart_file_"):
        try:
            idx = int(data.rsplit("_", 1)[1])
            task_names = _saved_task_names()
            task_name = task_names[idx]
        except Exception:
            await callback.answer("❌ Task পাওয়া যায়নি। আবার চেষ্টা করুন।", show_alert=True)
            return

        action = "restart" if data.startswith("admin_restart_file_") else "delete"
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            colored_button("✅ Confirm", callback_data=f"admin_report_action_confirm_{action}_{idx}"),
            colored_button("❌ বাতিল", callback_data=f"admin_delete_task_{idx}")
        )
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_delete_report"))
        action_text = "Restart" if action == "restart" else "Delete"
        await callback.message.edit_text(
            f"⚠️ **{action_text} File নিশ্চিত করুন**\n\n📌 Task: `{task_name}`\n\n"
            + ("এই task-এর পুরোনো data clear হবে এবং নতুন data-এর জন্য empty file থাকবে।" if action == "restart" else "এই task-এর saved data এবং task file মুছে যাবে। অন্য task-এর data থাকবে।"),
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

    elif data.startswith("admin_report_action_confirm_"):
        parts = data.split("_")
        try:
            action = parts[-2]
            idx = int(parts[-1])
            task_names = _saved_task_names()
            task_name = task_names[idx]
        except Exception:
            await callback.answer("❌ Task পাওয়া যায়নি। আবার চেষ্টা করুন।", show_alert=True)
            return

        is_restart = action == "restart"
        try:
            await callback.message.edit_text(f"⏳ **{task_name}** ডেটা মুছে ফেলা হচ্ছে...")
        except Exception:
            pass

        def _do_delete_report(tname, restart=False):
            removed_csv = 0
            removed_fs = 0
            # 1) Local CSV
            try:
                _ensure_csv_file()
                with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
                    rows = list(csv.DictReader(f))
                remaining = [r for r in rows if (r.get("Task Type") or "").strip() != tname]
                removed_csv = len(rows) - len(remaining)
                with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, quoting=csv.QUOTE_ALL, escapechar='\\')
                    writer.writeheader()
                    writer.writerows(remaining)
            except Exception as e:
                logger.error(f"delete report csv: {e}")

            task_file = _safe_task_filename(tname)
            try:
                if restart:
                    _write_task_file(tname, [])
                elif os.path.exists(task_file):
                    os.remove(task_file)
            except OSError:
                pass

            # 2) Firestore submissions (so list doesn't come back after restart)
            tname_l = tname.strip().lower()
            for status in ("pending", "approved", "cancelled", "rejected"):
                try:
                    docs = list(
                        db.collection("submissions")
                        .where("status", "==", status)
                        .limit(400)
                        .stream()
                    )
                except Exception as e:
                    logger.warning(f"delete report fs query {status}: {e}")
                    continue
                for d in docs:
                    s = d.to_dict() or {}
                    ttype = str(s.get("task_type") or s.get("task_id") or "").strip()
                    if ttype != tname and ttype.lower() != tname_l:
                        continue
                    try:
                        if restart:
                            # keep doc but mark cancelled so it won't show as pending report
                            d.reference.update({
                                "status": "cancelled",
                                "report_cleared": True,
                                "reset_at": firestore.SERVER_TIMESTAMP,
                            })
                        else:
                            d.reference.delete()
                        removed_fs += 1
                    except Exception as e:
                        logger.warning(f"delete report one sub: {e}")
            return removed_csv, removed_fs

        try:
            removed_csv, removed_fs = await asyncio.to_thread(
                _do_delete_report, task_name, is_restart
            )
        except Exception as e:
            logger.error(f"Task report delete error: {e}")
            try:
                await callback.message.edit_text(
                    f"❌ Delete ব্যর্থ: {type(e).__name__}",
                    reply_markup=InlineKeyboardMarkup(row_width=1).add(
                        colored_button("🔙 Data Sheet Management", callback_data="admin_folder_data")
                    )
                )
            except Exception:
                pass
            return

        action_text = (
            "🔄 Restart complete — পুরোনো data clear, নতুন data আবার save হবে।"
            if is_restart else
            "🗑️ Delete complete — CSV + Firestore থেকে মুছেছে।"
        )
        try:
            await callback.message.edit_text(
                f"✅ **{task_name}**\n\n{action_text}\n\n"
                f"📄 CSV removed: **{removed_csv}**\n"
                f"☁️ Firestore removed: **{removed_fs}**",
                reply_markup=InlineKeyboardMarkup(row_width=1).add(
                    colored_button("🗑️ Delete Report", callback_data="admin_delete_report"),
                    colored_button("🔙 Data Sheet Management", callback_data="admin_folder_data")
                ),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            try:
                await callback.message.answer(
                    f"✅ {task_name}\nCSV: {removed_csv} | Firestore: {removed_fs}"
                )
            except Exception:
                pass

    elif data == "admin_download_report":
        await callback.answer("⏳ Task list লোড হচ্ছে...")
        try:
            task_names = await asyncio.to_thread(_saved_task_names)
        except Exception:
            task_names = _saved_task_names()
        keyboard = InlineKeyboardMarkup(row_width=1)
        if not task_names:
            keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_folder_data"))
            await callback.message.edit_text(
                "📥 **Download Report**\n\n"
                "❌ কোনো task data নেই।\n\n"
                "📌 নোট: ডেটা Firestore + CSV থেকে আসে।\n"
                "ইউজাররা টাস্ক সাবমিট করলে এখানে দেখা যাবে।",
                reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
            )
            return
        for idx, name in enumerate(task_names[:50]):
            keyboard.add(colored_button(
                f"📥 {name.replace(chr(10), ' ')[:45]}",
                callback_data=f"admin_download_task_{idx}"
            ))
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_folder_data"))
        await callback.message.edit_text(
            "📥 **Download Report**\n\n"
            f"মোট {len(task_names)} টি task পাওয়া গেছে।\n"
            "যেটা select করবেন সেটার CSV download হবে:\n\n"
            "💾 Source: Local CSV + Firestore (restart-safe)",
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )

    elif data.startswith("admin_download_task_"):
        try:
            idx = int(data.rsplit("_", 1)[1])
            task_names = await asyncio.to_thread(_saved_task_names)
            task_name = task_names[idx]
        except Exception:
            await callback.answer("❌ Task পাওয়া যায়নি। আবার চেষ্টা করুন।", show_alert=True)
            return
        await callback.answer("⏳ Data লোড হচ্ছে...")
        try:
            rows = await asyncio.to_thread(_load_task_rows, task_name)
        except Exception as e:
            logger.error(f"Task download load error: {e}")
            rows = _load_task_rows(task_name)
        if not rows:
            await callback.message.answer(
                f"❌ **{task_name}**\n\nএই task-এর কোনো submission data নেই।",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        try:
            export_path = _write_task_file(task_name, rows)
            from aiogram.types import InputFile
            await callback.message.answer_document(
                InputFile(export_path),
                caption=f"📥 {task_name} — {len(rows)}টি data (CSV + Firestore)"
            )
        except Exception as e:
            logger.error(f"Task download error: {e}")
            await callback.message.reply("❌ File download করতে সমস্যা হয়েছে।")

    if data == "admin_download_csv":
        _ensure_csv_file()
        try:
            from aiogram.types import InputFile
            await callback.message.answer_document(
                InputFile(CSV_FILE),
                caption="📥 এখন পর্যন্ত জমা হওয়া সব টাস্ক ডেটা।"
            )
        except Exception as e:
            logger.error(f"Download CSV Error: {e}")
            await callback.message.reply("❌ ফাইল পাঠাতে সমস্যা হয়েছে।")
        await callback.answer()
    
    elif data == "admin_reset_csv":
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            colored_button("✅ হ্যাঁ, রিসেট করুন", callback_data="admin_reset_csv_confirm"),
            colored_button("❌ বাতিল", callback_data="admin_panel_back")
        )
        await callback.message.reply(
            "⚠️ **আপনি কি নিশ্চিত?**\n\nএখন পর্যন্ত জমা হওয়া সব টাস্ক ডেটা মুছে যাবে এবং নতুন করে সেভ হওয়া শুরু হবে।",
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
    
    elif data == "admin_reset_csv_confirm":
        ok = reset_csv_data()
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
        await callback.message.edit_text(
            "✅ টাস্ক ডেটা রিসেট করা হয়েছে! নতুন ডেটা এখন থেকে সেভ হবে।" if ok else "❌ রিসেট করতে সমস্যা হয়েছে।",
            reply_markup=keyboard
        )
        await callback.answer()
    
    elif data == "admin_toggle_sheet":
        new_state = toggle_sheet_sync()
        text, keyboard = build_data_folder_content()
        try:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
        await callback.answer(f"📊 Google Sheet সেভ এখন {'চালু ✅' if new_state else 'বন্ধ ❌'}")
    
    elif data == "admin_toggle_csv":
        new_state = toggle_csv_sync()
        text, keyboard = build_data_folder_content()
        try:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
        await callback.answer(f"📁 Local Save এখন {'চালু ✅' if new_state else 'বন্ধ ❌'}")
    
    elif data == "admin_add_task":
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("❌ বাতিল", callback_data="admin_panel_back"))
        user_states[user_id] = "add_task_step1"
        await callback.message.reply(
            "📝 **টাস্ক আইডি লিখুন:**\n\nউদাহরণ:\n`insta_2fa` — Username+Password+2FA\n`fb_2fa` — UID+2FA\n`fb_cookies` — শুধু UID+Cookies\n`fb_2fa_cookies` — UID+2FA+Cookies\n`threads_2fa` — Username+Password+2FA",
            reply_markup=keyboard
        )
        await callback.answer()
    
    elif data == "admin_edit_task":
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("❌ বাতিল", callback_data="admin_panel_back"))
        user_states[user_id] = "edit_task_step1"
        await callback.message.reply(
            "✏️ **টাস্ক আইডি লিখুন:**\n\nযে টাস্ক এডিট করতে চান তার আইডি দিন:\nউদাহরণ: `insta_2fa`",
            reply_markup=keyboard
        )
        await callback.answer()
    
    elif data == "admin_delete_task":
        tasks = list(db.collection('tasks').limit(50).stream())
        keyboard = InlineKeyboardMarkup(row_width=1)
        if not tasks:
            await callback.message.edit_text(
                "🗑️ **টাস্ক ডিলিট**\n\n❌ কোনো টাস্ক পাওয়া যায়নি!",
                reply_markup=InlineKeyboardMarkup(row_width=1).add(
                    colored_button("🔙 পিছনে", callback_data="admin_panel_back")
                ),
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
            return
        for doc in tasks:
            t = doc.to_dict()
            tid = t.get('task_id') or doc.id
            label = f"{t.get('emoji', '📱')} {t.get('name', tid)} — Tk {float(t.get('reward', 0) or 0):.2f}"
            keyboard.add(colored_button(label[:60], callback_data=f"admin_del_task_{tid}"))
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
        await callback.message.edit_text(
            "🗑️ **কোন টাস্ক ডিলিট করবেন?**\n\nনিচের তালিকা থেকে টাস্ক নির্বাচন করুন:",
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
    
    elif data.startswith("admin_del_task_"):
        task_id = data.replace("admin_del_task_", "", 1)
        doc = db.collection('tasks').document(task_id).get()
        if not doc.exists:
            await callback.answer("❌ টাস্ক পাওয়া যায়নি!", show_alert=True)
            return
        t = doc.to_dict()
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            colored_button("✅ হ্যাঁ, ডিলিট", callback_data=f"admin_del_confirm_{task_id}"),
            colored_button("❌ বাতিল", callback_data="admin_delete_task")
        )
        await callback.message.edit_text(
            f"🗑️ **টাস্ক ডিলিট নিশ্চিত করুন**\n\n"
            f"📌 {t.get('emoji', '📱')} {t.get('name', task_id)}\n"
            f"🆔 `{task_id}`\n"
            f"💵 Tk {float(t.get('reward', 0) or 0):.2f}",
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

    elif data.startswith("admin_del_confirm_"):
        task_id = data.replace("admin_del_confirm_", "", 1)
        doc = db.collection('tasks').document(task_id).get()
        if not doc.exists:
            await callback.answer("❌ টাস্ক পাওয়া যায়নি!", show_alert=True)
            return
        # Soft-delete: users can never start/submit this task again
        try:
            db.collection('tasks').document(task_id).set({
                "is_active": False,
                "deleted": True,
                "deleted_at": firestore.SERVER_TIMESTAMP,
            }, merge=True)
            # Hard remove from list queries
            db.collection('tasks').document(task_id).delete()
        except Exception as e:
            logger.error(f"task delete error: {e}")
            await callback.answer("❌ ডিলিট ব্যর্থ", show_alert=True)
            return
        clear_task_cache(task_id)
        # short tombstone only — re-add same ID soon will work after 60s or clear on add
        cache.set(f"task:{task_id}", {"task_id": task_id, "is_active": False, "deleted": True}, ttl=30)
        await callback.message.edit_text(
            f"✅ `{task_id}` টাস্ক ডিলিট করা হয়েছে।" + chr(10) +
            "ইউজাররা আর এই টাস্ক সাবমিট করতে পারবে না।",
            reply_markup=InlineKeyboardMarkup(row_width=1).add(
                colored_button("🗑️ আবার টাস্ক ডিলিট", callback_data="admin_delete_task"),
                colored_button("🔙 পিছনে", callback_data="admin_panel_back")
            ),
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

    elif data == "admin_all_tasks":
        tasks = db.collection('tasks').limit(30).stream()
        text = "📋 **সব টাস্ক:**\n\n"
        count = 0
        for task in tasks:
            t = task.to_dict()
            text += f"{t.get('emoji', '')} **{t.get('name', 'N/A')}**\n├── আইডি: `{t.get('task_id', 'N/A')}`\n├── মূল্য: Tk {t.get('reward', 0):.2f}\n└── স্ট্যাটাস: {'✅ সক্রিয়' if t.get('is_active', True) else '❌ নিষ্ক্রিয়'}\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            count += 1
            if count > 20:
                text += "\n... এবং আরও অনেক"
                break
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
        await callback.message.reply(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
    
    elif data == "admin_users":
        users = db.collection('users').limit(25).stream()
        text = "👥 **ইউজার লিস্ট:**\n\n"
        count = 0
        for user in users:
            u = user.to_dict() or {}
            text += f"🆔 {u.get('user_id', 'N/A')}\n├── ইউজারনেম: {u.get('username', 'N/A')}\n├── ব্যালেন্স: Tk {float(u.get('balance', 0) or 0):.2f}\n└── মোট টাস্ক: {u.get('total_tasks', 0)}\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            count += 1
            if count > 20:
                text += "\n... এবং আরও অনেক"
                break
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
        await callback.message.reply(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
    
    elif data == "admin_broadcast":
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
        await callback.message.reply(
            "📢 Brodcast\n\nযে মেসেজ ব্রডকাস্ট করতে চান তা লিখুন।",
            reply_markup=keyboard
        )
        user_states[user_id] = "admin_broadcast"
        await callback.answer()
    
    elif data == "admin_leaderboard":
        # সবসময় ফ্রেশ ডেটা (পুরনো ক্যাশ বাদ) — সঠিক সংখ্যা দেখাতে
        cache.delete("leaderboard_text")
        try:
            all_docs = list(db.collection('users').limit(500).stream())
            all_users = []
            for d in all_docs:
                u = d.to_dict() or {}
                u['_id'] = u.get('user_id') or d.id
                u['approved_tasks'] = int(u.get('approved_tasks', 0) or 0)
                u['total_tasks'] = int(u.get('total_tasks', 0) or 0)
                u['total_refers'] = int(u.get('total_refers', 0) or 0)
                u['balance'] = float(u.get('balance', 0) or 0)
                all_users.append(u)
        except Exception as e:
            logger.error(f"Leaderboard load error: {e}")
            all_users = []

        # টপ সাবমিট (মোট জমা)
        by_submit = sorted(all_users, key=lambda x: x['total_tasks'], reverse=True)
        by_submit = [u for u in by_submit if u['total_tasks'] > 0][:10]
        # টপ অ্যাপ্রুভড
        by_approved = sorted(all_users, key=lambda x: x['approved_tasks'], reverse=True)
        by_approved = [u for u in by_approved if u['approved_tasks'] > 0][:10]
        # টপ রেফারার
        by_ref = sorted(all_users, key=lambda x: x['total_refers'], reverse=True)
        by_ref = [u for u in by_ref if u['total_refers'] > 0][:10]

        total_submit_all = sum(u['total_tasks'] for u in all_users)
        total_approved_all = sum(u['approved_tasks'] for u in all_users)

        lines = [
            "🏆 **লিডারবোর্ড**\n",
            f"📊 মোট জমা (সব ইউজার): **{total_submit_all}**",
            f"✅ মোট অ্যাপ্রুভড: **{total_approved_all}**\n",
            "📤 **টপ ১০ সাবমিট (জমা):**\n",
        ]
        if by_submit:
            for i, u in enumerate(by_submit, 1):
                name = get_user_display(u['_id'], u)
                lines.append(
                    f"{i}. 👤 {name} — 📤 {u['total_tasks']} জমা | ✅ {u['approved_tasks']} | 💰 Tk {u['balance']:.2f}"
                )
        else:
            lines.append("└── কোনো সাবমিট নেই")

        lines.append("\n✅ **টপ ১০ অ্যাপ্রুভড:**\n")
        if by_approved:
            for i, u in enumerate(by_approved, 1):
                name = get_user_display(u['_id'], u)
                lines.append(
                    f"{i}. 👤 {name} — ✅ {u['approved_tasks']} অ্যাপ্রুভ | 💰 Tk {u['balance']:.2f}"
                )
        else:
            lines.append("└── কোনো অ্যাপ্রুভ নেই")

        lines.append("\n🔗 **টপ ১০ রেফারার:**\n")
        if by_ref:
            for i, u in enumerate(by_ref, 1):
                name = get_user_display(u['_id'], u)
                lines.append(f"{i}. 👤 {name} — {u['total_refers']} জন")
        else:
            lines.append("└── কোনো রেফার নেই")

        text = "\n".join(lines)
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
        try:
            await callback.message.reply(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await callback.message.reply(text, reply_markup=keyboard, parse_mode=None)
        await callback.answer()
    
    elif data == "admin_settings":
        text = f"⚙️ **সেটিংস**\n\n"
        text += f"📌 উইথড্র স্ট্যাটাস: {'🟢 ON' if WITHDRAW_ENABLED else '🔴 OFF'}\n"
        text += f"📌 মিনিমাম উইথড্র: {MIN_WITHDRAW} টাকা\n"
        text += f"📌 উইথড্র মেথড: {', '.join(WITHDRAW_METHODS)}\n"
        text += f"📌 উইথড্র গ্রুপ: {WITHDRAW_GROUP if WITHDRAW_GROUP else 'সেট করা নেই'}\n"
        text += f"📌 ফোর্স জয়েন: {len(FORCE_CHANNELS)} টি চ্যানেল\n"
        text += f"📌 রেফারেল কমিশন: {REFERRAL_COMMISSION_PERCENT:.0f}%\n"
        text += f"📌 সাপোর্ট আইডি: {SUPPORT_CONTACT}\n"
        text += f"📌 Admin Support Link: {SUPPORT_ADMIN_LINK or 'সেট নেই'}\n"
        text += f"📌 Official Channel Link: {SUPPORT_CHANNEL_LINK or 'সেট নেই'}\n"
        text += f"📌 পাসওয়ার্ড: {'সহজ' if PASSWORD_SIMPLE else 'জটিল'}, লেন্থ {PASSWORD_LENGTH}\n"
        text += f"📌 ফিক্সড পাসওয়ার্ড: {FIXED_PASSWORD if FIXED_PASSWORD else 'বন্ধ (র‍্যান্ডম চলছে)'}\n"
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            colored_button("💸 Withdraw ON/OFF", callback_data="settings_withdraw_toggle"),
            colored_button("💰 মিনিমাম উইথড্র", callback_data="settings_min_withdraw"),
            colored_button("📱 মেথড যোগ", callback_data="settings_add_method"),
            colored_button("🗑️ মেথড ডিলিট", callback_data="settings_del_method"),
            colored_button("📢 উইথড্র গ্রুপ", callback_data="settings_withdraw_group"),
            colored_button("🔗 ফোর্স জয়েন", callback_data="settings_force_join"),
            colored_button("🚀 রেফারেল কমিশন %", callback_data="settings_ref_commission"),
            colored_button("🛠️ সাপোর্ট আইডি", callback_data="settings_support"),
            colored_button("👨‍💼 Admin Support Link", callback_data="settings_admin_link"),
            colored_button("📢 Official Channel Link", callback_data="settings_channel_link"),
            colored_button("🎯 পারসোনাল রেট", callback_data="settings_custom_rate"),
            colored_button("🔐 পাসওয়ার্ড ফরম্যাট", callback_data="settings_password"),
            colored_button("🔑 ফিক্সড পাসওয়ার্ড", callback_data="settings_fixed_password"),
            colored_button("🔙 পিছনে", callback_data="admin_panel_back")
        )
        try:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Admin Settings Markdown Error: {e}")
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)
        await callback.answer()
    
    elif data == "admin_manage":
        admins = get_admins()
        lines = ["👑 **অ্যাডমিন ম্যানেজমেন্ট**", "", f"👥 মোট অ্যাডমিন: {len(admins)}", ""]
        keyboard = InlineKeyboardMarkup(row_width=1)
        for a in admins:
            u = get_user(a) or {}
            uname = u.get('username')
            display = f"@{uname}" if uname else (u.get('first_name') or str(a))
            lines.append(f"👤 {display} — 🆔 `{a}`")
        lines.append("")
        lines.append("নিচের বাটন থেকে অ্যাড/রিমুভ করুন:")
        keyboard.add(
            colored_button("➕ Add Admin", callback_data="admin_add_admin"),
            colored_button("➖ Remove Admin", callback_data="admin_remove_admin")
        )
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
        await callback.message.edit_text(
            "\n".join(lines), reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

    elif data == "admin_add_admin":
        user_states[user_id] = "admin_add_admin"
        keyboard = InlineKeyboardMarkup(row_width=1).add(
            colored_button("❌ বাতিল", callback_data="admin_manage")
        )
        await callback.message.reply(
            "➕ **Add Admin**\n\nযে ইউজারকে অ্যাডমিন করতে চান তার Telegram User ID দিন:",
            reply_markup=keyboard
        )
        await callback.answer()

    elif data == "admin_remove_admin":
        admins = [a for a in get_admins() if int(a) != int(ADMIN_ID)]
        keyboard = InlineKeyboardMarkup(row_width=1)
        if not admins:
            keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_manage"))
            await callback.message.edit_text(
                "➖ **Remove Admin**\n\n❌ Remove করার মতো কোনো secondary admin নেই!",
                reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
            return
        for a in admins:
            u = get_user(a) or {}
            uname = u.get('username')
            display = f"@{uname}" if uname else (u.get('first_name') or str(a))
            keyboard.add(colored_button(f"❌ {display} ({a})", callback_data=f"admin_remove_confirm_{a}"))
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_manage"))
        await callback.message.edit_text(
            "➖ **কোন অ্যাডমিন Remove করবেন?**",
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

    elif data.startswith("admin_remove_confirm_"):
        remove_id = int(data.replace("admin_remove_confirm_", "", 1))
        if remove_id == int(ADMIN_ID):
            await callback.answer("❌ মূল অ্যাডমিন Remove করা যাবে না!", show_alert=True)
            return
        if remove_admin(remove_id):
            await callback.answer("✅ Admin removed")
        else:
            await callback.answer("❌ এই User admin নয়!", show_alert=True)
        admins = get_admins()
        lines = ["👑 **অ্যাডমিন ম্যানেজমেন্ট**", "", f"👥 মোট অ্যাডমিন: {len(admins)}", ""]
        for a in admins:
            u = get_user(a) or {}
            uname = u.get('username')
            display = f"@{uname}" if uname else (u.get('first_name') or str(a))
            lines.append(f"👤 {display} — 🆔 `{a}`")
        keyboard = InlineKeyboardMarkup(row_width=1).add(
            colored_button("➕ Add Admin", callback_data="admin_add_admin"),
            colored_button("➖ Remove Admin", callback_data="admin_remove_admin"),
            colored_button("🔙 পিছনে", callback_data="admin_panel_back")
        )
        await callback.message.edit_text(
            "\n".join(lines), reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "admin_user_manage":
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            colored_button("💰 ব্যালেন্স দেখুন", callback_data="um_balance"),
            colored_button("➕ ব্যালেন্স যোগ", callback_data="um_add_balance"),
            colored_button("➖ ব্যালেন্স কাটুন", callback_data="um_sub_balance"),
            colored_button("🚫 ব্লক করুন", callback_data="um_ban"),
            colored_button("✅ আনব্লক করুন", callback_data="um_unban"),
            colored_button("👤 User Profile", callback_data="um_profile"),
            colored_button("🔙 পিছনে", callback_data="admin_panel_back")
        )
        await callback.message.edit_text("👤 **ইউজার ম্যানেজমেন্ট**\n\nনিচের বাটন ব্যবহার করুন:", reply_markup=keyboard)
        await callback.answer()
    
    elif data == "admin_submissions":
        text, keyboard = build_submissions_page(0)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()

    elif data == "admin_reset_subs_ask":
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            colored_button("✅ হ্যাঁ, সব Reset (→ 0)", callback_data="admin_reset_subs_go", style="danger"),
            colored_button("❌ বাতিল", callback_data="admin_submissions"),
        )
        try:
            await callback.message.edit_text(
                "⚠️ **সব Pending সাবমিশন Reset?**" + chr(10) + chr(10) +
                "• সব pending submission → **cancelled**" + chr(10) +
                "• ইউজারদের pending_tasks → **0**" + chr(10) +
                "• সাবমিশন কাউন্ট → **0**" + chr(10) + chr(10) +
                "এটা আনডু করা যাবে না!",
                reply_markup=kb,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            await callback.message.answer(
                "⚠️ সব Pending Reset করতে চাপুন ✅",
                reply_markup=kb
            )

    elif data == "admin_reset_subs_go":
        # Don't call callback.answer again — middleware already answered
        try:
            await callback.message.edit_text("⏳ **Reset চলছে...** অনুগ্রহ করে অপেক্ষা করুন।")
        except Exception:
            try:
                await callback.message.answer("⏳ Reset চলছে...")
            except Exception:
                pass

        def _reset_all():
            n = 0
            users = set()
            # Loop batches until no more pending (not just 500)
            for _batch in range(20):  # max ~20*400 = 8000
                try:
                    docs = list(
                        db.collection("submissions")
                        .where("status", "==", "pending")
                        .limit(400)
                        .stream()
                    )
                except Exception as e:
                    logger.error(f"reset subs query: {e}")
                    break
                if not docs:
                    break
                for d in docs:
                    try:
                        s = d.to_dict() or {}
                        uid = s.get("user_id")
                        if uid is not None:
                            users.add(uid)
                        d.reference.update({
                            "status": "cancelled",
                            "reset_at": firestore.SERVER_TIMESTAMP
                        })
                        n += 1
                    except Exception as e:
                        logger.warning(f"reset one sub: {e}")
            for uid in users:
                try:
                    db.collection("users").document(str(uid)).update({"pending_tasks": 0})
                    invalidate_user_cache(uid)
                except Exception:
                    pass
            return n, len(users)

        try:
            n, u = await asyncio.to_thread(_reset_all)
        except Exception as e:
            logger.error(f"reset subs: {e}")
            n, u = 0, 0
            try:
                await callback.message.edit_text(f"❌ Reset ব্যর্থ: {type(e).__name__}: {e}")
            except Exception:
                pass
            return

        cache.delete("admin_counts")
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            colored_button("📥 সাবমিশন", callback_data="admin_submissions"),
            colored_button("🔙 Admin Panel", callback_data="admin_panel_back"),
        )
        try:
            await callback.message.edit_text(
                f"✅ **Reset সম্পন্ন!**" + chr(10) + chr(10) +
                f"🗑️ Cancelled submissions: **{n}**" + chr(10) +
                f"👥 Users pending→0: **{u}**" + chr(10) +
                f"📥 Pending count: **0**",
                reply_markup=kb,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            try:
                await callback.message.answer(
                    f"✅ Reset সম্পন্ন!\n🗑️ Cancelled: {n}\n👥 Users: {u}",
                    reply_markup=kb
                )
            except Exception:
                pass

    elif data == "admin_user_pending":
        user_states[user_id] = "admin_lookup_pending"
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("❌ বাতিল", callback_data="admin_panel_back"))
        await callback.message.edit_text(
            "🔍 **User Pending ID**\n\n"
            "যে ইউজারের pending ID / submission দেখতে চান, "
            "তার **Telegram User ID** পাঠান:\n\n"
            "উদাহরণ: `8807600220`",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
    
    elif data == "admin_withdrawals":
        text, keyboard = build_withdrawals_page(0)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
    
    elif data == "admin_folder_guide":
        text, keyboard = build_guide_folder_content()
        try:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await callback.message.reply(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()

    elif data == "admin_folder_data":
        text, keyboard = build_data_folder_content()
        try:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await callback.message.reply(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()

    elif data == "admin_set_video":
        user_states[user_id] = "admin_set_video"
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
        current = "✅ একটা ভিডিও সেট করা আছে" if GUIDE_VIDEO else "❌ কোনো ভিডিও সেট নেই"
        await callback.message.reply(
            f"🎥 **বট ওয়ার্ক সিস্টেম ভিডিও সেট করুন**\n\n"
            f"বর্তমান অবস্থা: {current}\n\n"
            f"এখন সরাসরি একটা ভিডিও পাঠান — এটাই \"🎥 বট ওয়ার্ক সিস্টেম\" বাটনে ক্লিক করলে সবাইকে দেখানো হবে।\n\n"
            f"ভিডিও বন্ধ করতে টাইপ করুন: `off`",
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

    elif data == "admin_add_gbtn":
        user_states[user_id] = "admin_add_gbtn_title"
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
        await callback.message.reply(
            "➕ **নতুন বাটন যোগ করুন**\n\n"
            "প্রথমে বাটনের নাম লিখে পাঠান।\n"
            "উদাহরণ: `💰 কিভাবে কয়েন ইনকাম করবেন` অথবা `📸 Instagram 2FA কিভাবে করবেন`",
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

    elif data == "admin_del_gbtn":
        if not GUIDE_BUTTONS:
            await callback.answer("❌ কোনো কাস্টম বাটন নেই", show_alert=True)
            return
        keyboard = InlineKeyboardMarkup(row_width=1)
        for btn in GUIDE_BUTTONS:
            keyboard.add(colored_button(f"🗑️ {btn['title']}", callback_data=f"delgbtn_{btn['id']}"))
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
        await callback.message.reply("🗑️ **কোন বাটনটা ডিলিট করবেন?**", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()

    elif data == "admin_close":
        await callback.message.delete()
        await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("delgbtn_"))
async def delete_guide_button(callback: types.CallbackQuery):
    global GUIDE_BUTTONS
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("❌ আপনি অ্যাডমিন নন!", show_alert=True)
        return
    btn_id = callback.data.replace("delgbtn_", "", 1)
    GUIDE_BUTTONS = [b for b in GUIDE_BUTTONS if b['id'] != btn_id]
    save_guide_buttons()
    await callback.answer("✅ বাটন ডিলিট হয়ে গেছে")
    try:
        await callback.message.delete()
    except Exception:
        pass

# ==================== উইথড্র রিকোয়েস্ট (অ্যাডমিন প্যানেল থেকে) ====================

@dp.callback_query_handler(lambda c: c.data.startswith("wdpage_"))
async def wdpage(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("❌ আপনি অ্যাডমিন নন!", show_alert=True)
        return
    page_str = callback.data.replace("wdpage_", "", 1)
    page = int(page_str) if page_str.isdigit() else 0
    text, keyboard = build_withdrawals_page(page)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        pass
    await callback.answer()

# ==================== সাবমিশন রিভিউ ====================

@dp.callback_query_handler(lambda c: c.data.startswith("subpage_"))
async def subpage(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("❌ আপনি অ্যাডমিন নন!", show_alert=True)
        return
    page_str = callback.data.replace("subpage_", "", 1)
    page = int(page_str) if page_str.isdigit() else 0
    text, keyboard = build_submissions_page(page)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        pass
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("subview_"))
async def subview(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("❌ আপনি অ্যাডমিন নন!", show_alert=True)
        return
    raw = callback.data.replace("subview_", "", 1)
    if "_" in raw:
        sub_id, page_str = raw.rsplit("_", 1)
        page = int(page_str) if page_str.isdigit() else 0
    else:
        sub_id, page = raw, 0
    doc = db.collection('submissions').document(sub_id).get()
    if not doc.exists:
        await callback.answer("❌ সাবমিশন পাওয়া যায়নি!", show_alert=True)
        return
    s = doc.to_dict()
    lines = [
        f"📥 **সাবমিশন ডিটেইলস**\n",
        f"🔸 **টাস্ক:** {s.get('task_type', 'N/A')}",
        f"🆔 **ইউজার আইডি:** `{s.get('user_id', 'N/A')}`"
    ]
    if s.get('uid'):
        lines.append(f"🆔 **Facebook UID:** `{s.get('uid')}`")
    if s.get('username'):
        lines.append(f"👤 **ইউজারনেম:** `{s.get('username')}`")
    lines.append(f"🔐 **পাসওয়ার্ড:** `{s.get('password', 'N/A')}`")
    lines.append(f"📝 **পুরো নাম:** {s.get('full_name', 'N/A')}")
    if s.get('cookies'):
        lines.append(f"🍪 **Cookies:** `{s.get('cookies')}`")
    else:
        lines.append(f"🔑 **2FA Key:** `{s.get('twofa_key', 'N/A')}`")
        lines.append(f"🔢 **2FA Code:** `{s.get('twofa_code', 'N/A')}`")
    lines.append(f"💵 **রিওয়ার্ড:** Tk {s.get('reward', 0):.2f}")
    lines.append(f"📌 **স্ট্যাটাস:** {s.get('status', 'pending')}")
    text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        colored_button("✅ Approve", callback_data=f"subapprove_{sub_id}_{page}"),
        colored_button("❌ Reject", callback_data=f"subreject_{sub_id}_{page}"),
        colored_button("🔙 পিছনে", callback_data=f"subpage_{page}")
    )
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("subapprove_") or c.data.startswith("subreject_"))
async def sub_decide(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("❌ আপনি অ্যাডমিন নন!", show_alert=True)
        return
    
    approve = callback.data.startswith("subapprove_")
    raw = callback.data.replace("subapprove_" if approve else "subreject_", "", 1)
    if "_" in raw:
        sub_id, page_str = raw.rsplit("_", 1)
        page = int(page_str) if page_str.isdigit() else 0
    else:
        sub_id, page = raw, 0
    
    sub_ref = db.collection('submissions').document(sub_id)
    doc = sub_ref.get()
    if not doc.exists:
        await callback.answer("❌ সাবমিশন পাওয়া যায়নি!", show_alert=True)
        return
    s = doc.to_dict()
    if s.get('status') != 'pending':
        await callback.answer("⚠️ এই সাবমিশন আগেই প্রসেস হয়ে গেছে!", show_alert=True)
        return
    
    target_id = s.get('user_id')
    reward = s.get('reward', 0)
    
    if approve:
        sub_ref.update({'status': 'approved'})
        if target_id:
            actual_reward = await credit_task_approval(target_id, reward)
            db.collection('users').document(str(target_id)).update({
                'approved_tasks': firestore.Increment(1),
                'pending_tasks': firestore.Increment(-1)
            })
            invalidate_user_cache(target_id)
            try:
                uname = get_task_account_name(s)
                await bot.send_message(
                    target_id,
                    f"🎉 Congratulations ({uname}) approved successful ✅\n"
                    f"💵 Tk {actual_reward:.2f} আপনার ব্যালেন্সে যোগ হয়েছে।"
                )
            except Exception:
                pass
        back_kb = InlineKeyboardMarkup().add(colored_button("📥 লিস্টে ফিরুন", callback_data=f"subpage_{page}"))
        await callback.message.edit_text(
            f"✅ সাবমিশন অ্যাপ্রুভ!\n📌 Account: `{get_task_account_name(s)}`\n🆔 TG: {target_id}\n💵 Tk {reward:.2f}",
            reply_markup=back_kb,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        sub_ref.update({'status': 'rejected'})
        if target_id:
            db.collection('users').document(str(target_id)).update({
                'rejected_tasks': firestore.Increment(1),
                'pending_tasks': firestore.Increment(-1)
            })
            invalidate_user_cache(target_id)
            try:
                uname = get_task_account_name(s)
                await bot.send_message(
                    target_id,
                    f"❌ This task ({uname}) rejected\n\nTry Again"
                )
            except Exception:
                pass
        back_kb = InlineKeyboardMarkup().add(colored_button("📥 লিস্টে ফিরুন", callback_data=f"subpage_{page}"))
        await callback.message.edit_text(f"❌ সাবমিশন রিজেক্ট করা হয়েছে।\n🆔 ইউজার: {target_id}", reply_markup=back_kb)
    
    await callback.answer()

# ==================== টাস্ক যোগ (স্টেপ বাই স্টেপ) ====================


@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "admin_lookup_pending")
async def admin_lookup_pending_user(message: types.Message):
    """Admin: User ID → pending submissions + CSV (fast, no composite index)"""
    admin_id = message.from_user.id
    if not is_admin(admin_id):
        user_states.pop(admin_id, None)
        await message.answer("❌ আপনি অ্যাডমিন নন!")
        return

    raw = (message.text or "").strip()
    if raw in MENU_BUTTON_TEXTS or raw.lower() in ("cancel", "বাতিল", "/start"):
        user_states.pop(admin_id, None)
        await message.answer("❌ বাতিল করা হয়েছে।")
        return

    try:
        target_id = int(raw.replace("@", "").strip())
    except ValueError:
        await message.answer("❌ সঠিক Telegram User ID দিন (শুধু সংখ্যা)।\nউদাহরণ: `8807600220`", parse_mode=ParseMode.MARKDOWN)
        return

    user_states.pop(admin_id, None)
    wait = await message.answer("⏳ খোঁজা হচ্ছে...")

    def _fetch_pending_sync(uid):
        """Single-field queries only — avoids Firestore composite-index hang."""
        results = []  # list of dicts with _doc_id
        seen = set()

        def _add_stream(stream):
            for d in stream:
                if d.id in seen:
                    continue
                data = d.to_dict() or {}
                if str(data.get("status", "")).lower() != "pending":
                    continue
                seen.add(d.id)
                data["_doc_id"] = d.id
                results.append(data)

        # Try int user_id
        try:
            _add_stream(db.collection("submissions").where("user_id", "==", uid).limit(60).stream())
        except Exception as e:
            logger.warning(f"pending int query: {e}")
        # Try string user_id
        if len(results) < 50:
            try:
                _add_stream(db.collection("submissions").where("user_id", "==", str(uid)).limit(60).stream())
            except Exception as e:
                logger.warning(f"pending str query: {e}")

        # Local CSV fallback (task_data.csv)
        try:
            if os.path.exists(CSV_FILE):
                with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
                    for row in csv.DictReader(f):
                        row_uid = str(row.get("User ID") or "").strip()
                        st = str(row.get("Status") or "").strip().lower()
                        if row_uid == str(uid) and st in ("pending", "", "pending "):
                            key = f"csv:{row.get('Serial')}:{row.get('Username')}"
                            if key in seen:
                                continue
                            seen.add(key)
                            results.append({
                                "_doc_id": None,
                                "user_id": uid,
                                "uid": row.get("Username") or "",
                                "username": row.get("Username") or "",
                                "full_name": row.get("Full Name") or "",
                                "password": row.get("Password") or "",
                                "cookies": row.get("Cookies") or "",
                                "twofa_key": row.get("2FA Key") or "",
                                "task_type": row.get("Task Type") or "",
                                "reward": row.get("Reward") or 0,
                                "status": "pending",
                                "submitted_at": row.get("Time") or "",
                                "_from_csv": True,
                            })
        except Exception as e:
            logger.warning(f"csv pending fallback: {e}")

        return results

    try:
        docs_data = await asyncio.to_thread(_fetch_pending_sync, target_id)
    except Exception as e:
        logger.error(f"pending lookup thread error: {e}")
        try:
            await wait.edit_text(f"❌ খুঁজতে সমস্যা হয়েছে:\n{type(e).__name__}: {e}")
        except Exception:
            await message.answer(f"❌ খুঁজতে সমস্যা হয়েছে: {e}")
        return

    try:
        user = get_user(target_id) or {}
    except Exception:
        user = {}
    uname = user.get("username") or user.get("first_name") or "N/A"
    bal = user.get("balance", 0)
    pending_count = user.get("pending_tasks", 0)

    keyboard = InlineKeyboardMarkup(row_width=1)

    # Build CSV
    csv_name = f"pending_{target_id}.csv"
    csv_bytes = None
    try:
        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
        writer.writerow(CSV_HEADERS)
        for i, s in enumerate(docs_data, 1):
            submitted = s.get("submitted_at")
            if hasattr(submitted, "strftime"):
                time_str = submitted.strftime("%Y-%m-%d %H:%M:%S")
            else:
                time_str = str(submitted or "")
            uid_val = s.get("uid") or s.get("username") or ""
            writer.writerow([
                f"#{i:03d}",
                str(s.get("user_id") or target_id),
                str(uid_val),
                str(s.get("full_name") or ""),
                str(s.get("password") or ""),
                str(s.get("cookies") or "").replace("\r", " ").replace("\n", " "),
                str(s.get("twofa_key") or ""),
                str(s.get("task_type") or s.get("task_id") or ""),
                str(s.get("reward") or 0),
                str(s.get("status") or "pending"),
                time_str,
            ])
        csv_bytes = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
        csv_bytes.name = csv_name
    except Exception as e:
        logger.error(f"pending CSV build error: {e}")

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(colored_button("🔍 আরেকজন খুঁজুন", callback_data="admin_user_pending"))
    keyboard.add(colored_button("🔙 Admin Panel", callback_data="admin_panel_back"))

    if not docs_data:
        text_out = (
            f"🔍 User Pending ID\n\n"
            f"👤 User: {target_id} (@{uname})\n"
            f"💰 Balance: Tk {float(bal or 0):.2f}\n"
            f"📊 pending_tasks field: {pending_count}\n\n"
            f"✅ এই ইউজারের কোনো pending submission নেই।"
        )
        try:
            await wait.edit_text(text_out, reply_markup=keyboard)
        except Exception:
            await message.answer(text_out, reply_markup=keyboard)
        return

    # Only short summary + CSV file (no per-ID buttons)
    text_out = (
        f"🔍 User Pending ID\n\n"
        f"👤 User: {target_id} (@{uname})\n"
        f"💰 Balance: Tk {float(bal or 0):.2f}\n"
        f"📥 Pending: {len(docs_data)}\n\n"
        f"📄 শুধু CSV ফাইল পাঠানো হচ্ছে..."
    )
    try:
        await wait.edit_text(text_out, reply_markup=keyboard)
    except Exception:
        try:
            await message.answer(text_out, reply_markup=keyboard)
        except Exception:
            pass

    if csv_bytes:
        try:
            from aiogram.types import InputFile
            csv_bytes.seek(0)
            await message.answer_document(
                InputFile(csv_bytes, filename=csv_name),
                caption=f"📄 Pending IDs\n👤 User: {target_id}\n📥 Count: {len(docs_data)}"
            )
        except Exception as e:
            logger.error(f"send pending csv: {e}")
            await message.answer(f"❌ CSV পাঠাতে সমস্যা: {type(e).__name__}")
    else:
        await message.answer("❌ CSV তৈরি করা যায়নি।")


@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "add_task_step1")
async def add_task_step2(message: types.Message):
    user_id = message.from_user.id
    task_id = message.text.strip()
    if not task_id:
        await message.answer("❌ টাস্ক আইডি দিন!")
        return
    temp_data[user_id] = {'task_id': task_id}
    user_states[user_id] = "add_task_step2"
    await message.answer(f"📝 Task name\n\ntopic: `{task_id}`")

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "add_task_step2")
async def add_task_step3(message: types.Message):
    user_id = message.from_user.id
    name = message.text.strip()
    if not name:
        await message.answer("❌ টাস্কের নাম দিন!")
        return
    temp_data[user_id]['name'] = name
    user_states[user_id] = "add_task_step3"
    await message.answer(f"🎨 **ইমোজি দিন:**\n\nউদাহরণ: `📸`, `📘`, `🎵`, `🐦`")

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "add_task_step3")
async def add_task_step4(message: types.Message):
    user_id = message.from_user.id
    emoji = message.text.strip()
    if not emoji:
        await message.answer("❌ ইমোজি দিন!")
        return
    temp_data[user_id]['emoji'] = emoji
    user_states[user_id] = "add_task_step4"
    await message.answer(f"💰 Par acount price:\n\nউদাহরণ: `4.0`, `5.0`, `6.0`")

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "add_task_step4")
async def add_task_step5(message: types.Message):
    user_id = message.from_user.id
    try:
        reward = float(message.text.strip())
        if reward < 0:
            await message.answer("❌ ঋণাত্মক মান দিতে পারবেন না!")
            return
        temp_data[user_id]['reward'] = reward
        user_states[user_id] = "add_task_step5"
        await message.answer(
            "🔐 **এই টাস্কের Fixed Password দিন:**\n\n"
            "উদাহরণ: `Task@09`, `Pass1234`\n"
            "র‍্যান্ডম রাখতে লিখুন: `random` বা `skip`"
        )
    except ValueError:
        await message.answer("❌ সঠিক সংখ্যা দিন!")

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "add_task_step5")
async def add_task_step6(message: types.Message):
    user_id = message.from_user.id
    pw = message.text.strip()
    if not pw:
        await message.answer("❌ Password দিন অথবা `random` লিখুন!")
        return
    if pw.lower() in ("random", "skip", "off", "none", "-"):
        temp_data[user_id]['fixed_password'] = ""
    else:
        temp_data[user_id]['fixed_password'] = pw
    user_states[user_id] = "add_task_step6"
    await message.answer("📋 **নির্দেশনা লিখুন:**\n\nউদাহরণ: `Profile Picture যোগ করুন এবং ১ জন Follow করুন`")

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "add_task_step6")
async def add_task_final(message: types.Message):
    user_id = message.from_user.id
    instructions = message.text.strip()
    if not instructions:
        await message.answer("❌ নির্দেশনা দিন!")
        return
    data = temp_data.get(user_id, {})
    task_id = data.get('task_id')
    name = data.get('name')
    emoji = data.get('emoji')
    reward = data.get('reward')
    fixed_password = data.get('fixed_password', "")
    try:
        task_data = {
            'task_id': task_id,
            'name': name,
            'emoji': emoji,
            'reward': float(reward),
            'instructions': instructions,
            'fixed_password': fixed_password,
            'is_active': True,
            'created_at': datetime.now()
        }
        db.collection('tasks').document(task_id).set(task_data)
        clear_task_cache(task_id)
        invalidate_tasks_cache()
        pw_line = fixed_password if fixed_password else "র‍্যান্ডম / গ্লোবাল"
        await message.answer(f"""
✅ **'{name}' টাস্ক যোগ করা হয়েছে!**

📌 **টাস্ক ডিটেইল:**
├── আইডি: `{task_id}`
├── নাম: {emoji} {name}
├── মূল্য: Tk {reward:.2f}
├── Password: `{pw_line}`
├── নির্দেশনা: {instructions}
└── স্ট্যাটাস: ✅ সক্রিয়
        """)
    except Exception as e:
        await message.answer(f"❌ সমস্যা: {e}")
    del user_states[user_id]
    del temp_data[user_id]

# ==================== টাস্ক এডিট (স্টেপ বাই স্টেপ) ====================

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "edit_task_step1")
async def edit_task_step2(message: types.Message):
    user_id = message.from_user.id
    task_id = message.text.strip()
    task = get_task(task_id)
    if not task:
        await message.answer("❌ টাস্ক পাওয়া যায়নি! আবার চেষ্টা করুন:")
        return
    temp_data[user_id] = {'task_id': task_id, 'task': task}
    user_states[user_id] = "edit_task_step2"
    await message.answer(f"✏️ **নতুন নাম লিখুন:**\n\nবর্তমান নাম: {task.get('name', 'N/A')}")

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "edit_task_step2")
async def edit_task_step3(message: types.Message):
    user_id = message.from_user.id
    new_name = message.text.strip()
    temp_data[user_id]['new_name'] = new_name
    user_states[user_id] = "edit_task_step3"
    await message.answer(f"🎨 **নতুন ইমোজি লিখুন:**")

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "edit_task_step3")
async def edit_task_step4(message: types.Message):
    user_id = message.from_user.id
    new_emoji = message.text.strip()
    temp_data[user_id]['new_emoji'] = new_emoji
    user_states[user_id] = "edit_task_step4"
    await message.answer(f"💰 **নতুন মূল্য লিখুন (Tk):**")

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "edit_task_step4")
async def edit_task_step5(message: types.Message):
    user_id = message.from_user.id
    try:
        new_reward = float(message.text.strip())
        temp_data[user_id]['new_reward'] = new_reward
        user_states[user_id] = "edit_task_step5"
        await message.answer(f"📋 **নতুন নির্দেশনা লিখুন:**")
    except ValueError:
        await message.answer("❌ সঠিক সংখ্যা দিন!")

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "edit_task_step5")
async def edit_task_final(message: types.Message):
    user_id = message.from_user.id
    new_instructions = message.text.strip()
    data = temp_data.get(user_id, {})
    task_id = data.get('task_id')
    new_name = data.get('new_name')
    new_emoji = data.get('new_emoji')
    new_reward = data.get('new_reward')
    try:
        update_data = {
            'name': new_name,
            'emoji': new_emoji,
            'reward': float(new_reward),
            'instructions': new_instructions,
            'is_active': True
        }
        db.collection('tasks').document(task_id).update(update_data)
        invalidate_tasks_cache()
        cache.delete(f"task:{task_id}")
        await message.answer(f"✅ '{task_id}' টাস্ক আপডেট হয়েছে!")
    except Exception as e:
        await message.answer(f"❌ সমস্যা: {e}")
    del user_states[user_id]
    del temp_data[user_id]

# ==================== টাস্ক ডিলিট (স্টেপ বাই স্টেপ) ====================

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "delete_task_step1")
async def delete_task_final(message: types.Message):
    user_id = message.from_user.id
    task_id = message.text.strip()
    try:
        doc = db.collection('tasks').document(task_id).get()
        if doc.exists:
            db.collection('tasks').document(task_id).delete()
            invalidate_tasks_cache()
            await message.answer(f"✅ '{task_id}' টাস্ক ডিলিট করা হয়েছে!")
        else:
            await message.answer(f"❌ '{task_id}' টাস্ক পাওয়া যায়নি!")
    except Exception as e:
        await message.answer(f"❌ সমস্যা: {e}")
    del user_states[user_id]

# ==================== ইউজার ম্যানেজমেন্ট ====================

@dp.callback_query_handler(lambda c: c.data.startswith("um_"))
async def user_management_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("❌ আপনি অ্যাডমিন নন!", show_alert=True)
        return
    data = callback.data
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
    
    if data == "um_balance":
        user_states[user_id] = "um_balance"
        await callback.message.reply("📝 **ইউজার আইডি লিখুন:**\n\nযার ব্যালেন্স দেখতে চান:", reply_markup=keyboard)
        await callback.answer()
    
    elif data == "um_add_balance":
        user_states[user_id] = "um_add_balance"
        await callback.message.reply("📝 **ফরম্যাট:**\n\n`ইউজার_আইডি | টাকা`\n\nউদাহরণ:\n`7294314847 | 50`", reply_markup=keyboard)
        await callback.answer()
    
    elif data == "um_sub_balance":
        user_states[user_id] = "um_sub_balance"
        await callback.message.reply("📝 **ফরম্যাট:**\n\n`ইউজার_আইডি | টাকা`\n\nউদাহরণ:\n`7294314847 | 20`", reply_markup=keyboard)
        await callback.answer()
    
    elif data == "um_ban":
        user_states[user_id] = "um_ban"
        await callback.message.reply("🚫 **ব্লক করতে ইউজার আইডি লিখুন:**", reply_markup=keyboard)
        await callback.answer()
    
    elif data == "um_unban":
        user_states[user_id] = "um_unban"
        await callback.message.reply("✅ **আনব্লক করতে ইউজার আইডি লিখুন:**", reply_markup=keyboard)
        await callback.answer()

    elif data == "um_profile":
        user_states[user_id] = "um_profile"
        await callback.message.reply(
            "👤 **User Profile**" + chr(10) + chr(10) +
            "যে ইউজারের প্রোফাইল দেখতে চান, তার **Telegram User ID** লিখুন:" + chr(10) + chr(10) +
            "উদাহরণ: `7026052448`",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id].startswith("um_"))
async def user_management_text(message: types.Message):
    user_id = message.from_user.id
    state = user_states[user_id]
    text = message.text.strip()
    
    amount = None
    if "|" in text:
        parts = text.split("|")
        try:
            target_id = int(parts[0].strip())
            amount = float(parts[1].strip())
        except (IndexError, ValueError):
            await message.answer("❌ সঠিক ফরম্যাট দিন! ব্যবহার করুন: `ইউজার_আইডি | টাকা`")
            return
    else:
        try:
            target_id = int(text)
        except ValueError:
            await message.answer("❌ সঠিক ইউজার আইডি দিন!")
            return
    
    if state in ("um_add_balance", "um_sub_balance") and amount is None:
        await message.answer("❌ সঠিক ফরম্যাট দিন! ব্যবহার করুন: `ইউজার_আইডি | টাকা`")
        return
    
    user = get_user(target_id)
    if not user:
        await message.answer(f"❌ ইউজার `{target_id}` পাওয়া যায়নি!\n\nনিশ্চিত করুন যে ইউজার আগে `/start` দিয়েছে।")
        del user_states[user_id]
        return
    
    if state == "um_profile":
        uname = user.get("username") or "—"
        fname = user.get("first_name") or "—"
        bal = float(user.get("balance", 0) or 0)
        pending_bal = float(user.get("pending_balance", 0) or 0)
        total_earned = float(user.get("total_earned", 0) or 0)
        total_tasks = user.get("total_tasks", 0) or 0
        approved = user.get("approved_tasks", 0) or 0
        pending = user.get("pending_tasks", 0) or 0
        rejected = user.get("rejected_tasks", 0) or 0
        refers = user.get("total_refers", 0) or 0
        ref_income = float(user.get("refer_income", 0) or 0)
        referred_by = user.get("referred_by") or "—"
        lang = user.get("lang") or "—"
        banned = "✅ Banned" if user.get("is_banned") else "❌ Not banned"
        rate = user.get("custom_base_reward", None)
        rate_pct = user.get("custom_rate", 100)
        ref_notify = "ON" if user.get("ref_notify", True) is not False else "OFF"
        joined = user.get("joined_at")
        if hasattr(joined, "strftime"):
            joined_s = joined.strftime("%Y-%m-%d %H:%M")
        else:
            joined_s = str(joined or "—")
        profile = (
            f"👤 **User Profile**" + chr(10) + chr(10) +
            f"🆔 User ID: `{target_id}`" + chr(10) +
            f"👤 Username: @{str(uname).lstrip('@')}" + chr(10) +
            f"📝 Name: {fname}" + chr(10) +
            f"🌐 Lang: {lang}" + chr(10) +
            f"🚫 Status: {banned}" + chr(10) +
            f"📅 Joined: {joined_s}" + chr(10) + chr(10) +
            f"💰 Balance: Tk {bal:.2f}" + chr(10) +
            f"⏳ Pending balance: Tk {pending_bal:.2f}" + chr(10) +
            f"📊 Total earned: Tk {total_earned:.2f}" + chr(10) +
            f"🎯 Personal base: " + (f"Tk {float(rate):.2f} / task" if rate is not None else f"default (rate {rate_pct}%)") + chr(10) + chr(10) +
            f"📋 Total tasks: {total_tasks}" + chr(10) +
            f"✅ Approved: {approved}" + chr(10) +
            f"⏳ Pending: {pending}" + chr(10) +
            f"❌ Rejected: {rejected}" + chr(10) + chr(10) +
            f"🔗 Total refers: {refers}" + chr(10) +
            f"💵 Refer income: Tk {ref_income:.2f}" + chr(10) +
            f"👤 Referred by: `{referred_by}`" + chr(10) +
            f"🔔 Ref notify: {ref_notify}"
        )
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(colored_button("🔍 User Pending ID", callback_data="admin_user_pending"))
        kb.add(colored_button("🔙 User Manage", callback_data="admin_user_manage"))
        try:
            await message.answer(profile, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await message.answer(profile.replace("**", "").replace("`", ""), reply_markup=kb)

    elif state == "um_balance":
        await message.answer(get_text(user_id, 'user_balance',
            user_id=target_id,
            balance=user.get('balance', 0),
            total=user.get('total_earned', 0)
        ))
    
    elif state == "um_add_balance":
        update_balance(target_id, amount)
        await message.answer(f"✅ `{target_id}` এর ব্যালেন্সে `{amount}` টাকা যোগ করা হয়েছে!\n\nনতুন ব্যালেন্স: Tk {get_balance(target_id):.2f}")
    
    elif state == "um_sub_balance":
        update_balance(target_id, -amount)
        await message.answer(f"✅ `{target_id}` এর ব্যালেন্স থেকে `{amount}` টাকা কাটা হয়েছে!\n\nনতুন ব্যালেন্স: Tk {get_balance(target_id):.2f}")
    
    elif state == "um_ban":
        db.collection('users').document(str(target_id)).update({'is_banned': True})
        invalidate_user_cache(target_id)
        await message.answer(f"🚫 `{target_id}` ব্লক করা হয়েছে!")
    
    elif state == "um_unban":
        db.collection('users').document(str(target_id)).update({'is_banned': False})
        invalidate_user_cache(target_id)
        await message.answer(f"✅ `{target_id}` আনব্লক করা হয়েছে!")
    
    del user_states[user_id]

# ==================== সেটিংস কলব্যাক ====================

@dp.callback_query_handler(lambda c: c.data.startswith("settings_"))
async def settings_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("❌ আপনি অ্যাডমিন নন!", show_alert=True)
        return
    data = callback.data
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
    
    if data == "settings_withdraw_toggle":
        global WITHDRAW_ENABLED
        WITHDRAW_ENABLED = not WITHDRAW_ENABLED
        save_withdraw_settings()
        status = "🟢 Withdraw Now ON" if WITHDRAW_ENABLED else "🔴 Withdraw Now OFF"
        await callback.answer(status, show_alert=True)
        text = f"⚙️ **সেটিংস**\n\n"
        text += f"📌 উইথড্র স্ট্যাটাস: {'🟢 ON' if WITHDRAW_ENABLED else '🔴 OFF'}\n"
        text += f"📌 মিনিমাম উইথড্র: {MIN_WITHDRAW} টাকা\n"
        text += f"📌 উইথড্র মেথড: {', '.join(WITHDRAW_METHODS)}\n"
        text += f"📌 উইথড্র গ্রুপ: {WITHDRAW_GROUP if WITHDRAW_GROUP else 'সেট করা নেই'}\n"
        text += f"📌 ফোর্স জয়েন: {len(FORCE_CHANNELS)} টি চ্যানেল\n"
        text += f"📌 রেফারেল কমিশন: {REFERRAL_COMMISSION_PERCENT:.0f}%\n"
        text += f"📌 সাপোর্ট আইডি: {SUPPORT_CONTACT}\n"
        text += f"📌 পাসওয়ার্ড: {'সহজ' if PASSWORD_SIMPLE else 'জটিল'}, লেন্থ {PASSWORD_LENGTH}\n"
        text += f"📌 ফিক্সড পাসওয়ার্ড: {FIXED_PASSWORD if FIXED_PASSWORD else 'বন্ধ (র‍্যান্ডম চলছে)'}\n"
        try:
            await callback.message.edit_text(text, reply_markup=callback.message.reply_markup, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
        return

    elif data == "settings_min_withdraw":
        user_states[user_id] = "settings_min_withdraw"
        await callback.message.reply(f"📝 **নতুন মিনিমাম উইথড্র লিখুন:**\n\nবর্তমান: {MIN_WITHDRAW} টাকা", reply_markup=keyboard)
        await callback.answer()
    
    elif data == "settings_add_method":
        user_states[user_id] = "settings_add_method"
        await callback.message.reply(f"📝 **নতুন উইথড্র মেথড লিখুন:**\n\nবর্তমান: {', '.join(WITHDRAW_METHODS)}", reply_markup=keyboard)
        await callback.answer()
    
    elif data == "settings_del_method":
        text = "🗑️ **মেথড ডিলিট করুন:**\n\n"
        for i, method in enumerate(WITHDRAW_METHODS):
            text += f"{i+1}. {method}\n"
        text += "\nনম্বর লিখুন:"
        user_states[user_id] = "settings_del_method"
        await callback.message.reply(text, reply_markup=keyboard)
        await callback.answer()
    
    elif data == "settings_withdraw_group":
        user_states[user_id] = "settings_withdraw_group"
        await callback.message.reply(f"📝 **উইথড্র গ্রুপ আইডি লিখুন:**\n\nবর্তমান: {WITHDRAW_GROUP if WITHDRAW_GROUP else 'সেট করা নেই'}", reply_markup=keyboard)
        await callback.answer()
    
    elif data == "settings_force_join":
        text = "🔗 **ফোর্স জয়েন**\n\n"
        if FORCE_CHANNELS:
            text += "বর্তমান চ্যানেল/গ্রুপ:\n"
            for ch in FORCE_CHANNELS:
                n = normalize_channel(ch)
                url = channel_join_url(ch) or n
                text += f"📌 {n}\n🔗 {url}\n"
        else:
            text += "❌ কোনো চ্যানেল সেট করা নেই\n"
        text += (
            "\n📝 **যোগ করতে:** নিচের বাটনে চাপুন, তারপর চ্যানেল লিংক পাঠান\n"
            "উদাহরণ: `https://t.me/social_media_task_update`\n"
            "বা: `@social_media_task_update`"
        )
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("➕ চ্যানেল লিংক যোগ", callback_data="fj_add_link", style="success"))
        if FORCE_CHANNELS:
            keyboard.add(colored_button("🗑️ সব চ্যানেল মুছুন", callback_data="fj_clear_all", style="danger"))
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_settings"))
        await callback.message.reply(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
    
    elif data == "settings_ref_commission":
        user_states[user_id] = "settings_ref_commission"
        await callback.message.reply(f"📝 **নতুন রেফারেল কমিশন % লিখুন:**\n\nবর্তমান: {REFERRAL_COMMISSION_PERCENT:.0f}%\n\n(উদাহরণ: `10` মানে ১০%)", reply_markup=keyboard)
        await callback.answer()
    
    elif data == "settings_support":
        user_states[user_id] = "settings_support"
        await callback.message.reply(f"📝 **নতুন সাপোর্ট আইডি/ইউজারনেম লিখুন:**\n\nবর্তমান: {SUPPORT_CONTACT}\n\n(উদাহরণ: `@your_support_username`)", reply_markup=keyboard)
        await callback.answer()

    elif data == "settings_admin_link":
        user_states[user_id] = "settings_admin_link"
        await callback.message.reply(
            f"📝 **Admin Support লিংক দিন:**\n\nবর্তমান: {SUPPORT_ADMIN_LINK or 'সেট নেই'}\n\n"
            f"উদাহরণ: `https://t.me/your_admin`\nবন্ধ করতে: `off`",
            reply_markup=keyboard
        )
        await callback.answer()

    elif data == "settings_channel_link":
        user_states[user_id] = "settings_channel_link"
        await callback.message.reply(
            f"📝 **Official Channel লিংক দিন:**\n\nবর্তমান: {SUPPORT_CHANNEL_LINK or 'সেট নেই'}\n\n"
            f"উদাহরণ: `https://t.me/your_channel`\nবন্ধ করতে: `off`",
            reply_markup=keyboard
        )
        await callback.answer()
    
    elif data == "settings_custom_rate":
        user_states[user_id] = "settings_custom_rate"
        await callback.message.reply(
            "🎯 **পারসোনাল বেস রেট (টাকা)**" + chr(10) + chr(10) +
            "ফরম্যাট: `UserID | টাকা`" + chr(10) + chr(10) +
            "উদাহরণ:" + chr(10) +
            "`7026052448 | 1` → সব টাস্কে অ্যাপ্রুভে **Tk 1**" + chr(10) +
            "`7026052448 | 2.5` → সব টাস্কে Tk 2.5" + chr(10) + chr(10) +
            "রিসেট: `7026052448 | off`",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

    elif data == "settings_password":
        user_states[user_id] = "settings_password"
        await callback.message.reply(
            f"📝 **পাসওয়ার্ড ফরম্যাট সেট করুন:**\n\n"
            f"বর্তমান: {'সহজ' if PASSWORD_SIMPLE else 'জটিল'}, লেন্থ {PASSWORD_LENGTH}\n\n"
            f"ফরম্যাট: `লেন্থ | simple` অথবা `লেন্থ | complex`\n"
            f"উদাহরণ: `8 | simple` (শুধু অক্ষর+সংখ্যা)\n\n"
            f"⚠️ এটা তখনই কাজ করবে যখন ফিক্সড পাসওয়ার্ড বন্ধ থাকবে।",
            reply_markup=keyboard
        )
        await callback.answer()
    
    elif data == "settings_fixed_password":
        user_states[user_id] = "settings_fixed_password"
        await callback.message.reply(
            f"🔑 **ফিক্সড পাসওয়ার্ড সেট করুন:**\n\n"
            f"বর্তমান: {FIXED_PASSWORD if FIXED_PASSWORD else 'বন্ধ (র‍্যান্ডম চলছে)'}\n\n"
            f"যা খুশি টাইপ করে পাঠান, সেটাই সব নতুন টাস্কের পাসওয়ার্ড হয়ে যাবে।\n"
            f"উদাহরণ: `social@27`\n\n"
            f"আবার র‍্যান্ডম পাসওয়ার্ডে ফিরে যেতে টাইপ করুন: `off`",
            reply_markup=keyboard
        )
        await callback.answer()

# ==================== সেটিংস টেক্সট ====================

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id].startswith("settings_"))
async def settings_text(message: types.Message):
    user_id = message.from_user.id
    state = user_states[user_id]
    text = message.text.strip()
    
    if state == "settings_min_withdraw":
        try:
            new_amount = float(text)
            if new_amount < 0:
                await message.answer("❌ ঋণাত্মক মান দিতে পারবেন না!")
                return
            global MIN_WITHDRAW
            MIN_WITHDRAW = new_amount
            save_withdraw_settings()
            await message.answer(f"✅ মিনিমাম উইথড্র আপডেট হয়েছে! নতুন মান: {MIN_WITHDRAW} টাকা")
        except Exception:
            await message.answer("❌ সঠিক সংখ্যা দিন!")
        del user_states[user_id]
    
    elif state == "settings_add_method":
        if text in WITHDRAW_METHODS:
            await message.answer(f"❌ '{text}' ইতিমধ্যে আছে!")
            return
        WITHDRAW_METHODS.append(text)
        save_withdraw_settings()
        await message.answer(f"✅ '{text}' যোগ করা হয়েছে!\n\nবর্তমান: {', '.join(WITHDRAW_METHODS)}")
        del user_states[user_id]
    
    elif state == "settings_del_method":
        try:
            idx = int(text) - 1
            if idx < 0 or idx >= len(WITHDRAW_METHODS):
                await message.answer("❌ সঠিক নম্বর দিন!")
                return
            removed = WITHDRAW_METHODS.pop(idx)
            save_withdraw_settings()
            await message.answer(f"✅ '{removed}' ডিলিট করা হয়েছে!\n\nবর্তমান: {', '.join(WITHDRAW_METHODS)}")
        except Exception:
            await message.answer("❌ সঠিক নম্বর দিন!")
        del user_states[user_id]
    
    elif state == "settings_withdraw_group":
        global WITHDRAW_GROUP
        WITHDRAW_GROUP = str(normalize_withdraw_chat(text) or text)
        save_withdraw_settings()
        await message.answer(f"✅ উইথড্র গ্রুপ/চ্যানেল সেট: `{WITHDRAW_GROUP}`\n\n⚠️ বটকে ওই চ্যানেলে **Admin** দিন, নইলে মেসেজ যাবে না।", parse_mode=ParseMode.MARKDOWN)
        del user_states[user_id]
    
    elif state == "settings_ref_commission":
        try:
            new_pct = float(text.replace("%", "").strip())
            if new_pct < 0 or new_pct > 100:
                await message.answer("❌ ০ থেকে ১০০ এর মধ্যে দিন!")
                return
            global REFERRAL_COMMISSION_PERCENT
            REFERRAL_COMMISSION_PERCENT = new_pct
            save_extra_settings()
            await message.answer(f"✅ রেফারেল কমিশন আপডেট হয়েছে: {REFERRAL_COMMISSION_PERCENT:.0f}%")
        except Exception:
            await message.answer("❌ সঠিক সংখ্যা দিন!")
        del user_states[user_id]
    
    elif state == "settings_support":
        global SUPPORT_CONTACT
        SUPPORT_CONTACT = text
        save_extra_settings()
        await message.answer(f"✅ সাপোর্ট আইডি সেট করা হয়েছে: {SUPPORT_CONTACT}")
        del user_states[user_id]

    elif state == "settings_admin_link":
        global SUPPORT_ADMIN_LINK
        if text.lower() in ("off", "reset", "বন্ধ"):
            SUPPORT_ADMIN_LINK = ""
            await message.answer("✅ Admin Support লিংক বন্ধ করা হয়েছে।")
        else:
            SUPPORT_ADMIN_LINK = text
            await message.answer(f"✅ Admin Support লিংক সেট: {SUPPORT_ADMIN_LINK}")
        save_extra_settings()
        del user_states[user_id]

    elif state == "settings_channel_link":
        global SUPPORT_CHANNEL_LINK
        if text.lower() in ("off", "reset", "বন্ধ"):
            SUPPORT_CHANNEL_LINK = ""
            await message.answer("✅ Official Channel লিংক বন্ধ করা হয়েছে।")
        else:
            SUPPORT_CHANNEL_LINK = text
            await message.answer(f"✅ Official Channel লিংক সেট: {SUPPORT_CHANNEL_LINK}")
        save_extra_settings()
        del user_states[user_id]
    
    elif state == "settings_custom_rate":
        try:
            parts = text.split("|")
            target_id = int(parts[0].strip())
            rate_raw = parts[1].strip().lower().replace("tk", "").replace("টাকা", "").strip()
            user = get_user(target_id)
            if not user:
                await message.answer(f"❌ ইউজার `{target_id}` পাওয়া যায়নি!")
                del user_states[user_id]
                return
            if rate_raw in ("off", "reset", "default", "0", "নরমাল", "normal"):
                db.collection("users").document(str(target_id)).update({
                    "custom_base_reward": firestore.DELETE_FIELD,
                })
                invalidate_user_cache(target_id)
                await message.answer(
                    f"✅ ইউজার `{target_id}` রিসেট।" + chr(10) +
                    "এখন থেকে নরমাল টাস্ক রিওয়ার্ড পাবে।"
                )
            else:
                taka = float(rate_raw.replace("%", ""))
                if taka < 0:
                    await message.answer("❌ ঋণাত্মক টাকা দিতে পারবেন না!")
                    return
                db.collection("users").document(str(target_id)).update({
                    "custom_base_reward": taka,
                    "custom_rate": 100,
                })
                invalidate_user_cache(target_id)
                await message.answer(
                    f"✅ পারসোনাল বেস সেট!" + chr(10) + chr(10) +
                    f"👤 User: `{target_id}`" + chr(10) +
                    f"💰 সব টাস্কে অ্যাপ্রুভ হলে: **Tk {taka:.2f}**" + chr(10) + chr(10) +
                    f"রিসেট: `{target_id} | off`",
                    parse_mode=ParseMode.MARKDOWN
                )
        except (IndexError, ValueError):
            await message.answer("❌ ফরম্যাট: `UserID | টাকা`" + chr(10) + "উদাহরণ: `7026052448 | 1`")
        del user_states[user_id]

    elif state == "settings_password":
        try:
            parts = text.split("|")
            length = int(parts[0].strip())
            mode = parts[1].strip().lower()
            if length < 4 or length > 32:
                await message.answer("❌ লেন্থ ৪ থেকে ৩২ এর মধ্যে দিন!")
                return
            if mode not in ("simple", "complex"):
                await message.answer("❌ `simple` অথবা `complex` লিখুন!")
                return
            global PASSWORD_LENGTH, PASSWORD_SIMPLE
            PASSWORD_LENGTH = length
            PASSWORD_SIMPLE = (mode == "simple")
            save_extra_settings()
            await message.answer(f"✅ পাসওয়ার্ড ফরম্যাট আপডেট হয়েছে! লেন্থ: {PASSWORD_LENGTH}, মোড: {'সহজ' if PASSWORD_SIMPLE else 'জটিল'}")
        except (IndexError, ValueError):
            await message.answer("❌ সঠিক ফরম্যাট দিন! উদাহরণ: `8 | simple`")
        del user_states[user_id]
    
    elif state == "settings_fixed_password":
        global FIXED_PASSWORD
        if text.lower() in ("off", "random", "reset", "বন্ধ"):
            FIXED_PASSWORD = ""
            save_extra_settings()
            await message.answer("✅ ফিক্সড পাসওয়ার্ড বন্ধ করা হয়েছে! এখন থেকে আবার র‍্যান্ডম পাসওয়ার্ড জেনারেট হবে।")
        elif len(text) < 4:
            await message.answer("❌ পাসওয়ার্ড কমপক্ষে ৪ ক্যারেক্টার দিন!")
            return
        else:
            FIXED_PASSWORD = text
            save_extra_settings()
            confirm_text = f"✅ ফিক্সড পাসওয়ার্ড সেট হয়েছে: {FIXED_PASSWORD}\n\nএখন থেকে সব নতুন টাস্কে এই পাসওয়ার্ডটাই দেওয়া হবে।\nবন্ধ করতে টাইপ করুন: off"
            try:
                await message.answer(f"✅ ফিক্সড পাসওয়ার্ড সেট হয়েছে: `{FIXED_PASSWORD}`\n\nএখন থেকে সব নতুন টাস্কে এই পাসওয়ার্ডটাই দেওয়া হবে।\nবন্ধ করতে টাইপ করুন: `off`", parse_mode=ParseMode.MARKDOWN)
            except Exception:
                await message.answer(confirm_text, parse_mode=None)
        del user_states[user_id]

# ==================== গাইড ভিডিও ও কাস্টম বাটন টেক্সট ====================

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] in ("admin_set_video", "admin_add_gbtn_title"))
async def guide_video_text(message: types.Message):
    user_id = message.from_user.id
    state = user_states[user_id]
    text = message.text.strip()

    if state == "admin_set_video":
        global GUIDE_VIDEO
        if text.lower() in ("off", "reset", "বন্ধ"):
            GUIDE_VIDEO = ""
            save_extra_settings()
            await message.answer("✅ ভিডিও বন্ধ করা হয়েছে। এখন থেকে \"বট ওয়ার্ক সিস্টেম\"-এ শুধু টেক্সট গাইড দেখাবে।")
            del user_states[user_id]
        else:
            await message.answer("❌ এখানে টেক্সট না, সরাসরি একটা ভিডিও পাঠান (অথবা বন্ধ করতে `off` লিখুন)।")

    elif state == "admin_add_gbtn_title":
        PENDING_GUIDE_BUTTON[user_id] = text
        user_states[user_id] = "admin_add_gbtn_video"
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
        await message.answer(
            f"✅ নাম সেট হয়েছে: {text}\n\nএখন এই বাটনের জন্য সরাসরি একটা ভিডিও পাঠান।",
            reply_markup=keyboard
        )

# ==================== অ্যাডমিন ভিডিও আপলোড হ্যান্ডলার ====================

@dp.message_handler(content_types=types.ContentType.VIDEO)
async def handle_admin_video_upload(message: types.Message):
    global GUIDE_VIDEO
    user_id = message.from_user.id
    if user_states.get(user_id) == "admin_set_video" and is_admin(user_id):
        GUIDE_VIDEO = message.video.file_id
        save_extra_settings()
        del user_states[user_id]
        await message.answer("✅ ভিডিও সেট হয়ে গেছে! এখন থেকে \"🎥 বট ওয়ার্ক সিস্টেম\" বাটনে ক্লিক করলে সবাই এই ভিডিওটা দেখবে।")
        return

    if user_states.get(user_id) == "admin_add_gbtn_video" and is_admin(user_id):
        title = PENDING_GUIDE_BUTTON.pop(user_id, "🎥 গাইড")
        btn_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        GUIDE_BUTTONS.append({'id': btn_id, 'title': title, 'video': message.video.file_id})
        save_guide_buttons()
        del user_states[user_id]
        await message.answer(
            f"✅ নতুন বাটন যোগ হয়ে গেছে: {title}\n\n"
            f"এখন থেকে \"🎥 বট ওয়ার্ক সিস্টেম\" বাটনে ক্লিক করলে ইউজাররা এই বাটনটা দেখবে এবং ক্লিক করলে ভিডিওটা দেখবে।"
        )

# ==================== ফোর্স জয়েন কমান্ড ====================

@dp.callback_query_handler(lambda c: c.data in ("fj_add_link", "fj_clear_all"))
async def force_join_admin_actions(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("❌ অ্যাডমিন নন!", show_alert=True)
        return
    if callback.data == "fj_clear_all":
        FORCE_CHANNELS.clear()
        save_force_channels()
        await callback.message.answer("✅ সব Force Join চ্যানেল মুছে ফেলা হয়েছে।")
        await callback.answer()
        return
    # fj_add_link
    user_states[user_id] = "fj_wait_link"
    kb = InlineKeyboardMarkup().add(colored_button("❌ বাতিল", callback_data="settings_force_join"))
    await callback.message.answer(
        "🔗 **চ্যানেল/গ্রুপ লিংক পাঠান:**\n\n"
        "উদাহরণ:\n"
        "`https://t.me/social_media_task_update`\n"
        "`@social_media_task_update`\n\n"
        "লিংক পেলেই ইউজারদের কাছে **Join** বাটন হিসেবে দেখাবে।",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()


@dp.message_handler(lambda message: user_states.get(message.from_user.id) == "fj_wait_link" and is_admin(message.from_user.id))
async def force_join_receive_link(message: types.Message):
    user_id = message.from_user.id
    raw = (message.text or "").strip()
    if not raw or raw in MENU_BUTTON_TEXTS:
        user_states.pop(user_id, None)
        return
    channel = normalize_channel(raw)
    if not channel:
        await message.answer("❌ সঠিক লিংক দিন!\nউদাহরণ: `https://t.me/your_channel`", parse_mode=ParseMode.MARKDOWN)
        return
    existing = {normalize_channel(c) for c in FORCE_CHANNELS}
    if channel in existing:
        user_states.pop(user_id, None)
        await message.answer(f"ℹ️ `{channel}` আগে থেকেই আছে।", parse_mode=ParseMode.MARKDOWN)
        return
    FORCE_CHANNELS.append(channel)
    save_force_channels()
    user_states.pop(user_id, None)
    url = channel_join_url(channel) or channel
    await message.answer(
        f"✅ Force Join সেট হয়েছে!\n\n"
        f"📌 চ্যানেল: `{channel}`\n"
        f"🔗 লিংক: {url}\n\n"
        f"এখন ইউজাররা Join বাটনে এই লিংক দেখবে।\n"
        f"⚠️ বটকে এই চ্যানেলে **Admin** রাখুন।",
        parse_mode=ParseMode.MARKDOWN
    )


@dp.message_handler(lambda message: message.text and "add_channel |" in message.text and is_admin(message.from_user.id))
async def add_force_channel(message: types.Message):
    try:
        raw = message.text.split("|", 1)[1].strip()
        channel = normalize_channel(raw)
        if not channel:
            await message.answer("❌ সঠিক চ্যানেল দিন!\nউদাহরণ: `add_channel | @social_media_task_update`")
            return
        # আগে থেকে URL/username মিল থাকলে স্কিপ
        existing = {normalize_channel(c) for c in FORCE_CHANNELS}
        if channel in existing:
            await message.answer(f"❌ `{channel}` ইতিমধ্যে আছে!")
            return
        FORCE_CHANNELS.append(channel)
        save_force_channels()
        await message.answer(
            f"✅ Force Join যোগ হয়েছে: `{channel}`\n\n"
            f"⚠️ বটকে এই চ্যানেল/গ্রুপে **Admin** রাখুন, নাহলে চেক কাজ করবে না।",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        await message.answer("❌ ভুল ফরম্যাট!\nব্যবহার: `add_channel | @channel`\nবা: `add_channel | https://t.me/channel`")

@dp.message_handler(lambda message: message.text and "del_channel |" in message.text and is_admin(message.from_user.id))
async def del_force_channel(message: types.Message):
    try:
        raw = message.text.split("|", 1)[1].strip()
        channel = normalize_channel(raw)
        # ম্যাচ করে রিমুভ (URL বা @username যেভাবেই থাকুক)
        before = len(FORCE_CHANNELS)
        FORCE_CHANNELS[:] = [c for c in FORCE_CHANNELS if normalize_channel(c) != channel]
        if len(FORCE_CHANNELS) < before:
            save_force_channels()
            await message.answer(f"✅ `{channel}` ফোর্স জয়েন থেকে ডিলিট করা হয়েছে!", parse_mode=ParseMode.MARKDOWN)
        else:
            await message.answer(f"❌ `{channel}` পাওয়া যায়নি!", parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await message.answer("❌ ভুল ফরম্যাট! ব্যবহার করুন: `del_channel | @channel`")

# ==================== অ্যাডমিন যোগ/ডিলিট ====================

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "admin_add_admin")
async def add_admin_from_button(message: types.Message):
    user_id = message.from_user.id
    try:
        new_admin = int(message.text.strip())
    except ValueError:
        await message.answer("❌ সঠিক Telegram User ID দিন।")
        return
    if add_admin(new_admin):
        await message.answer(f"✅ নতুন অ্যাডমিন যোগ করা হয়েছে: {new_admin}")
    else:
        await message.answer(f"❌ {new_admin} ইতিমধ্যে অ্যাডমিন!")
    user_states.pop(user_id, None)

@dp.message_handler(lambda message: message.text and message.text.startswith("add_admin |") and is_admin(message.from_user.id))
async def add_admin_command(message: types.Message):
    try:
        new_admin = int(message.text.split("|")[1].strip())
        if add_admin(new_admin):
            await message.answer(f"✅ নতুন অ্যাডমিন যোগ করা হয়েছে: {new_admin}")
        else:
            await message.answer(f"❌ {new_admin} ইতিমধ্যে অ্যাডমিন!")
    except Exception:
        await message.answer("❌ ভুল ইউজার আইডি!")

@dp.message_handler(lambda message: message.text and message.text.startswith("remove_admin |") and is_admin(message.from_user.id))
async def remove_admin_command(message: types.Message):
    try:
        remove_id = int(message.text.split("|")[1].strip())
        if remove_id == ADMIN_ID:
            await message.answer("❌ মূল অ্যাডমিন ডিলিট করা যায় না!")
            return
        if remove_admin(remove_id):
            await message.answer(f"✅ অ্যাডমিন সরানো হয়েছে: {remove_id}")
        else:
            await message.answer(f"❌ {remove_id} অ্যাডমিন নয়!")
    except Exception:
        await message.answer("❌ ভুল ইউজার আইডি!")

# ==================== ব্রডকাস্ট (SUPER FAST) ====================

@dp.message_handler(lambda message: message.text and message.from_user.id in user_states and user_states[message.from_user.id] == "admin_broadcast")
async def broadcast_text(message: types.Message):
    user_id = message.from_user.id
    broadcast_msg = message.text
    user_states.pop(user_id, None)

    # দ্রুত সব user id সংগ্রহ
    try:
        user_ids = [int(doc.id) for doc in db.collection('users').stream()]
    except Exception as e:
        logger.error(f"Broadcast user list error: {e}")
        await message.answer("❌ ইউজার লিস্ট লোড করতে সমস্যা হয়েছে।")
        return

    total = len(user_ids)
    if total == 0:
        await message.answer("❌ কোনো ইউজার নেই।")
        return

    status_msg = await message.answer(f"📢 ব্রডকাস্ট শুরু...\n👥 মোট ইউজার: {total}\n⏳ পাঠানো হচ্ছে...")

    # Telegram rate limit ~30 msg/sec — parallel batch
    sem = asyncio.Semaphore(35)
    success = 0
    failed = 0
    lock = asyncio.Lock()

    async def _send_one(uid):
        nonlocal success, failed
        async with sem:
            try:
                try:
                    await bot.send_message(uid, broadcast_msg, parse_mode=ParseMode.MARKDOWN)
                except Exception:
                    await bot.send_message(uid, broadcast_msg, parse_mode=None)
                async with lock:
                    success += 1
            except Exception:
                async with lock:
                    failed += 1

    # ১০০ করে batch — memory + progress
    BATCH = 150
    for i in range(0, total, BATCH):
        batch = user_ids[i:i + BATCH]
        await asyncio.gather(*[_send_one(uid) for uid in batch])
        try:
            await status_msg.edit_text(
                f"📢 ব্রডকাস্ট চলছে...\n"
                f"✅ পাঠানো: {success}\n"
                f"❌ ব্যর্থ: {failed}\n"
                f"📊 অগ্রগতি: {min(i + BATCH, total)}/{total}"
            )
        except Exception:
            pass

    try:
        await status_msg.edit_text(
            f"✅ **ব্রডকাস্ট সম্পন্ন!**\n\n"
            f"👥 মোট: {total}\n"
            f"✅ সফল: {success}\n"
            f"❌ ব্যর্থ: {failed}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        await message.answer(f"✅ ব্রডকাস্ট সম্পন্ন! সফল: {success}, ব্যর্থ: {failed}")

# ==================== রিপোর্ট আপলোড ====================


@dp.message_handler(lambda message: message.from_user.id in user_states and user_states.get(message.from_user.id) == "admin_report_ready_task")
async def report_ready_task_name(message: types.Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        user_states.pop(user_id, None)
        return
    task_name = (message.text or "").strip()
    if not task_name or task_name in MENU_BUTTON_TEXTS:
        user_states.pop(user_id, None)
        await message.answer("❌ বাতিল।")
        return
    if user_id not in temp_data:
        temp_data[user_id] = {}
    temp_data[user_id]["report_ready_task"] = task_name
    user_states[user_id] = "admin_report_ready_file"
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(colored_button("❌ বাতিল", callback_data="admin_folder_data"))
    await message.answer(
        f"✅ Task: **{task_name}**" + chr(10) + chr(10) +
        "এখন **শুধু OK Username** গুলোর CSV/XLSX আপলোড করুন।" + chr(10) + chr(10) +
        "ফাইলে কলাম থাকতে পারে: `Username` বা `UID` বা এক কলামে শুধু username।" + chr(10) +
        "বট submissions থেকে match করে **User ID, Username, 2FA Key, Password, Cookies, Reward** দিয়ে CSV দেবে।",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message_handler(content_types=['document'])
async def handle_report_upload(message: types.Message):
    if message.from_user.id in user_states and user_states[message.from_user.id] == "admin_field_cancel_upload":
        user_id = message.from_user.id
        file_name = message.document.file_name or ""
        lower_name = file_name.lower()
        if not (lower_name.endswith(".csv") or lower_name.endswith(".xlsx")):
            await message.answer("❌ শুধু CSV অথবা XLSX ফাইল দিন।")
            return
        try:
            file_io = io.BytesIO()
            await message.document.download(destination_file=file_io)
            file_io.seek(0)
            rows = []
            if lower_name.endswith(".csv"):
                content = file_io.read().decode("utf-8-sig")
                rows = list(csv.DictReader(io.StringIO(content)))
            else:
                import openpyxl
                wb = openpyxl.load_workbook(file_io, data_only=True)
                ws = wb.active
                values = list(ws.iter_rows(values_only=True))
                if values:
                    headers = [str(v).strip() if v is not None else "" for v in values[0]]
                    rows = [
                        {headers[i]: (str(r[i]).strip() if r[i] is not None else "")
                         for i in range(min(len(headers), len(r))) if headers[i]}
                        for r in values[1:]
                    ]
            cancelled = 0
            for row in rows:
                username = (row.get("username") or row.get("Username") or
                            row.get("instagram_username") or row.get("Instagram Username") or
                            row.get("uid") or row.get("UID") or "").strip().lstrip("@")
                if not username:
                    continue
                docs = db.collection("submissions").where("status", "==", "pending").stream()
                for doc in docs:
                    sub = doc.to_dict() or {}
                    sub_username = str(sub.get("username") or sub.get("uid") or "").strip().lstrip("@")
                    if sub_username.lower() != username.lower():
                        continue
                    db.collection("submissions").document(doc.id).update({"status": "cancelled"})
                    target_id = sub.get("user_id")
                    if target_id:
                        try:
                            db.collection("users").document(str(target_id)).update({
                                "pending_tasks": firestore.Increment(-1)
                            })
                            invalidate_user_cache(target_id)
                        except Exception:
                            pass
                        try:
                            # CSV username = task account — Telegram name নয়
                            await bot.send_message(
                                int(target_id),
                                f"❌ This task ({username}) cancelled\n\nTry Again"
                            )
                        except Exception:
                            pass
                    cancelled += 1
            user_states.pop(user_id, None)
            await message.answer(f"✅ Cancelled Task Upload complete.\n\n❌ Cancelled: {cancelled}")
            return
        except Exception as e:
            logger.error(f"Cancelled Field Task Upload Error: {type(e).__name__}: {e}")
            user_states.pop(user_id, None)
            await message.answer("❌ ফাইল প্রসেস করতে সমস্যা হয়েছে।")
            return

    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    # ===== Report Ready: match OK usernames → full CSV =====
    if user_states.get(user_id) == "admin_report_ready_file":
        file_name = message.document.file_name or ""
        lower_name = file_name.lower()
        if not (lower_name.endswith(".csv") or lower_name.endswith(".xlsx")):
            await message.answer("❌ শুধু CSV বা XLSX দিন।")
            return
        task_filter = (temp_data.get(user_id) or {}).get("report_ready_task") or ""
        if not task_filter:
            user_states.pop(user_id, None)
            await message.answer("❌ Task নাম পাওয়া যায়নি। আবার Report Ready শুরু করুন।")
            return
        progress = await message.answer("⏳ Username match করা হচ্ছে...")
        try:
            file_io = io.BytesIO()
            await message.document.download(destination_file=file_io)
            file_io.seek(0)
            ok_names = set()
            if lower_name.endswith(".csv"):
                content = file_io.read().decode("utf-8-sig")
                # try headered
                sample = content[:2048]
                try:
                    reader = csv.DictReader(io.StringIO(content))
                    if reader.fieldnames:
                        fields = [str(h or "").strip().lower() for h in reader.fieldnames]
                        for r in reader:
                            val = (
                                r.get("username") or r.get("uid") or r.get("user name")
                                or r.get("account") or r.get("id") or ""
                            )
                            if not val:
                                # first non-empty cell
                                for v in r.values():
                                    if v and str(v).strip():
                                        val = v
                                        break
                            n = normalize_report_username(val)
                            if n:
                                ok_names.add(n)
                    else:
                        raise ValueError("no header")
                except Exception:
                    for line in content.splitlines():
                        n = normalize_report_username(line)
                        if n and n not in ("username", "uid", "user"):
                            ok_names.add(n)
            else:
                import openpyxl
                wb = openpyxl.load_workbook(file_io, data_only=True)
                ws = wb.active
                rows_xlsx = list(ws.iter_rows(values_only=True))
                if not rows_xlsx:
                    await progress.edit_text("❌ ফাইল খালি!")
                    return
                header = [str(c or "").strip().lower() for c in rows_xlsx[0]]
                uname_idx = 0
                for i, h in enumerate(header):
                    if h in ("username", "uid", "user name", "account"):
                        uname_idx = i
                        break
                start_i = 1
                # if header doesn't look like header, start from 0
                if not any(h in ("username", "uid", "user", "account") for h in header):
                    start_i = 0
                    uname_idx = 0
                for row in rows_xlsx[start_i:]:
                    if not row:
                        continue
                    val = row[uname_idx] if uname_idx < len(row) else row[0]
                    n = normalize_report_username(val)
                    if n:
                        ok_names.add(n)
            if not ok_names:
                await progress.edit_text("❌ ফাইলে কোনো Username পাওয়া যায়নি!")
                return

            task_l = task_filter.strip().lower()

            def _collect_matches():
                matched = []  # list of dicts
                used = set()
                # Firestore submissions
                try:
                    # stream recent pending+approved by scanning - filter task in python
                    for status in ("pending", "approved", "cancelled", "rejected"):
                        try:
                            q = db.collection("submissions").where("status", "==", status).limit(400).stream()
                        except Exception:
                            continue
                        for d in q:
                            s = d.to_dict() or {}
                            ttype = str(s.get("task_type") or s.get("task_id") or "").lower()
                            if task_l not in ttype and ttype not in task_l:
                                # soft contains either way
                                if task_l not in ttype:
                                    continue
                            uname = normalize_report_username(s.get("uid") or s.get("username") or "")
                            if not uname or uname not in ok_names:
                                continue
                            if uname in used:
                                continue
                            used.add(uname)
                            matched.append({
                                "User ID": str(s.get("user_id") or ""),
                                "Username": str(s.get("uid") or s.get("username") or ""),
                                "Full Name": str(s.get("full_name") or ""),
                                "Password": str(s.get("password") or ""),
                                "Cookies": str(s.get("cookies") or "").replace("\r", " ").replace("\n", " "),
                                "2FA Key": str(s.get("twofa_key") or ""),
                                "Task Type": str(s.get("task_type") or s.get("task_id") or ""),
                                "Reward": str(s.get("reward") or ""),
                                "Status": str(s.get("status") or ""),
                            })
                except Exception as e:
                    logger.error(f"report ready firestore: {e}")
                # CSV fallback
                try:
                    if os.path.exists(CSV_FILE):
                        with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
                            for row in csv.DictReader(f):
                                ttype = str(row.get("Task Type") or "").lower()
                                if task_l not in ttype and ttype not in task_l:
                                    if task_l not in ttype:
                                        continue
                                uname = normalize_report_username(row.get("Username") or "")
                                if not uname or uname not in ok_names or uname in used:
                                    continue
                                used.add(uname)
                                matched.append({
                                    "User ID": str(row.get("User ID") or ""),
                                    "Username": str(row.get("Username") or ""),
                                    "Full Name": str(row.get("Full Name") or ""),
                                    "Password": str(row.get("Password") or ""),
                                    "Cookies": str(row.get("Cookies") or ""),
                                    "2FA Key": str(row.get("2FA Key") or ""),
                                    "Task Type": str(row.get("Task Type") or ""),
                                    "Reward": str(row.get("Reward") or ""),
                                    "Status": str(row.get("Status") or ""),
                                })
                except Exception as e:
                    logger.error(f"report ready csv: {e}")
                missing = sorted(ok_names - used)
                return matched, missing

            matched, missing = await asyncio.to_thread(_collect_matches)
            user_states.pop(user_id, None)
            temp_data.pop(user_id, None)

            if not matched:
                await progress.edit_text(
                    f"❌ Task `{task_filter}` এর সাথে match করে কোনো submission পাওয়া যায়নি।" + chr(10) +
                    f"OK username: {len(ok_names)}",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            buf = io.StringIO()
            fields = ["Serial", "User ID", "Username", "Full Name", "Password", "Cookies", "2FA Key", "Task Type", "Reward", "Status"]
            writer = csv.DictWriter(buf, fieldnames=fields, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            for i, row in enumerate(matched, 1):
                out = {"Serial": f"#{i:03d}"}
                out.update(row)
                writer.writerow(out)
            data = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
            data.name = f"report_ready_{task_filter.replace(' ', '_')[:30]}.csv"
            from aiogram.types import InputFile
            await progress.edit_text(
                f"✅ **Report Ready**" + chr(10) + chr(10) +
                f"📌 Task: {task_filter}" + chr(10) +
                f"📥 OK Username: {len(ok_names)}" + chr(10) +
                f"✅ Matched: {len(matched)}" + chr(10) +
                f"❌ Not found: {len(missing)}"
            )
            cap = f"📄 Report Ready\nTask: {task_filter}\nMatched: {len(matched)}"
            await message.answer_document(InputFile(data, filename=data.name), caption=f"📄 Report Ready | Task: {task_filter} | Matched: {len(matched)}")
            if missing:
                miss_txt = ", ".join(f"`{m}`" for m in missing[:40])
                if len(missing) > 40:
                    miss_txt += f" ... +{len(missing)-40}"
                await message.answer("⚠️ Match হয়নি:" + chr(10) + miss_txt, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Report Ready error: {e}")
            user_states.pop(user_id, None)
            await progress.edit_text(f"❌ Error: {type(e).__name__}: {e}")
        return

    file_name = message.document.file_name or ""
    lower_name = file_name.lower()
    if not (lower_name.endswith('.csv') or lower_name.endswith('.xlsx')):
        await message.answer("❌ শুধু CSV (.csv) অথবা Excel (.xlsx) ফাইল সাপোর্টেড।")
        return
    
    report_mode = user_states.get(user_id)

    if report_mode not in ("admin_report_upload", "admin_report_upload_approve", "admin_report_upload_reject"):
        await message.answer("❌ আগে Admin Panel → Upload Report সিলেক্ট করে তারপর ফাইল পাঠান।")
        return
    user_states.pop(user_id, None)
    progress_msg = await message.answer("⏳ ফাইল প্রসেস করা হচ্ছে...")
    
    try:
        file_io = io.BytesIO()
        await message.document.download(destination_file=file_io)
        file_io.seek(0)
        
        rows = []
        if lower_name.endswith('.csv'):
            content = file_io.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))
            if reader.fieldnames is None:
                await progress_msg.edit_text("❌ ফাইলটা খালি বা ভুল ফরম্যাটে!")
                return
            headers = {h.strip().lower(): h for h in reader.fieldnames if h}
            for r in reader:
                rows.append({k.strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in r.items() if k})
        else:
            try:
                import openpyxl
            except ImportError:
                await progress_msg.edit_text("❌ Excel ফাইল প্রসেস করার জন্য `openpyxl` লাইব্রেরি ইনস্টল নেই।\n\n`requirements.txt`-এ `openpyxl` যোগ করে আবার ইনস্টল করুন, অথবা CSV ফরম্যাটে আপলোড করুন।")
                return
            wb = openpyxl.load_workbook(file_io, data_only=True)
            ws = wb.active
            all_rows = list(ws.iter_rows(values_only=True))
            if not all_rows:
                await progress_msg.edit_text("❌ ফাইলটা খালি!")
                return
            headers_row = [str(h).strip().lower() if h is not None else "" for h in all_rows[0]]
            for raw in all_rows[1:]:
                row_dict = {}
                for i, h in enumerate(headers_row):
                    if h and i < len(raw):
                        val = raw[i]
                        row_dict[h] = str(val).strip() if val is not None else ""
                rows.append(row_dict)
        
        def normalize_report_user_id(value):
            if value is None:
                return None
            text = str(value).strip()
            if not text:
                return None
            try:
                num = float(text)
                if num.is_integer():
                    return int(num)
            except (ValueError, TypeError, OverflowError):
                pass
            if text.endswith('.0') and text[:-2].isdigit():
                return int(text[:-2])
            return int(text)

        success, failed, skipped = 0, 0, 0
        kept_pending = 0
        already_marked = []
        fail_details = []
        
        for idx, row in enumerate(rows, start=2):
            raw_uid = row.get('user id') or row.get('user_id') or row.get('userid') or row.get('id')
            raw_reward = row.get('reward') or row.get('amount') or row.get('টাকা')
            # CSV/Excel Username কলাম = টাস্ক অ্যাকাউন্ট (FB UID / IG username)
            _ru = (
                row.get('username') or row.get('uid') or row.get('instagram username')
                or row.get('account') or row.get('id username') or ""
            )
            # Excel float fix: 6159608448299.0 → 6159608448299
            if isinstance(_ru, float):
                raw_username = str(int(_ru)) if _ru == int(_ru) else str(_ru)
            else:
                raw_username = str(_ru or "").strip()
                if raw_username.endswith(".0") and raw_username.replace(".", "", 1).isdigit():
                    raw_username = raw_username[:-2]
            uname_norm = normalize_report_username(raw_username)

            # Same Username cannot be reported twice
            if uname_norm and is_username_already_reported(uname_norm):
                already_marked.append(uname_norm)
                continue
            
            if not raw_uid:
                skipped += 1
                continue
            
            try:
                target_id = normalize_report_user_id(raw_uid)
                if target_id is None:
                    raise ValueError("empty user id")
            except (ValueError, TypeError, OverflowError):
                failed += 1
                fail_details.append(f"লাইন {idx}: ভুল User ID `{raw_uid}`")
                continue
            
            user = get_user(target_id)
            if not user:
                failed += 1
                fail_details.append(f"লাইন {idx}: ইউজার `{target_id}` পাওয়া যায়নি")
                continue

            # Parse reward — empty / 0 means keep pending (no balance)
            reward_val = None
            if raw_reward not in (None, ""):
                try:
                    reward_val = float(str(raw_reward).replace(",", "").strip())
                except (ValueError, TypeError):
                    failed += 1
                    fail_details.append(f"লাইন {idx}: ভুল Reward `{raw_reward}`")
                    continue

            # Find matching pending submission (prefer username/uid match if given)
            pending_docs = []
            try:
                pending_docs = list(
                    db.collection('submissions')
                    .where('user_id', '==', target_id)
                    .where('status', '==', 'pending')
                    .limit(20)
                    .stream()
                )
            except Exception:
                try:
                    pending_docs = [
                        d for d in db.collection('submissions').where('user_id', '==', target_id).limit(30).stream()
                        if (d.to_dict() or {}).get('status') == 'pending'
                    ]
                except Exception:
                    pending_docs = []
            if not pending_docs:
                try:
                    pending_docs = list(
                        db.collection('submissions')
                        .where('user_id', '==', str(target_id))
                        .where('status', '==', 'pending')
                        .limit(20)
                        .stream()
                    )
                except Exception:
                    pass

            pending_docs.sort(key=lambda d: (d.to_dict() or {}).get('submitted_at') or datetime.min)
            sub_ref = None
            sub_data = {}
            if pending_docs:
                if raw_username:
                    uname_q = str(raw_username).strip().lstrip("@").lower()
                    for d in pending_docs:
                        s = d.to_dict() or {}
                        cand = str(s.get("uid") or s.get("username") or "").strip().lstrip("@").lower()
                        if cand and cand == uname_q:
                            sub_ref = d.reference
                            sub_data = s
                            break
                if sub_ref is None:
                    sub_ref = pending_docs[0].reference
                    sub_data = pending_docs[0].to_dict() or {}

            # No reward → cancel (pending থেকে সরাবে, payment/pending থাকবে না)
            if reward_val is None or reward_val <= 0:
                if sub_ref:
                    try:
                        sub_ref.update({'status': 'cancelled'})
                    except Exception:
                        pass
                try:
                    db.collection('users').document(str(target_id)).update({
                        'pending_tasks': firestore.Increment(-1) if sub_ref else firestore.Increment(0)
                    })
                except Exception:
                    pass
                invalidate_user_cache(target_id)
                try:
                    # CSV Username কলামই দেখাবে — Telegram name কখনো নয়
                    uname = (raw_username or get_task_account_name(sub_data) or "account").strip()
                    await bot.send_message(
                        target_id,
                        f"❌ This task ({uname}) cancelled\n\nTry Again"
                    )
                except Exception:
                    pass
                if uname_norm:
                    mark_username_reported(uname_norm, {
                        "telegram_user_id": target_id,
                        "status": "cancelled",
                    })
                kept_pending += 1  # used as cancelled count
                continue

            # Has reward → approve + credit balance
            actual_reward = await credit_task_approval(target_id, reward_val)
            if sub_ref:
                try:
                    sub_ref.update({'status': 'approved'})
                except Exception:
                    pass
            try:
                db.collection('users').document(str(target_id)).update({
                    'approved_tasks': firestore.Increment(1),
                    'pending_tasks': firestore.Increment(-1) if sub_ref else firestore.Increment(0)
                })
            except Exception:
                pass
            invalidate_user_cache(target_id)
            try:
                # CSV Username কলামই দেখাবে — Telegram name কখনো নয়
                uname = (raw_username or get_task_account_name(sub_data) or "account").strip()
                await bot.send_message(
                    target_id,
                    f"🎉 Congratulations ({uname}) approved successful ✅\n"
                    f"💵 Tk {actual_reward:.2f} আপনার ব্যালেন্সে যোগ হয়েছে।"
                )
            except Exception:
                pass
            if uname_norm:
                mark_username_reported(uname_norm, {
                    "telegram_user_id": target_id,
                    "reward": reward_val,
                    "status": "approved",
                })
            success += 1
        

        summary_lines = [
            "✅ **প্রসেস সম্পন্ন!**",
            "",
            f"💰 Balance দেওয়া (Approve): {success}",
            f"🗑️ Cancelled (Reward নেই): {kept_pending}",
            f"❌ ব্যর্থ: {failed}",
            f"⏭️ স্কিপড (User ID ফাঁকা): {skipped}",
            f"🏷️ আগে Marked Username: {len(already_marked)}",
        ]
        if already_marked:
            uniq = []
            seen = set()
            for u in already_marked:
                if u not in seen:
                    seen.add(u)
                    uniq.append(u)
            summary_lines.append("")
            summary_lines.append("⚠️ **এই Username গুলো আগেই রিপোর্ট/Mark করা:**")
            summary_lines.append(", ".join(f"`{u}`" for u in uniq[:40]))
            if len(uniq) > 40:
                summary_lines.append(f"... এবং আরও {len(uniq) - 40}টি")
            summary_lines.append("")
            summary_lines.append("👉 এই Username গুলো **ফাইল থেকে remove** করে আবার Upload করুন।")
        if fail_details:
            summary_lines.append("")
            summary_lines.append("**সমস্যা যেসব লাইনে:**")
            summary_lines.extend(fail_details[:15])
            if len(fail_details) > 15:
                summary_lines.append(f"... এবং আরও {len(fail_details) - 15}টি")
        summary = chr(10).join(summary_lines)
        try:
            await progress_msg.edit_text(summary, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await progress_msg.edit_text(summary.replace("**", "").replace("`", ""))
    except Exception as e:
        logger.error(f"Report Upload Error: {type(e).__name__}: {e}")
        await progress_msg.edit_text(f"❌ ফাইল প্রসেস করতে সমস্যা হয়েছে:\n`{type(e).__name__}: {e}`", parse_mode=ParseMode.MARKDOWN)

# ==================== ইনলাইন শেয়ার ====================

@dp.inline_handler()
async def inline_share_referral(inline_query: types.InlineQuery):
    ref_link = inline_query.query or ""
    if not ref_link.startswith("https://t.me/"):
        return
    result = types.InlineQueryResultArticle(
        id="1",
        title="আপনার রেফারেল লিংক শেয়ার করুন",
        description=ref_link,
        input_message_content=types.InputTextMessageContent(
            message_text=f"🎁 আমার রেফারেল লিংক দিয়ে জয়েন করুন এবং বোনাস পান:\n{ref_link}"
        )
    )
    await bot.answer_inline_query(inline_query.id, results=[result], cache_time=1)

@dp.errors_handler()
async def global_error_handler(update, exception):
    logger.exception(f"Unhandled error in handler: {type(exception).__name__}: {exception}")
    return True

# ==================== Webhook ====================

WEBHOOK_PATH = "/telegram/webhook"

async def on_startup(dp):
    # Restart-এ local CSV হারিয়ে গেলে Firestore থেকে আবার বানায় — ডেটা ডিলিট হয় না
    try:
        n = await asyncio.to_thread(rebuild_csv_from_firestore, False)
        logger.info(f"Startup CSV ready: {n} rows")
    except Exception as e:
        logger.error(f"Startup CSV rebuild failed: {e}")
        try:
            _ensure_csv_file()
        except Exception:
            pass

    webhook_url = (os.getenv("WEBHOOK_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
    if webhook_url:
        full_webhook_url = f"{webhook_url}{WEBHOOK_PATH}"
        await bot.set_webhook(full_webhook_url)
        logger.info(f"Webhook set to {full_webhook_url}")
    else:
        logger.info("WEBHOOK_URL/RENDER_EXTERNAL_URL not set; polling mode will be used.")

async def on_shutdown(dp):
    logger.info("Shutting down...")
    try:
        session = await bot.get_session()
        await session.close()
    except Exception as e:
        logger.warning(f"Session close error: {e}")

async def health(request):
    from aiohttp import web
    return web.Response(text="OK")

# ==================== বট চালানো ====================

if __name__ == '__main__':
    from aiogram import executor
    
    if os.getenv("WEBHOOK_URL") or os.getenv("RENDER_EXTERNAL_URL"):
        from aiohttp import web
        from aiogram.utils.executor import set_webhook
        web_app = web.Application()
        web_app.router.add_get("/", health)
        runner = set_webhook(
            dispatcher=dp,
            webhook_path=WEBHOOK_PATH,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            skip_updates=True,
            web_app=web_app
        )
        runner.run_app(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
    else:
        # Polling mode-এও startup-এ CSV recover
        executor.start_polling(
            dp,
            skip_updates=True,
            timeout=20,
            relax=0.05,
            fast=True,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
        )
