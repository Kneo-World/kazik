# main.py — Brainrots Funny backend (FastAPI + Firebase Admin + Aiogram 3)
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

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("brainrots")

# ============================================================
# ENV
# ============================================================
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
WEBHOOK_URL = (os.getenv("WEBHOOK_URL") or "").strip().rstrip("/")
RENDER_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
FIREBASE_DB_URL = os.getenv(
    "FIREBASE_DB_URL",
    "https://casemine-online-default-rtdb.europe-west1.firebasedatabase.app"
)
ALLOWED_ORIGINS = [o.strip() for o in (os.getenv("ALLOWED_ORIGINS") or "*").split(",") if o.strip()]

# ============================================================
# GAME CONSTANTS (синхронизированы с фронтом)
# ============================================================
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

CASE_LOOT = {
    "free": {
        "coinChance": 90,
        "coins": [{"amount":2,"weight":30},{"amount":3,"weight":40},{"amount":5,"weight":30}],
        "items": [{"id":"trios","weight":70},{"id":"rot67","weight":30}],
    },
    "base": {
        "coinChance": 0, "coins": [],
        "items": [
            {"id":"trios","weight":30},{"id":"rot67","weight":30},
            {"id":"candyslap","weight":25},{"id":"lagrande","weight":15},
        ],
    },
    "bro": {
        "coinChance": 0, "coins": [],
        "items": [
            {"id":"hammy","weight":25},{"id":"noobinis","weight":20},
            {"id":"tangtang","weight":18},{"id":"tictac","weight":15},
            {"id":"bacuru","weight":10},{"id":"los67","weight":8},
            {"id":"yinyang","weight":4},
        ],
    },
}

THEMES = {
    "dark": {"name": "Тёмная",   "price": 0},
    "neon": {"name": "Неоновая", "price": 100},
    "gold": {"name": "Золотая",  "price": 500},
}

ACHIEVEMENTS = [
    {"id":"case1","title":"Первый кейс","desc":"Открой 1 кейс","stat":"casesOpened","goal":1,"reward":5},
    {"id":"case10","title":"Крутила","desc":"Открой 10 кейсов","stat":"casesOpened","goal":10,"reward":25},
    {"id":"case50","title":"Кейсоголик","desc":"Открой 50 кейсов","stat":"casesOpened","goal":50,"reward":100},
    {"id":"case200","title":"Легенда кейсов","desc":"Открой 200 кейсов","stat":"casesOpened","goal":200,"reward":500},
    {"id":"sell1","title":"Первая сделка","desc":"Продай 1 предмет","stat":"itemsSold","goal":1,"reward":3},
    {"id":"sell25","title":"Торговец","desc":"Продай 25 предметов","stat":"itemsSold","goal":25,"reward":30},
    {"id":"sell100","title":"Барыга","desc":"Продай 100 предметов","stat":"itemsSold","goal":100,"reward":150},
    {"id":"up1","title":"Первый апгрейд","desc":"Успешный апгрейд","stat":"upgradeSuccess","goal":1,"reward":10},
    {"id":"up10","title":"Кузнец","desc":"10 успешных апгрейдов","stat":"upgradeSuccess","goal":10,"reward":50},
    {"id":"up50","title":"Мастер апгрейда","desc":"50 успешных апгрейдов","stat":"upgradeSuccess","goal":50,"reward":200},
    {"id":"pvp1","title":"Дуэлянт","desc":"Выиграй 1 PvP","stat":"pvpWins","goal":1,"reward":10},
    {"id":"pvp10","title":"Гладиатор","desc":"Выиграй 10 PvP","stat":"pvpWins","goal":10,"reward":80},
    {"id":"col5","title":"Коллекционер","desc":"Собери 5 разных","stat":"uniqueCount","goal":5,"reward":40},
    {"id":"col10","title":"Фанат","desc":"Собери 10 разных","stat":"uniqueCount","goal":10,"reward":200},
    {"id":"col12","title":"Полный сет","desc":"Собери все 12","stat":"uniqueCount","goal":12,"reward":1500},
    {"id":"bal500","title":"Сотка","desc":"Заработай 500 всего","stat":"totalEarned","goal":500,"reward":25},
    {"id":"bal5000","title":"Богач","desc":"Заработай 5000 всего","stat":"totalEarned","goal":5000,"reward":250},
    {"id":"donate1","title":"Первая звезда","desc":"Купи любой пакет","stat":"donationsTotal","goal":1,"reward":50},
    {"id":"donate5","title":"Меценат","desc":"Купи 5 пакетов","stat":"donationsTotal","goal":5,"reward":300},
]

