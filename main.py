# main.py — Brainrots Funny backend
import os, json, hmac, hashlib, logging, random, time
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, db as fbdb
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher, types
from aiogram.types import LabeledPrice

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("brainrots")

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
WEBHOOK_URL = (os.getenv("WEBHOOK_URL") or "").strip().rstrip("/")
RENDER_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
FIREBASE_DB_URL = os.getenv("FIREBASE_DB_URL", "https://casemine-online-default-rtdb.europe-west1.firebasedatabase.app")
ALLOWED_ORIGINS = [o.strip() for o in (os.getenv("ALLOWED_ORIGINS") or "*").split(",") if o.strip()]

# ===================== ИГРОВЫЕ КОНСТАНТЫ =====================
RARITIES = {
    "common":    {"id":"common","name":"Common","color":"#6b7280","star":"⭐"},
    "uncommon":  {"id":"uncommon","name":"Uncommon","color":"#22c55e","star":"⭐⭐"},
    "rare":      {"id":"rare","name":"Rare","color":"#3b82f6","star":"⭐⭐⭐"},
    "epic":      {"id":"epic","name":"Epic","color":"#a855f7","star":"⭐⭐⭐⭐"},
    "legendary": {"id":"legendary","name":"Legendary","color":"#f59e0b","star":"⭐⭐⭐⭐⭐"},
}

ITEMS = [
    {"id":"trios",    "name":"Los Trios",           "price":4,     "rarity":"common",    "img":"assets/brainrots/los_trios.png"},
    {"id":"rot67",    "name":"67",                  "price":5,     "rarity":"common",    "img":"assets/brainrots/67.png"},
    {"id":"hammy",    "name":"Spinny Hammy",        "price":5,     "rarity":"uncommon",  "img":"assets/brainrots/spinny_hammy.png"},
    {"id":"candyslap","name":"Candy Slap",          "price":7,     "rarity":"uncommon",  "img":"assets/brainrots/CandySlap.png"},
    {"id":"noobinis", "name":"Los Noobinis",        "price":7,     "rarity":"rare",      "img":"assets/brainrots/Los_Noobinis.png"},
    {"id":"tangtang", "name":"Tang Tang Keletang",  "price":8,     "rarity":"rare",      "img":"assets/brainrots/TangTangKeletang.png"},
    {"id":"lagrande", "name":"La Grande",           "price":9,     "rarity":"epic",      "img":"assets/brainrots/La_Grande_Combinasion.png"},
    {"id":"tictac",   "name":"Tictac Sahur",        "price":12,    "rarity":"epic",      "img":"assets/brainrots/Tictac-Sahur.png"},
    {"id":"bacuru",   "name":"Bacuru and Egguru",   "price":12,    "rarity":"epic",      "img":"assets/brainrots/Bacuru_and_Egguru.png"},
    {"id":"los67",    "name":"Los 67",              "price":12,    "rarity":"epic",      "img":"assets/brainrots/Los_67.png"},
    {"id":"yinyang",  "name":"Yin Yang Slap",       "price":20,    "rarity":"legendary", "img":"assets/brainrots/YinYangSlap.png"},
    {"id":"skibidi",  "name":"Skibidi Toilet",      "price":13154, "rarity":"legendary", "img":"assets/brainrots/skibidi_toilet.png"},
]
ITEMS_BY_ID = {i["id"]: i for i in ITEMS}

CASE_PRICES = {"free": 0, "base": 9, "bro": 25}
CASE_TITLES = {"free": "Бесплатный Кейс", "base": "Начальный Кейс", "bro": "Про Бро Кейс"}
CASE_IMAGES = {
    "free": "assets/cases/free.png",
    "base": "assets/cases/base.png",
    "bro":  "assets/cases/bro.png",
}

# ⚠️ ЭКОНОМИКА ЗАДРОЧЕНА
CASE_LOOT = {
    "free": {
        "coinChance": 100,
        "coins": [{"amount":1,"weight":80},{"amount":2,"weight":20}],
        "items": [], # Бесплатный кейс теперь дает ТОЛЬКО монеты (1-2)
    },
    "base": {
        "coinChance": 0, "coins": [],
        "items": [
            {"id":"trios","weight":50},{"id":"rot67","weight":50} # Только дешевые
        ],
    },
    "bro": {
        "coinChance": 0, "coins": [],
        "items": [
            {"id":"hammy","weight":40},{"id":"candyslap","weight":30},
            {"id":"noobinis","weight":20},{"id":"tangtang","weight":10}
        ],
    },
}

THEMES = {
    "dark": {"name": "Тёмная",   "price": 0},
    "neon": {"name": "Неоновая", "price": 100},
    "gold": {"name": "Золотая",  "price": 500},
}

