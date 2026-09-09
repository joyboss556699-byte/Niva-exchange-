from flask import Blueprint, jsonify, request

# Define constants here to avoid circular import
ADMIN_IDS = {7294314847}

# Global db reference (will be set from bot.py)
db = None

def set_database(database):
    global db
    db = database

panel = Blueprint("panel", __name__, url_prefix="/admin")

@panel.get("/summary")
def summary():
    uid = request.headers.get("X-Telegram-User-Id", "")
    if not uid.isdigit() or int(uid) not in ADMIN_IDS:
        return jsonify({"ok": False, "error": "Admin access required"}), 403
    if not db:
        return jsonify({"ok": True, "firebase": False})
    try:
        users_count = len(list(db.collection("users").stream()))
        orders_count = len(list(db.collection("orders").stream()))
        return jsonify({
            "ok": True,
            "firebase": True,
            "users": users_count,
            "orders": orders_count
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500