DAILY_QUESTS = [
    {"id":"d_case3","title":"Разминка","desc":"Открой 3 кейса сегодня","stat":"casesOpened","goal":3,"reward":12},
    {"id":"d_sell5","title":"Скупщик","desc":"Продай 5 предметов сегодня","stat":"itemsSold","goal":5,"reward":10},
    {"id":"d_up1","title":"Удачный апгрейд","desc":"Сделай успешный апгрейд","stat":"upgradeSuccess","goal":1,"reward":15},
]

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

# ============================================================
# FIREBASE ADMIN
# ============================================================
def init_firebase():
    raw = os.getenv("FIREBASE_CRED_JSON")
    if not raw:
        log.warning("FIREBASE_CRED_JSON missing — Firebase disabled")
        return False
    try:
        cred_dict = json.loads(raw)
        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
        firebase_admin.initialize_app(
            credentials.Certificate(cred_dict),
            {"databaseURL": FIREBASE_DB_URL},
        )
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
                  "pvpWins":0,"pvpLosses":0,"totalEarned":0,"donationsTotal":0,
                  "starsSpent":0,"uniqueCollected":[]},
        "achievements": {}, "daily": {}, "themes": {"dark": True},
        "theme": "dark", "referrals": 0,
    }

def get_user_data(uid: str) -> dict:
    if not FIREBASE_OK:
        return _default_user()
    data = user_ref(uid).get() or {}
    defaults = _default_user()
    for k, v in defaults.items():
        data.setdefault(k, v)
    for k, v in defaults["stats"].items():
        data["stats"].setdefault(k, v)
    return data

def atomic_update(uid: str, updater) -> dict | None:
    """updater(d) -> d | None (abort)."""
    if not FIREBASE_OK:
        return None
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

# ============================================================
# AUTH
# ============================================================
def verify_init_data(init_data: str) -> dict | None:
    if not init_data or not BOT_TOKEN:
        return None
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=False))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None
        dcs = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received_hash):
            return None
        return json.loads(parsed.get("user", "{}"))
    except Exception:
        log.exception("verify_init_data error")
        return None

async def current_user(x_telegram_init_data: str = Header(None)):
    user = verify_init_data(x_telegram_init_data or "")
    if not user:
        raise HTTPException(401, "invalid initData")
    return user

# ============================================================
# GAME LOGIC
# ============================================================
def weighted_pick(entries):
    total = sum(e.get("weight", 1) for e in entries)
    r = random.random() * total
    for e in entries:
        r -= e.get("weight", 1)
        if r <= 0:
            return e
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

def today_str() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())

def ensure_daily(d: dict):
    daily = d.get("daily") or {}
    if daily.get("date") != today_str():
        d["daily"] = {"date": today_str(), "casesOpened":0, "itemsSold":0,
                       "upgradeSuccess":0, "claimed":{}}
    else:
        d["daily"] = daily
        d["daily"].setdefault("claimed", {})

def run_achievements(d: dict) -> list:
    ensure_daily(d)
    ach = d.setdefault("achievements", {})
    stats = d.get("stats", {})
    awarded = []
    for a in ACHIEVEMENTS:
        if ach.get(a["id"]):
            continue
        if a["stat"] == "uniqueCount":
            val = len(stats.get("uniqueCollected", []))
        else:
            val = int(stats.get(a["stat"], 0))
        if val >= a["goal"]:
            ach[a["id"]] = True
            d["balance"] = int(d.get("balance", 0)) + a["reward"]
            awarded.append(a)
    return awarded

def run_daily_quests(d: dict) -> list:
    ensure_daily(d)
    daily = d["daily"]
    claimed = daily.setdefault("claimed", {})
    awarded = []
    for q in DAILY_QUESTS:
        if claimed.get(q["id"]):
            continue
        if int(daily.get(q["stat"], 0)) >= q["goal"]:
            claimed[q["id"]] = True
            d["balance"] = int(d.get("balance", 0)) + q["reward"]
            awarded.append(q)
    return awarded

def push_drop(nick: str, item_name: str, item_img: str | None):
    if not FIREBASE_OK:
        return
    try:
        drop_id = "d_%d_%s" % (int(time.time()*1000), "".join(random.choices("abcdef", k=4)))
        fbdb.reference(f"drop_feed/{drop_id}").set({
            "nick": nick, "itemName": item_name,
            "itemImg": item_img or "", "ts": int(time.time()*1000),
        })
    except Exception:
        log.exception("push_drop error")

# ============================================================
# AIOGRAM
# ============================================================
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()

