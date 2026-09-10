from flask import Blueprint, jsonify, request, render_template_string

# ============================================================
# CONSTANTS / DEFAULTS
# ============================================================
ADMIN_IDS = {7294314847}

DEFAULT_COINS = [
    {"id": "niva", "name": "NIVA COIN", "icon": "🪙", "image": "", "price": 5.0, "rate": 1000, "unit": 1000,
     "requiresUsername": True, "requiresCoupon": False, "targetUsername": "", "enabled": True},
    {"id": "ns", "name": "NS COIN", "icon": "👤", "image": "", "price": 5.0, "rate": 1000, "unit": 1000,
     "requiresUsername": True, "requiresCoupon": False, "targetUsername": "", "enabled": True},
    {"id": "newtopfollow", "name": "NEW TOP FOLLOW", "icon": "✨", "image": "", "price": 5.0, "rate": 1000, "unit": 1000,
     "requiresUsername": True, "requiresCoupon": False, "targetUsername": "", "enabled": True},
    {"id": "topfollow", "name": "TOP FOLLOW", "icon": "💗", "image": "", "price": 5.0, "rate": 1000, "unit": 1000,
     "requiresUsername": False, "requiresCoupon": True, "targetUsername": "", "enabled": True},
]
DEFAULT_PAYMENT_METHODS = [
    {"id": "bikas", "name": "bKash", "enabled": True, "image": "", "icon": "💳"},
    {"id": "nogod", "name": "Nagad", "enabled": True, "image": "", "icon": "💳"},
    {"id": "rokat", "name": "Rocket", "enabled": True, "image": "", "icon": "💳"},
    {"id": "binance", "name": "Binance", "enabled": True, "image": "", "icon": "🔶"},
    {"id": "other", "name": "Other", "enabled": True, "image": "", "icon": "💳"},
]
DEFAULT_BRANDING = {
    "helpLineUrl": "https://t.me/Sapportotp",
    "channelUrl": "https://t.me/yourchannel",
    "disclaimer": "",
    "tutorialVideoUrl": "",
}

db = None

def set_database(database):
    global db
    db = database

panel = Blueprint("panel", __name__, url_prefix="/admin")


# ============================================================
# ACCESS CONTROL HELPERS
# ============================================================
def is_admin_request():
    """Accept admin id from header (panel JS) or query string (initial page load)."""
    uid = request.headers.get("X-Telegram-User-Id", "") or request.args.get("uid", "")
    return uid.isdigit() and int(uid) in ADMIN_IDS

def admin_denied():
    return jsonify({"ok": False, "error": "Admin access required"}), 403


