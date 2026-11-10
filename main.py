import os, json, hmac, hashlib, logging, random, time, re, uuid
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl
from pathlib import Path
from typing import Optional

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

HARDCODED_ADMIN_IDS = {6636765626, 8364667153}

RARITIES = {
    "common":    {"id":"common","name":"Common","color":"#6b7280"},
    "uncommon":  {"id":"uncommon","name":"Uncommon","color":"#22c55e"},
    "rare":      {"id":"rare","name":"Rare","color":"#3b82f6"},
    "epic":      {"id":"epic","name":"Epic","color":"#a855f7"},
    "legendary": {"id":"legendary","name":"Legendary","color":"#f59e0b"},
}

DEFAULT_ITEMS = [
    {"id":"trios",    "name":"Los Trios",           "price":4,     "rarity":"common",    "img":"assets/brainrots/los_trios.png", "emoji":"🥉"},
    {"id":"rot67",    "name":"67",                  "price":5,     "rarity":"common",    "img":"assets/brainrots/67.png", "emoji":"6️⃣7️⃣"},
    {"id":"hammy",    "name":"Spinny Hammy",        "price":5,     "rarity":"uncommon",  "img":"assets/brainrots/spinny_hammy.png", "emoji":"🐹"},
    {"id":"candyslap","name":"Candy Slap",          "price":7,     "rarity":"uncommon",  "img":"assets/brainrots/CandySlap.png", "emoji":"🍬"},
    {"id":"noobinis", "name":"Los Noobinis",        "price":5,     "rarity":"rare",      "img":"assets/brainrots/Los_Noobinis.png", "emoji":"🤡"},
    {"id":"tangtang", "name":"Tang Tang Keletang",  "price":17,    "rarity":"rare",      "img":"assets/brainrots/TangTangKeletang.png", "emoji":"🦴"},
    {"id":"lagrande", "name":"La Grande",           "price":9,     "rarity":"epic",      "img":"assets/brainrots/La_Grande_Combinasion.png", "emoji":"🇫🇷"},
    {"id":"tictac",   "name":"Tictac Sahur",        "price":12,    "rarity":"epic",      "img":"assets/brainrots/Tictac-Sahur.png", "emoji":"🕒"},
    {"id":"bacuru",   "name":"Bacuru and Egguru",   "price":6,     "rarity":"epic",      "img":"assets/brainrots/Bacuru_and_Egguru.png", "emoji":"🥚"},
    {"id":"los67",    "name":"Los 67",              "price":6,     "rarity":"epic",      "img":"assets/brainrots/Los_67.png", "emoji":"🎲"},
    {"id":"yinyang",  "name":"Yin Yang Slap",       "price":17,    "rarity":"legendary", "img":"assets/brainrots/YinYangSlap.png", "emoji":"☯️"},
    {"id":"burguro",     "name":"Burguro & Fryuro",     "price":90,    "rarity":"epic",      "img":"assets/brainrots/Burguro_And_Fryuro.webp", "emoji":"🍔"},
    {"id":"capitano",    "name":"Capitano Moby",        "price":125,   "rarity":"legendary", "img":"assets/brainrots/Capitano_Moby.webp", "emoji":"🐋"},
    {"id":"cashcard",    "name":"Cash or Card",         "price":63,    "rarity":"rare",      "img":"assets/brainrots/Cash_or_Card_New.webp", "emoji":"💳"},
    {"id":"cerberus",    "name":"Cerberus",             "price":125,   "rarity":"epic",      "img":"assets/brainrots/Cerberus.webp", "emoji":"🐕"},
    {"id":"dragon",      "name":"Dragon Cannelloni",    "price":1067,  "rarity":"epic",      "img":"assets/brainrots/Dragon_Cannelloni.webp", "emoji":"🐉"},
    {"id":"esok",        "name":"Esok Sekolah",         "price":16,    "rarity":"uncommon",  "img":"assets/brainrots/Esok_Sekolah.webp", "emoji":"🎒"},
    {"id":"garama",      "name":"Garamadundung",        "price":64,    "rarity":"rare",      "img":"assets/brainrots/Garamadundung.webp", "emoji":"🥁"},
    {"id":"hydra",       "name":"Hydra Serpent",        "price":350,   "rarity":"epic",      "img":"assets/brainrots/Hydra_Serpent.webp", "emoji":"🐍"},
    {"id":"ketchuru",    "name":"Ketchuru",             "price":29,    "rarity":"rare",      "img":"assets/brainrots/Ketchuru.webp", "emoji":"🍅"},
    {"id":"ketupat",     "name":"Ketupat Kepat",        "price":28,    "rarity":"uncommon",  "img":"assets/brainrots/KetupatKepat.webp", "emoji":"🍚"},
    {"id":"lassis",      "name":"Las Sis",              "price":14,    "rarity":"epic",      "img":"assets/brainrots/Las_Sis.webp", "emoji":"👭"},
    {"id":"meowl",       "name":"Meowl",                "price":14154, "rarity":"legendary", "img":"assets/brainrots/Meowl.webp", "emoji":"🦉"},
    {"id":"mmcat",       "name":"Money Money Cat",      "price":29,    "rarity":"legendary", "img":"assets/brainrots/Money_Money_Cat.webp", "emoji":"💰"},
    {"id":"mmpuggy",     "name":"Money Money Puggy",    "price":28,    "rarity":"legendary", "img":"assets/brainrots/Money_Money_Puggy.webp", "emoji":"💵"},
    {"id":"pavone",      "name":"Pavoneroventoliero",   "price":38,    "rarity":"epic",      "img":"assets/brainrots/Pavoneroventoliero.webp", "emoji":"🦚"},
    {"id":"hotspot",     "name":"Pot Hotspot",          "price":14,    "rarity":"uncommon",  "img":"assets/brainrots/Pot_Hotspot.webp", "emoji":"🍲"},
    {"id":"strawberry",  "name":"Strawberry Elephant",  "price":15067, "rarity":"legendary", "img":"assets/brainrots/Strawberry_Elephant.webp", "emoji":"🍓"},
    {"id":"skibidi",     "name":"Skibidi Toilet",       "price":13229, "rarity":"legendary", "img":"assets/brainrots/skibidi_toilet.png", "emoji":"🚽"},
    {"id":"pegas",       "name":"Pegasus",              "price":5000,  "rarity":"legendary", "img":"assets/brainrots/pegas.webp", "emoji":"🦄"}, # Добавлен Пегас
]

DEFAULT_SECTIONS = [
    {"id": "free_cases",   "name": "Free Cases", "order": 0, "icon": "🆓"},
    {"id": "shop",         "name": "Магазин",    "order": 1, "icon": "🛒"},
    {"id": "allin_section","name": "ALL IN",     "order": 2, "icon": "🎰"},
]