@dp.message()
async def on_message(message: types.Message):
    if message.text and message.text.startswith("/start"):
        base = WEBHOOK_URL or RENDER_URL or "https://example.com"
        await message.answer(
            "🎮 <b>Brainrots Funny</b>\n\nКрути кейсы, апгрейди брейнротов!",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
                types.InlineKeyboardButton(text="🎮 Открыть", web_app=types.WebAppInfo(url=base))
            ]])
        )

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
    except Exception:
        return
    pack = STARS_PACKAGES.get(payload.get("package_id"))
    if not pack:
        return
    uid = str(message.from_user.id)
    def upd(d):
        d["balance"] = int(d.get("balance", 0)) + pack["coins"]
        d["stats"]["donationsTotal"] = int(d["stats"].get("donationsTotal", 0)) + 1
        d["stats"]["starsSpent"] = int(d["stats"].get("starsSpent", 0)) + pack["stars"]
        d["stats"]["totalEarned"] = int(d["stats"].get("totalEarned", 0)) + pack["coins"]
        run_achievements(d)
        return d
    atomic_update(uid, upd)
    await message.answer(
        f"⭐ <b>Оплата прошла!</b>\n+{pack['coins']} монет начислено."
    )

# ============================================================
# LIFESPAN
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=== STARTUP ===")
    log.info("Bot: %s | Firebase: %s", bot is not None, FIREBASE_OK)
    if bot and (WEBHOOK_URL or RENDER_URL):
        try:
            await bot.set_webhook(
                f"{WEBHOOK_URL or RENDER_URL}/webhook/tg",
                allowed_updates=dp.resolve_used_update_types(),
                drop_pending_updates=True,
            )
            log.info("Webhook set")
        except Exception:
            log.exception("Webhook fail")
    yield
    if bot:
        try: await bot.delete_webhook()
        except: pass
        await bot.session.close()

# ============================================================
# FASTAPI
# ============================================================
app = FastAPI(lifespan=lifespan, title="Brainrots Funny")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE = Path(__file__).parent
if (BASE / "assets").exists():
    app.mount("/assets", StaticFiles(directory=BASE / "assets"), name="assets")

@app.get("/", response_class=HTMLResponse)
async def root():
    idx = BASE / "index.html"
    if not idx.exists():
        return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
    return HTMLResponse(idx.read_text(encoding="utf-8"))

@app.get("/health")
async def health():
    return {"ok": True, "firebase": FIREBASE_OK, "bot": bot is not None}

@app.get("/debug")
async def debug():
    return {
        "bot_token_set": bool(BOT_TOKEN),
        "bot_ready": bot is not None,
        "webhook_url": WEBHOOK_URL or None,
        "render_url": RENDER_URL or None,
        "firebase_ready": FIREBASE_OK,
        "firebase_db": FIREBASE_DB_URL,
        "webhook_path": "/webhook/tg",
    }

@app.get("/api/me")
async def api_me(user=Depends(current_user)):
    uid = str(user["id"])
    data = get_user_data(uid)
    # Обеспечим свежесть daily
    if FIREBASE_OK:
        def upd(d):
            ensure_daily(d)
            run_achievements(d)
            run_daily_quests(d)
            return d
        atomic_update(uid, upd)
        data = get_user_data(uid)
    data["uid"] = uid
    data["serverTime"] = int(time.time() * 1000)
    data["items"] = ITEMS
    data["casePrices"] = CASE_PRICES
    data["caseTitles"] = CASE_TITLES
    data["caseImages"] = CASE_IMAGES
    data["themes"] = THEMES
    data["freeCooldownMs"] = FREE_COOLDOWN_MS
    data["achievements"] = ACHIEVEMENTS
    data["dailyQuests"] = DAILY_QUESTS
    data["rarities"] = RARITIES
    return data

