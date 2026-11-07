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

BOT_USERNAME = "Brain_Funbot"
INIT_DATA_MAX_AGE = 24 * 3600

ADMIN_IDS = {6636765626, 8364667153}

def is_admin(user) -> bool:
    try:
        return int(user["id"]) in ADMIN_IDS
    except Exception:
        return False

RARITIES = {
    "common":    {"id":"common","name":"Common","color":"#6b7280"},
    "uncommon":  {"id":"uncommon","name":"Uncommon","color":"#22c55e"},
    "rare":      {"id":"rare","name":"Rare","color":"#3b82f6"},
    "epic":      {"id":"epic","name":"Epic","color":"#a855f7"},
    "legendary": {"id":"legendary","name":"Legendary","color":"#f59e0b"},
}

# Базовый список всех предметов
DEFAULT_ITEMS = [
    # Старые
    {"id":"trios",    "name":"Los Trios",           "price":4,     "rarity":"common",    "img":"assets/brainrots/los_trios.png", "emoji":"🥉"},
    {"id":"rot67",    "name":"67",                  "price":5,     "rarity":"common",    "img":"assets/brainrots/67.png", "emoji":"6️⃣7️⃣"},
    {"id":"hammy",    "name":"Spinny Hammy",        "price":5,     "rarity":"uncommon",  "img":"assets/brainrots/spinny_hammy.png", "emoji":"🐹"},
    {"id":"candyslap","name":"Candy Slap",          "price":7,     "rarity":"uncommon",  "img":"assets/brainrots/CandySlap.png", "emoji":"🍬"},
    {"id":"noobinis", "name":"Los Noobinis",        "price":7,     "rarity":"rare",      "img":"assets/brainrots/Los_Noobinis.png", "emoji":"🤡"},
    {"id":"tangtang", "name":"Tang Tang Keletang",  "price":8,     "rarity":"rare",      "img":"assets/brainrots/TangTangKeletang.png", "emoji":"🦴"},
    {"id":"lagrande", "name":"La Grande",           "price":9,     "rarity":"epic",      "img":"assets/brainrots/La_Grande_Combinasion.png", "emoji":"🇫🇷"},
    {"id":"tictac",   "name":"Tictac Sahur",        "price":12,    "rarity":"epic",      "img":"assets/brainrots/Tictac-Sahur.png", "emoji":"🕒"},
    {"id":"bacuru",   "name":"Bacuru and Egguru",   "price":12,    "rarity":"epic",      "img":"assets/brainrots/Bacuru_and_Egguru.png", "emoji":"🥚"},
    {"id":"los67",    "name":"Los 67",              "price":12,    "rarity":"epic",      "img":"assets/brainrots/Los_67.png", "emoji":"🎲"},
    {"id":"yinyang",  "name":"Yin Yang Slap",       "price":20,    "rarity":"legendary", "img":"assets/brainrots/YinYangSlap.png", "emoji":"☯️"},
    
    # Новые
    {"id":"bloodrot",    "name":"Bloodrot",             "price":10,    "rarity":"rare",      "img":"assets/brainrots/Bloodrot_Mutation_Icon.webp", "emoji":"🩸"},
    {"id":"burguro",     "name":"Burguro & Fryuro",     "price":15,    "rarity":"epic",      "img":"assets/brainrots/Burguro_And_Fryuro.webp", "emoji":"🍔"},
    {"id":"capitano",    "name":"Capitano Moby",        "price":25,    "rarity":"legendary", "img":"assets/brainrots/Capitano_Moby.webp", "emoji":"🐋"},
    {"id":"cashcard",    "name":"Cash or Card",         "price":8,     "rarity":"rare",      "img":"assets/brainrots/Cash_or_Card_New.webp", "emoji":"💳"},
    {"id":"cerberus",    "name":"Cerberus",             "price":18,    "rarity":"epic",      "img":"assets/brainrots/Cerberus.webp", "emoji":"🐕"},
    {"id":"defmut",      "name":"Default Mutation",     "price":2,     "rarity":"common",    "img":"assets/brainrots/Default_Mutation_Icon.webp", "emoji":"🧬"},
    {"id":"diamut",      "name":"Diamond Mutation",     "price":50,    "rarity":"legendary", "img":"assets/brainrots/Diamond_Mutation_Icon.webp", "emoji":"💎"},
    {"id":"dragon",      "name":"Dragon Cannelloni",    "price":22,    "rarity":"epic",      "img":"assets/brainrots/Dragon_Cannelloni.webp", "emoji":"🐉"},
    {"id":"esok",        "name":"Esok Sekolah",         "price":6,     "rarity":"uncommon",  "img":"assets/brainrots/Esok_Sekolah.webp", "emoji":"🎒"},
    {"id":"garama",      "name":"Garamadundung",        "price":11,    "rarity":"rare",      "img":"assets/brainrots/Garamadundung.webp", "emoji":"🥁"},
    {"id":"goldmut",     "name":"Gold Mutation",        "price":30,    "rarity":"epic",      "img":"assets/brainrots/Gold_Mutation_Icon.webp", "emoji":"🥇"},
    {"id":"hydra",       "name":"Hydra Serpent",        "price":35,    "rarity":"epic",      "img":"assets/brainrots/Hydra_Serpent.webp", "emoji":"🐍"},
    {"id":"ketchuru",    "name":"Ketchuru",             "price":9,     "rarity":"rare",      "img":"assets/brainrots/Ketchuru.webp", "emoji":"🍅"},
    {"id":"ketupat",     "name":"Ketupat Kepat",        "price":8,     "rarity":"uncommon",  "img":"assets/brainrots/KetupatKepat.webp", "emoji":"🍚"},
    {"id":"lassis",      "name":"Las Sis",              "price":14,    "rarity":"epic",      "img":"assets/brainrots/Las_Sis.webp", "emoji":"👭"},
    {"id":"meowl",       "name":"Meowl",                "price":13154, "rarity":"legendary", "img":"assets/brainrots/Meowl.webp", "emoji":"🦉"},
    {"id":"mmcat",       "name":"Money Money Cat",      "price":28,    "rarity":"legendary", "img":"assets/brainrots/Money_Money_Cat.webp", "emoji":"💰"},
    {"id":"mmpuggy",     "name":"Money Money Puggy",    "price":28,    "rarity":"legendary", "img":"assets/brainrots/Money_Money_Puggy.webp", "emoji":"💵"},
    {"id":"pavone",      "name":"Pavoneroventoliero",   "price":16,    "rarity":"epic",      "img":"assets/brainrots/Pavoneroventoliero.webp", "emoji":"🦚"},
    {"id":"hotspot",     "name":"Pot Hotspot",          "price":7,     "rarity":"uncommon",  "img":"assets/brainrots/Pot_Hotspot.webp", "emoji":"🍲"},
    {"id":"rainbowmut",  "name":"Rainbow Mutation",     "price":75,    "rarity":"legendary", "img":"assets/brainrots/Rainbow_Mutation_Icon.webp", "emoji":"🌈"},
    {"id":"strawberry",  "name":"Strawberry Elephant",  "price":15000, "rarity":"legendary", "img":"assets/brainrots/Strawberry_Elephant.webp", "emoji":"🍓"},
    {"id":"skibidi",     "name":"Skibidi Toilet",       "price":13154, "rarity":"legendary", "img":"assets/brainrots/skibidi_toilet.png", "emoji":"🚽"},
]
ITEMS_BY_ID = {i["id"]: i for i in DEFAULT_ITEMS}

