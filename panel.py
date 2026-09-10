from flask import Blueprint, jsonify, request, render_template_string

ADMIN_IDS = {7294314847}
DEFAULT_BINANCE_RATE = 125.0

DEFAULT_COINS = [
    {"id":"niva","name":"NIVA COIN","icon":"🪙","image":"","price":5.0,"rate":1000,"unit":1000,"requiresUsername":True,"requiresCoupon":False,"targetUsername":"","targetImage":"","enabled":True},
    {"id":"ns","name":"NS COIN","icon":"👤","image":"","price":5.0,"rate":1000,"unit":1000,"requiresUsername":True,"requiresCoupon":False,"targetUsername":"","targetImage":"","enabled":True},
    {"id":"newtopfollow","name":"NEW TOP FOLLOW","icon":"✨","image":"","price":5.0,"rate":1000,"unit":1000,"requiresUsername":True,"requiresCoupon":False,"targetUsername":"","targetImage":"","enabled":True},
    {"id":"topfollow","name":"TOP FOLLOW","icon":"💗","image":"","price":5.0,"rate":1000,"unit":1000,"requiresUsername":False,"requiresCoupon":True,"targetUsername":"","targetImage":"","enabled":True},
]
DEFAULT_PAYMENT_METHODS = [
    {"id":"bkash","name":"bKash","icon":"💳","image":"","enabled":True},
    {"id":"nagad","name":"Nagad","icon":"💳","image":"","enabled":True},
    {"id":"rocket","name":"Rocket","icon":"💳","image":"","enabled":True},
    {"id":"binance","name":"Binance","icon":"🔶","image":"","enabled":True},
    {"id":"other","name":"Other","icon":"💳","image":"","enabled":True},
]
DEFAULT_TRANSFER = {"transferId":"","transferUsername":"","transferProfileImage":""}
DEFAULT_BRANDING = {"helpLineUrl":"https://t.me/Sapportotp","channelUrl":"https://t.me/yourchannel","disclaimer":"","tutorialVideoUrl":""}

db = None

def set_database(database):
    global db
    db = database

panel = Blueprint("panel", __name__, url_prefix="/admin")

def is_admin_request():
    uid = request.headers.get("X-Telegram-User-Id", "") or request.args.get("uid", "")
    return uid.isdigit() and int(uid) in ADMIN_IDS

def denied():
    return jsonify({"ok":False,"error":"Admin access required"}), 403