STARS_PACKAGES = {
    "p10":  {"stars":10,  "coins":50,   "bonus":0},
    "p25":  {"stars":25,  "coins":135,  "bonus":8},
    "p50":  {"stars":50,  "coins":300,  "bonus":20},
    "p100": {"stars":100, "coins":650,  "bonus":30},
    "p250": {"stars":250, "coins":1750, "bonus":40},
    "p500": {"stars":500, "coins":4000, "bonus":60},
}

FREE_COOLDOWN_MS = 12 * 3600 * 1000
MAX_UPGRADE_CHANCE = 95.0
MAX_MULTIPLIER = 5
MAX_UPG_INPUTS = 5

# ===================== FIREBASE ADMIN =====================
def init_firebase():
    raw = os.getenv("FIREBASE_CRED_JSON")
    if not raw:
        log.warning("FIREBASE_CRED_JSON missing")
        return False
    try:
        cred_dict = json.loads(raw)
        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
        firebase_admin.initialize_app(credentials.Certificate(cred_dict), {"databaseURL": FIREBASE_DB_URL})
        log.info("Firebase OK project=%s", cred_dict.get("project_id"))
        return True
    except Exception:
        log.exception("Firebase init error")
        return False

FIREBASE_OK = init_firebase()

def user_ref(uid: str):
    return fbdb.reference(f"users/{uid}")

def _default_user() -> dict:
    return {
        "balance": 0, "inventory": {}, "lastFree": 0,
        "stats": {"casesOpened":0,"itemsSold":0,"upgradeSuccess":0,"upgradeFail":0,
                  "totalEarned":0,"donationsTotal":0,"starsSpent":0,"uniqueCollected":[]},
        "themes": {"dark": True}, "theme": "dark", "referrals": 0,
    }

def get_user_data(uid: str) -> dict:
    if not FIREBASE_OK: return _default_user()
    data = user_ref(uid).get() or {}
    defaults = _default_user()
    for k, v in defaults.items():
        data.setdefault(k, v)
    for k, v in defaults["stats"].items():
        data["stats"].setdefault(k, v)
    return data

def atomic_update(uid: str, updater) -> dict | None:
    if not FIREBASE_OK: return None
    def tx(current):
        d = current or {}
        defaults = _default_user()
        for k, v in defaults.items():
            d.setdefault(k, v)
        for k, v in defaults["stats"].items():
            d["stats"].setdefault(k, v)
        result = updater(d)
        return result if result is not None else d
    try:
        return user_ref(uid).transaction(tx)
    except Exception:
        log.exception("transaction error uid=%s", uid)
        return None

# ===================== AUTH =====================
def verify_init_data(init_data: str) -> dict | None:
    if not init_data or not BOT_TOKEN: return None
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=False))
        received_hash = parsed.pop("hash", None)
        if not received_hash: return None
        dcs = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received_hash): return None
        return json.loads(parsed.get("user", "{}"))
    except Exception:
        return None

async def current_user(x_telegram_init_data: str = Header(None)):
    user = verify_init_data(x_telegram_init_data or "")
    if not user:
        raise HTTPException(401, "invalid initData")
    return user

# ===================== GAME LOGIC =====================
def weighted_pick(entries):
    total = sum(e.get("weight", 1) for e in entries)
    r = random.random() * total
    for e in entries:
        r -= e.get("weight", 1)
        if r <= 0: return e
    return entries[-1]

def roll_drop(case_type: str) -> dict:
    cfg = CASE_LOOT[case_type]
    if cfg["coins"] and random.random() * 100 < cfg["coinChance"]:
        picked = weighted_pick(cfg["coins"])
        return {"type": "coin", "amount": picked["amount"]}
    picked = weighted_pick(cfg["items"])
    return {"type": "item", "item": dict(ITEMS_BY_ID[picked["id"]])}

def make_inv_item(item: dict) -> dict:
    uid = "u_%d_%s" % (int(time.time()*1000), "".join(random.choices("abcdef0123456789", k=6)))
    return {**item, "uid": uid}

def push_drop(nick: str, item_name: str, item_img: str | None):
    if not FIREBASE_OK: return
    try:
        drop_id = "d_%d_%s" % (int(time.time()*1000), "".join(random.choices("abcdef", k=4)))
        fbdb.reference(f"drop_feed/{drop_id}").set({
            "nick": nick, "itemName": item_name,
            "itemImg": item_img or "", "ts": int(time.time()*1000),
        })
    except Exception:
        log.exception("push_drop error")

# ===================== AIOGRAM =====================
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()

@dp.message()
async def on_message(message: types.Message):
    if message.text and message.text.startswith("/start"):
        base = WEBHOOK_URL or RENDER_URL or "https://example.com"
        await message.answer("🎮 <b>Brainrots Funny</b>", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
            types.InlineKeyboardButton(text="🎮 Открыть", web_app=types.WebAppInfo(url=base))
        ]]))