CASE_PRICES = {"free": 0, "user": 0, "base": 9, "bro": 25, "allin": 29}

CASE_LOOT = {
    "free": {"coinChance": 70, "coins": [{"amount":1,"weight":50}, {"amount":2,"weight":30}, {"amount":3,"weight":20}], "items": [{"id":"trios","weight":30},{"id":"rot67","weight":30},{"id":"defmut","weight":40}]},
    "user": {"coinChance": 30, "coins": [{"amount":3,"weight":100}], "items": [{"id":"trios","weight":30},{"id":"rot67","weight":30},{"id":"hammy","weight":20},{"id":"candyslap","weight":10},{"id":"esok","weight":10}]},
    "base": {"coinChance": 0, "coins": [], "items": [{"id":"trios","weight":20},{"id":"rot67","weight":20},{"id":"candyslap","weight":20},{"id":"lagrande","weight":15},{"id":"ketupat","weight":15},{"id":"hotspot","weight":10}]},
    "bro": {"coinChance": 0, "coins": [], "items": [{"id":"hammy","weight":15},{"id":"noobinis","weight":15},{"id":"tangtang","weight":15},{"id":"tictac","weight":10},{"id":"bacuru","weight":10},{"id":"los67","weight":10},{"id":"cashcard","weight":8},{"id":"ketchuru","weight":7},{"id":"garama","weight":5},{"id":"yinyang","weight":5}]},
    "allin": {"coinChance": 0, "coins": [], "items": [{"id":"lagrande","weight":40},{"id":"bloodrot","weight":20},{"id":"burguro","weight":15},{"id":"pavone","weight":10},{"id":"cerberus","weight":5},{"id":"dragon","weight":4},{"id":"capitano","weight":3},{"id":"mmpuggy","weight":2},{"id":"strawberry","weight":1}]}
}

EVENT_TYPES = {
    "miniboost": {"name": "Минибуст", "multiplier": 1.5, "color": "#22c55e", "icon": "fa-bolt"},
    "gold":      {"name": "Голд",     "multiplier": 2.0, "color": "#fbbf24", "icon": "fa-star"},
    "diamond":   {"name": "Алмаз",    "multiplier": 3.0, "color": "#06b6d4", "icon": "fa-gem"},
    "bloody":    {"name": "Кровавый", "multiplier": 4.0, "color": "#dc2626", "icon": "fa-fire"},
}

STARS_PACKAGES = {
    "p10":  {"stars":10,  "coins":50,   "bonus":0},
    "p25":  {"stars":25,  "coins":135,  "bonus":8},
    "p50":  {"stars":50,  "coins":300,  "bonus":20},
    "p100": {"stars":100, "coins":650,  "bonus":30},
    "p250": {"stars":250, "coins":1750, "bonus":40},
    "p500": {"stars":500, "coins":4000, "bonus":60},
}

FREE_COOLDOWN_MS = 24 * 3600 * 1000
USER_COOLDOWN_MS = 12 * 3600 * 1000
MAX_UPGRADE_CHANCE = 95.0
MAX_MULTIPLIER = 5
MAX_UPG_INPUTS = 5
MAX_COINFLIP_BET = 1_000_000
MAX_GIVE_COINS = 10_000_000
MAX_EVENT_MINUTES = 60 * 24 * 7
MAX_PROMO_REWARD = 1_000_000
MAX_PROMO_USES = 1_000_000


