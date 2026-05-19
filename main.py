import asyncio
import json
import logging
import os
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.types import BusinessMessagesDeleted, Message
from aiogram.filters import Command
from flask import Flask
from threading import Thread

# 1. Sozlamalar
def load_config():
    return {
        "BOT_TOKEN": os.getenv("BOT_TOKEN", "8819070930:AAFKDEpnlNUTm_0V5L2F7KQn0_yC-gXtnoY"),
        "OWNER_ID": int(os.getenv("OWNER_ID", 1087194622)),
        "DATABASE_NAME": "messages.json",
        "MESSAGES": {
            "START_TEXT": "DialogSpy bot ishga tushdi!",
            "EDIT_TEMPLATE": "✍️ Xabar o'zgartirildi!\nKim: {name}\nOld: {old}\nNew: {new}",
            "DELETE_TEMPLATE": "🗑 Xabar o'chirildi!\nKim: {name}\nKontent: {content}",
            "UNAUTHORIZED": "Bu bot shaxsiy foydalanish uchun."
        }
    }

CONFIG = load_config()

# 2. Flask Web Server (Render uchun)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    # Render'da port doim 10000 yoki o'zgaruvchida keladi
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# 3. Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 4. Bot sozlamalari
bot = Bot(token=CONFIG["BOT_TOKEN"])
dp = Dispatcher()

# 5. JSON Baza
def get_db():
    if os.path.exists(CONFIG["DATABASE_NAME"]):
        with open(CONFIG["DATABASE_NAME"], "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_db(db):
    with open(CONFIG["DATABASE_NAME"], "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)

# 6. Handlerlar
@dp.business_message()
async def on_msg(m: Message):
    db = get_db()
    name = m.from_user.full_name if m.from_user else "Noma'lum"
    f_id, m_type = None, "text"
    if m.photo: f_id, m_type = m.photo[-1].file_id, "photo"
    elif m.video: f_id, m_type = m.video.file_id, "video"
    elif m.document: f_id, m_type = m.document.file_id, "document"
    elif m.voice: f_id, m_type = m.voice.file_id, "voice"
    elif m.video_note: f_id, m_type = m.video_note.file_id, "video_note"
    elif m.audio: f_id, m_type = m.audio.file_id, "audio"

    db[f"{m.chat.id}_{m.message_id}"] = {
        "name": name,
        "text": m.text or m.caption or "",
        "file_id": f_id,
        "type": m_type
    }
    save_db(db)

@dp.edited_business_message()
async def on_edit(m: Message):
    db = get_db()
    key = f"{m.chat.id}_{m.message_id}"
    if key in db:
        old = db[key]
        text = CONFIG["MESSAGES"]["EDIT_TEMPLATE"].format(
            name=old["name"],
            old=old["text"] or "[Media]",
            new=m.text or m.caption or "[Media]"
        )
        await bot.send_message(CONFIG["OWNER_ID"], text)
    await on_msg(m)

@dp.deleted_business_messages()
async def on_delete(ev: BusinessMessagesDeleted):
    db = get_db()
    for mid in ev.message_ids:
        key = f"{ev.chat.id}_{mid}"
        if key in db:
            old = db[key]
            cap = CONFIG["MESSAGES"]["DELETE_TEMPLATE"].format(name=old["name"], content=old["text"])
            oid, fid, mt = CONFIG["OWNER_ID"], old["file_id"], old["type"]
            try:
                if mt == "text" or not fid: await bot.send_message(oid, cap)
                elif mt == "photo": await bot.send_photo(oid, fid, caption=cap)
                elif mt == "video": await bot.send_video(oid, fid, caption=cap)
                elif mt == "document": await bot.send_document(oid, fid, caption=cap)
                elif mt == "voice": await bot.send_voice(oid, fid, caption=cap)
                elif mt == "audio": await bot.send_audio(oid, fid, caption=cap)
                elif mt == "video_note":
                    await bot.send_video_note(oid, fid)
                    await bot.send_message(oid, cap)
            except: pass

@dp.message(Command("start"))
async def start(m: Message):
    if m.from_user.id == CONFIG["OWNER_ID"]:
        await m.answer(CONFIG["MESSAGES"]["START_TEXT"])
    else:
        await m.answer(CONFIG["MESSAGES"]["UNAUTHORIZED"])

# 7. ASOSIY QISM (Run)
if __name__ == "__main__":
    # 1-qadam: Web serverni alohida oqimda boshlash
    Thread(target=run_web).start()
    
    # 2-qadam: Botni boshlash
    print("Bot started...")
    asyncio.run(dp.start_polling(bot))