@dp.pre_checkout_query()
async def pre_checkout(q: types.PreCheckoutQuery):
    try:
        payload = json.loads(q.invoice_payload)
        if payload.get("package_id") not in STARS_PACKAGES:
            await q.answer(ok=False, error_message="Unknown package")
            return
        await q.answer(ok=True)
    except Exception:
        await q.answer(ok=False, error_message="Bad payload")

@dp.message(lambda m: m.successful_payment)
async def on_paid(message: types.Message):
    sp = message.successful_payment
    try:
        payload = json.loads(sp.invoice_payload)
    except Exception: return
    pack = STARS_PACKAGES.get(payload.get("package_id"))
    if not pack: return
    uid = str(message.from_user.id)
    def upd(d):
        d["balance"] = int(d.get("balance", 0)) + pack["coins"]
        d["stats"]["donationsTotal"] = int(d["stats"].get("donationsTotal", 0)) + 1
        d["stats"]["starsSpent"] = int(d["stats"].get("starsSpent", 0)) + pack["stars"]
        d["stats"]["totalEarned"] = int(d["stats"].get("totalEarned", 0)) + pack["coins"]
        return d
    atomic_update(uid, upd)
    await message.answer(f"⭐ <b>Оплата прошла!</b>\n+{pack['coins']} монет начислено.")

# ===================== LIFESPAN =====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    if bot and (WEBHOOK_URL or RENDER_URL):
        try:
            await bot.set_webhook(f"{WEBHOOK_URL or RENDER_URL}/webhook/tg",
                                  allowed_updates=dp.resolve_used_update_types(),
                                  drop_pending_updates=True)
        except Exception: pass
    yield
    if bot:
        try: await bot.delete_webhook()
        except: pass
        await bot.session.close()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["*"], allow_headers=["*"])

BASE = Path(__file__).parent
if (BASE / "assets").exists():
    app.mount("/assets", StaticFiles(directory=BASE / "assets"), name="assets")

@app.get("/", response_class=HTMLResponse)
async def root():
    idx = BASE / "index.html"
    return HTMLResponse(idx.read_text(encoding="utf-8") if idx.exists() else "<h1>no index</h1>")

@app.get("/health")
async def health():
    return {"ok": True, "firebase": FIREBASE_OK, "bot": bot is not None}

@app.get("/api/me")
async def api_me(user=Depends(current_user)):
    uid = str(user["id"])
    data = get_user_data(uid)
    data["uid"] = uid
    return data

@app.post("/api/open_case")
async def api_open_case(request: Request, user=Depends(current_user)):
    body = await request.json()
    case_type = body.get("case_type", "")
    multiplier = int(body.get("multiplier", 1))
    if case_type not in CASE_LOOT: raise HTTPException(400, "unknown case")
    if multiplier < 1 or multiplier > MAX_MULTIPLIER: raise HTTPException(400, "bad multiplier")
    if case_type == "free": multiplier = 1
    
    uid = str(user["id"])
    nick = user.get("first_name") or "Player"
    now = int(time.time() * 1000)
    data = get_user_data(uid)

    if case_type == "free":
        if now - int(data.get("lastFree", 0)) < FREE_COOLDOWN_MS:
            raise HTTPException(400, "free case on cooldown")
        price = 0
    else:
        price = CASE_PRICES[case_type] * multiplier
    if int(data.get("balance", 0)) < price:
        raise HTTPException(400, "not enough coins")

    results = [roll_drop(case_type) for _ in range(multiplier)]

    def upd(d):
        if case_type == "free":
            if now - int(d.get("lastFree", 0)) < FREE_COOLDOWN_MS: return None
            d["lastFree"] = now
        else:
            bal = int(d.get("balance", 0))
            if bal < price: return None
            d["balance"] = bal - price
        
        inv = d.setdefault("inventory", {})
        coins_won = 0
        for r in results:
            if r["type"] == "coin":
                coins_won += r["amount"]
            else:
                new_item = make_inv_item(r["item"])
                inv[new_item["uid"]] = new_item
                uniq = set(d["stats"].get("uniqueCollected", []))
                uniq.add(r["item"]["id"])
                d["stats"]["uniqueCollected"] = list(uniq)
        
        d["balance"] = int(d.get("balance", 0)) + coins_won
        d["stats"]["casesOpened"] = int(d["stats"].get("casesOpened", 0)) + multiplier
        d["stats"]["totalEarned"] = int(d["stats"].get("totalEarned", 0)) + coins_won
        return d

    atomic_update(uid, upd)
    for r in results:
        if r["type"] == "coin": push_drop(nick, f"{r['amount']} монет", None)
        else: push_drop(nick, r["item"]["name"], r["item"]["img"])

    new_data = get_user_data(uid)
    return {"ok": True, "results": results, "balance": new_data["balance"], "inventory": new_data["inventory"], "lastFree": new_data.get("lastFree", 0)}