def init_firebase():
    raw = os.getenv("FIREBASE_CRED_JSON")
    if not raw:
        log.error("FIREBASE_CRED_JSON is missing!")
        return False
    try:
        cred_dict = json.loads(raw)
        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
        if not firebase_admin._apps:
            firebase_admin.initialize_app(
                credentials.Certificate(cred_dict),
                {"databaseURL": FIREBASE_DB_URL},
            )
        log.info("Firebase initialized successfully.")
        return True
    except Exception as e:
        log.exception("Firebase init error: %s", e)
        return False

FIREBASE_OK = init_firebase()

def get_items_dict() -> dict:
    """Возвращает актуальный список предметов из Firebase, либо дефолтный"""
    if not FIREBASE_OK:
        return ITEMS_BY_ID
    try:
        raw = fbdb.reference("meta/items").get()
        if not raw:
            # Если в базе пусто, инициализируем дефолтными
            fbdb.reference("meta/items").set(DEFAULT_ITEMS)
            return ITEMS_BY_ID
        # Преобразуем список в словарь
        return {item["id"]: item for item in raw}
    except Exception as e:
        log.error(f"Error loading items from DB: {e}")
        return ITEMS_BY_ID

def user_ref(uid: str):
    return fbdb.reference(f"users/{uid}")

def _default_user() -> dict:
    return {
        "balance": 0, "inventory": {}, "lastFree": 0, "lastUser": 0,
        "used_promos": {}, "paid_ids": {}, "refUsed": False,
        "stats": {
            "casesOpened": 0, "itemsSold": 0, "upgradeSuccess": 0, "upgradeFail": 0,
            "totalEarned": 0, "donationsTotal": 0, "starsSpent": 0, "uniqueCollected": [],
        },
        "themes": {"dark": True}, "theme": "dark", "referrals": 0,
    }

def _normalize(data: dict) -> dict:
    defaults = _default_user()
    for k, v in defaults.items():
        data.setdefault(k, v)
    for k, v in defaults["stats"].items():
        data["stats"].setdefault(k, v)
    return data

def get_user_data(uid: str, strict: bool = False) -> dict | None:
    if not FIREBASE_OK:
        return None if strict else _default_user()
    data = user_ref(uid).get()
    if data is None and strict:
        return None
    return _normalize(data or {})

def atomic_update(uid: str, updater):
    if not FIREBASE_OK:
        return False

    def tx(current):
        d = _normalize(current or {})
        result = updater(d)
        return result if result is not None else None

    try:
        user_ref(uid).transaction(tx)
        return True
    except Exception:
        log.exception("transaction error uid=%s", uid)
        return False

def verify_init_data(init_data: str) -> dict | None:
    if not init_data or not BOT_TOKEN:
        return None
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=False))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        auth_date = int(parsed.get("auth_date", 0) or 0)
        if not auth_date or (time.time() - auth_date) > INIT_DATA_MAX_AGE:
            return None

        dcs = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received_hash):
            return None
        return json.loads(parsed.get("user", "{}"))
    except Exception:
        return None

async def current_user(x_telegram_init_data: str = Header(None)):
    user = verify_init_data(x_telegram_init_data or "")
    if not user:
        raise HTTPException(401, "invalid initData")
    return user

async def require_admin(user=Depends(current_user)):
    if not is_admin(user):
        raise HTTPException(403, "admin only")
    return user

def weighted_pick(entries):
    total = sum(e.get("weight", 1) for e in entries)
    r = random.random() * total
    for e in entries:
        r -= e.get("weight", 1)
        if r <= 0:
            return e
    return entries[-1]

def roll_drop(case_type: str, items_dict: dict) -> dict:
    cfg = CASE_LOOT[case_type]
    if cfg["coins"] and random.random() * 100 < cfg["coinChance"]:
        picked = weighted_pick(cfg["coins"])
        return {"type": "coin", "amount": picked["amount"]}
    picked = weighted_pick(cfg["items"])
    
    item_data = items_dict.get(picked["id"])
    if not item_data:
        # Фоллбэк, если предмет удалили
        item_data = items_dict.get("trios")
        
    return {"type": "item", "item": dict(item_data)}

def drop_value(drop: dict) -> int:
    if drop["type"] == "coin":
        return int(drop["amount"])
    return int(drop["item"]["price"])

def roll_with_event_luck(case_type: str, luck_mult: float, items_dict: dict) -> dict:
    best = roll_drop(case_type, items_dict)
    extra = max(0.0, luck_mult - 1.0)
    integer_extra = int(extra)
    frac_extra = extra - integer_extra

    for _ in range(integer_extra):
        cand = roll_drop(case_type, items_dict)
        if drop_value(cand) > drop_value(best):
            best = cand
    if random.random() < frac_extra:
        cand = roll_drop(case_type, items_dict)
        if drop_value(cand) > drop_value(best):
            best = cand
    return best

def make_inv_item(item: dict) -> dict:
    uid = "u_%d_%s" % (int(time.time() * 1000), "".join(random.choices("abcdef0123456789", k=6)))
    return {**item, "uid": uid}

def push_drop(nick: str, item_name: str, item_img: str | None, price: int, method: str, user_id: str):
    if not FIREBASE_OK or not item_img:
        return
    try:
        drop_id = "d_%d_%s" % (int(time.time() * 1000), "".join(random.choices("abcdef", k=4)))
        fbdb.reference(f"drop_feed/{drop_id}").set({
            "nick": nick, "itemName": item_name, "itemImg": item_img,
            "price": price, "method": method, "user_id": str(user_id), "ts": int(time.time() * 1000),
        })
    except Exception:
        pass