@app.post("/api/open_case")
async def api_open_case(request: Request, user=Depends(current_user)):
    body = await request.json()
    case_type = body.get("case_type", "")
    multiplier = int(body.get("multiplier", 1))
    if case_type not in CASE_LOOT:
        raise HTTPException(400, "unknown case")
    if multiplier < 1 or multiplier > MAX_MULTIPLIER:
        raise HTTPException(400, "bad multiplier")
    if case_type == "free":
        multiplier = 1
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
            if now - int(d.get("lastFree", 0)) < FREE_COOLDOWN_MS:
                return None
            d["lastFree"] = now
        else:
            bal = int(d.get("balance", 0))
            if bal < price:
                return None
            d["balance"] = bal - price
        inv = d.setdefault("inventory", {})
        coins_won = 0
        item_names = []
        for r in results:
            if r["type"] == "coin":
                coins_won += r["amount"]
            else:
                new_item = make_inv_item(r["item"])
                inv[new_item["uid"]] = new_item
                item_names.append(r["item"]["name"])
                uniq = set(d["stats"].get("uniqueCollected", []))
                uniq.add(r["item"]["id"])
                d["stats"]["uniqueCollected"] = list(uniq)
        d["balance"] = int(d.get("balance", 0)) + coins_won
        d["stats"]["casesOpened"] = int(d["stats"].get("casesOpened", 0)) + multiplier
        d["stats"]["totalEarned"] = int(d["stats"].get("totalEarned", 0)) + coins_won
        ensure_daily(d)
        d["daily"]["casesOpened"] = int(d["daily"].get("casesOpened", 0)) + multiplier
        run_achievements(d)
        run_daily_quests(d)
        return d

    atomic_update(uid, upd)

    # drop_feed
    for r in results:
        if r["type"] == "coin":
            push_drop(nick, f"{r['amount']} монет", None)
        else:
            push_drop(nick, r["item"]["name"], r["item"]["img"])

    new_data = get_user_data(uid)
    return {
        "ok": True,
        "results": results,
        "balance": new_data["balance"],
        "inventory": new_data["inventory"],
        "lastFree": new_data.get("lastFree", 0),
        "stats": new_data["stats"],
        "daily": new_data["daily"],
        "achievements": new_data["achievements"],
    }

@app.post("/api/sell_item")
async def api_sell_item(request: Request, user=Depends(current_user)):
    body = await request.json()
    item_uid = body.get("uid", "")
    uid = str(user["id"])
    def upd(d):
        inv = d.get("inventory", {})
        if item_uid not in inv:
            return None
        item = inv[item_uid]
        del inv[item_uid]
        d["balance"] = int(d.get("balance", 0)) + int(item.get("price", 0))
        d["stats"]["itemsSold"] = int(d["stats"].get("itemsSold", 0)) + 1
        ensure_daily(d)
        d["daily"]["itemsSold"] = int(d["daily"].get("itemsSold", 0)) + 1
        run_achievements(d)
        run_daily_quests(d)
        return d
    result = atomic_update(uid, upd)
    if result is None:
        raise HTTPException(400, "sell failed")
    data = get_user_data(uid)
    return {"ok": True, "balance": data["balance"], "inventory": data["inventory"],
            "stats": data["stats"], "daily": data["daily"]}

@app.post("/api/sell_all")
async def api_sell_all(request: Request, user=Depends(current_user)):
    uid = str(user["id"])
    def upd(d):
        inv = d.get("inventory", {})
        total = sum(int(i.get("price", 0)) for i in inv.values())
        count = len(inv)
        if count == 0:
            return None
        d["inventory"] = {}
        d["balance"] = int(d.get("balance", 0)) + total
        d["stats"]["itemsSold"] = int(d["stats"].get("itemsSold", 0)) + count
        ensure_daily(d)
        d["daily"]["itemsSold"] = int(d["daily"].get("itemsSold", 0)) + count
        run_achievements(d)
        run_daily_quests(d)
        return d
    atomic_update(uid, upd)
    data = get_user_data(uid)
    return {"ok": True, "balance": data["balance"], "inventory": data["inventory"],
            "stats": data["stats"], "daily": data["daily"]}

@app.post("/api/upgrade")
async def api_upgrade(request: Request, user=Depends(current_user)):
    body = await request.json()
    input_uids = body.get("input_uids", [])
    target_id = body.get("target_id", "")
    if not isinstance(input_uids, list) or not (1 <= len(input_uids) <= MAX_UPG_INPUTS):
        raise HTTPException(400, "input_uids must be 1..5")
    target = ITEMS_BY_ID.get(target_id)
    if not target:
        raise HTTPException(400, "unknown target")

    uid = str(user["id"])
    data = get_user_data(uid)
    inv = data.get("inventory", {})
    total = 0
    for iuid in input_uids:
        if iuid not in inv:
            raise HTTPException(400, "item not in inventory")
        total += int(inv[iuid]["price"])
    chance = min(MAX_UPGRADE_CHANCE, (total / int(target["price"])) * 100)
    success = random.random() * 100 <= chance

    def upd(d):
        inv2 = d.get("inventory", {})
        for iuid in input_uids:
            if iuid not in inv2:
                return None
        if sum(int(inv2[iuid]["price"]) for iuid in input_uids) != total:
            return None
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
        ensure_daily(d)
        if success:
            d["daily"]["upgradeSuccess"] = int(d["daily"].get("upgradeSuccess", 0)) + 1
        run_achievements(d)
        run_daily_quests(d)
        return d
    atomic_update(uid, upd)

    if success:
        push_drop(user.get("first_name") or "Player", target["name"], target["img"])

    new_data = get_user_data(uid)
    return {"ok": True, "success": success, "chance": chance, "target": target,
            "balance": new_data["balance"], "inventory": new_data["inventory"],
            "stats": new_data["stats"], "daily": new_data["daily"]}

