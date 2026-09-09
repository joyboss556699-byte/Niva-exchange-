from flask import Blueprint, jsonify, request, render_template_string
import firebase_admin
from firebase_admin import firestore

# Define constants
ADMIN_IDS = {7294314847}

# Global db reference
db = None

def set_database(database):
    global db
    db = database

panel = Blueprint("panel", __name__, url_prefix="/admin")

# Admin Panel HTML Template
ADMIN_PANEL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Admin Panel - NIVA EXCHANGE</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: #fff;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
        }
        h1 {
            text-align: center;
            margin-bottom: 30px;
            color: #FFD700;
        }
        .section {
            background: rgba(255,255,255,0.1);
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .section h2 {
            margin-bottom: 15px;
            color: #FFD700;
        }
        .toggle-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px;
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
            margin: 10px 0;
        }
        .toggle-switch {
            position: relative;
            width: 60px;
            height: 30px;
            background: #ccc;
            border-radius: 15px;
            cursor: pointer;
            transition: background 0.3s;
        }
        .toggle-switch.active {
            background: #4CAF50;
        }
        .toggle-switch::after {
            content: '';
            position: absolute;
            top: 5px;
            left: 5px;
            width: 20px;
            height: 20px;
            background: white;
            border-radius: 50%;
            transition: transform 0.3s;
        }
        .toggle-switch.active::after {
            transform: translateX(30px);
        }
        .stats {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: rgba(255,255,255,0.1);
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }
        .stat-value {
            font-size: 32px;
            font-weight: bold;
            color: #FFD700;
        }
        .stat-label {
            font-size: 14px;
            margin-top: 5px;
        }
        button {
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            margin: 5px;
        }
        .btn-primary {
            background: #4169E1;
            color: white;
        }
        .btn-danger {
            background: #DC143C;
            color: white;
        }
        .btn-success {
            background: #4CAF50;
            color: white;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>👨‍💼 ADMIN PANEL</h1>
        
        <div class="section">
            <h2>📊 Statistics</h2>
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-value" id="usersCount">0</div>
                    <div class="stat-label">Total Users</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="ordersCount">0</div>
                    <div class="stat-label">Total Orders</div>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2>⚙️ System Controls</h2>
            <div class="toggle-item">
                <div>
                    <strong>System Status</strong>
                    <div style="font-size: 12px; opacity: 0.8;">Enable/Disable entire system</div>
                </div>
                <div class="toggle-switch" id="systemToggle" onclick="toggleSystem()"></div>
            </div>
        </div>
        
        <div class="section">
            <h2> Feature Toggles</h2>
            <div class="toggle-item">
                <div>
                    <strong>XR7 Task</strong>
                    <div style="font-size: 12px; opacity: 0.8;">Enable/disable XR7 task system</div>
                </div>
                <div class="toggle-switch" id="xr7Toggle" onclick="toggleFeature('xr7Task')"></div>
            </div>
            <div class="toggle-item">
                <div>
                    <strong>Coin Selling</strong>
                    <div style="font-size: 12px; opacity: 0.8;">Enable/disable coin selling</div>
                </div>
                <div class="toggle-switch" id="coinToggle" onclick="toggleFeature('coinSell')"></div>
            </div>
            <div class="toggle-item">
                <div>
                    <strong>History</strong>
                    <div style="font-size: 12px; opacity: 0.8;">Show/hide history feature</div>
                </div>
                <div class="toggle-switch" id="historyToggle" onclick="toggleFeature('history')"></div>
            </div>
            <div class="toggle-item">
                <div>
                    <strong>Refer System</strong>
                    <div style="font-size: 12px; opacity: 0.8;">Show/hide refer feature</div>
                </div>
                <div class="toggle-switch" id="referToggle" onclick="toggleFeature('refer')"></div>
            </div>
        </div>
        
        <div class="section">
            <h2>💰 Payment Methods</h2>
            <div class="toggle-item">
                <div><strong>Bikas</strong></div>
                <div class="toggle-switch" id="bikasToggle" onclick="togglePayment('bikas')"></div>
            </div>
            <div class="toggle-item">
                <div><strong>Nogod</strong></div>
                <div class="toggle-switch" id="nogodToggle" onclick="togglePayment('nogod')"></div>
            </div>
            <div class="toggle-item">
                <div><strong>Rockat</strong></div>
                <div class="toggle-switch" id="rokatToggle" onclick="togglePayment('rokat')"></div>
            </div>
        </div>
    </div>
    
    <script>
        const userId = new URLSearchParams(window.location.search).get('uid');
        
        // Load initial state
        async function loadState() {
            try {
                const response = await fetch('/admin/state', {
                    headers: { 'X-Telegram-User-Id': userId }
                });
                const data = await response.json();
                
                if (data.ok) {
                    // Update stats
                    document.getElementById('usersCount').textContent = data.stats.users || 0;
                    document.getElementById('ordersCount').textContent = data.stats.orders || 0;
                    
                    // Update toggles
                    updateToggle('systemToggle', data.status.enabled);
                    updateToggle('xr7Toggle', data.features.xr7Task);
                    updateToggle('coinToggle', data.features.coinSell);
                    updateToggle('historyToggle', data.features.history);
                    updateToggle('referToggle', data.features.refer);
                    updateToggle('bikasToggle', data.payments.bikas);
                    updateToggle('nogodToggle', data.payments.nogod);
                    updateToggle('rokatToggle', data.payments.rokat);
                } else {
                    alert('Access denied');
                    window.close();
                }
            } catch (error) {
                console.error('Error loading state:', error);
            }
        }
        
        function updateToggle(id, active) {
            const el = document.getElementById(id);
            if (active) {
                el.classList.add('active');
            } else {
                el.classList.remove('active');
            }
        }
        
        async function toggleSystem() {
            await toggleEndpoint('/admin/toggle/system');
        }
        
        async function toggleFeature(feature) {
            await toggleEndpoint('/admin/toggle/feature', { feature });
        }
        
        async function togglePayment(method) {
            await toggleEndpoint('/admin/toggle/payment', { method });
        }
        
        async function toggleEndpoint(endpoint, data = {}) {
            try {
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Telegram-User-Id': userId
                    },
                    body: JSON.stringify(data)
                });
                const result = await response.json();
                if (result.ok) {
                    loadState(); // Reload state
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }
        
        // Load on page load
        loadState();
    </script>