def get_active_event() -> dict | None:
    if not FIREBASE_OK: return None
    try:
        ev = fbdb.reference("meta/event").get()
        if not ev: return None
        if int(ev.get("endsAt", 0) or 0) < int(time.time() * 1000): return None
        return ev
    except Exception: return None

def get_active_poll() -> dict | None:
    if not FIREBASE_OK: return None
    try:
        p = fbdb.reference("meta/poll").get()
        if not p: return None
        if p.get("endsAt") and int(p["endsAt"]) < int(time.time() * 1000): return None
        return p
    except Exception: return None


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
            ]]),
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
    if not pack: return
    uid = str(message.from_user.id)
    charge_id = sp.telegram_payment_charge_id or sp.provider_payment_charge_id
    if not charge_id: return

    def upd(d):
        paid = d.setdefault("paid_ids", {})
        if charge_id in paid: return None
        paid[charge_id] = int(time.time() * 1000)
        d["balance"] = int(d.get("balance", 0)) + pack["coins"]
        d["stats"]["donationsTotal"] = int(d["stats"].get("donationsTotal", 0)) + 1
        d["stats"]["starsSpent"] = int(d["stats"].get("starsSpent", 0)) + pack["stars"]
        d["stats"]["totalEarned"] = int(d["stats"].get("totalEarned", 0)) + pack["coins"]
        return d

    if atomic_update(uid, upd):
        await message.answer(f"⭐ <b>Оплата прошла!</b>\n+{pack['coins']} монет начислено.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    if bot and (WEBHOOK_URL or RENDER_URL):
        try:
            await bot.set_webhook(f"{WEBHOOK_URL or RENDER_URL}/webhook/tg", allowed_updates=dp.resolve_used_update_types(), drop_pending_updates=True)
        except Exception: pass
    yield
    if bot:
        try:
            await bot.delete_webhook()
            await bot.session.close()
        except Exception: pass

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["*"], allow_headers=["*"])

BASE = Path(__file__).parent
if (BASE / "assets").exists():
    app.mount("/assets", StaticFiles(directory=BASE / "assets"), name="assets")

@app.get("/", response_class=HTMLResponse)
async def root():
    idx = BASE / "index.html"
    if not idx.exists(): return HTMLResponse("<h1>no index</h1>", status_code=404)
    return HTMLResponse(idx.read_text(encoding="utf-8"))

@app.get("/health")
async def health():
    return {"ok": True, "firebase_ok": FIREBASE_OK}

# ============ PUBLIC API ============

@app.get("/api/items")
async def api_items():
    """Отдает список всех предметов для фронтенда"""
    return {"items": list(get_items_dict().values())}

@app.get("/api/me")
async def api_me(user=Depends(current_user)):
    uid = str(user["id"])
    data = get_user_data(uid)
    uname = (user.get("first_name", "") + user.get("last_name", "") + user.get("username", "")).lower()
    data["uid"] = uid
    data["hasUserCase"] = BOT_USERNAME.lower() in uname
    data["isAdmin"] = is_admin(user)
    data["freeCooldownMs"] = FREE_COOLDOWN_MS
    data["userCooldownMs"] = USER_COOLDOWN_MS
    return data

@app.get("/api/event")
async def api_event():
    return {"event": get_active_event()}

@app.get("/api/poll")
async def api_poll(user=Depends(current_user)):
    p = get_active_poll()
    if not p: return {"poll": None}
    uid = str(user["id"])
    my_vote = p.get("voters", {}).get(uid)
    options = p.get("options", [])
    return {
        "poll": {
            "id": p.get("id"), "question": p.get("question"), "options": options,
            "endsAt": p.get("endsAt"), "myVote": my_vote if my_vote is not None else None,
            "totalVotes": sum(int(o.get("votes", 0)) for o in options),
        }
    }

@app.post("/api/poll/vote")
async def api_poll_vote(request: Request, user=Depends(current_user)):
    body = await request.json()
    try: option_index = int(body.get("option_index", -1))
    except: raise HTTPException(400, "bad option")
    if not FIREBASE_OK: raise HTTPException(503, "Database unavailable")

    uid = str(user["id"])
    ref = fbdb.reference("meta/poll")
    result = {"ok": False, "reason": None}

    def tx(current):
        if not current: result["reason"] = "no poll"; return None
        if current.get("endsAt") and int(current["endsAt"]) < int(time.time() * 1000):
            result["reason"] = "poll ended"; return None
        opts = current.get("options", [])
        if option_index < 0 or option_index >= len(opts):
            result["reason"] = "bad option"; return None
        voters = current.setdefault("voters", {})
        if uid in voters: result["reason"] = "already voted"; return None
        voters[uid] = option_index
        opts[option_index]["votes"] = int(opts[option_index].get("votes", 0)) + 1
        result["ok"] = True
        return current

    try: ref.transaction(tx)
    except: raise HTTPException(500, "transaction failed")

    if not result["ok"]: raise HTTPException(400, result["reason"] or "failed")
    return {"ok": True}

