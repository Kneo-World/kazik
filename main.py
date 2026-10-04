# main.py
# -*- coding: utf-8 -*-
"""
Brainrots Funny — Telegram Mini App + Stars Payments
=====================================================
Один файл: aiogram 3 + FastAPI.
- Отдаёт index.html по корню "/"
- Обрабатывает Telegram webhook по "/webhook/tg"
- Создаёт инвойсы для Stars по "/api/create-invoice-link"
- Диагностика: /debug и /health

Поведение:
- Даже если BOT_TOKEN не задан или вебхук не установился — сайт работает.
- Все ошибки бота логируются, но приложение не падает.
"""

import os
import json
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import aiohttp
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher, Router, types
from aiogram.types import Update, LabeledPrice, PreCheckoutQuery, Message


# ============================================================
# КОНФИГ
# ============================================================
load_dotenv()

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
WEBHOOK_URL = (os.getenv("WEBHOOK_URL") or "").strip().rstrip("/")
RENDER_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
PORT = int(os.getenv("PORT", "10000"))

BASE_DIR = Path(__file__).parent.resolve()
INDEX_HTML = BASE_DIR / "index.html"
ASSETS_DIR = BASE_DIR / "assets"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("brainrots")


# ============================================================
# БОТ И ДИСПЕТЧЕР (с защитой от краха)
# ============================================================
dp = Dispatcher()
router = Router()
dp.include_router(router)

bot: Bot | None = None
if BOT_TOKEN:
    try:
        bot = Bot(token=BOT_TOKEN)
        log.info("Bot создан (token=%s...)", BOT_TOKEN[:8])
    except Exception as e:
        log.exception("Не удалось создать Bot: %s", e)
        bot = None
else:
    log.error("BOT_TOKEN не задан — бот и оплата будут недоступны")


# Память (в проде — БД)
USER_BALANCES: dict[int, dict] = {}

STARS_PACKAGES = {
    "p10":  {"stars": 10,  "coins": 50,   "bonus": 0},
    "p25":  {"stars": 25,  "coins": 135,  "bonus": 8},
    "p50":  {"stars": 50,  "coins": 300,  "bonus": 20},
    "p100": {"stars": 100, "coins": 650,  "bonus": 30},
    "p250": {"stars": 250, "coins": 1750, "bonus": 40},
    "p500": {"stars": 500, "coins": 4000, "bonus": 60},
}


def get_user(user_id: int) -> dict:
    if user_id not in USER_BALANCES:
        USER_BALANCES[user_id] = {"coins": 0, "stars_spent": 0, "purchases": 0}
    return USER_BALANCES[user_id]


# ============================================================
# ХЕНДЛЕРЫ БОТА
# ============================================================
@router.message(types.ContentType.TEXT)
async def handle_text(message: Message):
    if message.text and message.text.startswith("/start"):
        base = WEBHOOK_URL or RENDER_URL or "https://example.com"
        await message.answer(
            "🎮 <b>Brainrots Funny</b>\n\nОткрывай приложение и крути кейсы!",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[
                    types.InlineKeyboardButton(
                        text="🎮 Открыть Brainrots Funny",
                        web_app=types.WebAppInfo(url=base),
                    )
                ]]
            ),
        )


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    try:
        payload = json.loads(query.invoice_payload)
        pack_id = payload.get("package_id")
        if pack_id not in STARS_PACKAGES:
            await query.answer(ok=False, error_message="Неизвестный пакет")
            return
        await query.answer(ok=True)
    except Exception:
        log.exception("pre_checkout error")
        await query.answer(ok=False, error_message="Ошибка валидации")