DEFAULT_CASES = {
    "free":    {"id":"free","name":"Ежедневный","section":"free_cases","price":0,"img":"assets/cases/free.png","emoji":"🎁","order":0,
                "coinChance":70,"coins":[{"amount":1,"weight":50},{"amount":2,"weight":30},{"amount":3,"weight":20}],
                "items":[{"id":"trios","weight":100}]},
    "user":    {"id":"user","name":"Кейс за Юз","section":"free_cases","price":0,"img":"assets/cases/user.png","emoji":"👤","order":1,
                "coinChance":30,"coins":[{"amount":3,"weight":100}],
                "items":[{"id":"trios","weight":30},{"id":"rot67","weight":30},{"id":"hammy","weight":20},{"id":"candyslap","weight":20}]},
    "starter": {"id":"starter","name":"Стартер","section":"shop","price":10,"img":"assets/cases/base.png","emoji":"📦","order":0,
                "coinChance":0,"coins":[],
                "items":[{"id":"trios","weight":20},{"id":"rot67","weight":15},{"id":"hammy","weight":15},{"id":"candyslap","weight":10},
                         {"id":"tictac","weight":20},{"id":"esok","weight":15},{"id":"ketchuru","weight":4.9},{"id":"burguro","weight":0.1}]},
    "meme":    {"id":"meme","name":"Мемный","section":"shop","price":50,"img":"assets/cases/bro.png","emoji":"💎","order":1,
                "coinChance":0,"coins":[],
                "items":[{"id":"tictac","weight":20},{"id":"ketupat","weight":20},{"id":"pavone","weight":20},
                         {"id":"cashcard","weight":30},{"id":"garama","weight":8.8},{"id":"burguro","weight":1},{"id":"capitano","weight":0.2}]},
    "zoo":     {"id":"zoo","name":"Зоопарк","section":"shop","price":100,"img":"assets/cases/allin.png","emoji":"🦁","order":2,
                "coinChance":0,"coins":[],
                "items":[{"id":"ketchuru","weight":20},{"id":"pavone","weight":20},{"id":"garama","weight":20},
                         {"id":"cerberus","weight":35},{"id":"hydra","weight":4.9},{"id":"dragon","weight":0.099},{"id":"skibidi","weight":0.001}]},
    "mafia":   {"id":"mafia","name":"Мафия","section":"shop","price":250,"img":"assets/cases/user.png","emoji":"💼","order":3,
                "coinChance":0,"coins":[],
                "items":[{"id":"garama","weight":20},{"id":"burguro","weight":20},{"id":"capitano","weight":20},
                         {"id":"hydra","weight":38},{"id":"dragon","weight":1.95},{"id":"skibidi","weight":0.04},{"id":"meowl","weight":0.009},{"id":"strawberry","weight":0.001}]},
    "allin":   {"id":"allin","name":"ALL IN","section":"allin_section","price":29,"img":"assets/cases/allin.png","emoji":"🎰","order":0,
                "coinChance":0,"coins":[],
                "items":[{"id":"trios","weight":99.9},{"id":"skibidi","weight":0.1}]},
}

EVENT_TYPES = {
    "miniboost": {"name": "Минибуст", "multiplier": 1.5, "color": "#22c55e", "img": "assets/brainrots/Default_Mutation_Icon.webp"},
    "gold":      {"name": "Голд",     "multiplier": 2.0, "color": "#fbbf24", "img": "assets/brainrots/Gold_Mutation_Icon.webp"},
    "diamond":   {"name": "Алмаз",    "multiplier": 3.0, "color": "#06b6d4", "img": "assets/brainrots/Diamond_Mutation_Icon.webp"},
    "bloody":    {"name": "Кровавый", "multiplier": 4.0, "color": "#dc2626", "img": "assets/brainrots/Bloodrot_Mutation_Icon.webp"},
}