@app.post("/api/open_case")
async def api_open_case(request: Request, user=Depends(current_user)):
    body = await request.json()
    case_type = body.get("case_type", "")
    multiplier = int(body.get("multiplier", 1))

    if case_type not in CASE_LOOT: raise HTTPException(400, "Неизвестный кейс")
    if multiplier < 1 or multiplier > MAX_MULTIPLIER: raise HTTPException(400, "Неверный множитель")
    if case_type in ("free", "user"): multiplier = 1

    uid = str(user["id"])
    nick = user.get("first_name") or "Player"
    now = int(time.time() * 1000)
    data = get_user_data(uid)

    if case_type == "free":
        if now - int(data.get("lastFree", 0)) < FREE_COOLDOWN_MS: raise HTTPException(400, "Бесплатный кейс ещё не готов")
        price = 0
    elif case_type == "user":
        uname = (user.get("first_name", "") + user.get("last_name", "") + user.get("username", "")).lower()
        if BOT_USERNAME.lower() not in uname: raise HTTPException(400, "Вы не указали бота в нике!")
        if now - int(data.get("lastUser", 0)) < USER_COOLDOWN_MS: raise HTTPException(400, "Кейс за Юз ещё не готов")
        price = 0
    else:
        price = CASE_PRICES[case_type] * multiplier

    if int(data.get("balance", 0)) < price: raise HTTPException(400, "Недостаточно монет")

    event = get_active_event()
    luck_mult = float(event["multiplier"]) if event else 1.0
    
    # Загружаем актуальный список предметов
    items_dict = get_items_dict()

    results = [roll_with_event_luck(case_type, luck_mult, items_dict) for _ in range(multiplier)]

    def upd(d):
        if price > 0:
            if int(d.get("balance", 0)) < price: return None

        if case_type == "free": d["lastFree"] = now
        elif case_type == "user": d["lastUser"] = now
        else: d["balance"] = int(d.get("balance", 0)) - price

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

    if not atomic_update(uid, upd): raise HTTPException(400, "Не удалось открыть кейс.")

    for r in results:
        if r["type"] != "coin":
            push_drop(nick, r["item"]["name"], r["item"]["img"], r["item"]["price"], "case", uid)

    new_data = get_user_data(uid)
    return {
        "ok": True, "results": results, "balance": new_data["balance"],
        "inventory": new_data["inventory"], "lastFree": new_data.get("lastFree", 0),
        "lastUser": new_data.get("lastUser", 0), "eventBoost": luck_mult,
    }

@app.post("/api/sell_item")
async def api_sell_item(request: Request, user=Depends(current_user)):
    body = await request.json()
    item_uid = body.get("uid", "")
    if not item_uid: raise HTTPException(400, "Не указан предмет")
    uid = str(user["id"])

    def upd(d):
        inv = d.get("inventory", {})
        if item_uid not in inv: return None
        item = inv.pop(item_uid)
        d["balance"] = int(d.get("balance", 0)) + int(item.get("price", 0))
        d["stats"]["itemsSold"] = int(d["stats"].get("itemsSold", 0)) + 1
        return d

    if not atomic_update(uid, upd): raise HTTPException(400, "Ошибка продажи")
    data = get_user_data(uid)
    return {"ok": True, "balance": data["balance"], "inventory": data["inventory"]}

@app.post("/api/sell_all")
async def api_sell_all(request: Request, user=Depends(current_user)):
    uid = str(user["id"])

    def upd(d):
        inv = d.get("inventory", {})
        if not inv: return None
        total = sum(int(i.get("price", 0)) for i in inv.values())
        count = len(inv)
        d["inventory"] = {}
        d["balance"] = int(d.get("balance", 0)) + total
        d["stats"]["itemsSold"] = int(d["stats"].get("itemsSold", 0)) + count
        return d

    if not atomic_update(uid, upd): raise HTTPException(400, "Нечего продавать")
    data = get_user_data(uid)
    return {"ok": True, "balance": data["balance"], "inventory": data["inventory"]}

@app.post("/api/upgrade")
async def api_upgrade(request: Request, user=Depends(current_user)):
    body = await request.json()
    input_uids = body.get("input_uids", [])
    target_id = body.get("target_id", "")

    if not isinstance(input_uids, list) or not (1 <= len(input_uids) <= MAX_UPG_INPUTS):
        raise HTTPException(400, f"Выберите от 1 до {MAX_UPG_INPUTS} предметов")
    if len(set(input_uids)) != len(input_uids): raise HTTPException(400, "Дубликаты предметов")

    items_dict = get_items_dict()
    target = items_dict.get(target_id)
    if not target: raise HTTPException(400, "Неизвестная цель")

    uid = str(user["id"])
    data = get_user_data(uid)
    inv = data.get("inventory", {})

    total = 0
    for iuid in input_uids:
        if iuid not in inv: raise HTTPException(400, "Предмет не найден в инвентаре")
        total += int(inv[iuid]["price"])

    if total <= 0: raise HTTPException(400, "Сумма предметов некорректна")
    if int(target["price"]) <= total: raise HTTPException(400, "Цель должна стоить больше суммы")

    chance = min(MAX_UPGRADE_CHANCE, (total / int(target["price"])) * 100)
    success = random.random() * 100 <= chance

    def upd(d):
        inv2 = d.get("inventory", {})
        for iuid in input_uids:
            if iuid not in inv2: return None
        for iuid in input_uids: del inv2[iuid]

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

    if not atomic_update(uid, upd): raise HTTPException(400, "Ошибка апгрейда")

    if success:
        push_drop(user.get("first_name") or "Player", target["name"], target["img"], target["price"], "upgrade", uid)

    new_data = get_user_data(uid)
    return {
        "ok": True, "success": success, "chance": chance,
        "target": target, "balance": new_data["balance"], "inventory": new_data["inventory"],
    }