def esc(v):
    return str(v or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"','&quot;').replace("'","&#039;")

ADMIN_HTML = r'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>NIVA ADMIN</title>
<style>
*{box-sizing:border-box}body{margin:0;padding:14px;background:linear-gradient(135deg,#1e3c72,#2a5298);color:#fff;font-family:Arial,sans-serif}.wrap{max-width:850px;margin:auto}h1{text-align:center;color:#ffd700;margin:6px 0 16px}.nav{display:grid;grid-template-columns:1fr 1fr;gap:8px;position:sticky;top:5px;z-index:20}.nav button{border:1px solid #ffffff33;border-radius:10px;background:#ffffff18;color:#fff;padding:12px;font-weight:800}.nav button.active{background:#4773ef;box-shadow:0 0 15px #4773ef88}.section{display:none;background:#ffffff12;padding:15px;border-radius:14px;margin-top:12px}.section.active{display:block}.stats{display:grid;grid-template-columns:1fr 1fr;gap:8px}.stat{background:#ffffff12;border-radius:12px;padding:16px;text-align:center}.stat b{font-size:28px;color:#ffd700;display:block}.row{background:#ffffff0d;border-radius:12px;padding:12px;margin:9px 0}.coin{display:grid;grid-template-columns:54px 1fr 82px 90px;gap:8px;align-items:end}.preview{width:50px;height:50px;border-radius:12px;object-fit:cover;background:#fff;display:grid;place-items:center;font-size:25px}.field label{font-size:10px;opacity:.8;display:block;margin-bottom:3px}.field input,.full{width:100%;padding:9px;border:0;border-radius:8px}.toggle{width:48px;height:25px;border-radius:20px;background:#777;cursor:pointer;position:relative}.toggle.on{background:#22c55e}.toggle:after{content:'';position:absolute;width:17px;height:17px;border-radius:50%;background:#fff;top:4px;left:4px}.toggle.on:after{left:27px}.payment{display:grid;grid-template-columns:58px 1fr auto auto;gap:8px;align-items:center}.actions button,button{cursor:pointer;border:0;border-radius:8px;padding:9px 12px;font-weight:700}.blue{background:#4169e1;color:#fff}.green{background:#22c55e;color:#fff}.red{background:#dc143c;color:#fff}.yellow{background:#ffd43b;color:#111}.preview.round{border-radius:50%}.order{border-left:3px solid #ffd700}.small{font-size:12px;opacity:.8}.order img{max-width:100%;max-height:260px;border-radius:8px;margin-top:8px}.transfer-card{background:#ffffff0d;border-radius:12px;padding:12px}.transfer-card img{width:76px;height:76px;border-radius:50%;object-fit:cover;display:none;border:2px solid #31b8f4;margin:8px 0}.spacer{height:4px}@media(max-width:600px){.coin{grid-template-columns:50px 1fr 78px}.coin .target{grid-column:1/-1}.payment{grid-template-columns:52px 1fr auto}.payment .file{grid-column:2/-1}.nav button{font-size:12px}}
</style></head><body><div class="wrap"><h1>👨‍💼 NIVA ADMIN PANEL</h1>
<div class="nav"><button onclick="show('dashboard')">📊 Dashboard</button><button onclick="show('orders')">📋 Orders</button><button onclick="show('users')">👥 Users</button><button onclick="show('coins')">🪙 Coin Management</button><button onclick="show('payments')">💰 Payment Methods</button><button onclick="show('transfer')">👤 Transfer Settings</button><button onclick="show('branding')">🎨 Branding</button><button onclick="show('broadcast')">📢 Broadcast</button></div>
<section id="dashboard" class="section active"><h2>📊 Dashboard</h2><div class="stats"><div class="stat"><b id="usersCount">0</b>Users</div><div class="stat"><b id="ordersCount">0</b>Orders</div><div class="stat"><b id="pendingCount">0</b>Pending</div><div class="stat"><b id="blockedCount">0</b>Blocked</div></div><div class="row"><b>System Status</b><div id="systemToggle" class="toggle" onclick="toggleSystem()"></div></div><div class="row"><b>Coin Selling</b><div id="coinToggle" class="toggle" onclick="toggleFeature('coinSell')"></div></div></section>
<section id="orders" class="section"><h2>📋 Orders</h2><button class="blue" onclick="loadOrders('pending')">Pending</button><button class="blue" onclick="loadOrders('')">All</button><div id="ordersBox"></div></section>
<section id="users" class="section"><h2>👥 Users</h2><input class="full" id="userSearch" placeholder="Username / Telegram ID"><button class="blue" onclick="loadUsers()">Search</button><div id="usersBox"></div></section>
<section id="coins" class="section"><h2>🪙 Coin Management</h2><div id="coinsBox"></div><button class="blue" onclick="addCoin()">➕ Add Coin</button><button class="green" onclick="saveCoins()">💾 Save Coins</button></section>
<section id="payments" class="section"><h2>💰 Payment Methods</h2><div class="row"><label>Binance rate: 1 USDT = BDT</label><input class="full" type="number" id="binanceRate" step="0.01"><button class="green" onclick="saveBinanceRate()">Save Rate</button></div><div id="paymentsBox"></div><button class="blue" onclick="addPayment()">➕ Add Payment</button><button class="green" onclick="savePayments()">💾 Save</button></section>
<section id="transfer" class="section"><h2>👤 Transfer / Instagram Profile</h2><div class="transfer-card"><label>Transfer ID</label><input class="full" id="transferId" placeholder="এখানে Transfer ID দিন"><div class="spacer"></div><label>Instagram / Transfer Username</label><input class="full" id="transferUsername" placeholder="@username"><div class="spacer"></div><label>Profile Picture</label><input type="file" id="transferFile" accept="image/*" onchange="uploadTransfer(this)"><img id="transferPreview"><input type="hidden" id="transferImage"><button class="green" onclick="saveTransfer()">💾 Save Transfer Settings</button></div></section>
<section id="branding" class="section"><h2>🎨 Branding</h2><label>Help Line</label><input class="full" id="helpLineUrl"><label>Channel</label><input class="full" id="channelUrl"><label>Tutorial</label><input class="full" id="tutorialVideoUrl"><label>Disclaimer</label><textarea class="full" id="disclaimer"></textarea><button class="green" onclick="saveBranding()">Save</button></section>
<section id="broadcast" class="section"><h2>📢 Broadcast</h2><textarea class="full" id="broadcastText" placeholder="Message"></textarea><button class="blue" onclick="broadcast()">Send to All</button><p id="broadcastResult"></p></section></div>
<script>
const uid=new URLSearchParams(location.search).get('uid');const H=x=>Object.assign({'X-Telegram-User-Id':uid},x||{});let state={coins:[],payments:[]};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
function show(id){document.querySelectorAll('.section').forEach(x=>x.classList.toggle('active',x.id===id));document.querySelectorAll('.nav button').forEach((b,i)=>b.classList.toggle('active',b.textContent.toLowerCase().includes(id==='coins'?'coin':id)));window.scrollTo(0,0)}
function setToggle(id,on){document.getElementById(id)?.classList.toggle('on',!!on)}
async function loadState(){try{let r=await fetch('/admin/state',{headers:H()});let d=await r.json();if(!d.ok)return alert(d.error);state.coins=d.coins||[];state.payments=d.paymentMethods||[];usersCount.textContent=d.stats.users||0;ordersCount.textContent=d.stats.orders||0;pendingCount.textContent=d.stats.pending||0;blockedCount.textContent=d.stats.blocked||0;setToggle('systemToggle',d.status.enabled);setToggle('coinToggle',d.features.coinSell);binanceRate.value=d.binanceRate||125;transferId.value=d.transfer?.transferId||'';transferUsername.value=d.transfer?.transferUsername||'';transferImage.value=d.transfer?.transferProfileImage||'';if(d.transfer?.transferProfileImage){transferPreview.src=d.transfer.transferProfileImage;transferPreview.style.display='block'}helpLineUrl.value=d.branding?.helpLineUrl||'';channelUrl.value=d.branding?.channelUrl||'';tutorialVideoUrl.value=d.branding?.tutorialVideoUrl||'';disclaimer.value=d.branding?.disclaimer||'';renderCoins();renderPayments()}catch(e){alert('Admin load failed: '+e.message)}}
async function toggleSystem(){await post('/admin/toggle/system',{})}async function toggleFeature(f){await post('/admin/toggle/feature',{feature:f})}
async function post(url,body){try{let r=await fetch(url,{method:'POST',headers:H({'Content-Type':'application/json'}),body:JSON.stringify(body)});let d=await r.json();if(!d.ok)alert(d.error);else loadState();return d}catch(e){alert(e.message)}}
function renderCoins(){coinsBox.innerHTML=state.coins.map((c,i)=>`<div class="row coin" data-i="${i}"><div>${c.image?`<img class="preview" src="${esc(c.image)}">`:`<div class="preview">${esc(c.icon||'🪙')}</div>`}</div><div class="field"><label>Name</label><input class="cname" value="${esc(c.name)}"></div><div class="field"><label>Price</label><input class="cprice" type="number" step="0.01" value="${c.price}"></div><div class="field"><label>Per rate</label><input class="crate" type="number" value="${c.rate}"></div><div class="field target"><label>Instagram/Transfer Username</label><input class="ctarget" value="${esc(c.targetUsername||'')}"></div><div class="file target"><label>Profile Picture</label><input type="file" accept="image/*" onchange="uploadCoinTarget(this,${i})"><input type="hidden" class="ctargetimage" value="${esc(c.targetImage||'')}"></div><div class="field"><label>Active</label><div class="toggle ${c.enabled?'on':''} ctoggle"></div></div><div class="file"><label>Coin Picture</label><input type="file" accept="image/*" onchange="uploadCoin(this,${i})"></div><button class="red" onclick="removeCoin(${i})">🗑</button><input type="hidden" class="cid" value="${esc(c.id)}"><input type="hidden" class="cicon" value="${esc(c.icon||'🪙')}"><input type="hidden" class="cimage" value="${esc(c.image||'')}"><input type="hidden" class="ccoupon" value="${c.requiresCoupon?'1':'0'}"></div>`).join('')}
function collectCoins(){return [...document.querySelectorAll('#coinsBox .coin')].map((r,i)=>({id:r.querySelector('.cid').value||'coin'+Date.now()+i,name:r.querySelector('.cname').value||'COIN',icon:r.querySelector('.cicon').value||'🪙',image:r.querySelector('.cimage').value||'',price:+r.querySelector('.cprice').value||0,rate:+r.querySelector('.crate').value||1000,unit:+r.querySelector('.crate').value||1000,targetUsername:r.querySelector('.ctarget').value.trim(),targetImage:r.querySelector('.ctargetimage')?.value||'',requiresUsername:true,requiresCoupon:r.querySelector('.ccoupon').value==='1',enabled:r.querySelector('.ctoggle').classList.contains('on')}))}
function addCoin(){state.coins.push({id:'',name:'NEW COIN',icon:'🪙',image:'',price:1,rate:1000,unit:1000,targetUsername:'',requiresUsername:true,requiresCoupon:false,enabled:true});renderCoins()}function removeCoin(i){state.coins=collectCoins();state.coins.splice(i,1);renderCoins()}
async function uploadCoin(input,i){let f=input.files[0];if(!f)return;let fd=new FormData();fd.append('icon',f);try{let r=await fetch('/admin/coins/upload-icon',{method:'POST',headers:H(),body:fd});let d=await r.json();if(!d.ok)throw Error(d.error);state.coins=collectCoins();state.coins[i].image=d.url;renderCoins()}catch(e){alert('Coin image upload failed: '+e.message)}}
async function uploadCoinTarget(input,i){let f=input.files[0];if(!f)return;let fd=new FormData();fd.append('photo',f);try{let r=await fetch('/admin/coins/upload-target-profile',{method:'POST',headers:H(),body:fd});let d=await r.json();if(!d.ok)throw Error(d.error);state.coins=collectCoins();state.coins[i].targetImage=d.url;renderCoins()}catch(e){alert('Profile upload failed: '+e.message)}}
async function saveCoins(){state.coins=collectCoins();await post('/admin/update-coins',{coins:state.coins})}
function renderPayments(){paymentsBox.innerHTML=state.payments.map((m,i)=>`<div class="row payment"><div>${m.image?`<img class="preview" src="${esc(m.image)}">`:`<div class="preview">${esc(m.icon||'💳')}</div>`}</div><input class="pname" value="${esc(m.name)}"><div class="toggle ${m.enabled?'on':''} ptoggle"></div><div class="file"><input type="file" accept="image/*" onchange="uploadPayment(this,${i})"></div><button class="red" onclick="removePayment(${i})">🗑</button><input type="hidden" class="pid" value="${esc(m.id)}"><input type="hidden" class="picon" value="${esc(m.icon||'💳')}"><input type="hidden" class="pimage" value="${esc(m.image||'')}"></div>`).join('')}
function collectPayments(){return [...document.querySelectorAll('#paymentsBox .payment')].map((r,i)=>({id:r.querySelector('.pid').value||'method'+Date.now()+i,name:r.querySelector('.pname').value||'Method',icon:r.querySelector('.picon').value||'💳',image:r.querySelector('.pimage').value||'',enabled:r.querySelector('.ptoggle').classList.contains('on')}))}
function addPayment(){state.payments=collectPayments();state.payments.push({id:'',name:'New Method',icon:'💳',image:'',enabled:true});renderPayments()}function removePayment(i){state.payments=collectPayments();state.payments.splice(i,1);renderPayments()}
async function uploadPayment(input,i){let f=input.files[0];if(!f)return;let fd=new FormData();fd.append('icon',f);try{let r=await fetch('/admin/payments/upload-icon',{method:'POST',headers:H(),body:fd});let d=await r.json();if(!d.ok)throw Error(d.error);state.payments=collectPayments();state.payments[i].image=d.url;renderPayments()}catch(e){alert('Payment icon upload failed: '+e.message)}}
async function savePayments(){state.payments=collectPayments();await post('/admin/update-payments',{paymentMethods:state.payments})}async function saveBinanceRate(){await post('/admin/update-binance-rate',{binanceRate:+binanceRate.value})}
async function uploadTransfer(input){let f=input.files[0];if(!f)return;let fd=new FormData();fd.append('photo',f);try{let r=await fetch('/admin/transfer/upload-profile',{method:'POST',headers:H(),body:fd});let d=await r.json();if(!d.ok)throw Error(d.error);transferImage.value=d.url;transferPreview.src=d.url;transferPreview.style.display='block'}catch(e){alert('Profile upload failed: '+e.message)}}
async function saveTransfer(){await post('/admin/update-transfer',{transferId:transferId.value.trim(),transferUsername:transferUsername.value.trim(),transferProfileImage:transferImage.value.trim()})}
async function saveBranding(){await post('/admin/update-branding',{helpLineUrl:helpLineUrl.value,channelUrl:channelUrl.value,tutorialVideoUrl:tutorialVideoUrl.value,disclaimer:disclaimer.value})}
async function loadOrders(status){ordersBox.innerHTML='Loading...';try{let r=await fetch('/admin/orders'+(status?'?status='+status:''),{headers:H()});let d=await r.json();if(!d.ok)throw Error(d.error);ordersBox.innerHTML=d.orders.map(o=>`<div class="row order"><b>${esc(o.coin)}</b> — ${o.quantity} coins — <b>${o.payment_method==='binance'?esc(o.usdt_amount||0)+' USDT':esc(o.total_amount)+' ৳'}</b> — ${esc(o.status)}<br>User: @${esc(o.username||'—')} (${esc(o.user_id)})<br>Instagram: ${esc(o.instagram_username||'—')}<br>Payment: ${esc(o.payment_method||'—')} → ${esc(o.account_number||'—')}<br>${o.screenshot_url?`<img src="${esc(o.screenshot_url)}">`:''}${o.status==='pending'?`<br><button class="green" onclick="decide('${o.id}','approve')">Approve</button><button class="red" onclick="decide('${o.id}','reject')">Reject</button>`:''}</div>`).join('')||'No orders'}catch(e){ordersBox.textContent=e.message}}
async function decide(id,a){await post('/admin/orders/'+id+'/'+a,{}) ;loadOrders('pending')}
async function loadUsers(){let q=userSearch.value.trim();try{let r=await fetch('/admin/users'+(q?'?q='+encodeURIComponent(q):''),{headers:H()});let d=await r.json();usersBox.innerHTML=(d.users||[]).map(u=>`<div class="row">@${esc(u.username||'—')} (ID: ${esc(u.id)}) <button class="${u.blocked?'green':'red'}" onclick="userAction('${esc(u.id)}','${u.blocked?'unblock':'block'}')">${u.blocked?'Unblock':'Block'}</button></div>`).join('')||'No users'}catch(e){usersBox.textContent=e.message}}
async function userAction(id,a){await post('/admin/users/'+id+'/'+a,{}) ;loadUsers()}
async function broadcast(){let d=await post('/admin/broadcast',{message:broadcastText.value.trim()});if(d)broadcastResult.textContent=`Sent: ${d.sent||0}, Failed: ${d.failed||0}`}
loadState();loadOrders('pending');loadUsers();
</script></body></html>'''

@panel.get('/panel')
def admin_panel():
    uid=request.args.get('uid','')
    if not uid.isdigit() or int(uid) not in ADMIN_IDS: return denied()
    return render_template_string(ADMIN_HTML)

@panel.get('/state')
def state():
    if not is_admin_request(): return denied()
    system={"enabled":True};features={"xr7Task":True,"coinSell":True,"history":False}
    coins=DEFAULT_COINS;payments=DEFAULT_PAYMENT_METHODS;transfer=DEFAULT_TRANSFER;branding=DEFAULT_BRANDING;rate=DEFAULT_BINANCE_RATE
    users_count=orders_count=pending=blocked=0
    try:
        if db:
            d=db.collection('system').document('status').get()
            if d.exists: system=d.to_dict()
            d=db.collection('system').document('features').get()
            if d.exists: features.update(d.to_dict()); features.pop('refer',None)
            d=db.collection('system').document('coins').get()
            if d.exists and d.to_dict().get('list'): coins=d.to_dict()['list']
            d=db.collection('system').document('payments').get()
            if d.exists and d.to_dict().get('list'): payments=d.to_dict()['list']
            d=db.collection('system').document('transfer').get()
            if d.exists: transfer={**DEFAULT_TRANSFER,**d.to_dict()}
            d=db.collection('system').document('branding').get()
            if d.exists: branding={**DEFAULT_BRANDING,**d.to_dict()}
            d=db.collection('system').document('config').get()
            if d.exists: rate=float(d.to_dict().get('binanceRate',DEFAULT_BINANCE_RATE) or DEFAULT_BINANCE_RATE)
            users=list(db.collection('users').stream()); users_count=len(users); blocked=sum(bool(x.to_dict().get('blocked')) for x in users)
            orders=list(db.collection('orders').stream()); orders_count=len(orders); pending=sum(x.to_dict().get('status','pending')=='pending' for x in orders)
        return jsonify({"ok":True,"status":system,"features":features,"coins":coins,"paymentMethods":payments,"transfer":transfer,"branding":branding,"binanceRate":rate,"stats":{"users":users_count,"orders":orders_count,"pending":pending,"blocked":blocked}})
    except Exception as e: return jsonify({"ok":False,"error":str(e)}),500

@panel.post('/toggle/system')
def toggle_system():
    if not is_admin_request(): return denied()
    if not db: return jsonify({"ok":False,"error":"Database not connected"}),500
    d=db.collection('system').document('status').get(); cur=d.to_dict() if d.exists else {"enabled":True}; new=not cur.get('enabled',True); db.collection('system').document('status').set({"enabled":new},merge=True); return jsonify({"ok":True,"enabled":new})

@panel.post('/toggle/feature')
def toggle_feature():
    if not is_admin_request(): return denied()
    if not db: return jsonify({"ok":False,"error":"Database not connected"}),500
    f=(request.get_json(silent=True) or {}).get('feature');
    if f=='refer': return jsonify({"ok":False,"error":"Referral feature removed"}),400
    d=db.collection('system').document('features').get(); data=d.to_dict() if d.exists else {}; data[f]=not data.get(f,True); db.collection('system').document('features').set(data,merge=True); return jsonify({"ok":True,"feature":f,"enabled":data[f]})

@panel.post('/update-coins')
def update_coins():
    if not is_admin_request(): return denied()
    data=request.get_json(silent=True) or {}; items=data.get('coins')
    if not isinstance(items,list): return jsonify({"ok":False,"error":"Invalid coins data"}),400
    clean=[]
    for c in items:
        price=float(c.get('price',0)); rate=float(c.get('rate',1))
        if price<0 or rate<=0: return jsonify({"ok":False,"error":"Price/rate must be positive"}),400
        clean.append({"id":str(c.get('id') or f'coin{len(clean)}')[:50],"name":str(c.get('name','COIN'))[:80],"icon":str(c.get('icon','🪙'))[:20],"image":str(c.get('image',''))[:600],"price":price,"rate":rate,"unit":rate,"requiresUsername":bool(c.get('requiresUsername',True)),"requiresCoupon":bool(c.get('requiresCoupon',False)),"targetUsername":str(c.get('targetUsername',''))[:150],"targetImage":str(c.get('targetImage',''))[:600],"enabled":bool(c.get('enabled',True))})
    if not db:return jsonify({"ok":False,"error":"Database not connected"}),500
    db.collection('system').document('coins').set({'list':clean},merge=True);return jsonify({"ok":True,"coins":clean})

@panel.post('/coins/upload-icon')
def upload_coin_icon():
    if not is_admin_request(): return denied()
    import bot
    url=bot.save_upload(request.files.get('icon'),bot.COINS_UPLOAD_DIR)
    return jsonify({"ok":bool(url),"url":url,"error":None if url else 'Invalid image file'}), 200 if url else 400

@panel.post('/coins/upload-target-profile')
def upload_coin_target_profile():
    if not is_admin_request(): return denied()
    import bot
    url=bot.save_upload(request.files.get('photo') or request.files.get('image'),bot.PAYMENTS_UPLOAD_DIR)
    return jsonify({"ok":bool(url),"url":url,"error":None if url else 'Invalid image file'}),200 if url else 400

@panel.post('/update-payments')
def update_payments():
    if not is_admin_request(): return denied()
    items=(request.get_json(silent=True) or {}).get('paymentMethods')
    if not isinstance(items,list):return jsonify({"ok":False,"error":"Invalid payment methods"}),400
    clean=[{"id":str(m.get('id') or f'method{i}')[:50],"name":str(m.get('name','Method'))[:80],"icon":str(m.get('icon','💳'))[:20],"image":str(m.get('image',''))[:600],"enabled":bool(m.get('enabled',True))} for i,m in enumerate(items)]
    if not db:return jsonify({"ok":False,"error":"Database not connected"}),500
    db.collection('system').document('payments').set({'list':clean},merge=True);return jsonify({"ok":True,"paymentMethods":clean})

@panel.post('/payments/upload-icon')
def upload_payment_icon():
    if not is_admin_request(): return denied()
    import bot
    url=bot.save_upload(request.files.get('icon'),bot.PAYMENTS_UPLOAD_DIR)
    return jsonify({"ok":bool(url),"url":url,"error":None if url else 'Invalid image file'}),200 if url else 400

@panel.post('/update-binance-rate')
def update_binance_rate():
    if not is_admin_request(): return denied()
    rate=float((request.get_json(silent=True) or {}).get('binanceRate',0) or 0)
    if rate<=0:return jsonify({"ok":False,"error":"Binance rate must be greater than 0"}),400
    if not db:return jsonify({"ok":False,"error":"Database not connected"}),500
    db.collection('system').document('config').set({'binanceRate':rate},merge=True);return jsonify({"ok":True,"binanceRate":rate})

@panel.post('/update-transfer')
def update_transfer():
    if not is_admin_request(): return denied()
    data=request.get_json(silent=True) or {}; transfer={"transferId":str(data.get('transferId','')).strip()[:150],"transferUsername":str(data.get('transferUsername','')).strip()[:150],"transferProfileImage":str(data.get('transferProfileImage','')).strip()[:600]}
    if not db:return jsonify({"ok":False,"error":"Database not connected"}),500
    db.collection('system').document('transfer').set(transfer,merge=True);return jsonify({"ok":True,"transfer":transfer})

@panel.post('/transfer/upload-profile')
def upload_transfer_profile():
    if not is_admin_request(): return denied()
    import bot
    url=bot.save_upload(request.files.get('photo') or request.files.get('image'),bot.PAYMENTS_UPLOAD_DIR)
    return jsonify({"ok":bool(url),"url":url,"error":None if url else 'Invalid image file'}),200 if url else 400

@panel.post('/update-branding')
def update_branding():
    if not is_admin_request(): return denied()
    if not db:return jsonify({"ok":False,"error":"Database not connected"}),500
    data=request.get_json(silent=True) or {}; b={"helpLineUrl":str(data.get('helpLineUrl',''))[:300],"channelUrl":str(data.get('channelUrl',''))[:300],"tutorialVideoUrl":str(data.get('tutorialVideoUrl',''))[:300],"disclaimer":str(data.get('disclaimer',''))[:2000]};db.collection('system').document('branding').set(b,merge=True);return jsonify({"ok":True,"branding":b})

@panel.get('/orders')
def orders():
    if not is_admin_request(): return denied()
    if not db:return jsonify({"ok":True,"orders":[]})
    status=request.args.get('status',''); out=[]
    for d in db.collection('orders').stream():
        x=d.to_dict();x['id']=d.id;x.setdefault('status','pending')
        if status and x['status']!=status:continue
        out.append(x)
    out.sort(key=lambda x:str(x.get('timestamp','')),reverse=True);return jsonify({"ok":True,"orders":out[:50]})

@panel.post('/orders/<order_id>/<action>')
def order_action(order_id,action):
    if not is_admin_request(): return denied()
    if action not in ('approve','reject'):return jsonify({"ok":False,"error":"Invalid action"}),400
    import bot
    return jsonify(bot.process_order_decision(order_id,'approved' if action=='approve' else 'rejected'))

@panel.get('/users')
def users():
    if not is_admin_request():return denied()
    if not db:return jsonify({"ok":True,"users":[]})
    q=request.args.get('q','').lower().strip();out=[]
    for d in db.collection('users').stream():
        x=d.to_dict();x['id']=d.id
        if q and q not in str(x.get('username','')).lower() and q not in str(x.get('telegram_id','')):continue
        out.append(x)
    return jsonify({"ok":True,"users":out[:100]})

@panel.post('/users/<uid>/<action>')
def user_action(uid,action):
    if not is_admin_request():return denied()
    if action not in ('block','unblock') or not db:return jsonify({"ok":False,"error":"Invalid request"}),400
    db.collection('users').document(uid).set({'blocked':action=='block'},merge=True);return jsonify({"ok":True})

@panel.post('/broadcast')
def broadcast():
    if not is_admin_request():return denied()
    text=str((request.get_json(silent=True) or {}).get('message','')).strip()
    if not text:return jsonify({"ok":False,"error":"Message required"}),400
    import bot
    sent,failed=bot.send_broadcast(text);return jsonify({"ok":True,"sent":sent,"failed":failed})