STARS_PACKAGES = {
    "p10":  {"stars":10,  "coins":15,   "bonus":0},
    "p25":  {"stars":25,  "coins":37,   "bonus":0},
    "p50":  {"stars":50,  "coins":75,   "bonus":0},
    "p100": {"stars":100, "coins":150,  "bonus":0},
    "p250": {"stars":250, "coins":375,  "bonus":0},
    "p500": {"stars":500, "coins":750,  "bonus":0},
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

# ---> ИЗМЕНЕНИЕ: Обновленный список доступных к выводу <---
DEFAULT_WITHDRAWABLE = {"garama", "burguro", "pegas", "cerberus", "dragon", "skibidi", "meowl", "strawberry"}
MIN_WITHDRAW_VALUE = 128  # 2 garamas = 2*64
GARAMA_PRICE = 64

REFERRAL_LEVELS = [
    {"level": 1, "invited": 0,    "pct": 5},
    {"level": 2, "invited": 50,   "pct": 10},
    {"level": 3, "invited": 200,  "pct": 15},
    {"level": 4, "invited": 500,  "pct": 20},
    {"level": 5, "invited": 1000, "pct": 25},
    {"level": 6, "invited": 2000, "pct": 30},
    {"level": 7, "invited": 5000, "pct": 35},
    {"level": 8, "invited": 10000,"pct": 40},
    {"level": 9, "invited": 25000,"pct": 45},
    {"level": 10,"invited": 50000,"pct": 50},
]

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
    if not FIREBASE_OK:
        return {i["id"]: i for i in DEFAULT_ITEMS}
    try:
        overrides = fbdb.reference("meta/items_overrides").get() or {}
        extra = fbdb.reference("meta/items_extra").get() or {}
        final_dict = {}
        for item in DEFAULT_ITEMS:
            base_item = dict(item)
            if base_item["id"] in overrides:
                ovr = overrides[base_item["id"]]
                if "price" in ovr: base_item["price"] = int(ovr["price"])
                if "rarity" in ovr: base_item["rarity"] = ovr["rarity"]
                if "name" in ovr: base_item["name"] = ovr["name"]
                if "img" in ovr: base_item["img"] = ovr["img"]
                if "emoji" in ovr: base_item["emoji"] = ovr["emoji"]
                if ovr.get("deleted"): continue
            final_dict[base_item["id"]] = base_item
        for iid, it in extra.items():
            if isinstance(it, dict) and not it.get("deleted"):
                final_dict[iid] = {
                    "id": iid, "name": it.get("name", iid),
                    "price": int(it.get("price", 1)),
                    "rarity": it.get("rarity", "common"),
                    "img": it.get("img", ""), "emoji": it.get("emoji", "🧠"),
                }
        return final_dict
    except Exception as e:
        log.error(f"Error loading items from DB: {e}")
        return {i["id"]: i for i in DEFAULT_ITEMS}

def get_cases_dict() -> dict:
    if not FIREBASE_OK:
        return {cid: dict(c) for cid, c in DEFAULT_CASES.items()}
    try:
        db_cases = fbdb.reference("meta/cases").get() or {}
        final = {}
        for cid, c in DEFAULT_CASES.items():
            base = dict(c)
            if cid in db_cases and isinstance(db_cases[cid], dict):
                ovr = db_cases[cid]
                for k, v in ovr.items():
                    if v is None: continue
                    base[k] = v
                if ovr.get("deleted"): continue
            final[cid] = base
        for cid, c in db_cases.items():
            if cid not in DEFAULT_CASES and isinstance(c, dict) and not c.get("deleted"):
                final[cid] = c
        return final
    except Exception as e:
        log.error(f"Error loading cases: {e}")
        return {cid: dict(c) for cid, c in DEFAULT_CASES.items()}

def get_sections_list() -> list:
    if not FIREBASE_OK:
        return [dict(s) for s in DEFAULT_SECTIONS]
    try:
        db_sections = fbdb.reference("meta/sections").get() or {}
        final = {}
        for s in DEFAULT_SECTIONS:
            base = dict(s)
            if s["id"] in db_sections and isinstance(db_sections[s["id"]], dict):
                ovr = db_sections[s["id"]]
                for k, v in ovr.items():
                    if v is None: continue
                    base[k] = v
                if ovr.get("deleted"): continue
            final[s["id"]] = base
        for sid, s in db_sections.items():
            if sid not in {x["id"] for x in DEFAULT_SECTIONS} and isinstance(s, dict) and not s.get("deleted"):
                final[sid] = s
        return sorted(final.values(), key=lambda x: x.get("order", 999))
    except Exception as e:
        log.error(f"Error loading sections: {e}")
        return [dict(s) for s in DEFAULT_SECTIONS]

def get_withdrawable_ids() -> set:
    if not FIREBASE_OK: return DEFAULT_WITHDRAWABLE
    try:
        data = fbdb.reference("meta/withdrawable_items").get()
        if isinstance(data, list): return set(data)
        if isinstance(data, dict): return set(k for k,v in data.items() if v)
        return DEFAULT_WITHDRAWABLE
    except Exception: return DEFAULT_WITHDRAWABLE

def get_depositable_ids() -> set:
    if not FIREBASE_OK: return set(i["id"] for i in DEFAULT_ITEMS if i["price"] >= GARAMA_PRICE)
    try:
        data = fbdb.reference("meta/depositable_items").get()
        if isinstance(data, list): return set(data)
        if isinstance(data, dict): return set(k for k,v in data.items() if v)
        return set(i["id"] for i in DEFAULT_ITEMS if i["price"] >= GARAMA_PRICE)
    except Exception: return set(i["id"] for i in DEFAULT_ITEMS if i["price"] >= GARAMA_PRICE)

def get_medals_dict() -> dict:
    if not FIREBASE_OK: return {}
    try:
        medals = fbdb.reference("meta/medals").get() or {}
        return {mid: m for mid, m in medals.items() if isinstance(m, dict)}
    except Exception: return {}

def get_user_medals(uid: str) -> list:
    if not FIREBASE_OK: return []
    try:
        user_medal_ids = fbdb.reference(f"users/{uid}/medals").get() or {}
        all_medals = get_medals_dict()
        result = []
        for mid, val in user_medal_ids.items():
            if val and mid in all_medals:
                result.append({"id": mid, **all_medals[mid]})
        return result
    except Exception: return []

def get_dynamic_admin_ids() -> set:
    if not FIREBASE_OK: return set()
    try:
        data = fbdb.reference("meta/admins").get() or {}
        return {int(k) for k in data.keys()}
    except Exception: return set()

def is_admin(user) -> bool:
    try:
        uid = int(user["id"])
        return uid in HARDCODED_ADMIN_IDS or uid in get_dynamic_admin_ids()
    except Exception:
        return False

def user_ref(uid: str):
    return fbdb.reference(f"users/{uid}")

def _default_user() -> dict:
    return {
        "balance": 0, "inventory": {}, "lastFree": 0, "lastUser": 0,
        "used_promos": {}, "paid_ids": {}, "refUsed": False,
        "invited_by": "", "ref_earnings": 0,
        "medals": {}, "medals_hidden": False,
        "stats": {
            "casesOpened": 0, "itemsSold": 0, "upgradeSuccess": 0, "upgradeFail": 0,
            "totalEarned": 0, "donationsTotal": 0, "starsSpent": 0, "uniqueCollected": [],
            "coinsLost": 0, "coinsReferralEarned": 0,
        },
        "themes": {"dark": True}, "theme": "dark", "referrals": 0,
        "created_promos": {},
        "username": "", "first_name": "", "photo_url": "",
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
    if not entries: return None
    total = sum(e.get("weight", 1) for e in entries)
    r = random.random() * total
    for e in entries:
        r -= e.get("weight", 1)
        if r <= 0: return e
    return entries[-1]

def roll_drop(case_cfg: dict, items_dict: dict) -> dict:
    if case_cfg.get("coins") and random.random() * 100 < float(case_cfg.get("coinChance", 0)):
        picked = weighted_pick(case_cfg["coins"])
        return {"type": "coin", "amount": int(picked["amount"])}
    picked = weighted_pick(case_cfg.get("items", []))
    if not picked: 
        picked = {"id": "trios"}
    item_data = items_dict.get(picked["id"]) or items_dict.get("trios")
    return {"type": "item", "item": dict(item_data)}

def drop_value(drop: dict) -> int:
    if drop["type"] == "coin": return int(drop["amount"])
    return int(drop["item"]["price"])

def roll_with_event_luck(case_cfg: dict, luck_mult: float, items_dict: dict) -> dict:
    best = roll_drop(case_cfg, items_dict)
    extra = max(0.0, luck_mult - 1.0)
    integer_extra = int(extra)
    frac_extra = extra - integer_extra
    for _ in range(integer_extra):
        cand = roll_drop(case_cfg, items_dict)
        if drop_value(cand) > drop_value(best): best = cand
    if random.random() < frac_extra:
        cand = roll_drop(case_cfg, items_dict)
        if drop_value(cand) > drop_value(best): best = cand
    return best

def make_inv_item(item: dict) -> dict:
    uid = "u_%d_%s" % (int(time.time() * 1000), "".join(random.choices("abcdef0123456789", k=6)))
    return {**item, "uid": uid}

def push_drop(nick: str, item_id: str, item_name: str, item_img: str | None, price: int, method: str, user_id: str):
    if not FIREBASE_OK or not item_img: return
    try:
        drop_id = "d_%d_%s" % (int(time.time() * 1000), "".join(random.choices("abcdef", k=4)))
        fbdb.reference(f"drop_feed/{drop_id}").set({
            "nick": nick, "itemId": item_id, "itemName": item_name, "itemImg": item_img,
            "price": price, "method": method, "user_id": str(user_id),
            "ts": int(time.time() * 1000),
        })
    except Exception: pass

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

def get_referral_level(invited_count: int) -> dict:
    current = REFERRAL_LEVELS[0]
    for lvl in REFERRAL_LEVELS:
        if invited_count >= lvl["invited"]: current = lvl
        else: break
    return current

def apply_referral_earnings(loser_uid: str, coins_lost: int):
    if coins_lost <= 0 or not FIREBASE_OK: return
    try:
        loser_data = get_user_data(loser_uid)
        referrer_uid = loser_data.get("invited_by")
        if not referrer_uid: return
        ref_data = get_user_data(referrer_uid, strict=True)
        if not ref_data: return
        lvl = get_referral_level(int(ref_data.get("referrals", 0)))
        pct = lvl["pct"]
        bonus = int(coins_lost * pct / 100)
        if bonus <= 0: return
        def upd(d):
            d["balance"] = int(d.get("balance", 0)) + bonus
            d["ref_earnings"] = int(d.get("ref_earnings", 0)) + bonus
            d["stats"]["coinsReferralEarned"] = int(d["stats"].get("coinsReferralEarned", 0)) + bonus
            d["stats"]["totalEarned"] = int(d["stats"].get("totalEarned", 0)) + bonus
            return d
        atomic_update(referrer_uid, upd)
    except Exception:
        log.exception("referral earnings error")

def chat_id_for(uid_a: str, uid_b: str) -> str:
    return "_".join(sorted([str(uid_a), str(uid_b)]))

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
            await q.answer(ok=False, error_message="Unknown package"); return
        await q.answer(ok=True)
    except Exception:
        await q.answer(ok=False, error_message="Bad payload")

@dp.message(lambda m: m.successful_payment)
async def on_paid(message: types.Message):
    sp = message.successful_payment
    try: payload = json.loads(sp.invoice_payload)
    except Exception: return
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
            await bot.set_webhook(f"{WEBHOOK_URL or RENDER_URL}/webhook/tg",
                                  allowed_updates=dp.resolve_used_update_types(),
                                  drop_pending_updates=True)
        except Exception: pass
    yield
    if bot:
        try:
            await bot.delete_webhook(); await bot.session.close()
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

@app.get("/api/items")
async def api_items():
    return {"items": list(get_items_dict().values())}

@app.get("/api/cases")
async def api_cases():
    cases = get_cases_dict()
    sections = get_sections_list()
    return {"cases": list(cases.values()), "sections": sections}

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
    data["telegram_username"] = user.get("username", "")
    data["my_medals"] = get_user_medals(uid)
    lvl = get_referral_level(int(data.get("referrals", 0)))
    data["referral_level"] = lvl
    data["referral_pct"] = lvl["pct"]

    def save_un(d):
        d["username"] = user.get("username", "")
        d["first_name"] = user.get("first_name", "")
        d["photo_url"] = user.get("photo_url", "")
        return d
    atomic_update(uid, save_un)
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
    return {"poll": {"id": p.get("id"), "question": p.get("question"), "options": options,
                     "endsAt": p.get("endsAt"), "myVote": my_vote if my_vote is not None else None,
                     "totalVotes": sum(int(o.get("votes", 0)) for o in options)}}

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
    cases = get_cases_dict()
    if case_type not in cases: raise HTTPException(400, "Неизвестный кейс")
    if multiplier < 1 or multiplier > MAX_MULTIPLIER: raise HTTPException(400, "Неверный множитель")
    if case_type in ("free", "user"): multiplier = 1

    case_cfg = cases[case_type]
    uid = str(user["id"])
    nick = user.get("first_name") or "Player"
    now = int(time.time() * 1000)
    data = get_user_data(uid)

    if case_type == "free":
        if now - int(data.get("lastFree", 0)) < FREE_COOLDOWN_MS:
            raise HTTPException(400, "Бесплатный кейс ещё не готов")
        price = 0
    elif case_type == "user":
        uname = (user.get("first_name", "") + user.get("last_name", "") + user.get("username", "")).lower()
        if BOT_USERNAME.lower() not in uname:
            raise HTTPException(400, "Вы не указали бота в нике!")
        if now - int(data.get("lastUser", 0)) < USER_COOLDOWN_MS:
            raise HTTPException(400, "Кейс за Юз ещё не готов")
        price = 0
    else:
        price = int(case_cfg.get("price", 0)) * multiplier

    if int(data.get("balance", 0)) < price: raise HTTPException(400, "Недостаточно монет")

    event = get_active_event()
    luck_mult = float(event["multiplier"]) if event else 1.0
    items_dict = get_items_dict()

    results = [roll_with_event_luck(case_cfg, luck_mult, items_dict) for _ in range(multiplier)]

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
            push_drop(nick, r["item"]["id"], r["item"]["name"], r["item"]["img"], r["item"]["price"], "case", uid)

    new_data = get_user_data(uid)
    return {"ok": True, "results": results, "balance": new_data["balance"],
            "inventory": new_data["inventory"], "lastFree": new_data.get("lastFree", 0),
            "lastUser": new_data.get("lastUser", 0), "eventBoost": luck_mult}

@app.post("/api/sell_item")
async def api_sell_item(request: Request, user=Depends(current_user)):
    body = await request.json()
    item_uid = body.get("uid", "")
    if not item_uid: raise HTTPException(400, "Не указан предмет")
    uid = str(user["id"])
    items_dict = get_items_dict()
    def upd(d):
        inv = d.get("inventory", {})
        if item_uid not in inv: return None
        item = inv.pop(item_uid)
        live_price = int(items_dict.get(item.get("id"), {}).get("price", item.get("price", 0)))
        d["balance"] = int(d.get("balance", 0)) + live_price
        d["stats"]["itemsSold"] = int(d["stats"].get("itemsSold", 0)) + 1
        return d
    if not atomic_update(uid, upd): raise HTTPException(400, "Ошибка продажи")
    data = get_user_data(uid)
    return {"ok": True, "balance": data["balance"], "inventory": data["inventory"]}

@app.post("/api/sell_all")
async def api_sell_all(request: Request, user=Depends(current_user)):
    uid = str(user["id"])
    items_dict = get_items_dict()
    def upd(d):
        inv = d.get("inventory", {})
        if not inv: return None
        total = sum(int(items_dict.get(i.get("id"), {}).get("price", i.get("price", 0))) for i in inv.values())
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
        total += int(items_dict.get(inv[iuid].get("id"), {}).get("price", inv[iuid].get("price", 0)))
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
            d["stats"]["coinsLost"] = int(d["stats"].get("coinsLost", 0)) + total
        return d
    if not atomic_update(uid, upd): raise HTTPException(400, "Ошибка апгрейда")
    if success:
        push_drop(user.get("first_name") or "Player", target["id"], target["name"], target["img"], target["price"], "upgrade", uid)
    else:
        apply_referral_earnings(uid, total)
    new_data = get_user_data(uid)
    return {"ok": True, "success": success, "chance": chance, "target": target,
            "balance": new_data["balance"], "inventory": new_data["inventory"]}

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
        else: d["stats"]["coinsLost"] = int(d["stats"].get("coinsLost", 0)) + bet
        return d
    if not atomic_update(uid, upd): raise HTTPException(400, "Ошибка ставки")
    if not won: apply_referral_earnings(uid, bet)
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
    if used >= max_uses: raise HTTPException(400, "Промокод больше не активен")
    promo_type = promo_data.get("type", "coins")
    reward = int(promo_data.get("reward", 0))
    case_id = promo_data.get("case_id", "")

    if promo_type == "case" and case_id:
        cases = get_cases_dict()
        if case_id not in cases: raise HTTPException(400, "Кейс не найден")
        case_cfg = cases[case_id]
        items_dict = get_items_dict()
        results = [roll_drop(case_cfg, items_dict)]
    else:
        results = None

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
        if results:
            inv = d.setdefault("inventory", {})
            for r in results:
                if r["type"] == "coin":
                    d["balance"] = int(d.get("balance", 0)) + r["amount"]
                else:
                    new_item = make_inv_item(r["item"])
                    inv[new_item["uid"]] = new_item
        else:
            d["balance"] = int(d.get("balance", 0)) + reward
            d["stats"]["totalEarned"] = int(d["stats"].get("totalEarned", 0)) + reward
        return d
    if not atomic_update(uid, upd): raise HTTPException(400, "Ошибка активации")
    new_data = get_user_data(uid)
    return {"ok": True, "reward": reward, "results": results, "balance": new_data["balance"],
            "inventory": new_data["inventory"]}

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
        d["invited_by"] = ref_id
        d["balance"] = int(d.get("balance", 0)) + 2
        d["stats"]["totalEarned"] = int(d["stats"].get("totalEarned", 0)) + 2
        state["ok"] = True
        return d
    if not atomic_update(uid, upd) or not state["ok"]:
        raise HTTPException(400, "Рефка уже использована или вы уже играли")
    def upd2(d):
        d["referrals"] = int(d.get("referrals", 0)) + 1
        d["balance"] = int(d.get("balance", 0)) + 4
        d["stats"]["totalEarned"] = int(d["stats"].get("totalEarned", 0)) + 4
        return d
    atomic_update(ref_id, upd2)
    return {"ok": True, "bonus": 2}

@app.get("/api/user_profile/{target_uid}")
async def api_user_profile(target_uid: str, user=Depends(current_user)):
    if not target_uid or target_uid in ("undefined", "null"):
        raise HTTPException(400, "Неверный ID игрока")
    data = get_user_data(target_uid, strict=True)
    if data is None: raise HTTPException(404, "Игрок не найден в базе данных")
    medals = get_user_medals(target_uid) if not data.get("medals_hidden") else []
    return {"uid": target_uid, "balance": int(data.get("balance", 0) or 0),
            "inventory": data.get("inventory") or {}, "stats": data.get("stats") or {},
            "lastFree": int(data.get("lastFree", 0) or 0), "lastUser": int(data.get("lastUser", 0) or 0),
            "medals": medals, "medals_hidden": bool(data.get("medals_hidden")),
            "username": data.get("username", ""), "first_name": data.get("first_name", ""),
            "photo_url": data.get("photo_url", "")}

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

@app.get("/api/medals")
async def api_medals():
    return {"medals": list(get_medals_dict().values())}

@app.post("/api/me/medals/toggle")
async def api_toggle_medals(request: Request, user=Depends(current_user)):
    body = await request.json()
    hidden = bool(body.get("hidden", False))
    uid = str(user["id"])
    def upd(d):
        d["medals_hidden"] = hidden
        return d
    atomic_update(uid, upd)
    return {"ok": True, "hidden": hidden}

@app.get("/api/referral/info")
async def api_referral_info(user=Depends(current_user)):
    uid = str(user["id"])
    data = get_user_data(uid)
    invited = int(data.get("referrals", 0))
    lvl = get_referral_level(invited)
    next_lvl = None
    for L in REFERRAL_LEVELS:
        if L["invited"] > invited: next_lvl = L; break
    promos = data.get("created_promos", {}) or {}
    my_promo_list = []
    for code in promos:
        try:
            p = fbdb.reference(f"promos/{code}").get()
            if p: my_promo_list.append({"code": code, **p})
        except Exception: pass
    return {
        "referrals": invited, "level": lvl, "next_level": next_lvl,
        "ref_earnings": int(data.get("ref_earnings", 0)),
        "levels": REFERRAL_LEVELS,
        "my_promos": my_promo_list,
        "bot_username": BOT_USERNAME,
        "invite_link": f"https://t.me/{BOT_USERNAME}?startapp=ref_{uid}",
    }

@app.post("/api/referral/create_promo")
async def api_referral_create_promo(request: Request, user=Depends(current_user)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    code = str(body.get("code", "")).strip().upper()
    ptype = body.get("type", "coins")
    reward = int(body.get("reward", 0))
    case_id = str(body.get("case_id", ""))
    max_uses = int(body.get("max_uses", 1))

    if not code or not re.match(r"^[A-Z0-9_-]{2,32}$", code):
        raise HTTPException(400, "Код 2-32 символа (A-Z, 0-9, _, -)")
    if max_uses < 1 or max_uses > 10000:
        raise HTTPException(400, "Использований 1..10000")
    if ptype not in ("coins", "case"):
        raise HTTPException(400, "Неверный тип")

    if ptype == "coins":
        if reward < 1 or reward > 10000:
            raise HTTPException(400, "Награда 1..10000")
        cost_per_use = reward
    else:
        cases = get_cases_dict()
        if case_id not in cases: raise HTTPException(400, "Кейс не найден")
        cost_per_use = int(cases[case_id].get("price", 0)) or 1
        reward = 0

    total_cost = cost_per_use * max_uses
    uid = str(user["id"])
    data = get_user_data(uid)
    if int(data.get("balance", 0)) < total_cost:
        raise HTTPException(400, f"Нужно {total_cost} монет")

    if fbdb.reference(f"promos/{code}").get():
        raise HTTPException(400, "Промокод уже существует")

    def upd(d):
        if int(d.get("balance", 0)) < total_cost: return None
        d["balance"] = int(d.get("balance", 0)) - total_cost
        created = d.setdefault("created_promos", {})
        created[code] = {"ts": int(time.time() * 1000), "cost": total_cost}
        return d
    if not atomic_update(uid, upd):
        raise HTTPException(400, "Ошибка списания")

    fbdb.reference(f"promos/{code}").set({
        "reward": reward, "max_uses": max_uses, "used": 0,
        "type": ptype, "case_id": case_id if ptype == "case" else "",
        "createdAt": int(time.time() * 1000), "createdBy": uid,
    })
    return {"ok": True, "code": code, "cost": total_cost}

@app.get("/api/withdraw/options")
async def api_withdraw_options(user=Depends(current_user)):
    uid = str(user["id"])
    data = get_user_data(uid)
    inv = data.get("inventory", {}) or {}
    items_dict = get_items_dict()
    wd_ids = get_withdrawable_ids()
    avail = []
    total_val = 0
    for iuid, it in inv.items():
        if it.get("id") in wd_ids:
            live_it = dict(it)
            live_it["price"] = items_dict.get(it["id"], {}).get("price", it.get("price", 0))
            avail.append({"uid": iuid, **live_it})
            total_val += int(live_it["price"])
    withdrawable_defs = [it for it in items_dict.values() if it["id"] in wd_ids]
    return {
        "available": avail,
        "withdrawable_items": withdrawable_defs,
        "min_value": MIN_WITHDRAW_VALUE,
        "total_available_value": total_val,
        "garama_price": GARAMA_PRICE,
    }

# ---> ИЗМЕНЕНИЕ: Поддержка нескольких исходников для обмена <---
@app.post("/api/withdraw/exchange")
async def api_withdraw_exchange(request: Request, user=Depends(current_user)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    source_uids = body.get("source_uids", [])
    target_ids = body.get("target_ids", [])
    if not isinstance(source_uids, list) or not source_uids or not isinstance(target_ids, list) or not target_ids:
        raise HTTPException(400, "Выберите предметы для обмена")
    
    items_dict = get_items_dict()
    wd_ids = get_withdrawable_ids()
    uid = str(user["id"])
    data = get_user_data(uid)
    inv = data.get("inventory", {}) or {}
    
    source_total = 0
    for suid in source_uids:
        if suid not in inv: raise HTTPException(400, "Исходный предмет не найден")
        source_total += int(items_dict.get(inv[suid]["id"], {}).get("price", inv[suid].get("price", 0)))
        
    target_total = 0
    targets = []
    for tid in target_ids:
        if tid not in wd_ids:
            raise HTTPException(400, f"Предмет {tid} не подходит для обмена")
        tgt = items_dict.get(tid)
        if not tgt: raise HTTPException(400, f"Неизвестный предмет {tid}")
        targets.append(tgt)
        target_total += int(tgt["price"])
        
    if target_total > source_total:
        raise HTTPException(400, "Цели дороже источников")
        
    remainder = source_total - target_total

    def upd(d):
        inv2 = d.get("inventory", {})
        for suid in source_uids:
            if suid not in inv2: return None
        for suid in source_uids: del inv2[suid]
        for tgt in targets:
            new_it = make_inv_item(tgt)
            inv2[new_it["uid"]] = new_it
        d["balance"] = int(d.get("balance", 0)) + remainder
        return d
    if not atomic_update(uid, upd): raise HTTPException(400, "Ошибка обмена")
    new_data = get_user_data(uid)
    return {"ok": True, "balance": new_data["balance"], "inventory": new_data["inventory"], "remainder": remainder}

@app.post("/api/withdraw/request")
async def api_withdraw_request(request: Request, user=Depends(current_user)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    item_uids = body.get("item_uids", [])
    nick = str(body.get("nick", "")).strip()
    if not item_uids or not nick: raise HTTPException(400, "Выберите предметы и укажите ник")
    if len(nick) < 2 or len(nick) > 64: raise HTTPException(400, "Ник 2..64 символа")
    uid = str(user["id"])
    data = get_user_data(uid)
    inv = data.get("inventory", {}) or {}
    items_dict = get_items_dict()
    wd_ids = get_withdrawable_ids()
    total = 0
    selected = []
    for iuid in item_uids:
        if iuid not in inv: raise HTTPException(400, "Предмет не найден")
        it = inv[iuid]
        if it.get("id") not in wd_ids:
            raise HTTPException(400, f"Предмет {it.get('name')} нельзя вывести")
        live_it = dict(it)
        live_it["price"] = items_dict.get(it["id"], {}).get("price", it.get("price", 0))
        selected.append(live_it)
        total += int(live_it["price"])
    if total < MIN_WITHDRAW_VALUE:
        raise HTTPException(400, f"Минимум {MIN_WITHDRAW_VALUE} монет (≈2 гарамы)")

    def upd(d):
        inv2 = d.get("inventory", {})
        for iuid in item_uids:
            if iuid not in inv2: return None
        for iuid in item_uids: del inv2[iuid]
        return d
    if not atomic_update(uid, upd): raise HTTPException(400, "Ошибка")

    rid = "wr_" + uuid.uuid4().hex[:10]
    fbdb.reference(f"withdraw_requests/{rid}").set({
        "id": rid, "user_uid": uid, "nick": nick,
        "items": [{"id": i["id"], "name": i["name"], "price": i["price"], "img": i.get("img", "")} for i in selected],
        "total": total, "status": "pending",
        "created_at": int(time.time() * 1000),
        "scheduled_at": 0, "comment": "",
    })
    return {"ok": True, "request_id": rid, "total": total}

@app.get("/api/withdraw/my_requests")
async def api_withdraw_my(user=Depends(current_user)):
    if not FIREBASE_OK: return {"requests": []}
    uid = str(user["id"])
    try:
        allr = fbdb.reference("withdraw_requests").get() or {}
        return {"requests": [r for r in allr.values() if isinstance(r, dict) and r.get("user_uid") == uid]}
    except Exception: return {"requests": []}

@app.get("/api/deposit/options")
async def api_deposit_options(user=Depends(current_user)):
    items_dict = get_items_dict()
    dep_ids = get_depositable_ids()
    available = [it for it in items_dict.values() if it["id"] in dep_ids]
    return {"available": available, "min_value": GARAMA_PRICE}

@app.post("/api/deposit/request")
async def api_deposit_request(request: Request, user=Depends(current_user)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    item_id = str(body.get("item_id", ""))
    nick = str(body.get("nick", "")).strip()
    if not item_id or not nick: raise HTTPException(400, "Выберите предмет и укажите ник")
    items_dict = get_items_dict()
    if item_id not in items_dict: raise HTTPException(400, "Предмет не найден")
    item = items_dict[item_id]
    if item_id not in get_depositable_ids(): raise HTTPException(400, "Этот предмет нельзя получить через пополнение")
    
    uid = str(user["id"])
    rid = "dp_" + uuid.uuid4().hex[:10]
    fbdb.reference(f"deposit_requests/{rid}").set({
        "id": rid, "user_uid": uid, "nick": nick,
        "item_id": item_id, "item_name": item["name"], "item_price": item["price"],
        "status": "pending", "scheduled_at": 0,
        "created_at": int(time.time() * 1000), "comment": "",
    })
    return {"ok": True, "request_id": rid}

@app.get("/api/deposit/my_requests")
async def api_deposit_my(user=Depends(current_user)):
    if not FIREBASE_OK: return {"requests": []}
    uid = str(user["id"])
    try:
        allr = fbdb.reference("deposit_requests").get() or {}
        return {"requests": [r for r in allr.values() if isinstance(r, dict) and r.get("user_uid") == uid]}
    except Exception: return {"requests": []}

@app.post("/api/chats/find_user")
async def api_chats_find(request: Request, user=Depends(current_user)):
    body = await request.json()
    q = str(body.get("query", "")).strip().lstrip("@")
    if not q: raise HTTPException(400, "Введите ID или username")
    if q.isdigit():
        target_uid = q
        ud = get_user_data(target_uid, strict=True)
        if not ud: raise HTTPException(404, "Пользователь не найден")
        return {"uid": target_uid, "username": ud.get("username", ""), "first_name": ud.get("first_name", "")}
    if not FIREBASE_OK: raise HTTPException(503)
    try:
        users = fbdb.reference("users").get() or {}
        for uid_k, u in users.items():
            if isinstance(u, dict) and str(u.get("username", "")).lower() == q.lower():
                return {"uid": str(uid_k), "username": u.get("username", ""), "first_name": u.get("first_name", "")}
    except Exception: pass
    raise HTTPException(404, "Пользователь не найден")

@app.get("/api/chats")
async def api_chats_list(user=Depends(current_user)):
    if not FIREBASE_OK: return {"chats": []}
    uid = str(user["id"])
    try:
        allchats = fbdb.reference("chats").get() or {}
        result = []
        for cid, ch in allchats.items():
            if not isinstance(ch, dict): continue
            if uid not in ch.get("members", []): continue
            last = None
            msgs = ch.get("messages", {}) or {}
            if msgs:
                last_msg = max(msgs.values(), key=lambda m: int(m.get("ts", 0)))
                last = {"text": last_msg.get("text", ""), "from": last_msg.get("from"),
                        "ts": int(last_msg.get("ts", 0))}
            other = [m for m in ch.get("members", []) if m != uid]
            other_uid = other[0] if other else ""
            other_data = get_user_data(other_uid, strict=True) or {}
            result.append({
                "chat_id": cid, "other_uid": other_uid,
                "other_name": other_data.get("first_name") or other_data.get("username") or f"ID {other_uid}",
                "last_message": last,
            })
        result.sort(key=lambda x: (x["last_message"]["ts"] if x["last_message"] else 0), reverse=True)
        return {"chats": result}
    except Exception: return {"chats": []}

@app.get("/api/chats/{chat_id}/messages")
async def api_chat_messages(chat_id: str, user=Depends(current_user)):
    if not FIREBASE_OK: raise HTTPException(503)
    uid = str(user["id"])
    try: ch = fbdb.reference(f"chats/{chat_id}").get()
    except: ch = None
    if not ch or uid not in ch.get("members", []):
        raise HTTPException(403, "Нет доступа")
    msgs = ch.get("messages", {}) or {}
    return {"messages": sorted(msgs.values(), key=lambda m: int(m.get("ts", 0)))}

@app.post("/api/chats/{chat_id}/send")
async def api_chat_send(chat_id: str, request: Request, user=Depends(current_user)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    text = str(body.get("text", "")).strip()
    if not text or len(text) > 2000: raise HTTPException(400, "Текст 1..2000 символов")
    uid = str(user["id"])
    try: ch = fbdb.reference(f"chats/{chat_id}").get()
    except: ch = None
    if not ch or uid not in ch.get("members", []):
        raise HTTPException(403, "Нет доступа")
    mid = "m_" + uuid.uuid4().hex[:10]
    fbdb.reference(f"chats/{chat_id}/messages/{mid}").set({
        "id": mid, "from": uid, "text": text, "ts": int(time.time() * 1000),
    })
    return {"ok": True, "message_id": mid}

@app.post("/api/chats/start")
async def api_chat_start(request: Request, user=Depends(current_user)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    target_uid = str(body.get("target_uid", "")).strip()
    if not target_uid or target_uid == str(user["id"]): raise HTTPException(400, "Неверный пользователь")
    if not get_user_data(target_uid, strict=True): raise HTTPException(404, "Пользователь не найден")
    cid = chat_id_for(str(user["id"]), target_uid)
    existing = fbdb.reference(f"chats/{cid}").get()
    if not existing:
        fbdb.reference(f"chats/{cid}").set({
            "chat_id": cid, "members": [str(user["id"]), target_uid],
            "created_at": int(time.time() * 1000), "messages": {},
        })
    return {"ok": True, "chat_id": cid}

@app.get("/api/admin/items")
async def admin_get_items(user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    return {"items": list(get_items_dict().values())}

@app.post("/api/admin/item/update")
async def admin_update_item(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    item_id = body.get("item_id")
    if not item_id: raise HTTPException(400, "no item_id")
    update = {}
    if "price" in body:
        p = int(body["price"])
        if p < 0: raise HTTPException(400, "Цена < 0")
        update["price"] = p
    if "rarity" in body:
        if body["rarity"] not in RARITIES: raise HTTPException(400, "Неверная редкость")
        update["rarity"] = body["rarity"]
    if "name" in body: update["name"] = str(body["name"])[:64]
    if "img" in body: update["img"] = str(body["img"])[:256]
    if "emoji" in body: update["emoji"] = str(body["emoji"])[:8]
    fbdb.reference(f"meta/items_overrides/{item_id}").update(update)
    return {"ok": True}

@app.post("/api/admin/item/create")
async def admin_create_item(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    iid = str(body.get("id", "")).strip().lower()
    if not iid or not re.match(r"^[a-z0-9_]{2,32}$", iid):
        raise HTTPException(400, "ID 2..32 (a-z, 0-9, _)")
    if iid in {i["id"] for i in DEFAULT_ITEMS}:
        raise HTTPException(400, "ID уже существует")
    fbdb.reference(f"meta/items_extra/{iid}").set({
        "name": str(body.get("name", iid))[:64],
        "price": max(1, int(body.get("price", 1))),
        "rarity": body.get("rarity", "common") if body.get("rarity") in RARITIES else "common",
        "img": str(body.get("img", ""))[:256],
        "emoji": str(body.get("emoji", "🧠"))[:8],
    })
    return {"ok": True, "id": iid}

@app.post("/api/admin/item/delete")
async def admin_delete_item(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    iid = str(body.get("item_id", ""))
    if not iid: raise HTTPException(400, "no item_id")
    if iid in {i["id"] for i in DEFAULT_ITEMS}:
        fbdb.reference(f"meta/items_overrides/{iid}").update({"deleted": True})
    else:
        fbdb.reference(f"meta/items_extra/{iid}").delete()
    return {"ok": True}

@app.post("/api/admin/case/save")
async def admin_case_save(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    cid = str(body.get("id", "")).strip()
    if not cid or not re.match(r"^[a-z0-9_]{2,32}$", cid):
        raise HTTPException(400, "ID кейса 2..32 (a-z, 0-9, _)")
    case = {
        "id": cid,
        "name": str(body.get("name", cid))[:64],
        "section": str(body.get("section", "shop")),
        "price": max(0, int(body.get("price", 0))),
        "img": str(body.get("img", ""))[:256],
        "emoji": str(body.get("emoji", "📦"))[:8],
        "order": int(body.get("order", 0)),
        "coinChance": max(0, min(100, float(body.get("coinChance", 0)))),
        "coins": body.get("coins", []),
        "items": body.get("items", []),
    }
    fbdb.reference(f"meta/cases/{cid}").set(case)
    return {"ok": True, "case": case}

@app.post("/api/admin/case/delete")
async def admin_case_delete(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    cid = str(body.get("id", ""))
    if not cid: raise HTTPException(400, "no id")
    if cid in DEFAULT_CASES:
        fbdb.reference(f"meta/cases/{cid}").update({"deleted": True})
    else:
        fbdb.reference(f"meta/cases/{cid}").delete()
    return {"ok": True}

@app.post("/api/admin/section/save")
async def admin_section_save(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    sid = str(body.get("id", "")).strip()
    if not sid or not re.match(r"^[a-z0-9_]{2,32}$", sid):
        raise HTTPException(400, "ID секции 2..32")
    sec = {
        "id": sid,
        "name": str(body.get("name", sid))[:64],
        "order": int(body.get("order", 0)),
        "icon": str(body.get("icon", "📁"))[:8],
    }
    fbdb.reference(f"meta/sections/{sid}").set(sec)
    return {"ok": True, "section": sec}

@app.post("/api/admin/section/delete")
async def admin_section_delete(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    sid = str(body.get("id", ""))
    if not sid: raise HTTPException(400, "no id")
    if sid in {s["id"] for s in DEFAULT_SECTIONS}:
        fbdb.reference(f"meta/sections/{sid}").update({"deleted": True})
    else:
        fbdb.reference(f"meta/sections/{sid}").delete()
    return {"ok": True}

@app.post("/api/admin/medal/save")
async def admin_medal_save(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    mid = str(body.get("id", "")).strip()
    if not mid or not re.match(r"^[a-z0-9_]{2,32}$", mid):
        raise HTTPException(400, "ID медали 2..32")
    medal = {
        "id": mid,
        "name": str(body.get("name", mid))[:64],
        "description": str(body.get("description", ""))[:512],
        "icon": str(body.get("icon", "🏅"))[:8],
        "img": str(body.get("img", ""))[:256],
        "color": str(body.get("color", "#fbbf24"))[:16],
    }
    fbdb.reference(f"meta/medals/{mid}").set(medal)
    return {"ok": True, "medal": medal}

@app.post("/api/admin/medal/delete")
async def admin_medal_delete(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    mid = str(body.get("id", ""))
    if not mid: raise HTTPException(400, "no id")
    fbdb.reference(f"meta/medals/{mid}").delete()
    return {"ok": True}

@app.post("/api/admin/medal/give")
async def admin_medal_give(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    target_uid = str(body.get("user_id", "")).strip()
    mid = str(body.get("medal_id", "")).strip()
    if not target_uid or not mid: raise HTTPException(400, "user_id и medal_id обязательны")
    medal = fbdb.reference(f"meta/medals/{mid}").get()
    if not medal: raise HTTPException(404, "Медаль не найдена")
    def upd(d):
        d.setdefault("medals", {})[mid] = True
        return d
    if not atomic_update(target_uid, upd): raise HTTPException(400, "Ошибка")
    return {"ok": True}

@app.post("/api/admin/medal/remove")
async def admin_medal_remove(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    target_uid = str(body.get("user_id", "")).strip()
    mid = str(body.get("medal_id", "")).strip()
    def upd(d):
        m = d.get("medals", {})
        if mid in m: del m[mid]
        return d
    if not atomic_update(target_uid, upd): raise HTTPException(400, "Ошибка")
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
    if duration_minutes < 1 or duration_minutes > MAX_EVENT_MINUTES:
        raise HTTPException(400, f"duration 1..{MAX_EVENT_MINUTES}")
    now = int(time.time() * 1000)
    meta = EVENT_TYPES[ev_type]
    ev = {"type": ev_type, "name": meta["name"], "multiplier": meta["multiplier"],
          "color": meta["color"], "img": meta["img"], "startedAt": now,
          "endsAt": now + duration_minutes * 60 * 1000, "startedBy": str(user["id"])}
    fbdb.reference("meta/event").set(ev)
    return {"ok": True, "event": ev}

@app.post("/api/admin/promo")
async def admin_create_promo(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    code = str(body.get("code", "")).strip().upper()
    reward = int(body.get("reward", 0))
    max_uses = int(body.get("max_uses", 0))
    if not code or len(code) < 2 or len(code) > 32: raise HTTPException(400, "Код 2..32")
    if not all(c.isalnum() or c in "_-" for c in code): raise HTTPException(400, "Только буквы/цифры/_/-")
    if reward <= 0 or reward > MAX_PROMO_REWARD: raise HTTPException(400, f"Награда 1..{MAX_PROMO_REWARD}")
    if max_uses < 1 or max_uses > MAX_PROMO_USES: raise HTTPException(400, f"Использований 1..{MAX_PROMO_USES}")
    ref = fbdb.reference(f"promos/{code}")
    if ref.get(): raise HTTPException(400, "Промокод уже существует")
    ref.set({"reward": reward, "max_uses": max_uses, "used": 0,
             "type": "coins", "case_id": "",
             "createdAt": int(time.time() * 1000), "createdBy": str(user["id"])})
    return {"ok": True, "code": code}

@app.get("/api/admin/promos")
async def admin_list_promos(user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    try: promos = fbdb.reference("promos").get() or {}
    except: promos = {}
    result = []
    for code, p in promos.items():
        if not isinstance(p, dict): continue
        result.append({"code": code, "reward": p.get("reward", 0), "used": p.get("used", 0),
                       "max_uses": p.get("max_uses", 0), "createdAt": p.get("createdAt", 0),
                       "type": p.get("type", "coins"), "case_id": p.get("case_id", "")})
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
    if coins < 0: raise HTTPException(400, "Монет < 0")
    if coins > MAX_GIVE_COINS: raise HTTPException(400, f"Макс {MAX_GIVE_COINS}")
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
    if not atomic_update(target_id, upd): raise HTTPException(400, "Ошибка")
    return {"ok": True, "gave": gave}

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
    if not atomic_update(target_id, upd): raise HTTPException(400, "Ошибка")
    return {"ok": True}

@app.post("/api/admin/grant_admin")
async def admin_grant_admin(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    target = str(body.get("user_id", "")).strip()
    if not target: raise HTTPException(400, "user_id")
    fbdb.reference(f"meta/admins/{target}").set(True)
    return {"ok": True}

@app.post("/api/admin/revoke_admin")
async def admin_revoke_admin(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    target = str(body.get("user_id", "")).strip()
    if not target: raise HTTPException(400, "user_id")
    if int(target) in HARDCODED_ADMIN_IDS:
        raise HTTPException(400, "Нельзя снять с хардкод админа")
    fbdb.reference(f"meta/admins/{target}").delete()
    return {"ok": True}

@app.post("/api/admin/poll")
async def admin_create_poll(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    question = str(body.get("question", "")).strip()
    options = body.get("options", [])
    duration_minutes = body.get("duration_minutes")
    if not question or len(question) > 300: raise HTTPException(400, "Вопрос 1..300")
    if not isinstance(options, list) or len(options) < 2 or len(options) > 6:
        raise HTTPException(400, "2..6 вариантов")
    cleaned = [str(o).strip() for o in options]
    for o in cleaned:
        if not o or len(o) > 100: raise HTTPException(400, "Каждый вариант 1..100")
    now = int(time.time() * 1000)
    ends_at = None
    if duration_minutes:
        try: dm = int(duration_minutes)
        except: raise HTTPException(400, "bad duration")
        if dm < 1 or dm > 60 * 24 * 30: raise HTTPException(400, "1..43200 минут")
        ends_at = now + dm * 60 * 1000
    poll = {"id": "poll_" + str(now), "question": question,
            "options": [{"text": o, "votes": 0} for o in cleaned],
            "createdAt": now, "endsAt": ends_at, "createdBy": str(user["id"]), "voters": {}}
    fbdb.reference("meta/poll").set(poll)
    return {"ok": True}

@app.post("/api/admin/poll/end")
async def admin_end_poll(user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    fbdb.reference("meta/poll").delete()
    return {"ok": True}

@app.get("/api/admin/withdrawals")
async def admin_withdrawals(user=Depends(require_admin)):
    if not FIREBASE_OK: return {"requests": []}
    try:
        allr = fbdb.reference("withdraw_requests").get() or {}
        reqs = [r for r in allr.values() if isinstance(r, dict)]
        reqs.sort(key=lambda r: r.get("created_at", 0), reverse=True)
        return {"requests": reqs}
    except Exception: return {"requests": []}

@app.post("/api/admin/withdrawal/schedule")
async def admin_withdrawal_schedule(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    rid = str(body.get("id", ""))
    sched_at = int(body.get("scheduled_at", 0))
    comment = str(body.get("comment", ""))[:256]
    if not rid: raise HTTPException(400, "no id")
    fbdb.reference(f"withdraw_requests/{rid}").update({
        "status": "scheduled", "scheduled_at": sched_at, "comment": comment,
    })
    return {"ok": True}

@app.post("/api/admin/withdrawal/complete")
async def admin_withdrawal_complete(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    rid = str(body.get("id", ""))
    if not rid: raise HTTPException(400, "no id")
    fbdb.reference(f"withdraw_requests/{rid}").update({
        "status": "completed", "completed_at": int(time.time() * 1000),
    })
    return {"ok": True}

@app.post("/api/admin/withdrawal/cancel")
async def admin_withdrawal_cancel(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    rid = str(body.get("id", ""))
    if not rid: raise HTTPException(400, "no id")
    fbdb.reference(f"withdraw_requests/{rid}").update({"status": "cancelled"})
    return {"ok": True}

@app.get("/api/admin/deposits")
async def admin_deposits(user=Depends(require_admin)):
    if not FIREBASE_OK: return {"requests": []}
    try:
        allr = fbdb.reference("deposit_requests").get() or {}
        reqs = [r for r in allr.values() if isinstance(r, dict)]
        reqs.sort(key=lambda r: r.get("created_at", 0), reverse=True)
        return {"requests": reqs}
    except Exception: return {"requests": []}

# ---> ИЗМЕНЕНИЕ: Добавлено планирование пополнений <---
@app.post("/api/admin/deposit/update")
async def admin_deposit_update(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    rid = str(body.get("id", ""))
    status = str(body.get("status", ""))
    comment = str(body.get("comment", ""))[:256]
    sched_at = int(body.get("scheduled_at", 0))
    
    if not rid or status not in ("pending", "approved", "rejected", "scheduled"): 
        raise HTTPException(400, "bad args")
    
    req_ref = fbdb.reference(f"deposit_requests/{rid}")
    req = req_ref.get()
    if not req: raise HTTPException(404, "Заявка не найдена")
    
    if status == "approved" and req.get("status") != "approved":
        target_uid = req["user_uid"]
        item_id = req["item_id"]
        items_dict = get_items_dict()
        if item_id not in items_dict: raise HTTPException(400, "Предмет не найден на сайте")
        
        def upd(d):
            new_item = make_inv_item(items_dict[item_id])
            d.setdefault("inventory", {})[new_item["uid"]] = new_item
            return d
        if not atomic_update(target_uid, upd):
            raise HTTPException(400, "Ошибка выдачи предмета игроку")

    update_data = {"status": status, "comment": comment}
    if status == "scheduled":
        update_data["scheduled_at"] = sched_at
        
    req_ref.update(update_data)
    return {"ok": True}

# ---> ИЗМЕНЕНИЕ: Сохранение списков для вывода и пополнения <---
@app.post("/api/admin/lists/save")
async def admin_lists_save(request: Request, user=Depends(require_admin)):
    if not FIREBASE_OK: raise HTTPException(503)
    body = await request.json()
    wd_ids = body.get("withdrawable", [])
    dep_ids = body.get("depositable", [])
    
    if isinstance(wd_ids, list):
        fbdb.reference("meta/withdrawable_items").set({k: True for k in wd_ids})
    if isinstance(dep_ids, list):
        fbdb.reference("meta/depositable_items").set({k: True for k in dep_ids})
        
    return {"ok": True}

@app.get("/api/admin/stats")
async def admin_stats(user=Depends(require_admin)):
    if not FIREBASE_OK:
        return {"firebase_ok": False, "total_users": 0, "total_balance": 0, "total_opened": 0,
                "total_inventory_items": 0, "total_unique_collected": 0, "active_24h": 0,
                "total_referrals": 0, "total_donations": 0, "total_stars": 0,
                "top_by_balance": [], "top_by_opened": [], "recent_drops": [],
                "recent_count_1h": 0, "recent_count_24h": 0, "active_event": None, "active_poll": None}
    try: users = fbdb.reference("users").get() or {}
    except: users = {}
    total_users = total_balance = total_opened = total_inv = total_uniq = 0
    active_24h = total_refs = total_don = total_stars = 0
    user_list = []
    now_ms = int(time.time() * 1000); day_ago = now_ms - 24 * 3600 * 1000
    for uid, u in users.items():
        if not isinstance(u, dict): continue
        total_users += 1
        try: bal = int(u.get("balance", 0) or 0)
        except: bal = 0
        total_balance += bal
        stats = u.get("stats") if isinstance(u.get("stats"), dict) else {}
        try: opened = int(stats.get("casesOpened", 0) or 0)
        except: opened = 0
        total_opened += opened
        uniq = stats.get("uniqueCollected")
        if isinstance(uniq, list): total_uniq += len(uniq)
        try: total_don += int(stats.get("donationsTotal", 0) or 0)
        except: pass
        try: total_stars += int(stats.get("starsSpent", 0) or 0)
        except: pass
        if isinstance(u.get("inventory"), dict): total_inv += len(u["inventory"])
        try: total_refs += int(u.get("referrals", 0) or 0)
        except: pass
        try: lf = int(u.get("lastFree", 0) or 0); lu = int(u.get("lastUser", 0) or 0)
        except: lf = lu = 0
        if max(lf, lu) > day_ago: active_24h += 1
        user_list.append({"uid": str(uid), "balance": bal, "opened": opened})
    top_bal = sorted(user_list, key=lambda x: x["balance"], reverse=True)[:5]
    top_open = sorted(user_list, key=lambda x: x["opened"], reverse=True)[:5]
    try:
        drops = fbdb.reference("drop_feed").get() or {}
        drops_list = list(drops.values()) if isinstance(drops, dict) else []
        def gts(d): return int(d.get("ts", 0)) if isinstance(d, dict) else 0
        recent = sorted(drops_list, key=gts, reverse=True)[:20]
        c1h = sum(1 for d in drops_list if gts(d) > now_ms - 3600 * 1000)
        c24h = sum(1 for d in drops_list if gts(d) > day_ago)
    except: recent = []; c1h = c24h = 0
    ev = get_active_event(); poll = get_active_poll()
    return {"firebase_ok": True, "total_users": total_users, "total_balance": total_balance,
            "total_opened": total_opened, "total_inventory_items": total_inv,
            "total_unique_collected": total_uniq, "active_24h": active_24h,
            "total_referrals": total_refs, "total_donations": total_don, "total_stars": total_stars,
            "top_by_balance": top_bal, "top_by_opened": top_open, "recent_drops": recent,
            "recent_count_1h": c1h, "recent_count_24h": c24h, "active_event": ev,
            "active_poll": {"question": poll.get("question") if poll else None,
                            "endsAt": poll.get("endsAt") if poll else None,
                            "totalVotes": sum(int(o.get("votes", 0)) for o in poll.get("options", [])) if poll else 0} if poll else None}

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