@app.post("/api/coinflip")
async def api_coinflip(request: Request, user=Depends(current_user)):
    body = await request.json()
    bet = int(body.get("bet", 0))
    choice = body.get("choice", "heads")

    if choice not in ("heads", "tails"): raise HTTPException(400, "Неверный выбор")
    if bet <= 0: raise HTTPException(400, "Ставка должна быть больше 0")
    if bet > MAX_COINFLIP_BET: raise HTTPException(400, "Слишком большая ставка")

    uid = str(user["id"])
    data = get_user_data(uid)
    if int(data.get("balance", 0)) < bet: raise HTTPException(400, "Недостаточно монет")

    won = random.random() < 0.5
    coin_result = choice if won else ("tails" if choice == "heads" else "heads")

    def upd(d):
        bal = int(d.get("balance", 0))
        if bal < bet: return None
        d["balance"] = bal - bet
        if won: d["balance"] += bet * 2
        return d

    if not atomic_update(uid, upd): raise HTTPException(400, "Ошибка ставки")

    new_data = get_user_data(uid)
    return {"ok": True, "won": won, "result": coin_result, "balance": new_data["balance"]}

@app.post("/api/claim_promo")
async def api_claim_promo(request: Request, user=Depends(current_user)):
    body = await request.json()
    code = str(body.get("code", "")).strip().upper()
    if not code: raise HTTPException(400, "Введите код")
    if not FIREBASE_OK: raise HTTPException(503, "База данных недоступна")

    uid = str(user["id"])
    data = get_user_data(uid)
    if code in data.get("used_promos", {}): raise HTTPException(400, "Вы уже использовали этот промокод")

    promo_ref = fbdb.reference(f"promos/{code}")
    promo_data = promo_ref.get()
    if not promo_data: raise HTTPException(404, "Промокод не найден")

    max_uses = int(promo_data.get("max_uses", 0))
    used = int(promo_data.get("used", 0))
    reward = int(promo_data.get("reward", 0))

    if used >= max_uses: raise HTTPException(400, "Промокод больше не активен")

    def tx_promo(current):
        if current is None: return None
        if int(current.get("used", 0)) >= int(current.get("max_uses", 0)): return None
        current["used"] = int(current.get("used", 0)) + 1
        return current

    try: promo_ref.transaction(tx_promo)
    except: raise HTTPException(400, "Не удалось активировать промокод")

    def upd(d):
        d["used_promos"] = d.get("used_promos", {})
        d["used_promos"][code] = True
        d["balance"] = int(d.get("balance", 0)) + reward
        d["stats"]["totalEarned"] = int(d["stats"].get("totalEarned", 0)) + reward
        return d

    if not atomic_update(uid, upd): raise HTTPException(400, "Ошибка активации")

    new_data = get_user_data(uid)
    return {"ok": True, "reward": reward, "balance": new_data["balance"]}

@app.post("/api/claim_referral")
async def api_claim_referral(request: Request, user=Depends(current_user)):
    body = await request.json()
    ref_id = str(body.get("ref_id", "")).strip()
    if not ref_id or ref_id == str(user["id"]): raise HTTPException(400, "Неверная ссылка")

    uid = str(user["id"])
    state = {"ok": False}

    def upd(d):
        if d.get("refUsed"): return None
        if d.get("stats", {}).get("casesOpened", 0) > 0: return None
        d["refUsed"] = True
        d["balance"] = int(d.get("balance", 0)) + 2
        d["stats"]["totalEarned"] = int(d["stats"].get("totalEarned", 0)) + 2
        state["ok"] = True
        return d

    if not atomic_update(uid, upd) or not state["ok"]: raise HTTPException(400, "Рефка уже использована или вы уже играли")

    def upd2(d):
        d["referrals"] = int(d.get("referrals", 0)) + 1
        d["balance"] = int(d.get("balance", 0)) + 4
        d["stats"]["totalEarned"] = int(d["stats"].get("totalEarned", 0)) + 4
        return d

    atomic_update(ref_id, upd2)
    return {"ok": True, "bonus": 2}

@app.get("/api/user_profile/{target_uid}")
async def api_user_profile(target_uid: str, user=Depends(current_user)):
    if not target_uid or target_uid == "undefined" or target_uid == "null":
        raise HTTPException(400, "Неверный ID игрока")
    
    data = get_user_data(target_uid, strict=True)
    if data is None: raise HTTPException(404, "Игрок не найден в базе данных")

    return {
        "uid": target_uid, "balance": int(data.get("balance", 0) or 0),
        "inventory": data.get("inventory") or {}, "stats": data.get("stats") or {},
        "lastFree": int(data.get("lastFree", 0) or 0), "lastUser": int(data.get("lastUser", 0) or 0),
    }

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
            description=f"Пакет монет для Brainrots Funny",
            payload=payload, currency="XTR",
            prices=[LabeledPrice(label=f"{pack['coins']} coins", amount=pack["stars"])],
            provider_token="",
        )
    except Exception as e:
        log.exception("create_invoice error")
        raise HTTPException(500, str(e))
    return {"invoice_link": link, "stars": pack["stars"], "coins": pack["coins"]}


# ============ ADMIN API ============