@app.post("/api/sell_item")
async def api_sell_item(request: Request, user=Depends(current_user)):
    body = await request.json()
    item_uid = body.get("uid", "")
    uid = str(user["id"])
    def upd(d):
        inv = d.get("inventory", {})
        if item_uid not in inv: return None
        item = inv[item_uid]
        del inv[item_uid]
        d["balance"] = int(d.get("balance", 0)) + int(item.get("price", 0))
        d["stats"]["itemsSold"] = int(d["stats"].get("itemsSold", 0)) + 1
        return d
    atomic_update(uid, upd)
    data = get_user_data(uid)
    return {"ok": True, "balance": data["balance"], "inventory": data["inventory"]}

@app.post("/api/upgrade")
async def api_upgrade(request: Request, user=Depends(current_user)):
    body = await request.json()
    input_uids = body.get("input_uids", [])
    target_id = body.get("target_id", "")
    if not isinstance(input_uids, list) or not (1 <= len(input_uids) <= MAX_UPG_INPUTS):
        raise HTTPException(400, "input_uids must be 1..5")
    target = ITEMS_BY_ID.get(target_id)
    if not target: raise HTTPException(400, "unknown target")

    uid = str(user["id"])
    data = get_user_data(uid)
    inv = data.get("inventory", {})
    total = 0
    for iuid in input_uids:
        if iuid not in inv: raise HTTPException(400, "item not in inventory")
        total += int(inv[iuid]["price"])
    
    chance = min(MAX_UPGRADE_CHANCE, (total / int(target["price"])) * 100)
    success = random.random() * 100 <= chance

    def upd(d):
        inv2 = d.get("inventory", {})
        for iuid in input_uids:
            if iuid not in inv2: return None
        if sum(int(inv2[iuid]["price"]) for iuid in input_uids) != total: return None
        
        for iuid in input_uids:
            del inv2[iuid]
        if success:
            new_item = make_inv_item(target)
            inv2[new_item["uid"]] = new_item
            d["stats"]["upgradeSuccess"] = int(d["stats"].get("upgradeSuccess", 0)) + 1
            uniq = set(d["stats"].get("uniqueCollected", []))
            uniq.add(target["id"])
            d["stats"]["uniqueCollected"] = list(uniq)
        else:
            d["stats"]["upgradeFail"] = int(d["stats"].get("upgradeFail", 0)) + 1
        return d

    atomic_update(uid, upd)
    if success: push_drop(user.get("first_name") or "Player", target["name"], target["img"])
    new_data = get_user_data(uid)
    return {"ok": True, "success": success, "chance": chance, "target": target, "balance": new_data["balance"], "inventory": new_data["inventory"]}

@app.post("/api/choose_theme")
async def api_choose_theme(request: Request, user=Depends(current_user)):
    body = await request.json()
    theme_id = body.get("theme_id", "")
    if theme_id not in THEMES: raise HTTPException(400, "unknown theme")
    uid = str(user["id"])
    price = int(THEMES[theme_id]["price"])
    def upd(d):
        owned = d.get("themes", {"dark": True})
        if not owned.get(theme_id):
            if int(d.get("balance", 0)) < price: return None
            d["balance"] = int(d.get("balance", 0)) - price
            owned[theme_id] = True
            d["themes"] = owned
        d["theme"] = theme_id
        return d
    atomic_update(uid, upd)
    new_data = get_user_data(uid)
    return {"ok": True, "theme": new_data["theme"], "themes": new_data["themes"], "balance": new_data["balance"]}

@app.post("/api/create-invoice-link")
async def create_invoice(request: Request, user=Depends(current_user)):
    if not bot: raise HTTPException(503, "bot off")
    body = await request.json()
    pack_id = body.get("package_id")
    pack = STARS_PACKAGES.get(pack_id)
    if not pack: raise HTTPException(400, "unknown package")
    
    payload = json.dumps({"package_id": pack_id, "coins": pack["coins"]})
    try:
        link = await bot.create_invoice_link(
            title=f"{pack['coins']} монет",
            description=f"Пакет «{pack_id}» для Brainrots Funny",
            payload=payload,
            currency="XTR",
            prices=[LabeledPrice(label=f"{pack['coins']} coins", amount=pack["stars"])],
        )
    except Exception as e:
        log.exception("create_invoice error")
        raise HTTPException(500, str(e))
    return {"invoice_link": link}

@app.post("/webhook/tg")
async def tg_webhook(request: Request):
    if not bot: raise HTTPException(503)
    try:
        update = types.Update.model_validate(await request.json(), context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception: pass
    return {"ok": True}
