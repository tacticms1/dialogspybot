import asyncio
import json
import logging
import os
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.types import BusinessMessagesDeleted, Message, BusinessConnection
from aiogram.filters import Command
from flask import Flask
from threading import Thread

# 1. Sozlamalar
def load_config():
    return {
        "BOT_TOKEN": os.getenv("BOT_TOKEN", "8819070930:AAFKDEpnlNUTm_0V5L2F7KQn0_yC-gXtnoY"),
        "OWNER_ID": int(os.getenv("OWNER_ID", 1087194622)),
        "DATABASE_NAME": "messages.json",
        "CONN_DB": "connections.json", # Ulanishlarni saqlash uchun
        "MESSAGES": {
            "START_TEXT": "DialogSpy bot ishga tushdi! Endi biznes hisobingizni ulab, o'chirilgan xabarlarni kuzatishingiz mumkin.",
            "EDIT_TEMPLATE": "✍️ Xabar o'zgartirildi!\nKim: {name}\nOld: {old}\nNew: {new}",
            "DELETE_TEMPLATE": "🗑 Xabar o'chirildi!\nKim: {name}\nKontent: {content}",
            "UNAUTHORIZED": "Bu bot shaxsiy foydalanish uchun."
        }
    }

CONFIG = load_config()

# 2. Flask Web Server (Render uchun)
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# 3. Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 4. Bot sozlamalari
bot = Bot(token=CONFIG["BOT_TOKEN"])
dp = Dispatcher()

# 5. Baza funksiyalari (JSON)
def get_db(file_name):
    if os.path.exists(file_name):
        with open(file_name, "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_db(file_name, db):
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)

# 6. Handlerlar

# Biznes ulanishlarni saqlash (kim botni ulaganini bilish uchun)
@dp.business_connection()
async def on_business_connection(conn: BusinessConnection):
    conns = get_db(CONFIG["CONN_DB"])
    if conn.is_enabled:
        conns[conn.id] = conn.user.id
        logger.info(f"Yangi ulanish: {conn.id} -> User: {conn.user.id}")
    else:
        if conn.id in conns:
            del conns[conn.id]
            logger.info(f"Ulanish uzildi: {conn.id}")
    save_db(CONFIG["CONN_DB"], conns)

@dp.business_message()
async def on_msg(m: Message):
    db = get_db(CONFIG["DATABASE_NAME"])
    conns = get_db(CONFIG["CONN_DB"])
    
    # Xabar egasini (biznes egasini) aniqlash
    owner_id = conns.get(m.business_connection_id)
    if not owner_id:
        return # Agar ulanish bazada bo'lmasa, saqlamaymiz

    name = m.from_user.full_name if m.from_user else "Noma'lum"
    f_id, m_type = None, "text"
    if m.photo: f_id, m_type = m.photo[-1].file_id, "photo"
    elif m.video: f_id, m_type = m.video.file_id, "video"
    elif m.document: f_id, m_type = m.document.file_id, "document"
    elif m.voice: f_id, m_type = m.voice.file_id, "voice"
    elif m.video_note: f_id, m_type = m.video_note.file_id, "video_note"
    elif m.audio: f_id, m_type = m.audio.file_id, "audio"

    db[f"{m.chat.id}_{m.message_id}"] = {
        "owner_id": owner_id, # Xabar aynan kimniki ekanini saqlaymiz
        "name": name,
        "text": m.text or m.caption or "",
        "file_id": f_id,
        "type": m_type
    }
    save_db(CONFIG["DATABASE_NAME"], db)

@dp.edited_business_message()
async def on_edit(m: Message):
    db = get_db(CONFIG["DATABASE_NAME"])
    key = f"{m.chat.id}_{m.message_id}"
    if key in db:
        old = db[key]
        text = CONFIG["MESSAGES"]["EDIT_TEMPLATE"].format(
            name=old["name"],
            old=old["text"] or "[Media]",
            new=m.text or m.caption or "[Media]"
        )
        # Xabarnomani FAQAT o'sha biznes egasiga yuboramiz
        await bot.send_message(old["owner_id"], text)
    await on_msg(m)

@dp.deleted_business_messages()
async def on_delete(ev: BusinessMessagesDeleted):
    db = get_db(CONFIG["DATABASE_NAME"])
    for mid in ev.message_ids:
        key = f"{ev.chat.id}_{mid}"
        if key in db:
            old = db[key]
            cap = CONFIG["MESSAGES"]["DELETE_TEMPLATE"].format(name=old["name"], content=old["text"])
            target_id, fid, mt = old["owner_id"], old["file_id"], old["type"]
            
            try:
                if mt == "text" or not fid: await bot.send_message(target_id, cap)
                elif mt == "photo": await bot.send_photo(target_id, fid, caption=cap)
                elif mt == "video": await bot.send_video(target_id, fid, caption=cap)
                elif mt == "document": await bot.send_document(target_id, fid, caption=cap)
                elif mt == "voice": await bot.send_voice(target_id, fid, caption=cap)
                elif mt == "audio": await bot.send_audio(target_id, fid, caption=cap)
                elif mt == "video_note":
                    await bot.send_video_note(target_id, fid)
                    await bot.send_message(target_id, cap)
            except: pass

@dp.message(Command("start"))
async def start(m: Message):
    await m.answer(CONFIG["MESSAGES"]["START_TEXT"])

if __name__ == "__main__":
    Thread(target=run_web).start()
    print("Bot started for multi-users...")
    asyncio.run(dp.start_polling(bot))