@app.get("/api/admin/items")
async def admin_get_items(user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    items_dict = get_items_dict()
    return {"items": list(items_dict.values())}

@app.post("/api/admin/item/update")
async def admin_update_item(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    item_id = body.get("item_id")
    new_price = int(body.get("price", 0))
    new_rarity = body.get("rarity")

    if not item_id: raise HTTPException(400, "no item_id")
    if new_price < 0: raise HTTPException(400, "Цена не может быть отрицательной")
    if new_rarity not in RARITIES: raise HTTPException(400, "Неверная редкость")

    items_dict = get_items_dict()
    if item_id not in items_dict: raise HTTPException(404, "Предмет не найден")

    # Обновляем предмет
    items_dict[item_id]["price"] = new_price
    items_dict[item_id]["rarity"] = new_rarity

    # Сохраняем весь список обратно в базу
    fbdb.reference("meta/items").set(list(items_dict.values()))
    return {"ok": True}

@app.post("/api/admin/event")
async def admin_set_event(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    ev_type = body.get("type")

    if ev_type is None or ev_type == "":
        fbdb.reference("meta/event").delete()
        return {"ok": True, "event": None}

    if ev_type not in EVENT_TYPES: raise HTTPException(400, "unknown event type")

    try: duration_minutes = int(body.get("duration_minutes", 60))
    except: raise HTTPException(400, "bad duration")
    if duration_minutes < 1 or duration_minutes > MAX_EVENT_MINUTES: raise HTTPException(400, f"duration 1..{MAX_EVENT_MINUTES}")

    now = int(time.time() * 1000)
    meta = EVENT_TYPES[ev_type]
    ev = {
        "type": ev_type, "name": meta["name"], "multiplier": meta["multiplier"],
        "color": meta["color"], "icon": meta["icon"], "startedAt": now,
        "endsAt": now + duration_minutes * 60 * 1000, "startedBy": str(user["id"]),
    }
    fbdb.reference("meta/event").set(ev)
    return {"ok": True, "event": ev}

@app.post("/api/admin/promo")
async def admin_create_promo(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    code = str(body.get("code", "")).strip().upper()
    reward = int(body.get("reward", 0))
    max_uses = int(body.get("max_uses", 0))

    if not code or len(code) < 2 or len(code) > 32: raise HTTPException(400, "Код 2..32 символа")
    if not all(c.isalnum() or c in "_-" for c in code): raise HTTPException(400, "Только буквы, цифры, _ и -")
    if reward <= 0 or reward > MAX_PROMO_REWARD: raise HTTPException(400, f"Награда 1..{MAX_PROMO_REWARD}")
    if max_uses < 1 or max_uses > MAX_PROMO_USES: raise HTTPException(400, f"Использований 1..{MAX_PROMO_USES}")

    ref = fbdb.reference(f"promos/{code}")
    if ref.get(): raise HTTPException(400, "Промокод уже существует")

    ref.set({
        "reward": reward, "max_uses": max_uses, "used": 0,
        "createdAt": int(time.time() * 1000), "createdBy": str(user["id"]),
    })
    return {"ok": True, "code": code, "reward": reward, "max_uses": max_uses}

@app.get("/api/admin/promos")
async def admin_list_promos(user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    try: promos = fbdb.reference("promos").get() or {}
    except: promos = {}
    result = []
    for code, p in promos.items():
        if not isinstance(p, dict): continue
        result.append({
            "code": code, "reward": p.get("reward", 0), "used": p.get("used", 0),
            "max_uses": p.get("max_uses", 0), "createdAt": p.get("createdAt", 0),
        })
    result.sort(key=lambda x: x.get("createdAt", 0), reverse=True)
    return {"promos": result}

@app.post("/api/admin/promo/delete")
async def admin_delete_promo(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    code = str(body.get("code", "")).strip().upper()
    if not code: raise HTTPException(400, "no code")
    fbdb.reference(f"promos/{code}").delete()
    return {"ok": True}

@app.post("/api/admin/give")
async def admin_give(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    target_id = str(body.get("user_id", "")).strip()
    coins = int(body.get("coins", 0) or 0)
    item_id = body.get("item_id")

    if not target_id: raise HTTPException(400, "Укажите Telegram ID")
    if coins == 0 and not item_id: raise HTTPException(400, "Нечего выдавать")
    if coins < 0: raise HTTPException(400, "Монет не может быть отрицательно")
    if coins > MAX_GIVE_COINS: raise HTTPException(400, f"Максимум {MAX_GIVE_COINS} монет")
    
    items_dict = get_items_dict()
    if item_id and item_id not in items_dict: raise HTTPException(400, "Неизвестный предмет")

    gave = {"coins": 0, "item": None}

    def upd(d):
        if coins > 0:
            d["balance"] = int(d.get("balance", 0)) + coins
            d["stats"]["totalEarned"] = int(d["stats"].get("totalEarned", 0)) + coins
            gave["coins"] = coins
        if item_id:
            new_item = make_inv_item(items_dict[item_id])
            d.setdefault("inventory", {})[new_item["uid"]] = new_item
            gave["item"] = new_item
        return d

    if not atomic_update(target_id, upd): raise HTTPException(400, "Не удалось обновить пользователя")
    return {"ok": True, "gave": gave, "target_id": target_id}

@app.post("/api/admin/reset_cooldowns")
async def admin_reset_cooldowns(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    target_id = str(body.get("user_id", "")).strip()
    if not target_id: raise HTTPException(400, "Укажите user_id")

    def upd(d):
        d["lastFree"] = 0
        d["lastUser"] = 0
        return d

    if not atomic_update(target_id, upd): raise HTTPException(400, "Не удалось сбросить кулдауны")
    return {"ok": True, "user_id": target_id}

@app.post("/api/admin/poll")
async def admin_create_poll(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    question = str(body.get("question", "")).strip()
    options = body.get("options", [])
    duration_minutes = body.get("duration_minutes")

    if not question or len(question) > 300: raise HTTPException(400, "Вопрос 1..300 символов")
    if not isinstance(options, list) or len(options) < 2 or len(options) > 6: raise HTTPException(400, "Нужно 2..6 вариантов")

    cleaned = [str(o).strip() for o in options]
    for o in cleaned:
        if not o or len(o) > 100: raise HTTPException(400, "Каждый вариант 1..100 символов")

    now = int(time.time() * 1000)
    ends_at = None
    if duration_minutes:
        try: dm = int(duration_minutes)
        except: raise HTTPException(400, "bad duration")
        if dm < 1 or dm > 60 * 24 * 30: raise HTTPException(400, "Длительность 1..43200 минут")
        ends_at = now + dm * 60 * 1000

    poll = {
        "id": "poll_" + str(now), "question": question,
        "options": [{"text": o, "votes": 0} for o in cleaned],
        "createdAt": now, "endsAt": ends_at, "createdBy": str(user["id"]), "voters": {},
    }
    fbdb.reference("meta/poll").set(poll)
    return {"ok": True}

@app.post("/api/admin/poll/end")
async def admin_end_poll(user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    fbdb.reference("meta/poll").delete()
    return {"ok": True}

@app.get("/api/admin/stats")
async def admin_stats(user=Depends(require_admin)):
    if not FIREBASE_OK:
        return {"firebase_ok": False, "total_users": 0, "total_balance": 0, "total_opened": 0, "total_inventory_items": 0, "total_unique_collected": 0, "active_24h": 0, "total_referrals": 0, "total_donations": 0, "total_stars": 0, "top_by_balance": [], "top_by_opened": [], "recent_drops": [], "recent_count_1h": 0, "recent_count_24h": 0, "active_event": None, "active_poll": None}

    try: users = fbdb.reference("users").get() or {}
    except: users = {}

    total_users = 0; total_balance = 0; total_opened = 0; total_inventory_items = 0; total_unique_collected = 0; active_24h = 0; total_referrals = 0; total_donations = 0; total_stars = 0
    user_list = []
    now_ms = int(time.time() * 1000); day_ago = now_ms - 24 * 3600 * 1000

    for uid, u in users.items():
        if not isinstance(u, dict): continue
        total_users += 1
        try: bal = int(u.get("balance", 0) or 0)
        except: bal = 0
        total_balance += bal
        stats = u.get("stats")
        if not isinstance(stats, dict): stats = {}
        try: opened = int(stats.get("casesOpened", 0) or 0)
        except: opened = 0
        total_opened += opened
        uniq = stats.get("uniqueCollected")
        if isinstance(uniq, list): total_unique_collected += len(uniq)
        try: total_donations += int(stats.get("donationsTotal", 0) or 0)
        except: pass
        try: total_stars += int(stats.get("starsSpent", 0) or 0)
        except: pass
        inv = u.get("inventory")
        if isinstance(inv, dict): total_inventory_items += len(inv)
        try: total_referrals += int(u.get("referrals", 0) or 0)
        except: pass
        try: last_free = int(u.get("lastFree", 0) or 0)
        except: last_free = 0
        try: last_user = int(u.get("lastUser", 0) or 0)
        except: last_user = 0
        last_activity = max(last_free, last_user)
        if last_activity > day_ago: active_24h += 1
        user_list.append({"uid": str(uid), "balance": bal, "opened": opened})

    top_by_balance = sorted(user_list, key=lambda x: x["balance"], reverse=True)[:5]
    top_by_opened = sorted(user_list, key=lambda x: x["opened"], reverse=True)[:5]

    try:
        drops = fbdb.reference("drop_feed").get() or {}
        drops_list = list(drops.values()) if isinstance(drops, dict) else []
        def get_ts(d):
            if not isinstance(d, dict): return 0
            try: return int(d.get("ts", 0))
            except: return 0
        recent = sorted(drops_list, key=lambda d: get_ts(d), reverse=True)[:20]
        recent_count_1h = sum(1 for d in drops_list if get_ts(d) > now_ms - 3600 * 1000)
        recent_count_24h = sum(1 for d in drops_list if get_ts(d) > day_ago)
    except: recent = []; recent_count_1h = 0; recent_count_24h = 0

    ev = get_active_event()
    poll = get_active_poll()

    return {
        "firebase_ok": True, "total_users": total_users, "total_balance": total_balance, "total_opened": total_opened,
        "total_inventory_items": total_inventory_items, "total_unique_collected": total_unique_collected,
        "active_24h": active_24h, "total_referrals": total_referrals, "total_donations": total_donations, "total_stars": total_stars,
        "top_by_balance": top_by_balance, "top_by_opened": top_by_opened, "recent_drops": recent,
        "recent_count_1h": recent_count_1h, "recent_count_24h": recent_count_24h, "active_event": ev,
        "active_poll": {"question": poll.get("question") if poll else None, "endsAt": poll.get("endsAt") if poll else None, "totalVotes": sum(int(o.get("votes", 0)) for o in poll.get("options", [])) if poll else 0} if poll else None,
    }

@app.post("/webhook/tg")
async def tg_webhook(request: Request):
    if not bot: raise HTTPException(503)
    try: data = await request.json()
    except: raise HTTPException(400)
    try:
        update = types.Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception: log.exception("webhook feed error")
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
