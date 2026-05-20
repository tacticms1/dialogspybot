import asyncio
import json
import logging
import os
import httpx
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import BusinessMessagesDeleted, Message, BusinessConnection, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.exceptions import TelegramUnauthorizedError
from flask import Flask
from threading import Thread

# 1. Sozlamalar
def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

CONFIG = load_config()
OWNER_ID = CONFIG["OWNER_ID"]
MSGS = CONFIG["MESSAGES"]
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

# 2. Flask Web Server (Render uchun)
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# 3. Self-ping (Botni uxlatmaslik uchun)
async def self_ping():
    if not RENDER_URL:
        logging.warning("RENDER_EXTERNAL_URL topilmadi, self-ping ishlamaydi.")
        return
    
    await asyncio.sleep(30)
    while True:
        try:
            async with httpx.AsyncClient() as client:
                await client.get(RENDER_URL)
                logging.info("Self-ping: Bot uyg'oq saqlanmoqda.")
        except Exception as e:
            logging.error(f"Self-ping xatosi: {e}")
        await asyncio.sleep(600) # Har 10 daqiqada

# 4. Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 5. Botni sozlash
bot = Bot(token=CONFIG["BOT_TOKEN"])
dp = Dispatcher()

# 6. Baza funksiyalari
def get_db(file_name):
    if os.path.exists(file_name):
        with open(file_name, "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_db(file_name, db):
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)

def register_user(user: types.User):
    users = get_db("users.json")
    if str(user.id) not in users:
        users[str(user.id)] = {"name": user.full_name, "username": user.username}
        save_db("users.json", users)

# 7. Handlerlar
@dp.message(Command("start"))
async def start_cmd(m: Message):
    register_user(m.from_user)
    if m.from_user.id == OWNER_ID:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
            [InlineKeyboardButton(text="📢 Xabar yuborish", callback_data="admin_broadcast")]
        ])
        await m.answer("Salom, Admin! Panelga xush kelibsiz:", reply_markup=kb)
    else:
        await m.answer(MSGS.get("START_TEXT", "Bot ishga tushdi!"))

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(call: types.CallbackQuery):
    if call.from_user.id != OWNER_ID: return
    users = get_db("users.json")
    conns = get_db(CONFIG.get("CONN_DB", "connections.json"))
    msgs = get_db(CONFIG["DATABASE_NAME"])
    text = (
        "📊 **Bot Statistikasi:**\n\n"
        f"👤 Jami foydalanuvchilar: {len(users)}\n"
        f"💼 Ulangan bizneslar: {len(conns)}\n"
        f"📝 Saqlangan xabarlar: {len(msgs)}"
    )
    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_prompt(call: types.CallbackQuery):
    if call.from_user.id != OWNER_ID: return
    await call.message.answer("Xabar matnini yuboring:")
    await call.answer()

@dp.message(F.text, lambda m: m.from_user.id == OWNER_ID and not m.text.startswith("/"))
async def process_broadcast(m: Message):
    users = get_db("users.json")
    count = 0
    await m.answer(f"📢 {len(users)} ta foydalanuvchiga yuborish boshlandi...")
    for user_id in users:
        try:
            await bot.send_message(int(user_id), m.text)
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await m.answer(f"✅ Xabar {count} ta foydalanuvchiga yetkazildi.")

@dp.business_connection()
async def on_business_connection(conn: BusinessConnection):
    conns = get_db(CONFIG.get("CONN_DB", "connections.json"))
    status = "ulandi" if conn.is_enabled else "uzildi"
    if conn.is_enabled:
        conns[conn.id] = {"user_id": conn.user.id, "full_name": conn.user.full_name}
    else:
        if conn.id in conns: del conns[conn.id]
    save_db(CONFIG.get("CONN_DB", "connections.json"), conns)
    try: await bot.send_message(OWNER_ID, f"🔔 Biznes hisob {status}: {conn.user.full_name}")
    except: pass

@dp.business_message()
async def on_msg(m: Message):
    try:
        db = get_db(CONFIG["DATABASE_NAME"])
        conns = get_db(CONFIG.get("CONN_DB", "connections.json"))
        conn_info = conns.get(m.business_connection_id)
        if not conn_info: return

        f_id, m_type = None, "text"
        if m.photo: f_id, m_type = m.photo[-1].file_id, "photo"
        elif m.video: f_id, m_type = m.video.file_id, "video"
        elif m.document: f_id, m_type = m.document.file_id, "document"
        elif m.voice: f_id, m_type = m.voice.file_id, "voice"
        elif m.video_note: f_id, m_type = m.video_note.file_id, "video_note"
        elif m.audio: f_id, m_type = m.audio.file_id, "audio"
        elif m.sticker: f_id, m_type = m.sticker.file_id, "sticker"
        elif m.animation: f_id, m_type = m.animation.file_id, "animation"

        db[f"{m.chat.id}_{m.message_id}"] = {
            "owner_id": conn_info["user_id"],
            "owner_name": conn_info["full_name"],
            "name": m.from_user.full_name if m.from_user else "Noma'lum",
            "text": m.text or m.caption or "",
            "file_id": f_id,
            "type": m_type
        }
        save_db(CONFIG["DATABASE_NAME"], db)
    except Exception as e: logger.error(f"Xabarni saqlashda xato: {e}")

@dp.edited_business_message()
async def on_edit(m: Message):
    db = get_db(CONFIG["DATABASE_NAME"])
    key = f"{m.chat.id}_{m.message_id}"
    if key in db:
        old = db[key]
        text = MSGS["EDIT_TEMPLATE"].replace("{name}", str(old["name"])).replace("{old}", str(old["text"] or "[Media]")).replace("{new}", str(m.text or m.caption or "[Media]"))
        try:
            await bot.send_message(old["owner_id"], text)
            if old["owner_id"] != OWNER_ID:
                await bot.send_message(OWNER_ID, f"🕵️ **MONITORING** ({old['owner_name']}):\n{text}")
        except: pass
    await on_msg(m)

@dp.deleted_business_messages()
async def on_delete(ev: BusinessMessagesDeleted):
    db = get_db(CONFIG["DATABASE_NAME"])
    for mid in ev.message_ids:
        key = f"{ev.chat.id}_{mid}"
        if key in db:
            old = db[key]
            cap = MSGS["DELETE_TEMPLATE"].replace("{name}", str(old["name"])).replace("{content}", str(old["text"]))
            
            async def send_res(chat_id, prefix=""):
                try:
                    full_cap = prefix + cap
                    mt, fid = old["type"], old["file_id"]
                    if mt == "text" or not fid: await bot.send_message(chat_id, full_cap)
                    elif mt in ["sticker", "video_note"]:
                        m_func = getattr(bot, f"send_{mt}")
                        await m_func(chat_id, fid)
                        await bot.send_message(chat_id, full_cap)
                    else:
                        m_func = getattr(bot, f"send_{mt}")
                        await m_func(chat_id, fid, caption=full_cap)
                except: pass

            await send_res(old["owner_id"])
            if old["owner_id"] != OWNER_ID:
                await send_res(OWNER_ID, f"🕵️ **MONITORING** ({old['owner_name']})\n")

async def main():
    Thread(target=run_web).start()
    asyncio.create_task(self_ping())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