# ============================================================
# ADMIN PANEL HTML
# ============================================================
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
        .container { max-width: 800px; margin: 0 auto; }
        .admin-nav{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:16px;position:sticky;top:8px;z-index:5}
        .admin-nav button{background:rgba(255,255,255,.12);color:#fff;border:1px solid rgba(255,255,255,.18);font-weight:700;margin:0}
        .admin-nav button.active{background:#4169E1;box-shadow:0 0 14px rgba(65,105,225,.7)}
        .manage-section{display:none}.manage-section.active{display:block}
        .payment-row{display:grid;grid-template-columns:1fr auto auto;gap:8px;align-items:center}
        .payment-image-preview{width:42px;height:42px;border-radius:8px;object-fit:cover;vertical-align:middle}

        h1 { text-align: center; margin-bottom: 30px; color: #FFD700; }
        .section {
            background: rgba(255,255,255,0.1);
            padding: 20px; border-radius: 10px; margin-bottom: 20px;
        }
        .section h2 { margin-bottom: 15px; color: #FFD700; }
        .toggle-item {
            display: flex; justify-content: space-between; align-items: center;
            padding: 15px; background: rgba(255,255,255,0.05);
            border-radius: 8px; margin: 10px 0;
        }
        .toggle-switch {
            position: relative; width: 60px; height: 30px; background: #ccc;
            border-radius: 15px; cursor: pointer; transition: background 0.3s; flex-shrink: 0;
        }
        .toggle-switch.active { background: #4CAF50; }
        .toggle-switch::after {
            content: ''; position: absolute; top: 5px; left: 5px;
            width: 20px; height: 20px; background: white; border-radius: 50%;
            transition: transform 0.3s;
        }
        .toggle-switch.active::after { transform: translateX(30px); }
        .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px; }
        .stat-card { background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; text-align: center; }
        .stat-value { font-size: 32px; font-weight: bold; color: #FFD700; }
        .stat-label { font-size: 14px; margin-top: 5px; }
        button {
            padding: 10px 20px; border: none; border-radius: 5px;
            cursor: pointer; font-size: 14px; margin: 5px 5px 5px 0;
        }
        .btn-primary { background: #4169E1; color: white; }
        .btn-danger { background: #DC143C; color: white; }
        .btn-success { background: #4CAF50; color: white; }
        .btn-small { padding: 6px 12px; font-size: 12px; }
        input[type="text"], input[type="number"], input[type="url"], textarea {
            width: 100%; padding: 8px 10px; border-radius: 6px; border: none;
            font-size: 14px; margin-top: 4px; font-family: inherit;
        }
        textarea { min-height: 70px; resize: vertical; }
        label.field-label { font-size: 11px; opacity: .8; display: block; margin-bottom: 3px; margin-top: 8px; }

        .coin-rate-row, .payment-row, .order-card, .user-row {
            padding: 12px; background: rgba(255,255,255,0.05); border-radius: 8px;
            margin: 10px 0;
        }
        .coin-rate-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .coin-rate-row .coin-label { flex: 1 1 100px; font-weight: bold; min-width: 90px; }
        .coin-rate-row label { font-size: 11px; opacity: 0.8; display: block; margin-bottom: 3px; }
        .coin-rate-row input[type="number"] { width: 80px; padding: 6px 8px; }
        .coin-rate-row .coin-icon-preview { width: 32px; height: 32px; border-radius: 6px; object-fit: cover; }
        .coin-enabled-toggle { width: 46px; height: 24px; }
        .coin-enabled-toggle::after { width: 16px; height: 16px; top: 4px; }
        .coin-enabled-toggle.active::after { transform: translateX(22px); }

        .payment-row { display: flex; align-items: center; gap: 10px; }
        .payment-row input[type="text"] { flex: 1; }

        .order-card { border-left: 3px solid #FFD700; }
        .order-card img { max-width: 100%; border-radius: 6px; margin: 8px 0; display: block; }
        .order-meta { font-size: 13px; line-height: 1.6; opacity: .95; }
        .order-status { font-size: 11px; padding: 3px 8px; border-radius: 10px; margin-left: 6px; }
        .status-pending { background: #FFA500; color: #191a1d; }
        .status-approved { background: #4CAF50; }
        .status-rejected { background: #DC143C; }

        .user-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; justify-content: space-between; }
        .user-info { font-size: 13px; }
        .user-actions { display: flex; gap: 6px; flex-wrap: wrap; }
        .small-note { font-size: 11px; opacity: .75; margin-top: 6px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>👨‍💼 ADMIN PANEL</h1>
        <div class="admin-nav">
            <button onclick="showSection('dashboard')">📊 Dashboard</button>
            <button onclick="showSection('orders')">📋 Orders</button>
            <button onclick="showSection('users')">👥 Users</button>
            <button onclick="showSection('coins')">🪙 Coin Management</button>
            <button onclick="showSection('payments')">💰 Payment Methods</button>
            <button onclick="showSection('transfer')">🔗 Transfer Settings</button>
            <button onclick="showSection('branding')">🎨 Branding</button>
            <button onclick="showSection('broadcast')">📢 Broadcast</button>
        </div>

        <div class="section manage-section active" data-section="dashboard">
            <h2>📊 Statistics</h2>
            <div class="stats">
                <div class="stat-card"><div class="stat-value" id="usersCount">0</div><div class="stat-label">Total Users</div></div>
                <div class="stat-card"><div class="stat-value" id="ordersCount">0</div><div class="stat-label">Total Orders</div></div>
                <div class="stat-card"><div class="stat-value" id="pendingCount">0</div><div class="stat-label">Pending Orders</div></div>
                <div class="stat-card"><div class="stat-value" id="blockedCount">0</div><div class="stat-label">Blocked Users</div></div>
            </div>
        </div>

        <div class="section manage-section active" data-section="dashboard">
            <h2>⚙️ System Controls</h2>
            <div class="toggle-item">
                <div><strong>System Status</strong><div style="font-size:12px;opacity:.8">Enable/Disable entire system</div></div>
                <div class="toggle-switch" id="systemToggle" onclick="toggleSystem()"></div>
            </div>
        </div>

        <div class="section manage-section active" data-section="dashboard">
            <h2>🧩 Feature Toggles</h2>
            <div class="toggle-item">
                <div><strong>XR7 Task</strong><div style="font-size:12px;opacity:.8">Enable/disable XR7 task system</div></div>
                <div class="toggle-switch" id="xr7Toggle" onclick="toggleFeature('xr7Task')"></div>
            </div>
            <div class="toggle-item">
                <div><strong>Coin Selling</strong><div style="font-size:12px;opacity:.8">Enable/disable coin selling</div></div>
                <div class="toggle-switch" id="coinToggle" onclick="toggleFeature('coinSell')"></div>
            </div>
            <div class="toggle-item">
                <div><strong>History</strong><div style="font-size:12px;opacity:.8">Show/hide history feature</div></div>
                <div class="toggle-switch" id="historyToggle" onclick="toggleFeature('history')"></div>
            </div>
        </div>

        <div class="section manage-section " data-section="orders">
            <h2>📋 Pending Orders</h2>
            <div id="ordersBox"><p class="small-note">Loading...</p></div>
            <button class="btn-primary btn-small" onclick="loadOrders('pending')">Show Pending</button>
            <button class="btn-primary btn-small" onclick="loadOrders('')">Show All (latest 30)</button>
        </div>

        <div class="section manage-section " data-section="users">
            <h2>👥 User Management</h2>
            <input type="text" id="userSearch" placeholder="Search by username / Telegram ID">
            <button class="btn-primary btn-small" onclick="loadUsers()">Search / Refresh</button>
            <div id="usersBox"></div>
        </div>

        <div class="section manage-section " data-section="coins">
            <h2>💱 Coin Rates &amp; Coins</h2>
            <div id="coinRatesBox"></div>
            <button class="btn-primary btn-small" onclick="addCoinRow()">➕ Add New Coin</button>
            <button class="btn-success" onclick="saveCoinRates()">💾 Save Coins</button>
        </div>

        <div class="section manage-section " data-section="payments">
            <h2>💰 Payment Methods</h2>
            <div class="toggle-item" style="display:block">
                <strong>Binance USDT Rate</strong>
                <div style="font-size:12px;opacity:.8;margin:4px 0 8px">1 USDT = কত BDT</div>
                <input type="number" id="binanceRate" step="0.01" min="0.01" placeholder="125">
                <button class="btn-success btn-small" onclick="saveBinanceRate()">💾 Save Rate</button>
            </div>
            <div id="paymentsBox"></div>
            <button class="btn-primary btn-small" onclick="addPaymentRow()">➕ Add Payment Method</button>
            <button class="btn-success" onclick="savePayments()">💾 Save Payment Methods</button>
        </div>

        <div class="section manage-section " data-section="transfer">
            <h2>🔗 Transfer Settings</h2>
            <label class="field-label">Send Coin Transfer ID</label>
            <input type="text" id="transferId" placeholder="যেমন: your_transfer_id" autocomplete="off">
            <label class="field-label">👤 Transfer Username / ID</label>
            <input type="text" id="transferUsername" placeholder="যেমন: @yourusername" autocomplete="off">
            <label class="field-label">🖼️ Transfer Profile Picture</label>
            <input type="file" id="transferProfileImageFile" accept="image/*">
            <input type="hidden" id="transferProfileImage">
            <div id="transferProfilePreview" style="margin:8px 0"></div>
            <p class="small-note">Admin এখানে Transfer ID, username এবং profile picture সেট করতে পারবে। User Panel-এ Admin-এর সেট করা তথ্যই দেখাবে। পুরোনো hardcoded ID/username থাকবে না।</p>
            <button class="btn-success" onclick="saveTransferSettings()">💾 Save Transfer Account</button>
        </div>

        <div class="section manage-section " data-section="branding">
            <h2>🔗 Branding &amp; Links</h2>
            <label class="field-label">Help Line URL (Telegram link)</label>
            <input type="url" id="helpLineUrl" placeholder="https://t.me/...">
            <label class="field-label">Channel URL</label>
            <input type="url" id="channelUrl" placeholder="https://t.me/...">
            <label class="field-label">🎬 Tutorial Video URL</label>
            <input type="url" id="tutorialVideoUrl" placeholder="https://youtube.com/... or https://t.me/...">
            <label class="field-label">📜 Disclaimer Notice (shown to users on open)</label>
            <textarea id="disclaimerText" placeholder="যেমন: ঝুঁকি সম্পর্কে সতর্কবার্তা..."></textarea>
            <button class="btn-success" onclick="saveBranding()">💾 Save Branding</button>
        </div>

        <div class="section manage-section " data-section="broadcast">
            <h2>📢 Broadcast Message</h2>
            <textarea id="broadcastText" placeholder="সব ইউজারকে যে মেসেজ পাঠাতে চান..."></textarea>
            <button class="btn-primary" onclick="sendBroadcast()">🚀 Send to All Users</button>
            <p class="small-note" id="broadcastResult"></p>
        </div>
    </div>

    <script>
        const userId = new URLSearchParams(window.location.search).get('uid');

        function authHeaders(extra) {
            return Object.assign({ 'X-Telegram-User-Id': userId }, extra || {});
        }

        async function loadState() {
            try {
                const response = await fetch('/admin/state', { headers: authHeaders() });
                const data = await response.json();
                if (!data.ok) { alert('Access denied'); window.close(); return; }

                document.getElementById('usersCount').textContent = data.stats.users || 0;
                document.getElementById('ordersCount').textContent = data.stats.orders || 0;
                document.getElementById('pendingCount').textContent = data.stats.pending || 0;
                document.getElementById('blockedCount').textContent = data.stats.blocked || 0;

                updateToggle('systemToggle', data.status.enabled);
                updateToggle('xr7Toggle', data.features.xr7Task);
                updateToggle('coinToggle', data.features.coinSell);
                updateToggle('historyToggle', data.features.history);

                renderCoinRates(data.coins || []);
                renderPayments(data.paymentMethods || []);
                document.getElementById('binanceRate').value = data.binanceRate || 125;
                document.getElementById('transferId').value = data.transferId || '';
                document.getElementById('transferUsername').value = data.transferUsername || '';
                document.getElementById('transferProfileImage').value = data.transferProfileImage || '';
                renderTransferProfilePreview(data.transferProfileImage || '');

                document.getElementById('helpLineUrl').value = data.branding?.helpLineUrl || '';
                document.getElementById('channelUrl').value = data.branding?.channelUrl || '';
                document.getElementById('tutorialVideoUrl').value = data.branding?.tutorialVideoUrl || '';
                document.getElementById('disclaimerText').value = data.branding?.disclaimer || '';
            } catch (error) {
                console.error('Error loading state:', error);
            }
        }

        function updateToggle(id, active) {
            const el = document.getElementById(id);
            if (active) el.classList.add('active'); else el.classList.remove('active');
        }

        async function toggleSystem() { await toggleEndpoint('/admin/toggle/system'); }
        async function toggleFeature(feature) { await toggleEndpoint('/admin/toggle/feature', { feature }); }

        async function toggleEndpoint(endpoint, data = {}) {
            try {
                const response = await fetch(endpoint, {
                    method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify(data)
                });
                const result = await response.json();
                if (result.ok) loadState(); else alert('Error: ' + result.error);
            } catch (error) { alert('Error: ' + error.message); }
        }

        // ---------------- Coin Rates ----------------
        function renderCoinRates(coins) {
            const box = document.getElementById('coinRatesBox');
            box.innerHTML = coins.map((c, i) => coinRowHtml(c, i)).join('');
            box.dataset.count = coins.length;
        }

        function coinRowHtml(c, i) {
            const iconHtml = c.image
                ? `<img class="coin-icon-preview" src="${c.image}">`
                : `<span style="font-size:24px">${c.icon || '🪙'}</span>`;
            return `
                <div class="coin-rate-row" data-index="${i}">
                    ${iconHtml}
                    <div class="coin-label">
                        <input type="text" class="coin-name" value="${escapeAttr(c.name || '')}" placeholder="Coin name" style="font-weight:bold">
                    </div>
                    <div><label>মূল্য (টাকা)</label><input type="number" step="0.01" class="rate-price" value="${c.price}"></div>
                    <div><label>কয়েন (per rate)</label><input type="number" step="1" class="rate-coins" value="${c.rate}"></div>
                    <div style="min-width:180px"><label>Transfer / Instagram Username</label><input type="text" class="coin-target-username" value="${escapeAttr(c.targetUsername || '')}" placeholder="e.g. instagram_username"></div>
                    <div><label>Coupon Mode</label><input type="checkbox" class="coin-requires-coupon" ${c.requiresCoupon ? 'checked' : ''}></div>
                    <div><label>সক্রিয়</label><div class="toggle-switch coin-enabled-toggle ${c.enabled ? 'active' : ''}" onclick="this.classList.toggle('active')"></div></div>
                    <div>
                        <label>আইকন ছবি</label>
                        <input type="file" accept="image/*" onchange="uploadCoinIcon(this, ${i})" style="width:120px">
                    </div>
                    <button class="btn-danger btn-small" onclick="removeCoinRow(${i})">🗑</button>
                    <input type="hidden" class="coin-id" value="${escapeAttr(c.id || '')}">
                    <input type="hidden" class="coin-icon" value="${escapeAttr(c.icon || '🪙')}">
                    <input type="hidden" class="coin-image" value="${escapeAttr(c.image || '')}">
                </div>`;
        }

        function escapeAttr(v) { return String(v).replace(/"/g, '&quot;'); }

        function collectCoins() {
            return [...document.querySelectorAll('#coinRatesBox .coin-rate-row')].map((row, i) => ({
                id: row.querySelector('.coin-id').value || ('coin' + Date.now() + i),
                name: row.querySelector('.coin-name').value || 'COIN',
                icon: row.querySelector('.coin-icon').value || '🪙',
                image: row.querySelector('.coin-image').value || '',
                price: parseFloat(row.querySelector('.rate-price').value) || 0,
                rate: parseFloat(row.querySelector('.rate-coins').value) || 1,
                unit: parseFloat(row.querySelector('.rate-coins').value) || 1000,
                targetUsername: row.querySelector('.coin-target-username') ? row.querySelector('.coin-target-username').value.trim() : '',
                requiresCoupon: row.querySelector('.coin-requires-coupon') ? row.querySelector('.coin-requires-coupon').checked : false,
                requiresUsername: !(row.querySelector('.coin-requires-coupon') && row.querySelector('.coin-requires-coupon').checked),
                enabled: row.querySelector('.coin-enabled-toggle').classList.contains('active')
            }));
        }

        function addCoinRow() {
            const coins = collectCoins();
            coins.push({ id: '', name: 'NEW COIN', icon: '🪙', image: '', price: 1, rate: 1000, unit: 1000, targetUsername: '', requiresUsername: true, requiresCoupon: false, enabled: true });
            renderCoinRates(coins);
        }

        function removeCoinRow(index) {
            const coins = collectCoins();
            coins.splice(index, 1);
            renderCoinRates(coins);
        }

        async function uploadCoinIcon(input, index) {
            const file = input.files[0];
            if (!file) return;
            const formData = new FormData();
            formData.append('icon', file);
            try {
                const response = await fetch('/admin/coins/upload-icon', {
                    method: 'POST', headers: authHeaders(), body: formData
                });
                const result = await response.json();
                if (result.ok) {
                    const coins = collectCoins();
                    coins[index].image = result.url;
                    renderCoinRates(coins);
                } else {
                    alert('Upload error: ' + result.error);
                }
            } catch (error) { alert('Upload error: ' + error.message); }
        }

        async function saveCoinRates() {
            const coins = collectCoins();
            for (const c of coins) {
                if (c.price < 0 || c.rate <= 0) { alert('মূল্য/rate সঠিক দিন'); return; }
            }
            try {
                const response = await fetch('/admin/update-coins', {
                    method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({ coins })
                });
                const result = await response.json();
                if (result.ok) { alert('✅ Coins আপডেট হয়েছে!'); loadState(); }
                else alert('Error: ' + result.error);
            } catch (error) { alert('Error: ' + error.message); }
        }

        // ---------------- Payment Methods ----------------
        function renderPayments(methods) {
            const box = document.getElementById('paymentsBox');
            box.innerHTML = methods.map((m, i) => `
                <div class="payment-row" data-index="${i}">
                    ${m.image ? `<img class="payment-image-preview" src="${escapeAttr(m.image)}">` : `<span style="font-size:26px">${m.icon || '💳'}</span>`}
                    <div><input type="text" class="pay-name" value="${escapeAttr(m.name || '')}" placeholder="Payment method name">
                    <input type="file" accept="image/*" onchange="uploadPaymentIcon(this, ${i})" style="width:145px;margin-top:5px"></div>
                    <div style="display:flex;align-items:center;gap:5px"><div class="toggle-switch coin-enabled-toggle ${m.enabled ? 'active' : ''}" onclick="this.classList.toggle('active')"></div><button class="btn-danger btn-small" onclick="removePaymentRow(${i})">🗑</button></div>
                    <input type="hidden" class="pay-id" value="${escapeAttr(m.id || '')}">
                    <input type="hidden" class="pay-image" value="${escapeAttr(m.image || '')}">
                    <input type="hidden" class="pay-icon" value="${escapeAttr(m.icon || '💳')}">
                </div>`).join('');
        }

        function collectPayments() {
            return [...document.querySelectorAll('#paymentsBox .payment-row')].map((row, i) => ({
                id: row.querySelector('.pay-id').value || ('method' + Date.now() + i),
                name: row.querySelector('.pay-name').value || 'Method',
                image: row.querySelector('.pay-image').value || '',
                icon: row.querySelector('.pay-icon').value || '💳',
                enabled: row.querySelector('.coin-enabled-toggle').classList.contains('active')
            }));
        }
        function addPaymentRow() { const methods=collectPayments(); methods.push({id:'',name:'New Method',enabled:true,image:'',icon:'💳'}); renderPayments(methods); }
        function removePaymentRow(index) { const methods=collectPayments(); methods.splice(index,1); renderPayments(methods); }
        async function uploadPaymentIcon(input,index){
            const file=input.files[0]; if(!file)return; const fd=new FormData(); fd.append('icon',file);
            try{const r=await fetch('/admin/payments/upload-icon',{method:'POST',headers:authHeaders(),body:fd}); const d=await r.json(); if(!d.ok)throw new Error(d.error); const m=collectPayments(); m[index].image=d.url; renderPayments(m);}catch(e){alert('Upload error: '+e.message);}
        }
        async function savePayments() {
            try { const response=await fetch('/admin/update-payments',{method:'POST',headers:authHeaders({'Content-Type':'application/json'}),body:JSON.stringify({paymentMethods:collectPayments()})}); const result=await response.json(); if(result.ok){alert('✅ Payment methods আপডেট হয়েছে!');loadState();}else alert('Error: '+result.error); } catch(e){alert('Error: '+e.message);}
        }
        async function saveBinanceRate(){
            const rate=parseFloat(document.getElementById('binanceRate').value); if(!(rate>0)){alert('সঠিক Binance rate দিন');return;}
            try{const r=await fetch('/admin/update-binance-rate',{method:'POST',headers:authHeaders({'Content-Type':'application/json'}),body:JSON.stringify({binanceRate:rate})});const d=await r.json();if(d.ok){alert('✅ Binance rate saved');loadState();}else alert('Error: '+d.error);}catch(e){alert('Error: '+e.message);}
        }

        function renderTransferProfilePreview(url){
            const box=document.getElementById('transferProfilePreview');
            if(!box)return;
            box.innerHTML=url ? `<img src="${escapeAttr(url)}" style="width:70px;height:70px;border-radius:50%;object-fit:cover;border:2px solid #31b8f4">` : '<span class="small-note">No profile picture</span>';
        }
        document.addEventListener('change', async function(e){
            if(e.target && e.target.id==='transferProfileImageFile'){
                const file=e.target.files[0]; if(!file)return;
                const fd=new FormData(); fd.append('image',file);
                try{const r=await fetch('/admin/transfer-profile/upload',{method:'POST',headers:authHeaders(),body:fd});const d=await r.json();if(!d.ok)throw new Error(d.error);document.getElementById('transferProfileImage').value=d.url;renderTransferProfilePreview(d.url);alert('✅ Profile picture uploaded');}
                catch(err){alert('Upload error: '+err.message);}
            }
        });
        async function saveTransferSettings(){
            const transferId=document.getElementById('transferId').value.trim();
            const transferUsername=document.getElementById('transferUsername').value.trim();
            const transferProfileImage=document.getElementById('transferProfileImage').value.trim();
            try{const r=await fetch('/admin/update-transfer-settings',{method:'POST',headers:authHeaders({'Content-Type':'application/json'}),body:JSON.stringify({transferId,transferUsername,transferProfileImage})});const d=await r.json();if(d.ok){alert('✅ Transfer account saved');loadState();}else alert('Error: '+d.error);}catch(e){alert('Error: '+e.message);}
        }
        function showSection(name){ document.querySelectorAll('.manage-section').forEach(x=>x.classList.toggle('active',x.dataset.section===name)); document.querySelectorAll('.admin-nav button').forEach(b=>b.classList.toggle('active',b.getAttribute('onclick')===`showSection('${name}')`)); window.scrollTo({top:0,behavior:'smooth'}); }

        // ---------------- Branding ----------------
        async function saveBranding() {
            const payload = {
                helpLineUrl: document.getElementById('helpLineUrl').value,
                channelUrl: document.getElementById('channelUrl').value,
                tutorialVideoUrl: document.getElementById('tutorialVideoUrl').value,
                disclaimer: document.getElementById('disclaimerText').value
            };
            try {
                const response = await fetch('/admin/update-branding', {
                    method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify(payload)
                });
                const result = await response.json();
                if (result.ok) alert('✅ Branding সেভ হয়েছে!'); else alert('Error: ' + result.error);
            } catch (error) { alert('Error: ' + error.message); }
        }

        // ---------------- Orders ----------------
        async function loadOrders(status) {
            const box = document.getElementById('ordersBox');
            box.innerHTML = '<p class="small-note">Loading...</p>';
            try {
                const url = '/admin/orders' + (status ? ('?status=' + status) : '');
                const response = await fetch(url, { headers: authHeaders() });
                const data = await response.json();
                if (!data.ok) { box.innerHTML = '<p class="small-note">Error: ' + data.error + '</p>'; return; }
                if (!data.orders.length) { box.innerHTML = '<p class="small-note">কোনো অর্ডার নেই।</p>'; return; }
                box.innerHTML = data.orders.map(orderCardHtml).join('');
            } catch (error) { box.innerHTML = '<p class="small-note">Error: ' + error.message + '</p>'; }
        }

        function orderCardHtml(o) {
            const statusClass = o.status === 'approved' ? 'status-approved' : o.status === 'rejected' ? 'status-rejected' : 'status-pending';
            const img = o.screenshot_url ? `<img src="${o.screenshot_url}">` : '';
            const actions = o.status === 'pending' ? `
                <button class="btn-success btn-small" onclick="decideOrder('${o.id}','approve')">✅ Approve</button>
                <button class="btn-danger btn-small" onclick="decideOrder('${o.id}','reject')">❌ Reject</button>` : '';
            return `
                <div class="order-card">
                    <div class="order-meta">
                        <strong>${o.coin}</strong> — ${o.quantity} কয়েন — <strong>${o.total_amount} টাকা</strong>
                        <span class="order-status ${statusClass}">${o.status}</span><br>
                        User: @${o.username || '—'} (ID: ${o.user_id})<br>
                        Instagram: ${o.instagram_username || '—'}<br>
                        Payment: ${o.payment_method || '—'} → ${o.account_number || '—'}<br>
                        Coupon: ${o.coupon_code || '—'}<br>
                        Time: ${o.timestamp || '—'}
                    </div>
                    ${img}
                    ${actions}
                </div>`;
        }

        async function decideOrder(orderId, action) {
            try {
                const response = await fetch(`/admin/orders/${orderId}/${action}`, {
                    method: 'POST', headers: authHeaders()
                });
                const result = await response.json();
                if (result.ok) { loadOrders('pending'); loadState(); }
                else alert('Error: ' + result.error);
            } catch (error) { alert('Error: ' + error.message); }
        }

        // ---------------- Users ----------------
        async function loadUsers() {
            const box = document.getElementById('usersBox');
            box.innerHTML = '<p class="small-note">Loading...</p>';
            const q = document.getElementById('userSearch').value.trim();
            try {
                const response = await fetch('/admin/users' + (q ? ('?q=' + encodeURIComponent(q)) : ''), { headers: authHeaders() });
                const data = await response.json();
                if (!data.ok) { box.innerHTML = '<p class="small-note">Error: ' + data.error + '</p>'; return; }
                if (!data.users.length) { box.innerHTML = '<p class="small-note">কোনো user পাওয়া যায়নি।</p>'; return; }
                box.innerHTML = data.users.map(userRowHtml).join('');
            } catch (error) { box.innerHTML = '<p class="small-note">Error: ' + error.message + '</p>'; }
        }

        function userRowHtml(u) {
            const blockBtn = u.blocked
                ? `<button class="btn-success btn-small" onclick="unblockUser('${u.id}')">Unblock</button>`
                : `<button class="btn-danger btn-small" onclick="blockUser('${u.id}')">Block</button>`;
            return `
                <div class="user-row">
                    <div class="user-info">
                        @${u.username || '—'} (ID: ${u.id})${u.blocked ? ' <span class="order-status status-rejected">BLOCKED</span>' : ''}
                    </div>
                    <div class="user-actions">
                        ${blockBtn}
                        <button class="btn-primary btn-small" onclick="promptCustomRate('${u.id}')">Set Custom Rate</button>
                    </div>
                </div>`;
        }

        async function blockUser(uid) { await userAction(uid, 'block'); }
        async function unblockUser(uid) { await userAction(uid, 'unblock'); }

        async function userAction(uid, action) {
            try {
                const response = await fetch(`/admin/users/${uid}/${action}`, { method: 'POST', headers: authHeaders() });
                const result = await response.json();
                if (result.ok) loadUsers(); else alert('Error: ' + result.error);
            } catch (error) { alert('Error: ' + error.message); }
        }

        function promptCustomRate(uid) {
            const coinId = prompt('কোন coin-এর জন্য special rate দিতে চান? (coin id লিখুন, যেমন: top)');
            if (!coinId) return;
            const price = prompt('বিশেষ মূল্য (টাকা):');
            if (price === null) return;
            const rate = prompt('বিশেষ কয়েন সংখ্যা (per rate):');
            if (rate === null) return;
            setCustomRate(uid, coinId, parseFloat(price), parseFloat(rate));
        }

        async function setCustomRate(uid, coinId, price, rate) {
            try {
                const response = await fetch(`/admin/users/${uid}/set-rate`, {
                    method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({ coin_id: coinId, price, rate })
                });
                const result = await response.json();
                if (result.ok) alert('✅ Custom rate সেট হয়েছে!'); else alert('Error: ' + result.error);
            } catch (error) { alert('Error: ' + error.message); }
        }

        // ---------------- Broadcast ----------------
        async function sendBroadcast() {
            const text = document.getElementById('broadcastText').value.trim();
            if (!text) { alert('মেসেজ লিখুন'); return; }
            if (!confirm('সব ইউজারকে এই মেসেজ পাঠাতে চান?')) return;
            try {
                const response = await fetch('/admin/broadcast', {
                    method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({ message: text })
                });
                const result = await response.json();
                if (result.ok) {
                    document.getElementById('broadcastResult').textContent = `পাঠানো হয়েছে: ${result.sent} জনকে, ব্যর্থ: ${result.failed}`;
                } else alert('Error: ' + result.error);
            } catch (error) { alert('Error: ' + error.message); }
        }

        // Initial load
        loadState();
        loadOrders('pending');
        loadUsers();
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
    """Get current state of all toggles + coins + payments + branding + stats"""
    if not is_admin_request():
        return admin_denied()

    try:
        system_status = {"enabled": True}
        features = {"xr7Task": True, "coinSell": True, "history": False, "tutorial": False}
        coins = DEFAULT_COINS
        payment_methods = DEFAULT_PAYMENT_METHODS
        branding = DEFAULT_BRANDING
        binance_rate = 125.0
        transfer_id = ''
        transfer_username = ''
        transfer_profile_image = ''
        users_count = orders_count = pending_count = blocked_count = 0

        if db:
            status_doc = db.collection("system").document("status").get()
            if status_doc.exists:
                system_status = status_doc.to_dict()

            features_doc = db.collection("system").document("features").get()
            if features_doc.exists:
                features.update(features_doc.to_dict())

            coins_doc = db.collection("system").document("coins").get()
            if coins_doc.exists and coins_doc.to_dict().get("list"):
                coins = coins_doc.to_dict()["list"]

            payments_doc = db.collection("system").document("payments").get()
            if payments_doc.exists and payments_doc.to_dict().get("list"):
                payment_methods = payments_doc.to_dict()["list"]
            config_doc = db.collection("system").document("config").get()
            if config_doc.exists:
                cfg = config_doc.to_dict() or {}
                try: binance_rate = float(cfg.get("binanceRate", 125.0) or 125.0)
                except Exception: pass
                transfer_id = str(cfg.get("transferId", "") or "")
                transfer_username = str(cfg.get("transferUsername", "") or "")
                transfer_profile_image = str(cfg.get("transferProfileImage", "") or "")

            branding_doc = db.collection("system").document("branding").get()
            if branding_doc.exists:
                branding = {**DEFAULT_BRANDING, **branding_doc.to_dict()}

            users = list(db.collection("users").stream())
            users_count = len(users)
            blocked_count = sum(1 for u in users if u.to_dict().get("blocked"))

            orders = list(db.collection("orders").stream())
            orders_count = len(orders)
            pending_count = sum(1 for o in orders if o.to_dict().get("status", "pending") == "pending")

        return jsonify({
            "ok": True,
            "status": system_status,
            "features": features,
            "coins": coins,
            "paymentMethods": payment_methods,
            "binanceRate": binance_rate,
            "transferId": transfer_id,
            "transferUsername": transfer_username,
            "transferProfileImage": transfer_profile_image,
            "branding": branding,
            "stats": {
                "users": users_count,
                "orders": orders_count,
                "pending": pending_count,
                "blocked": blocked_count,
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@panel.post("/toggle/system")
def toggle_system():
    if not is_admin_request():
        return admin_denied()
    try:
        if not db:
            return jsonify({"ok": False, "error": "Database not connected"}), 500
        status_doc = db.collection("system").document("status").get()
        current_status = status_doc.to_dict() if status_doc.exists else {"enabled": True}
        new_status = not current_status.get("enabled", True)
        db.collection("system").document("status").set({"enabled": new_status})
        return jsonify({"ok": True, "enabled": new_status})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@panel.post("/toggle/feature")
def toggle_feature():
    if not is_admin_request():
        return admin_denied()
    try:
        data = request.get_json() or {}
        feature = data.get("feature")
        if not feature or not db:
            return jsonify({"ok": False, "error": "Invalid request"}), 400
        features_doc = db.collection("system").document("features").get()
        features = features_doc.to_dict() if features_doc.exists else {}
        features[feature] = not features.get(feature, True)
        db.collection("system").document("features").set(features)
        return jsonify({"ok": True, "feature": feature, "enabled": features[feature]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# COIN MANAGEMENT (rate/price, add/remove, icon upload)
# ============================================================
@panel.post("/update-coins")
def update_coins():
    if not is_admin_request():
        return admin_denied()
    try:
        data = request.get_json() or {}
        coins = data.get("coins")
        if not isinstance(coins, list):
            return jsonify({"ok": False, "error": "Invalid coins data"}), 400

        clean_coins = []
        for c in coins:
            price = float(c.get("price", 0))
            rate = float(c.get("rate", 1))
            if price < 0 or rate <= 0:
                return jsonify({"ok": False, "error": "Price/rate must be positive"}), 400
            clean_coins.append({
                "id": str(c.get("id") or f"coin{len(clean_coins)}")[:40],
                "name": str(c.get("name", "COIN"))[:60],
                "icon": str(c.get("icon", "🪙"))[:8],
                "image": str(c.get("image", ""))[:300],
                "price": price,
                "rate": rate,
                "unit": float(c.get("unit", rate) or rate),
                "targetUsername": str(c.get("targetUsername", ""))[:120],
                "requiresUsername": bool(c.get("requiresUsername", not bool(c.get("requiresCoupon", False)))),
                "requiresCoupon": bool(c.get("requiresCoupon", False)),
                "enabled": bool(c.get("enabled", True)),
            })

        if not db:
            return jsonify({"ok": False, "error": "Database not connected"}), 500
        db.collection("system").document("coins").set({"list": clean_coins})
        return jsonify({"ok": True, "coins": clean_coins})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@panel.post("/coins/upload-icon")
def upload_coin_icon():
    if not is_admin_request():
        return admin_denied()
    try:
        import bot as bot_module  # lazy import to avoid circular import at startup
        file_storage = request.files.get("icon")
        url = bot_module.save_upload(file_storage, bot_module.COINS_UPLOAD_DIR)
        if not url:
            return jsonify({"ok": False, "error": "Invalid image file"}), 400
        return jsonify({"ok": True, "url": url})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# PAYMENT METHODS MANAGEMENT
# ============================================================
@panel.post("/update-payments")
def update_payments():
    if not is_admin_request():
        return admin_denied()
    try:
        data = request.get_json() or {}
        methods = data.get("paymentMethods")
        if not isinstance(methods, list):
            return jsonify({"ok": False, "error": "Invalid payment methods data"}), 400

        clean_methods = []
        for m in methods:
            clean_methods.append({
                "id": str(m.get("id") or f"method{len(clean_methods)}")[:40],
                "name": str(m.get("name", "Method"))[:60],
                "enabled": bool(m.get("enabled", True)),
                "image": str(m.get("image", ""))[:500],
                "icon": str(m.get("icon", "💳"))[:20],
            })

        if not db:
            return jsonify({"ok": False, "error": "Database not connected"}), 500
        db.collection("system").document("payments").set({"list": clean_methods})
        return jsonify({"ok": True, "paymentMethods": clean_methods})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500



@panel.post("/update-binance-rate")
def update_binance_rate():
    if not is_admin_request(): return admin_denied()
    try:
        rate=float((request.get_json() or {}).get("binanceRate",0))
        if rate<=0: return jsonify({"ok":False,"error":"Invalid Binance rate"}),400
        if not db: return jsonify({"ok":False,"error":"Database not connected"}),500
        db.collection("system").document("config").set({"binanceRate":rate}, merge=True)
        return jsonify({"ok":True,"binanceRate":rate})
    except Exception as e: return jsonify({"ok":False,"error":str(e)}),500

@panel.post("/payments/upload-icon")
def upload_payment_icon():
    if not is_admin_request(): return admin_denied()
    try:
        import bot as bot_module
        url=bot_module.save_upload(request.files.get("icon"), bot_module.PAYMENTS_UPLOAD_DIR)
        if not url: return jsonify({"ok":False,"error":"Invalid image file"}),400
        return jsonify({"ok":True,"url":url})
    except Exception as e: return jsonify({"ok":False,"error":str(e)}),500

# ============================================================
# BRANDING (links, disclaimer, tutorial video)
# ============================================================
@panel.post("/transfer-profile/upload")
def upload_transfer_profile():
    if not is_admin_request(): return admin_denied()
    try:
        import bot as bot_module
        url = bot_module.save_upload(request.files.get("image"), bot_module.PAYMENTS_UPLOAD_DIR)
        if not url: return jsonify({"ok": False, "error": "Invalid image file"}), 400
        return jsonify({"ok": True, "url": url})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@panel.post("/update-transfer-settings")
def update_transfer_settings():
    if not is_admin_request(): return admin_denied()
    try:
        data = request.get_json(silent=True) or {}
        values = {
            "transferId": str(data.get("transferId", "") or "").strip()[:120],
            "transferUsername": str(data.get("transferUsername", "") or "").strip()[:120],
            "transferProfileImage": str(data.get("transferProfileImage", "") or "").strip()[:500],
        }
        if not db: return jsonify({"ok": False, "error": "Database not connected"}), 500
        db.collection("system").document("config").set(values, merge=True)
        return jsonify({"ok": True, **values})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@panel.post("/update-transfer-id")
def update_transfer_id():
    if not is_admin_request(): return admin_denied()
    try:
        transfer_id = str((request.get_json() or {}).get("transferId", "") or "").strip()[:120]
        if not db: return jsonify({"ok": False, "error": "Database not connected"}), 500
        db.collection("system").document("config").set({"transferId": transfer_id}, merge=True)
        return jsonify({"ok": True, "transferId": transfer_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@panel.post("/update-branding")
def update_branding():
    if not is_admin_request():
        return admin_denied()
    try:
        data = request.get_json() or {}
        branding = {
            "helpLineUrl": str(data.get("helpLineUrl", ""))[:300],
            "channelUrl": str(data.get("channelUrl", ""))[:300],
            "tutorialVideoUrl": str(data.get("tutorialVideoUrl", ""))[:300],
            "disclaimer": str(data.get("disclaimer", ""))[:2000],
        }
        if not db:
            return jsonify({"ok": False, "error": "Database not connected"}), 500
        db.collection("system").document("branding").set(branding)
        return jsonify({"ok": True, "branding": branding})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# ORDERS (approve / reject / list)
# ============================================================
@panel.get("/orders")
def list_orders():
    if not is_admin_request():
        return admin_denied()
    try:
        if not db:
            return jsonify({"ok": True, "orders": []})
        status_filter = request.args.get("status", "")
        query = db.collection("orders")
        docs = list(query.stream())
        orders = []
        for doc in docs:
            d = doc.to_dict()
            d["id"] = doc.id
            d.setdefault("status", "pending")
            if status_filter and d["status"] != status_filter:
                continue
            orders.append(d)
        orders.sort(key=lambda o: o.get("timestamp") or "", reverse=True)
        return jsonify({"ok": True, "orders": orders[:30]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@panel.post("/orders/<order_id>/approve")
def approve_order(order_id):
    if not is_admin_request():
        return admin_denied()
    import bot as bot_module
    result = bot_module.process_order_decision(order_id, "approved")
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@panel.post("/orders/<order_id>/reject")
def reject_order(order_id):
    if not is_admin_request():
        return admin_denied()
    import bot as bot_module
    result = bot_module.process_order_decision(order_id, "rejected")
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


# ============================================================
# USER MANAGEMENT (block/unblock, custom rate)
# ============================================================
@panel.get("/users")
def list_users():
    if not is_admin_request():
        return admin_denied()
    try:
        if not db:
            return jsonify({"ok": True, "users": []})
        q = request.args.get("q", "").strip().lower()
        docs = list(db.collection("users").stream())
        users = []
        for doc in docs:
            d = doc.to_dict()
            d["id"] = doc.id
            if q and q not in str(d.get("username", "")).lower() and q not in str(d.get("telegram_id", "")):
                continue
            users.append(d)
        users.sort(key=lambda u: u.get("updated_at") or "", reverse=True)
        return jsonify({"ok": True, "users": users[:50]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@panel.post("/users/<uid>/block")
def block_user(uid):
    if not is_admin_request():
        return admin_denied()
    if not db:
        return jsonify({"ok": False, "error": "Database not connected"}), 500
    db.collection("users").document(uid).set({"blocked": True}, merge=True)
    return jsonify({"ok": True})


@panel.post("/users/<uid>/unblock")
def unblock_user(uid):
    if not is_admin_request():
        return admin_denied()
    if not db:
        return jsonify({"ok": False, "error": "Database not connected"}), 500
    db.collection("users").document(uid).set({"blocked": False}, merge=True)
    return jsonify({"ok": True})


@panel.post("/users/<uid>/set-rate")
def set_user_rate(uid):
    if not is_admin_request():
        return admin_denied()
    try:
        data = request.get_json() or {}
        coin_id = str(data.get("coin_id", "")).strip()
        if not coin_id:
            return jsonify({"ok": False, "error": "coin_id required"}), 400
        price = float(data.get("price", 0))
        rate = float(data.get("rate", 1))
        if price < 0 or rate <= 0:
            return jsonify({"ok": False, "error": "Price/rate must be positive"}), 400
        if not db:
            return jsonify({"ok": False, "error": "Database not connected"}), 500

        user_ref = db.collection("users").document(uid)
        user_doc = user_ref.get()
        custom_rates = user_doc.to_dict().get("custom_rates", {}) if user_doc.exists else {}
        custom_rates[coin_id] = {"price": price, "rate": rate}
        user_ref.set({"custom_rates": custom_rates}, merge=True)
        return jsonify({"ok": True, "custom_rates": custom_rates})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# BROADCAST
# ============================================================
@panel.post("/broadcast")
def broadcast():
    if not is_admin_request():
        return admin_denied()
    try:
        data = request.get_json() or {}
        text = str(data.get("message", "")).strip()
        if not text:
            return jsonify({"ok": False, "error": "Message required"}), 400
        import bot as bot_module
        sent, failed = bot_module.send_broadcast(text)
        return jsonify({"ok": True, "sent": sent, "failed": failed})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# LEGACY ENDPOINT
# ============================================================
@panel.get("/summary")
def summary():
    if not is_admin_request():
        return admin_denied()
    if not db:
        return jsonify({"ok": True, "firebase": False})
    try:
        users_count = len(list(db.collection("users").stream()))
        orders_count = len(list(db.collection("orders").stream()))
        return jsonify({"ok": True, "firebase": True, "users": users_count, "orders": orders_count})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
