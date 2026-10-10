# bot.py - Social Media Task Bot (কপি ফিচার ছাড়া)
# সব ফিচার কাজ করবে!  +  SPEED OPTIMIZED

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

    def set(self, key, value, ttl=60):
        expires = time.time() + ttl if ttl else None
        self._store[key] = (value, expires)

    def delete(self, key):
        self._store.pop(key, None)

    def clear(self):
        self._store.clear()

cache = SimpleCache()
# ইন-মেমোরি: 2FA অপেক্ষমাণ ইউজার (Firestore read কমায়)
PENDING_TASK_USERS = set()
BOT_USERNAME_CACHE = {"value": None}

def mark_pending_task(user_id):
    PENDING_TASK_USERS.add(user_id)

def clear_pending_task(user_id):
    PENDING_TASK_USERS.discard(user_id)
    try:
        db.collection('temp_tasks').document(str(user_id)).delete()
        db.collection('temp_2fa').document(str(user_id)).delete()
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
        if _gsheet_client is None or (now - _gsheet_last_init) > 300:
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

def save_task_submission(user_id, username, password, full_name, twofa_key, twofa_code, task_type, reward=0, cookies=""):
    """
    ২টা সিস্টেম আলাদাভাবে on/off — Google Sheet আর Local CSV।
    Sheet-এ লেখা ব্যাকগ্রাউন্ডে (fire-and-forget) হয়, তাই বট স্লো হয় না।
    সিরিয়াল নম্বর CSV থেকে (দ্রুততম, লোকাল) রিটার্ন করা হয়।
    """
    serial = "#001"
    if is_csv_sync_enabled():
        serial = save_to_csv(user_id, username, password, full_name, twofa_key, twofa_code, task_type, reward, cookies)
    if is_sheet_sync_enabled():
        asyncio.create_task(
            asyncio.to_thread(save_to_google_sheets, user_id, username, password, full_name, twofa_key, twofa_code, task_type, reward, cookies)
        )
        if not is_csv_sync_enabled():
            serial = f"#{datetime.now().strftime('%H%M%S')}"
    return serial

# ==================== বট ইনিশিয়ালাইজ ====================
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())


# ==================== ইউজার স্টেট ====================
user_states = {}
temp_data = {}

# ==================== গ্লোবাল ভেরিয়েবল ====================
WITHDRAW_METHODS = ["বিকাশ", "নগদ", "রকেট", "ব্যাংক"]
MIN_WITHDRAW = 50.0
WITHDRAW_GROUP = ""
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
    "📱 কাজ", "📋 Tasks ▸", "📊 আমার রিপোর্ট", "📊 Report",
    "💸 টাকা উত্তোলন", "💸 Withdraw", "🔗 রেফারেল", "🔗 Referral",
    "🛠 সাপোর্ট", "🛠 Support", "🌐 Language / ভাষা",
    "🎛️ অ্যাডমিন প্যানেল", "🎛️ Admin Panel", "❌ প্রধান মেনু", "❌ Main Menu",
    "Admin Panel", "অ্যাডমিন প্যানেল", "Tasks ▸", "Report", "Withdraw",
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
        cache.set("admins", ADMIN_LIST, ttl=120)
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
        cache.set("admins", admins, ttl=120)
        return True
    return False

def remove_admin(user_id):
    admins = get_admins()
    if user_id in admins and user_id != ADMIN_ID:
        admins.remove(user_id)
        db.collection('settings').document('admins').set({'list': admins})
        cache.set("admins", admins, ttl=120)
        return True
    return False

# ==================== উইথড্র সেটিংস (CACHED) ====================

WITHDRAW_ENABLED = True

def load_withdraw_settings():
    global MIN_WITHDRAW, WITHDRAW_METHODS, WITHDRAW_GROUP, WITHDRAW_ENABLED
    try:
        doc = db.collection('settings').document('withdraw').get()
        if doc.exists:
            data = doc.to_dict()
            MIN_WITHDRAW = data.get('min_withdraw', 50.0)
            WITHDRAW_METHODS = data.get('methods', ["বিকাশ", "নগদ", "রকেট", "ব্যাংক"])
            WITHDRAW_GROUP = data.get('group', "")
            WITHDRAW_ENABLED = data.get('enabled', True)
        cache.set("withdraw_settings", True, ttl=180)
    except Exception:
        pass

def save_withdraw_settings():
    try:
        db.collection('settings').document('withdraw').set({
            'min_withdraw': MIN_WITHDRAW,
            'methods': WITHDRAW_METHODS,
            'group': WITHDRAW_GROUP,
            'enabled': WITHDRAW_ENABLED
        })
        cache.delete("withdraw_settings")
    except Exception:
        pass

load_withdraw_settings()

# ==================== ফোর্স জয়েন (CACHED) ====================

def load_force_channels():
    global FORCE_CHANNELS
    try:
        doc = db.collection('settings').document('force_join').get()
        if doc.exists:
            FORCE_CHANNELS = doc.to_dict().get('channels', [])
        cache.set("force_channels", FORCE_CHANNELS, ttl=120)
    except Exception:
        pass

def save_force_channels():
    try:
        db.collection('settings').document('force_join').set({'channels': FORCE_CHANNELS})
        cache.set("force_channels", FORCE_CHANNELS, ttl=120)
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
        cache.set("extra_settings", True, ttl=180)
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
        cache.set("guide_buttons", GUIDE_BUTTONS, ttl=180)
    except Exception:
        pass

def save_guide_buttons():
    try:
        db.collection('settings').document('guide_buttons').set({'buttons': GUIDE_BUTTONS})
        cache.set("guide_buttons", GUIDE_BUTTONS, ttl=180)
    except Exception:
        pass