</body>
</html>
"""

@panel.get("/panel")
def admin_panel():
    """Render admin panel"""
    uid = request.args.get("uid", "")
    if not uid.isdigit() or int(uid) not in ADMIN_IDS:
        return jsonify({"ok": False, "error": "Admin access required"}), 403
    
    return render_template_string(ADMIN_PANEL_HTML)

@panel.get("/state")
def get_admin_state():
    """Get current state of all toggles"""
    uid = request.headers.get("X-Telegram-User-Id", "")
    if not uid.isdigit() or int(uid) not in ADMIN_IDS:
        return jsonify({"ok": False, "error": "Admin access required"}), 403
    
    try:
        # Get system status
        system_status = {"enabled": True}
        features = {
            "xr7Task": True,
            "coinSell": True,
            "history": False,
            "refer": False,
            "tutorial": False
        }
        payments = {
            "bikas": True,
            "nogod": True,
            "rokat": True
        }
        
        if db:
            # Get system status
            status_doc = db.collection("system").document("status").get()
            if status_doc.exists:
                system_status = status_doc.to_dict()
            
            # Get features
            features_doc = db.collection("system").document("features").get()
            if features_doc.exists:
                features.update(features_doc.to_dict())
            
            # Get payments
            payments_doc = db.collection("system").document("payments").get()
            if payments_doc.exists:
                payments.update(payments_doc.to_dict())
            
            # Get stats
            users_count = len(list(db.collection("users").stream()))
            orders_count = len(list(db.collection("orders").stream()))
        else:
            users_count = 0
            orders_count = 0
        
        return jsonify({
            "ok": True,
            "status": system_status,
            "features": features,
            "payments": payments,
            "stats": {
                "users": users_count,
                "orders": orders_count
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@panel.post("/toggle/system")
def toggle_system():
    """Toggle entire system on/off"""
    uid = request.headers.get("X-Telegram-User-Id", "")
    if not uid.isdigit() or int(uid) not in ADMIN_IDS:
        return jsonify({"ok": False, "error": "Admin access required"}), 403
    
    try:
        if not db:
            return jsonify({"ok": False, "error": "Database not connected"}), 500
        
        # Get current status
        status_doc = db.collection("system").document("status").get()
        current_status = status_doc.to_dict() if status_doc.exists else {"enabled": True}
        
        # Toggle
        new_status = not current_status.get("enabled", True)
        
        # Update
        db.collection("system").document("status").set({"enabled": new_status})
        
        return jsonify({"ok": True, "enabled": new_status})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@panel.post("/toggle/feature")
def toggle_feature():
    """Toggle a specific feature"""
    uid = request.headers.get("X-Telegram-User-Id", "")
    if not uid.isdigit() or int(uid) not in ADMIN_IDS:
        return jsonify({"ok": False, "error": "Admin access required"}), 403
    
    try:
        data = request.get_json()
        feature = data.get("feature")
        
        if not feature or not db:
            return jsonify({"ok": False, "error": "Invalid request"}), 400
        
        # Get current features
        features_doc = db.collection("system").document("features").get()
        features = features_doc.to_dict() if features_doc.exists else {}
        
        # Toggle
        features[feature] = not features.get(feature, True)
        
        # Update
        db.collection("system").document("features").set(features)
        
        return jsonify({"ok": True, "feature": feature, "enabled": features[feature]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@panel.post("/toggle/payment")
def toggle_payment():
    """Toggle a payment method"""
    uid = request.headers.get("X-Telegram-User-Id", "")
    if not uid.isdigit() or int(uid) not in ADMIN_IDS:
        return jsonify({"ok": False, "error": "Admin access required"}), 403
    
    try:
        data = request.get_json()
        method = data.get("method")
        
        if not method or not db:
            return jsonify({"ok": False, "error": "Invalid request"}), 400
        
        # Get current payments
        payments_doc = db.collection("system").document("payments").get()
        payments = payments_doc.to_dict() if payments_doc.exists else {}
        
        # Toggle
        payments[method] = not payments.get(method, True)
        
        # Update
        db.collection("system").document("payments").set(payments)
        
        return jsonify({"ok": True, "method": method, "enabled": payments[method]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@panel.get("/summary")
def summary():
    """Legacy endpoint for backward compatibility"""
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