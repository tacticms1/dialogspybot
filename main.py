import asyncio
import json
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import BusinessMessagesDeleted, Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramUnauthorizedError

# 1. JSON dan barcha sozlamalarni yuklash
def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

CONFIG = load_config()
MSGS = CONFIG["MESSAGES"]

# Botni sozlash
try:
    bot = Bot(token=CONFIG["BOT_TOKEN"])
    dp = Dispatcher()
except Exception:
    print("\n[!] XATO: config.json ichidagi BOT_TOKEN noto'g'ri!")
    exit()

# 2. JSON Baza (Xabarlarni saqlash uchun)
def get_db():
    if os.path.exists(CONFIG["DATABASE_NAME"]):
        with open(CONFIG["DATABASE_NAME"], "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_db(db):
    with open(CONFIG["DATABASE_NAME"], "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)

# 3. Handlerlar
@dp.business_message()
async def on_msg(m: Message):
    db = get_db()
    name = m.from_user.full_name if m.from_user else "Noma'lum"
    
    # Medianini aniqlash
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
        text = MSGS["EDIT_TEMPLATE"].format(
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
            cap = MSGS["DELETE_TEMPLATE"].format(name=old["name"], content=old["text"])
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
            except Exception: pass

@dp.message(Command("start"))
async def start(m: Message):
    if m.from_user.id == CONFIG["OWNER_ID"]:
        await m.answer(MSGS["START_TEXT"])
    else:
        await m.answer(MSGS["UNAUTHORIZED"])

async def main():
    print(f"\n[+] Bot ishga tushdi! (Ega ID: {CONFIG['OWNER_ID']})")
    try:
        await dp.start_polling(bot)
    except TelegramUnauthorizedError:
        print("\n[!] XATO: config.json dagi token noto'g'ri!")

if __name__ == "__main__":
    asyncio.run(main())