load_guide_buttons()

PENDING_GUIDE_BUTTON = {}

async def check_force_join(user_id):
    channels = cache.get("force_channels")
    if channels is None:
        load_force_channels()
        channels = FORCE_CHANNELS
    if not channels:
        return True
    if is_admin(user_id):
        return True
    # ইউজার-প্রতি ৯০ সেকেন্ড ক্যাশ — বারবার Telegram API কল নয়
    ck = f"force_join:{user_id}"
    cached = cache.get(ck)
    if cached is not None:
        return cached
    async def _one(ch):
        try:
            member = await bot.get_chat_member(ch, user_id)
            return member.status not in ('left', 'kicked')
        except Exception:
            return False
    results = await asyncio.gather(*[_one(ch) for ch in channels], return_exceptions=True)
    ok = all(r is True for r in results)
    cache.set(ck, ok, ttl=90)
    return ok

# ==================== Firebase ফাংশন (CACHED + FAST) ====================

def get_user(user_id):
    """Cache user data for 30 seconds – biggest speed win."""
    key = f"user:{user_id}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        doc = db.collection('users').document(str(user_id)).get()
        if doc.exists:
            data = doc.to_dict()
            cache.set(key, data, ttl=90)
            return data
    except Exception as e:
        logger.error(f"Get User Error: {e}")
    return None

def invalidate_user_cache(user_id):
    cache.delete(f"user:{user_id}")

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
        'total_refers': 0,
        'refer_income': 0.0,
        'is_banned': False,
        'lang': lang,
        'joined_at': firestore.SERVER_TIMESTAMP
    }
    db.collection('users').document(str(user_id)).set(user_data)
    cache.set(f"user:{user_id}", user_data, ttl=90)
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
    user = get_user(target_id)
    custom_rate = (user or {}).get('custom_rate', 100)
    actual_reward = base_reward * (custom_rate / 100.0)
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
                    await bot.send_message(referrer_id, f"🎉 আপনার রেফার করা একজনের টাস্ক অ্যাপ্রুভ হয়েছে!\n💵 কমিশন পেয়েছেন: Tk {commission:.2f}")
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Referral Commission Credit Error: {e}")
    
    return actual_reward

def get_balance(user_id):
    user = get_user(user_id)
    return user['balance'] if user else 0.0

def get_active_tasks():
    """Cache active tasks for 45 seconds."""
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

def get_task(task_id):
    key = f"task:{task_id}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        doc = db.collection('tasks').document(task_id).get()
        if doc.exists:
            data = doc.to_dict()
            cache.set(key, data, ttl=180)
            return data
    except Exception as e:
        logger.error(f"Get Task Error: {e}")
    return None

def invalidate_tasks_cache():
    cache.delete("active_tasks")

def save_to_google_sheets(user_id, username, password, full_name, twofa_key, twofa_code, task_type, reward=0, cookies=""):
    try:
        sheet = get_google_sheet()
        if not sheet:
            return "#001"
        
        all_values = sheet.get_all_values()
        
        if not all_values:
            sheet.append_row(["Serial", "User ID", "Username", "Full Name", "Password", "Cookies", "2FA Key", "Task Type", "Reward", "Status", "Time"])
            serial = 1
        else:
            serial = len(all_values)
        
        safe_cookies = str(cookies).replace("\r", " ").replace("\n", " ") if cookies else ""
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
        sheet.append_row(row, value_input_option="RAW")
        return f"#{serial:03d}"
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
        'report': "📊 **আমার রিপোর্ট**\n\n💰 **ব্যালেন্স:** Tk {balance:.2f}\n📋 **মোট সাবমিট করা টাস্ক:** {tasks}\n✅ **অ্যাপ্রুভড:** {approved}\n⏳ **মোট পেন্ডিং (এখনো অ্যাপ্রুভ হয়নি):** {pending} টি\n❌ **রিজেক্টেড:** {rejected}\n\n📌 **সর্বশেষ ৫ টাস্ক:**\n{tasks_list}",
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
        'force_join': "⚠️ **বট ব্যবহার করতে নিচের গ্রুপে জয়েন করুন:**\n\n{channels}",
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
        'report': "📊 **Report**\n\n💰 **Balance:** Tk {balance:.2f}\n📋 **Total Submitted Tasks:** {tasks}\n✅ **Approved:** {approved}\n⏳ **Total Pending (not yet approved):** {pending}\n❌ **Rejected:** {rejected}\n\n📌 **Last 5 Tasks:**\n{tasks_list}",
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
        'force_join': "⚠️ **Please join the following channels to use the bot:**\n\n{channels}",
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
            KeyboardButton("📊 Report", style="primary"),
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
            KeyboardButton("📊 আমার রিপোর্ট", style="primary"),
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
        await callback.answer("❌ আপনি অ্যাডমিন নন!", show_alert=True)
        return

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
        await callback.answer()
    except Exception as e:
        logger.error(f"Main Menu Callback Error: {e}")
        await callback.answer("❌ অনুরোধটি সম্পন্ন করা যায়নি।", show_alert=True)


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

    if not await check_force_join(user_id):
        channels = "\n".join([f"📌 {ch}" for ch in FORCE_CHANNELS])
        await message.answer(
            get_text(user_id, 'force_join', channels=channels),
            parse_mode=ParseMode.MARKDOWN
        )
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
        channels = "\n".join([f"📌 {ch}" for ch in FORCE_CHANNELS])
        await callback.message.answer(
            get_text(user_id, 'force_join', channels=channels),
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

# ==================== কাজ (কপি ফিচার ছাড়া) ====================

@dp.message_handler(lambda message: message.text in ["📱 কাজ", "📋 Tasks ▸"])
async def show_tasks(message: types.Message):
    user_id = message.from_user.id
    
    if not await check_force_join(user_id):
        channels = "\n".join([f"📌 {ch}" for ch in FORCE_CHANNELS])
        await message.answer(get_text(user_id, 'force_join', channels=channels))
        return
    
    tasks = get_active_tasks()
    if not tasks:
        await message.answer(get_text(user_id, 'no_tasks'))
        return
    
    user = get_user(user_id)
    lang = (user or {}).get('lang', 'bn')
    text = "✏️ **Select any task**" if lang == 'en' else "✏️ **যেকোনো একটি কাজ সিলেক্ট করুন**"
    back_label = "❌ Main Menu" if lang == 'en' else "❌ প্রধান মেনু"
    # মেনুবারের নিচে ReplyKeyboard — screenshot-এর মতো
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False, row_width=1)
    for task in tasks:
        emoji = task.get('emoji', '📱')
        name = task.get('name', 'Unknown')
        keyboard.add(KeyboardButton(f"{emoji} {name}", style="primary"))
    keyboard.add(KeyboardButton(back_label, style="danger"))
    MENU_BUTTON_TEXTS.add(back_label)
    temp_data[user_id] = temp_data.get(user_id, {}) if isinstance(temp_data.get(user_id), dict) else {}
    temp_data[user_id]['task_name_map'] = {
        f"{t.get('emoji', '📱')} {t.get('name', 'Unknown')}": t.get('task_id', '')
        for t in tasks
    }
    await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

