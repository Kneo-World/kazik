# main.py
# -*- coding: utf-8 -*-
"""
Brainrots Funny — Telegram Mini App + Stars Payments
=====================================================
Один файл: aiogram 3 + FastAPI.
- Отдаёт index.html по корню "/"
- Обрабатывает Telegram webhook по "/webhook/tg"
- Создаёт инвойсы для Stars по "/api/create-invoice-link"
- Обрабатывает успешную оплату и зачисляет монеты (в памяти, для демо)

Деплой на Render:
1. Загрузи этот файл + index.html + requirements.txt в репозиторий
2. На Render выбери "Web Service"
3. Build Command: pip install -r requirements.txt
4. Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
5. Добавь переменные окружения:
   BOT_TOKEN=твой_токен_от_BotFather
   WEBHOOK_URL=https://твой-сервис.onrender.com
   RENDER_EXTERNAL_URL=https://твой-сервис.onrender.com  (Render подставляет сам)
"""

import os
import json
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import aiohttp
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher, Router, types
from aiogram.types import (
    Update,
    LabeledPrice,
    PreCheckoutQuery,
    Message,
)
from aiogram.methods import CreateInvoiceLink

# ============================================================
# КОНФИГ
# ============================================================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не установлен в переменных окружения")

# Папка с файлами (там же где main.py)
BASE_DIR = Path(__file__).parent.resolve()
INDEX_HTML = BASE_DIR / "index.html"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("brainrots")

# ============================================================
# БОТ И ДИСПЕТЧЕР
# ============================================================
bot = Bot(token=BOT_TOKEN, default=None)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Память для балансов (в проде — база данных!)
# { user_id: {"coins": int, "stars_spent": int, "purchases": int} }
USER_BALANCES: dict[int, dict] = {}

# Соответствие package_id -> (stars, coins, bonus%)
# Должно совпадать с STARS_PACKAGES во фронтенде!
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
    """Приветствие + кнопка Mini App."""
    if message.text and message.text.startswith("/start"):
        await message.answer(
            "🎮 <b>Brainrots Funny</b>\n\n"
            "Открывай приложение и крути кейсы!",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[
                    types.InlineKeyboardButton(
                        text="🎮 Открыть Brainrots Funny",
                        web_app=types.WebAppInfo(url=RENDER_URL or WEBHOOK_URL or "https://example.com")
                    )
                ]]
            ),
        )

@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    """Обязательно ответить в течение 10 секунд."""
    try:
        payload = json.loads(query.invoice_payload)
        pack_id = payload.get("package_id")
        if pack_id not in STARS_PACKAGES:
            await query.answer(ok=False, error_message="Неизвестный пакет")
            return
        # Можно проверить, не куплен ли уже этот пакет
        await query.answer(ok=True)
    except Exception as e:
        log.exception("pre_checkout error")
        await query.answer(ok=False, error_message="Ошибка валидации")

@router.message(types.ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment(message: Message):
    """Зачисляем монеты после оплаты."""
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

    log.info(
        "Payment: user=%s pack=%s stars=%s coins=%s",
        user_id, pack_id, pack["stars"], pack["coins"]
    )

    await message.answer(
        f"⭐ <b>Оплата прошла!</b>\n\n"
        f"Начислено: <b>+{pack['coins']} монет</b>\n"
        f"Потрачено: {pack['stars']} ⭐\n"
        f"Баланс: <b>{u['coins']} монет</b>"
    )

# ============================================================
# LIFESPAN — установка/удаление вебхука
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Устанавливаем вебхук при старте, удаляем при остановке."""
    if not WEBHOOK_URL and not RENDER_URL:
        log.warning("WEBHOOK_URL/RENDER_URL не заданы — вебхук не установлен")
        yield
        return

    base = WEBHOOK_URL or RENDER_URL
    webhook_path = "/webhook/tg"
    webhook_full = f"{base}{webhook_path}"
    log.info("Устанавливаю вебхук: %s", webhook_full)

    await bot.set_webhook(
        url=webhook_full,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
    )

    # Self-ping (чтобы Render Free не засыпал)
    ping_task = None
    if RENDER_URL:
        ping_task = asyncio.create_task(self_ping_loop(RENDER_URL))

    yield

    if ping_task:
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            pass

    await bot.delete_webhook()
    await bot.session.close()

async def self_ping_loop(base_url: str):
    """Пингуем себя каждые 10 минут, чтобы Render не уснул."""
    url = f"{base_url}/health"
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    log.debug("Self-ping: %s %s", r.status, url)
            except Exception as e:
                log.warning("Self-ping failed: %s", e)
            await asyncio.sleep(600)  # 10 минут

# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(lifespan=lifespan, title="Brainrots Funny API")

# Отдаём статику (картинки кейсов, брейнротов) если лежат рядом
if (BASE_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=BASE_DIR / "assets"), name="assets")

@app.get("/", response_class=HTMLResponse)
async def root():
    """Отдаём index.html."""
    if not INDEX_HTML.exists():
        return HTMLResponse(
            "<h1>index.html не найден</h1><p>Положи его рядом с main.py</p>",
            status_code=404,
        )
    return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))

@app.get("/health")
async def health():
    """Health-check и self-ping эндпоинт."""
    return {"ok": True, "service": "brainrots-funny"}

@app.post("/webhook/tg")
async def telegram_webhook(request: Request):
    """Принимаем апдейты от Telegram."""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.post("/api/create-invoice-link")
async def create_invoice_link(request: Request):
    """
    Фронтенд стучится сюда, чтобы получить ссылку на оплату.
    Body: { "package_id": "p50", "user_id": 123456789 }
    """
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
            currency="XTR",              # XTR = Telegram Stars
            prices=[LabeledPrice(label=f"{coins} монет", amount=stars)],
            provider_token=None,         # Для Stars — не нужен
            # subscription_period не ставим — это разовый платёж
        )
    except Exception as e:
        log.exception("create_invoice_link error")
        raise HTTPException(status_code=500, detail=f"Telegram API error: {e}")

    log.info("Invoice link created: user=%s pack=%s stars=%s", user_id, pack_id, stars)
    return {"invoice_link": link, "stars": stars, "coins": coins}

@app.get("/api/balance/{user_id}")
async def get_balance(user_id: int):
    """Опционально: посмотреть баланс юзера (в памяти)."""
    return get_user(user_id)

# ============================================================
# ЗАПУСК (для локального теста: python main.py)
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