@router.message(types.ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment(message: Message):
    sp = message.successful_payment
    try:
        payload = json.loads(sp.invoice_payload)
    except Exception:
        payload = {}

    pack_id = payload.get("package_id", "")
    user_id = message.from_user.id
    pack = STARS_PACKAGES.get(pack_id)
    if not pack:
        log.error("Unknown package in successful_payment: %s", pack_id)
        return

    u = get_user(user_id)
    u["coins"] += pack["coins"]
    u["stars_spent"] += pack["stars"]
    u["purchases"] += 1

    log.info("Payment: user=%s pack=%s stars=%s coins=%s",
             user_id, pack_id, pack["stars"], pack["coins"])

    await message.answer(
        f"⭐ <b>Оплата прошла!</b>\n\n"
        f"Начислено: <b>+{pack['coins']} монет</b>\n"
        f"Потрачено: {pack['stars']} ⭐\n"
        f"Баланс: <b>{u['coins']} монет</b>"
    )


# ============================================================
# LIFESPAN
# ============================================================
async def self_ping_loop(base_url: str):
    """Пинг себя, чтобы Render Free не засыпал."""
    url = f"{base_url}/health"
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    log.debug("Self-ping: %s %s", r.status, url)
            except Exception as e:
                log.warning("Self-ping failed: %s", e)
            await asyncio.sleep(600)  # 10 минут


@asynccontextmanager
async def lifespan(app: FastAPI):
    # === Диагностика на старте ===
    log.info("========== STARTUP DIAGNOSTICS ==========")
    log.info("BOT_TOKEN set:        %s", bool(BOT_TOKEN))
    log.info("WEBHOOK_URL:          %s", WEBHOOK_URL or "(none)")
    log.info("RENDER_EXTERNAL_URL:  %s", RENDER_URL or "(none)")
    log.info("index.html exists:    %s", INDEX_HTML.exists())
    log.info("assets/ exists:       %s", ASSETS_DIR.exists())
    log.info("Bot initialized:      %s", bot is not None)
    log.info("=========================================")

    # === Установка вебхука (не критично если упадёт) ===
    if bot and (WEBHOOK_URL or RENDER_URL):
        base = WEBHOOK_URL or RENDER_URL
        webhook_full = f"{base}/webhook/tg"
        try:
            await bot.set_webhook(
                url=webhook_full,
                allowed_updates=dp.resolve_used_update_types(),
                drop_pending_updates=True,
            )
            log.info("Webhook установлен: %s", webhook_full)
        except Exception as e:
            log.exception("Не удалось установить вебхук: %s", e)
    elif bot:
        log.warning("Ни WEBHOOK_URL, ни RENDER_EXTERNAL_URL не заданы — вебхук не установлен")

    # === Self-ping ===
    ping_task = None
    if RENDER_URL:
        ping_task = asyncio.create_task(self_ping_loop(RENDER_URL))
        log.info("Self-ping запущен на %s/health", RENDER_URL)

    # === Отдаём управление приложению ===
    yield

    # === Остановка ===
    if ping_task:
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            pass
    if bot:
        try:
            await bot.delete_webhook()
        except Exception:
            pass
        try:
            await bot.session.close()
        except Exception:
            pass
    log.info("Shutdown complete")


# ============================================================
# FASTAPI
# ============================================================
app = FastAPI(lifespan=lifespan, title="Brainrots Funny API")

if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.get("/", response_class=HTMLResponse)
async def root():
    if not INDEX_HTML.exists():
        return HTMLResponse(
            "<h1>index.html не найден</h1>"
            "<p>Положи index.html рядом с main.py</p>",
            status_code=404,
        )
    return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))


@app.get("/health")
async def health():
    return {"ok": True, "service": "brainrots-funny"}


@app.get("/debug")
async def debug():
    """Диагностика: зайди сюда чтобы понять что не так."""
    return {
        "bot_token_set": bool(BOT_TOKEN),
        "bot_initialized": bot is not None,
        "webhook_url": WEBHOOK_URL or None,
        "render_url": RENDER_URL or None,
        "index_html_exists": INDEX_HTML.exists(),
        "assets_exists": ASSETS_DIR.exists(),
        "packages": list(STARS_PACKAGES.keys()),
        "webhook_path": "/webhook/tg",
    }


@app.post("/webhook/tg")
async def telegram_webhook(request: Request):
    if bot is None:
        raise HTTPException(status_code=503, detail="bot not initialized")
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    try:
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception as e:
        log.exception("Ошибка обработки апдейта: %s", e)
        # Отвечаем 200, чтобы Telegram не ретраил бесконечно
        return {"ok": True, "note": "error logged"}

    return {"ok": True}


@app.post("/api/create-invoice-link")
async def create_invoice_link(request: Request):
    if bot is None:
        raise HTTPException(status_code=503, detail="bot not initialized")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    pack_id = body.get("package_id")
    user_id = body.get("user_id") or 0

    pack = STARS_PACKAGES.get(pack_id)
    if not pack:
        raise HTTPException(status_code=400, detail="unknown package_id")

    stars = pack["stars"]
    coins = pack["coins"]

    payload = json.dumps({
        "package_id": pack_id,
        "coins": coins,
        "user_id": user_id,
    })

    try:
        link = await bot.create_invoice_link(
            title=f"{coins} монет",
            description=f"Пакет «{pack_id}» для Brainrots Funny",
            payload=payload,
            currency="XTR",
            prices=[LabeledPrice(label=f"{coins} монет", amount=stars)],
        )
    except Exception as e:
        log.exception("create_invoice_link error")
        raise HTTPException(status_code=500, detail=f"Telegram API error: {e}")

    log.info("Invoice link created: user=%s pack=%s stars=%s", user_id, pack_id, stars)
    return {"invoice_link": link, "stars": stars, "coins": coins}


@app.get("/api/balance/{user_id}")
async def get_balance(user_id: int):
    return get_user(user_id)


# ============================================================
# Локальный запуск
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