@app.post("/api/pvp")
async def api_pvp(request: Request, user=Depends(current_user)):
    body = await request.json()
    my_uid = body.get("my_uid", "")
    uid = str(user["id"])
    data = get_user_data(uid)
    inv = data.get("inventory", {})
    if my_uid not in inv:
        raise HTTPException(400, "item not in inventory")
    my_item = inv[my_uid]
    price = int(my_item.get("price", 0))
    lo, hi = price / 4, price * 4
    pool = [i for i in ITEMS if lo <= i["price"] <= hi]
    if not pool:
        pool = sorted(ITEMS, key=lambda i: abs(i["price"] - price))[:1]
    bot_item = dict(random.choice(pool))
    won = random.random() < 0.5

    def upd(d):
        inv2 = d.get("inventory", {})
        if my_uid not in inv2:
            return None
        del inv2[my_uid]
        if won:
            new_item = make_inv_item(bot_item)
            inv2[new_item["uid"]] = new_item
            d["stats"]["pvpWins"] = int(d["stats"].get("pvpWins", 0)) + 1
            uniq = set(d["stats"].get("uniqueCollected", []))
            uniq.add(bot_item["id"])
            d["stats"]["uniqueCollected"] = list(uniq)
        else:
            d["stats"]["pvpLosses"] = int(d["stats"].get("pvpLosses", 0)) + 1
        run_achievements(d)
        return d
    atomic_update(uid, upd)

    if won:
        push_drop(user.get("first_name") or "Player", bot_item["name"], bot_item["img"])

    new_data = get_user_data(uid)
    return {"ok": True, "won": won, "my_item": my_item, "bot_item": bot_item,
            "balance": new_data["balance"], "inventory": new_data["inventory"],
            "stats": new_data["stats"]}

@app.post("/api/choose_theme")
async def api_choose_theme(request: Request, user=Depends(current_user)):
    body = await request.json()
    theme_id = body.get("theme_id", "")
    if theme_id not in THEMES:
        raise HTTPException(400, "unknown theme")
    uid = str(user["id"])
    price = int(THEMES[theme_id]["price"])
    def upd(d):
        owned = d.get("themes", {"dark": True})
        if not owned.get(theme_id):
            if int(d.get("balance", 0)) < price:
                return None
            d["balance"] = int(d.get("balance", 0)) - price
            owned[theme_id] = True
            d["themes"] = owned
        d["theme"] = theme_id
        return d
    atomic_update(uid, upd)
    new_data = get_user_data(uid)
    return {"ok": True, "theme": new_data["theme"], "themes": new_data["themes"],
            "balance": new_data["balance"]}

@app.post("/api/claim_referral")
async def api_claim_referral(request: Request, user=Depends(current_user)):
    body = await request.json()
    ref_id = str(body.get("ref_id", "")).strip()
    if not ref_id or ref_id == str(user["id"]):
        raise HTTPException(400, "bad ref")
    uid = str(user["id"])
    def upd(d):
        if d.get("refUsed"):
            return None
        d["refUsed"] = True
        d["balance"] = int(d.get("balance", 0)) + 50
        d["stats"]["totalEarned"] = int(d["stats"].get("totalEarned", 0)) + 50
        run_achievements(d)
        return d
    atomic_update(uid, upd)
    # Пригласившему +100
    def upd2(d):
        d["referrals"] = int(d.get("referrals", 0)) + 1
        d["balance"] = int(d.get("balance", 0)) + 100
        d["stats"]["totalEarned"] = int(d["stats"].get("totalEarned", 0)) + 100
        return d
    atomic_update(ref_id, upd2)
    return {"ok": True, "bonus": 50}

@app.post("/api/create-invoice-link")
async def create_invoice(request: Request, user=Depends(current_user)):
    if not bot:
        raise HTTPException(503, "bot off")
    body = await request.json()
    pack_id = body.get("package_id")
    pack = STARS_PACKAGES.get(pack_id)
    if not pack:
        raise HTTPException(400, "unknown package")
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
    return {"invoice_link": link, "stars": pack["stars"], "coins": pack["coins"]}

@app.post("/webhook/tg")
async def tg_webhook(request: Request):
    if not bot:
        raise HTTPException(503)
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(400)
    try:
        update = types.Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception:
        log.exception("update error")
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