# ==================== টাস্ক হ্যান্ডলার ====================

def get_verification_mode(task_id):
    tid = (task_id or "").lower()
    # fb_2fa_cookies → 2FA Key + code জেনারেট + Cookies; sheet-এ শুধু Key
    has_cookie = ("cookie" in tid) or ("cokies" in tid) or ("cookies" in tid)
    has_2fa = ("2fa" in tid) or ("fb" in tid) or ("facebook" in tid)
    if has_cookie and has_2fa:
        return "fb_2fa_cookies"
    if has_cookie:
        return "cookie"
    elif "fb" in tid or "facebook" in tid:
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
        try:
            await callback_message.answer("❌ টাস্কটি পাওয়া যায়নি!")
        except Exception:
            try:
                await callback_message.edit_text("❌ টাস্কটি পাওয়া যায়নি!")
            except Exception:
                pass
        return
    
    mode = get_verification_mode(task_id)
    password = generate_password(task.get("fixed_password", "") or "")
    # threads_2fa → ভিয়েতনামি নাম; বাকি সব English
    if "threads" in (task_id or "").lower():
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
    """টাস্ক লিস্ট বাটন সরিয়ে মেইন মেনু বসায় — মেসেজ ডিলিট করে gap দেখায় না"""
    try:
        tmp = await message.answer("⏳", reply_markup=get_main_menu(user_id))
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
    if not await check_force_join(user_id):
        channels = "\n".join([f"📌 {ch}" for ch in FORCE_CHANNELS])
        await message.answer(get_text(user_id, 'force_join', channels=channels))
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
    
    if not await check_force_join(user_id):
        await callback.answer("❌ দয়া করে গ্রুপে জয়েন করুন!", show_alert=True)
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
    task_id = callback.data.replace("task_done_", "", 1)
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
    uid = message.text.strip()
    if not uid:
        await message.answer("❌ সঠিক UID দিন!", reply_markup=task_cancel_keyboard())
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
    # মেমোরি চেক আগে — Firestore skip (fast path)
    if uid not in PENDING_TASK_USERS:
        return False
    try:
        doc = db.collection('temp_tasks').document(str(uid)).get()
        exists = doc.exists
        if not exists:
            PENDING_TASK_USERS.discard(uid)
        return exists
    except Exception as e:
        logger.error(f"is_awaiting_2fa Error: {e}")
        return False

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
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        colored_button("🔄 নতুন কোড জেনারেট করুন", callback_data=f"refresh_2fa_{user_id}"),
        colored_button("✅ সাবমিট করুন", callback_data=f"submit_2fa_{user_id}"),
        colored_button("❌ বাতিল", callback_data=f"cancel_2fa_{user_id}")
    )
    
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
    db.collection('temp_2fa').document(str(user_id)).delete()
    db.collection('temp_tasks').document(str(user_id)).delete()
    await callback.message.edit_text("❌ বাতিল করা হয়েছে।")
    await callback.answer()

# ==================== 2FA রিফ্রেশ কলব্যাক ====================

@dp.callback_query_handler(lambda c: c.data.startswith("refresh_2fa_"))
async def refresh_2fa_code(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
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
    
    try:
        import pyotp
        totp = pyotp.TOTP(twofa_key)
        new_code = totp.now()
        
        if len(new_code) != 6 or not new_code.isdigit():
            raise ValueError("Invalid OTP")
            
    except Exception as e:
        await callback.message.edit_text(
            f"❌ 2FA Key ত্রুটিপূর্ণ! আবার Key দিন।\n\nএরর: {e}",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
        return
    
    db.collection('temp_2fa').document(str(user_id)).update({
        'updated_at': firestore.SERVER_TIMESTAMP
    })
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        colored_button("🔄 নতুন কোড জেনারেট করুন", callback_data=f"refresh_2fa_{user_id}"),
        colored_button("✅ সাবমিট করুন", callback_data=f"submit_2fa_{user_id}"),
        colored_button("❌ বাতিল", callback_data=f"cancel_2fa_{user_id}")
    )
    
    try:
        await callback.message.edit_text(
            f"🔢 ** Your 2FA Code:** `{new_code}`\n"
            f"⏰ **ভ্যালিডিটি:** ৩০ সেকেন্ড\n\n",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Refresh 2FA Edit Error: {e}")
        await callback.message.reply(
            f"✅ **নতুন 2FA Code:** `{new_code}`\n\n"
            f"⏰ Validity time : 30 SECOND ",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    
    await callback.answer("🔄 New 2fa code!")

# ==================== 2FA সাবমিট কলব্যাক ====================

@dp.callback_query_handler(lambda c: c.data.startswith("submit_2fa_"))
async def submit_2fa_code(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
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
    username = data.get('username', '')
    uid = data.get('uid', '')
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
    user = get_user(user_id)
    if not user:
        user = create_user(user_id, message.from_user.username, message.from_user.first_name)
    if not BOT_USERNAME_CACHE["value"]:
        bot_info = await bot.get_me()
        BOT_USERNAME_CACHE["value"] = bot_info.username
    ref_link = f"https://t.me/{BOT_USERNAME_CACHE['value']}?start=ref_{user_id}"
    await message.answer(get_text(user_id, 'referral',
        link=ref_link, total=user.get('total_refers', 0), income=user.get('refer_income', 0), commission=REFERRAL_COMMISSION_PERCENT
    ), reply_markup=InlineKeyboardMarkup(row_width=1).add(
        colored_button("📤 শেয়ার করুন", switch_inline_query=ref_link)
    ), parse_mode=ParseMode.MARKDOWN)

@dp.callback_query_handler(lambda c: c.data.startswith("copy_"))
async def copy_referral_link(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not BOT_USERNAME_CACHE["value"]:
        bot_info = await bot.get_me()
        BOT_USERNAME_CACHE["value"] = bot_info.username
    ref_link = f"https://t.me/{BOT_USERNAME_CACHE['value']}?start=ref_{user_id}"
    await callback.answer(f"লিংক কপি করতে নিচের মেসেজে থাকা লিংকে ট্যাপ করুন:\n{ref_link}", show_alert=True)

# ==================== রিপোর্ট ====================

@dp.message_handler(lambda message: message.text in ["📊 রিপোর্ট", "📊 Report"])
async def show_report(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user:
        await message.answer("❌ আপনার কোনো ডেটা নেই!")
        return
    try:
        # SPEED: limit to last 20 submissions only
        docs = db.collection('submissions').where('user_id', '==', user_id).order_by('submitted_at', direction=firestore.Query.DESCENDING).limit(20).stream()
        subs = [d.to_dict() for d in docs]
    except Exception as e:
        logger.error(f"Show Report Error: {e}")
        # fallback without order
        try:
            docs = db.collection('submissions').where('user_id', '==', user_id).limit(20).stream()
            subs = [d.to_dict() for d in docs]
            subs.sort(key=lambda s: s.get('submitted_at') or datetime.min, reverse=True)
        except Exception:
            subs = []
    tasks_list = ""
    for task_data in subs[:5]:
        status_emoji = "✅" if task_data.get('status') == 'approved' else "⏳" if task_data.get('status') == 'pending' else "❌"
        status_text = "অ্যাপ্রুভড" if task_data.get('status') == 'approved' else "পেন্ডিং" if task_data.get('status') == 'pending' else "রিজেক্টেড"
        tasks_list += f"{status_emoji} {task_data.get('task_type', 'N/A')} - {task_data.get('reward', 0):.2f} টাকা ({status_text})\n"
    if not tasks_list:
        tasks_list = "└── কোনো টাস্ক নেই"
    await message.answer(get_text(user_id, 'report',
        balance=user.get('balance', 0), tasks=user.get('total_tasks', 0),
        approved=user.get('approved_tasks', 0), pending=user.get('pending_tasks', 0),
        rejected=user.get('rejected_tasks', 0), tasks_list=tasks_list
    ), parse_mode=ParseMode.MARKDOWN)

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

# ==================== উইথড্র ====================

@dp.message_handler(lambda message: message.text in ["💸 টাকা উত্তোলন", "💸 Withdraw"])
async def show_withdraw(message: types.Message):
    user_id = message.from_user.id

    if not WITHDRAW_ENABLED:
        await message.answer(get_text(user_id, 'withdraw_disabled'))
        return
    
    if not await check_force_join(user_id):
        channels = "\n".join([f"📌 {ch}" for ch in FORCE_CHANNELS])
        await message.answer(get_text(user_id, 'force_join', channels=channels))
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
    data = callback.data
    if data == "withdraw_cancel":
        user_states.pop(user_id, None)
        temp_data.pop(user_id, None)
        await callback.message.edit_text("❌ উইথড্র বাতিল করা হয়েছে।")
        await callback.answer()
        return
    method = data.replace("withdraw_", "", 1)
    user_states[user_id] = f"withdraw_amount_{method}"
    temp_data[user_id] = {'method': method}
    cancel_kb = InlineKeyboardMarkup().add(colored_button("❌ বাতিল", callback_data="withdraw_cancel"))
    await callback.message.edit_text(get_text(user_id, 'withdraw_amount', balance=get_balance(user_id), min_withdraw=MIN_WITHDRAW), reply_markup=cancel_kb, parse_mode=ParseMode.MARKDOWN)
    await callback.answer()

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id].startswith("withdraw_amount_"))
async def withdraw_amount(message: types.Message):
    user_id = message.from_user.id
    # মেনু বাটন চাপলে state ক্লিয়ার — "সঠিক অ্যামাউন্ট" এরর আসবে না
    if (message.text or "").strip() in MENU_BUTTON_TEXTS:
        user_states.pop(user_id, None)
        temp_data.pop(user_id, None)
        return
    state = user_states[user_id]
    method = state.replace("withdraw_amount_", "")
    try:
        amount = float(message.text.strip())
        balance = get_balance(user_id)
        if amount < MIN_WITHDRAW:
            await message.answer(f"❌ মিনিমাম উইথড্র {MIN_WITHDRAW} টাকা!\nআবার অ্যামাউন্ট দিন:")
            return
        if amount > balance:
            await message.answer(f"❌ আপনার ব্যালেন্স অপর্যাপ্ত! ব্যালেন্স: {balance:.2f} টাকা\nআবার অ্যামাউন্ট দিন:")
            return
        temp_data[user_id]['amount'] = amount
        user_states[user_id] = f"withdraw_account_{method}"
        cancel_kb = InlineKeyboardMarkup().add(colored_button("❌ বাতিল", callback_data="withdraw_cancel"))
        await message.answer(get_text(user_id, 'withdraw_method', method=method), reply_markup=cancel_kb, parse_mode=ParseMode.MARKDOWN)
    except ValueError:
        await message.answer("❌ সঠিক অ্যামাউন্ট দিন!")

@dp.message_handler(lambda message: message.from_user.id in user_states and user_states[message.from_user.id].startswith("withdraw_account_"))
async def withdraw_account(message: types.Message):
    user_id = message.from_user.id
    if (message.text or "").strip() in MENU_BUTTON_TEXTS:
        user_states.pop(user_id, None)
        temp_data.pop(user_id, None)
        return
    state = user_states.pop(user_id, "")
    data = temp_data.pop(user_id, {})
    method = state.replace("withdraw_account_", "")
    account = message.text.strip()
    amount = data.get('amount', 0)
    req_id = f"WD{datetime.now().strftime('%Y%m%d%H%M%S')}{user_id % 1000}"
    update_balance(user_id, -amount)
    db.collection('withdrawals').document(req_id).set({
        'user_id': user_id, 'amount': amount, 'method': method,
        'account': account, 'status': 'pending', 'req_id': req_id,
        'created_at': firestore.SERVER_TIMESTAMP
    })
    await message.answer(get_text(user_id, 'withdraw_confirm',
        req_id=req_id, amount=amount, method=method, account=account
    ), parse_mode=ParseMode.MARKDOWN)
    
    user = get_user(user_id)
    group_text = get_text(user_id, 'withdraw_group',
        user=f"{user.get('first_name', 'User')} (ID: {user_id})",
        amount=amount, method=method, account=account, req_id=req_id
    )
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        colored_button("✅ Approve", callback_data=f"wd_approve_{req_id}"),
        colored_button("❌ Reject", callback_data=f"wd_reject_{req_id}")
    )
    notified = False
    if WITHDRAW_GROUP:
        try:
            await bot.send_message(WITHDRAW_GROUP, group_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            notified = True
        except Exception as e:
            logger.error(f"Withdraw Group Notify Error: {e}")
    if not notified:
        for admin_id in get_admins():
            try:
                await bot.send_message(admin_id, group_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                logger.error(f"Withdraw Admin DM Error: {e}")

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
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("❌ আপনি অ্যাডমিন নন!", show_alert=True)
        return
    text, keyboard = build_admin_panel_content(user_id)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await callback.message.reply(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
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
            cache.set("admin_counts", counts, ttl=20)
        except Exception:
            counts = {"tasks": 0, "users": 0, "pending_subs": 0, "pending_wd": 0}
    
    task_list = ""
    for task in tasks[:5]:
        task_list += f"├── {task.get('emoji', '')} {task.get('name', 'N/A')} (Tk {task.get('reward', 0):.2f})\n"
    if not task_list:
        task_list = "└── কোনো টাস্ক নেই"
    
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
    _ensure_csv_file()
    names = []
    try:
        with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                name = (row.get("Task Type") or "").strip()
                if name and name not in names:
                    names.append(name)
    except Exception as e:
        logger.error(f"Task name read error: {e}")
    return names

def _safe_task_filename(task_name):
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in task_name)[:50] or "task"
    return f"{safe_name}_task_data.csv"

def _write_task_file(task_name, rows=None):
    if rows is None:
        _ensure_csv_file()
        rows = []
        try:
            with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
                rows = [r for r in csv.DictReader(f) if (r.get("Task Type") or "").strip() == task_name]
        except Exception as e:
            logger.error(f"Task file source read error: {e}")
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
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
        return "📥 **পেন্ডিং সাবমিশন**\n\n✅ কোনো পেন্ডিং সাবমিশন নেই!", keyboard
    
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
    keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
    
    text = f"📥 **পেন্ডিং সাবমিশন (মোট {total}টি) — পেজ {page + 1}/{total_pages}**\n\nনিচে থেকে একটি সিলেক্ট করুন বিস্তারিত দেখতে ও Approve/Reject করতে:"
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

@dp.message_handler(lambda message: message.text in ["🎛️ অ্যাডমিন প্যানেল", "🎛️ Admin Panel", "Admin Panel", "অ্যাডমিন প্যানেল"])
async def admin_panel(message: types.Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("❌ আপনি অ্যাডমিন নন!")
        return
    # টাস্ক/2FA state ক্লিয়ার — Admin Panel চাপলে 2FA চাইবে না
    user_states.pop(user_id, None)
    temp_data.pop(user_id, None)
    clear_pending_task(user_id)
    text, keyboard = build_admin_panel_content(user_id)
    await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

# ==================== অ্যাডমিন কলব্যাক ====================

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("admin_"))
async def admin_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("❌ আপনি অ্যাডমিন নন!", show_alert=True)
        return
    data = callback.data
    
    if data == "admin_upload_report":
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            colored_button("✅ OK ID Report", callback_data="admin_report_mode_approve"),
            colored_button("❌ BAD ID Report", callback_data="admin_report_mode_reject"),
        )
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_folder_data"))
        await callback.message.edit_text(
            "📤 **Upload Report**\n\nরিপোর্টের ধরন নির্বাচন করুন:",
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

    elif data in ("admin_report_mode_approve", "admin_report_mode_reject"):
        mode = "approve" if data.endswith("approve") else "reject"
        user_states[user_id] = f"admin_report_upload_{mode}"
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_folder_data"))
        title = "OK ID Report" if mode == "approve" else "BAD ID Report"
        await callback.message.edit_text(
            f"📤 **{title}**\n\n"
            "এখন CSV অথবা XLSX রিপোর্ট ফাইল পাঠান।\n"
            "`User ID` কলাম জরুরি। Approve হলে `Reward` দেওয়া যাবে।",
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
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
        _ensure_csv_file()
        try:
            with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            remaining = [r for r in rows if (r.get("Task Type") or "").strip() != task_name]
            removed = len(rows) - len(remaining)
            with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, quoting=csv.QUOTE_ALL, escapechar='\\')
                writer.writeheader()
                writer.writerows(remaining)

            task_file = _safe_task_filename(task_name)
            if is_restart:
                _write_task_file(task_name, [])
                action_text = "🔄 File restart complete — পুরোনো data clear হয়েছে, নতুন data আবার save হবে।"
            else:
                try:
                    if os.path.exists(task_file):
                        os.remove(task_file)
                except OSError:
                    pass
                action_text = "🗑️ File delete complete — অন্য task-এর data অপরিবর্তিত আছে।"

            await callback.message.edit_text(
                f"✅ **{task_name}**\n\n{action_text}\n\n"
                f"🗑️ Removed: {removed} record(s)",
                reply_markup=InlineKeyboardMarkup(row_width=1).add(
                    colored_button("🗑️ Delete Report", callback_data="admin_delete_report"),
                    colored_button("🔙 Data Sheet Management", callback_data="admin_folder_data")
                ),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Task report file action error: {e}")
            await callback.message.edit_text(
                "❌ File manage করতে সমস্যা হয়েছে।",
                reply_markup=InlineKeyboardMarkup(row_width=1).add(
                    colored_button("🔙 Data Sheet Management", callback_data="admin_folder_data")
                )
            )
        await callback.answer()

    elif data == "admin_download_report":
        task_names = _saved_task_names()
        keyboard = InlineKeyboardMarkup(row_width=1)
        if not task_names:
            keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_folder_data"))
            await callback.message.edit_text(
                "📥 **Download Report**\n\n❌ কোনো saved task data নেই।",
                reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
            return
        for idx, name in enumerate(task_names[:50]):
            keyboard.add(colored_button(
                f"📥 {name.replace(chr(10), ' ')[:45]}",
                callback_data=f"admin_download_task_{idx}"
            ))
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_folder_data"))
        await callback.message.edit_text(
            "📥 **Download Report**\n\nসব জমা হওয়া task name দেখানো হচ্ছে। যেটা select করবেন সেটার file download হবে:",
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

    elif data.startswith("admin_download_task_"):
        try:
            idx = int(data.rsplit("_", 1)[1])
            task_names = _saved_task_names()
            task_name = task_names[idx]
        except Exception:
            await callback.answer("❌ Task পাওয়া যায়নি। আবার চেষ্টা করুন।", show_alert=True)
            return
        _ensure_csv_file()
        rows = []
        try:
            with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
                rows = [r for r in csv.DictReader(f) if (r.get("Task Type") or "").strip() == task_name]
        except Exception as e:
            logger.error(f"Task download source error: {e}")
        if not rows:
            await callback.answer("❌ এই task-এর কোনো data নেই!", show_alert=True)
            return
        try:
            export_path = _write_task_file(task_name, rows)
            from aiogram.types import InputFile
            await callback.message.answer_document(
                InputFile(export_path),
                caption=f"📥 {task_name} — {len(rows)}টি data"
            )
        except Exception as e:
            logger.error(f"Task download error: {e}")
            await callback.message.reply("❌ File download করতে সমস্যা হয়েছে।")
        await callback.answer()

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
            "📝 **টাস্ক আইডি লিখুন:**\n\nউদাহরণ: `insta_2fa`, `fb_2fa`, `tiktok_2fa`, `fb_2fa_cookies`, `threads_2fa`",
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
        db.collection('tasks').document(task_id).delete()
        invalidate_tasks_cache()
        await callback.message.edit_text(
            f"✅ `{task_id}` টাস্ক ডিলিট করা হয়েছে।",
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
            u = user.to_dict()
            text += f"🆔 {u.get('user_id', 'N/A')}\n├── ইউজারনেম: {u.get('username', 'N/A')}\n├── ব্যালেন্স: Tk {u.get('balance', 0):.2f}\n└── মোট টাস্ক: {u.get('total_tasks', 0)}\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
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
        text = "🏆 **টপ ইউজার (ব্যালেন্স অনুযায়ী):**\n\n"
        users = db.collection('users').order_by('balance', direction='DESCENDING').limit(10).stream()
        rank = 1
        for user in users:
            u = user.to_dict()
            text += f"{rank}. 🆔 {u.get('user_id', 'N/A')} → Tk {u.get('balance', 0):.2f}\n"
            rank += 1
        text += "\n🏆 **টপ রেফারার:**\n\n"
        users_ref = db.collection('users').order_by('total_refers', direction='DESCENDING').limit(10).stream()
        rank = 1
        for user in users_ref:
            u = user.to_dict()
            text += f"{rank}. 🆔 {u.get('user_id', 'N/A')} → {u.get('total_refers', 0)} জন\n"
            rank += 1
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
        await callback.message.reply(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
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
            colored_button("🔙 পিছনে", callback_data="admin_panel_back")
        )
        await callback.message.edit_text("👤 **ইউজার ম্যানেজমেন্ট**\n\nনিচের বাটন ব্যবহার করুন:", reply_markup=keyboard)
        await callback.answer()
    
    elif data == "admin_submissions":
        text, keyboard = build_submissions_page(0)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
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
                approved_user = get_user(target_id) or {}
                uname = s.get('username') or s.get('uid') or approved_user.get('username') or approved_user.get('first_name') or str(target_id)
                await bot.send_message(target_id, f"🎉 Congratulations ({uname}) approved successful ✅\n💵 Tk {actual_reward:.2f} আপনার ব্যালেন্সে যোগ হয়েছে।")
            except Exception:
                pass
        back_kb = InlineKeyboardMarkup().add(colored_button("📥 লিস্টে ফিরুন", callback_data=f"subpage_{page}"))
        await callback.message.edit_text(f"✅ সাবমিশন অ্যাপ্রুভ করা হয়েছে!\n🆔 ইউজার: {target_id}\n💵 Tk {reward:.2f}", reply_markup=back_kb)
    else:
        sub_ref.update({'status': 'rejected'})
        if target_id:
            db.collection('users').document(str(target_id)).update({
                'rejected_tasks': firestore.Increment(1),
                'pending_tasks': firestore.Increment(-1)
            })
            invalidate_user_cache(target_id)
            try:
                await bot.send_message(target_id, f"❌ দুঃখিত, আপনার '{s.get('task_type', 'N/A')}' টাস্কটি রিজেক্ট করা হয়েছে।")
            except Exception:
                pass
        back_kb = InlineKeyboardMarkup().add(colored_button("📥 লিস্টে ফিরুন", callback_data=f"subpage_{page}"))
        await callback.message.edit_text(f"❌ সাবমিশন রিজেক্ট করা হয়েছে।\n🆔 ইউজার: {target_id}", reply_markup=back_kb)
    
    await callback.answer()

# ==================== টাস্ক যোগ (স্টেপ বাই স্টেপ) ====================

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
    
    if state == "um_balance":
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
            for ch in FORCE_CHANNELS:
                text += f"📌 {ch}\n"
        else:
            text += "❌ কোনো চ্যানেল সেট করা নেই\n"
        text += "\n📌 **যোগ করতে:** `add_channel | @channel`\n"
        text += "📌 **ডিলিট করতে:** `del_channel | @channel`"
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(colored_button("🔙 পিছনে", callback_data="admin_panel_back"))
        await callback.message.reply(text, reply_markup=keyboard)
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
            "📝 **পারসোনাল রেট সেট করুন:**\n\n"
            "ফরম্যাট: `ইউজার_আইডি | রেট%`\n\n"
            "উদাহরণ: `7294314847 | 150` — এই ইউজার প্রতিটা টাস্কে স্ট্যান্ডার্ড রিওয়ার্ডের ১৫০% পাবে\n"
            "ডিফল্ট (রিসেট) করতে: `7294314847 | 100`",
            reply_markup=keyboard
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
        WITHDRAW_GROUP = text
        save_withdraw_settings()
        await message.answer(f"✅ উইথড্র গ্রুপ সেট করা হয়েছে: {WITHDRAW_GROUP}")
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
            rate = float(parts[1].strip().replace("%", ""))
            if rate < 0:
                await message.answer("❌ ঋণাত্মক রেট দিতে পারবেন না!")
                return
            user = get_user(target_id)
            if not user:
                await message.answer(f"❌ ইউজার `{target_id}` পাওয়া যায়নি!")
                return
            db.collection('users').document(str(target_id)).update({'custom_rate': rate})
            invalidate_user_cache(target_id)
            await message.answer(f"✅ ইউজার `{target_id}`-এর পারসোনাল রেট সেট হয়েছে: {rate:.0f}%\n\n(প্রতিটা টাস্কে এখন স্ট্যান্ডার্ড রিওয়ার্ডের {rate:.0f}% পাবে)")
        except (IndexError, ValueError):
            await message.answer("❌ সঠিক ফরম্যাট দিন! উদাহরণ: `7294314847 | 150`")
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

@dp.message_handler(lambda message: message.text and "add_channel |" in message.text and is_admin(message.from_user.id))
async def add_force_channel(message: types.Message):
    try:
        channel = message.text.split("|")[1].strip()
        if channel not in FORCE_CHANNELS:
            FORCE_CHANNELS.append(channel)
            save_force_channels()
            await message.answer(f"✅ '{channel}' ফোর্স জয়েনে যোগ করা হয়েছে!")
        else:
            await message.answer(f"❌ '{channel}' ইতিমধ্যে আছে!")
    except Exception:
        await message.answer("❌ ভুল ফরম্যাট! ব্যবহার করুন: `add_channel | @channel`")

@dp.message_handler(lambda message: message.text and "del_channel |" in message.text and is_admin(message.from_user.id))
async def del_force_channel(message: types.Message):
    try:
        channel = message.text.split("|")[1].strip()
        if channel in FORCE_CHANNELS:
            FORCE_CHANNELS.remove(channel)
            save_force_channels()
            await message.answer(f"✅ '{channel}' ফোর্স জয়েন থেকে ডিলিট করা হয়েছে!")
        else:
            await message.answer(f"❌ '{channel}' পাওয়া যায়নি!")
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

# ==================== ব্রডকাস্ট ====================

@dp.message_handler(lambda message: message.text and message.from_user.id in user_states and user_states[message.from_user.id] == "admin_broadcast")
async def broadcast_text(message: types.Message):
    user_id = message.from_user.id
    broadcast_msg = message.text
    
    users = db.collection('users').stream()
    count = 0
    for user in users:
        try:
            await bot.send_message(int(user.id), broadcast_msg, parse_mode=ParseMode.MARKDOWN)
            count += 1
        except Exception:
            pass
    
    await message.answer(f"✅ ব্রডকাস্ট পাঠানো হয়েছে! {count} জন পেয়েছে।")
    del user_states[user_id]

# ==================== রিপোর্ট আপলোড ====================

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
                            row.get("instagram_username") or row.get("Instagram Username") or "").strip().lstrip("@")
                if not username:
                    continue
                docs = db.collection("submissions").where("status", "==", "pending").stream()
                for doc in docs:
                    sub = doc.to_dict()
                    sub_username = str(sub.get("username") or "").strip().lstrip("@")
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
                            await bot.send_message(
                                int(target_id),
                                f"❌ This task ({username}) cansall\n\nTry Again"
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
    
    file_name = message.document.file_name or ""
    lower_name = file_name.lower()
    if not (lower_name.endswith('.csv') or lower_name.endswith('.xlsx')):
        await message.answer("❌ শুধু CSV (.csv) অথবা Excel (.xlsx) ফাইল সাপোর্টেড।")
        return
    
    report_mode = user_states.get(user_id)
    if report_mode not in ("admin_report_upload_approve", "admin_report_upload_reject"):
        await message.answer("❌ আগে Upload Report থেকে OK ID Report অথবা BAD ID Report select করুন।")
        return
    forced_status = "reject" if report_mode.endswith("reject") else "approve"
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
        fail_details = []
        
        for idx, row in enumerate(rows, start=2):
            raw_uid = row.get('user id') or row.get('user_id') or row.get('userid') or row.get('id')
            raw_reward = row.get('reward') or row.get('amount') or row.get('টাকা')
            status = (row.get('status') or forced_status or 'reject').strip().lower()
            if status not in ('approve', 'approved', 'reject', 'rejected'):
                status = forced_status or 'reject'
            
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
            
            pending_docs = list(db.collection('submissions').where('user_id', '==', target_id).where('status', '==', 'pending').limit(5).stream())
            pending_docs.sort(key=lambda d: d.to_dict().get('submitted_at') or datetime.min)
            sub_ref = pending_docs[0].reference if pending_docs else None
            
            if status.startswith('reject'):
                if sub_ref:
                    sub_ref.update({'status': 'rejected'})
                db.collection('users').document(str(target_id)).update({
                    'rejected_tasks': firestore.Increment(1),
                    'pending_tasks': firestore.Increment(-1) if sub_ref else firestore.Increment(0)
                })
                invalidate_user_cache(target_id)
                try:
                    await bot.send_message(target_id, "❌ দুঃখিত, আপনার একটি টাস্ক রিজেক্ট করা হয়েছে।")
                except Exception:
                    pass
                success += 1
            else:
                try:
                    reward = float(raw_reward) if raw_reward not in (None, "") else (pending_docs[0].to_dict().get('reward', 0) if pending_docs else 0)
                except (ValueError, TypeError):
                    failed += 1
                    fail_details.append(f"লাইন {idx}: ভুল Reward `{raw_reward}`")
                    continue
                
                actual_reward = await credit_task_approval(target_id, reward)
                if sub_ref:
                    sub_ref.update({'status': 'approved'})
                db.collection('users').document(str(target_id)).update({
                    'approved_tasks': firestore.Increment(1),
                    'pending_tasks': firestore.Increment(-1) if sub_ref else firestore.Increment(0)
                })
                invalidate_user_cache(target_id)
                try:
                    approved_user = get_user(target_id) or {}
                    uname = (pending_docs[0].to_dict().get('username') if pending_docs else None) or (pending_docs[0].to_dict().get('uid') if pending_docs else None) or approved_user.get('username') or approved_user.get('first_name') or str(target_id)
                    await bot.send_message(target_id, f"🎉 Congratulations ({uname}) approved successful ✅\n💵 Tk {actual_reward:.2f} আপনার ব্যালেন্সে যোগ হয়েছে।")
                except Exception:
                    pass
                success += 1
            
        
        summary = f"✅ **প্রসেস সম্পন্ন!**\n\n✅ সফল: {success}\n❌ ব্যর্থ: {failed}\n⏭️ স্কিপড (User ID ফাঁকা): {skipped}"
        if fail_details:
            summary += "\n\n**সমস্যা যেসব লাইনে:**\n" + "\n".join(fail_details[:15])
            if len(fail_details) > 15:
                summary += f"\n... এবং আরও {len(fail_details) - 15}টি"
        await progress_msg.edit_text(summary, parse_mode=ParseMode.MARKDOWN)
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
        executor.start_polling(dp, skip_updates=True)
