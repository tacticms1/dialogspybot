import asyncio
import json
import logging
import os
import sys
import httpx
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import BusinessMessagesDeleted, Message, BusinessConnection, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from flask import Flask
from threading import Thread

# 1. Sozlamalar
def load_config():
    return {
        "BOT_TOKEN": os.getenv("BOT_TOKEN", "8819070930:AAHk9Zzer7d_phkG7AZ2L3nvCFYFCgqHPkU"),
        "OWNER_ID": int(os.getenv("OWNER_ID", 1087194622)),
        "DATABASE_NAME": "messages.json",
        "CONN_DB": "connections.json",
        "USERS_DB": "users.json", # Barcha start bosganlar
        "RENDER_URL": os.getenv("RENDER_EXTERNAL_URL"),
        "MESSAGES": {
            "START_TEXT": "DialogSpy bot ishga tushdi! Endi biznes hisobingizni ulab, o'chirilgan xabarlarni kuzatishingiz mumkin.",
            "EDIT_TEMPLATE": "✍️ Xabar o'zgartirildi!\nKim: {name}\nOld: {old}\nNew: {new}",
            "DELETE_TEMPLATE": "🗑 Xabar o'chirildi!\nKim: {name}\nKontent: {content}"
        }
    }

CONFIG = load_config()
OWNER_ID = CONFIG["OWNER_ID"]

# 2. Flask Web Server
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running"

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

# Foydalanuvchini bazaga qo'shish
def register_user(user: types.User):
    users = get_db(CONFIG["USERS_DB"])
    if str(user.id) not in users:
        users[str(user.id)] = {
            "full_name": user.full_name,
            "username": user.username,
            "joined_at": str(asyncio.get_event_loop().time())
        }
        save_db(CONFIG["USERS_DB"], users)

@dp.message(Command("start"))
async def start_cmd(m: Message):
    register_user(m.from_user)
    
    if m.from_user.id == OWNER_ID:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
            [InlineKeyboardButton(text="📢 Xabar yuborish", callback_data="admin_broadcast")]
        ])
        await m.answer("Salom, Ega! Admin panelga xush kelibsiz:", reply_markup=kb)
    else:
        await m.answer(CONFIG["MESSAGES"]["START_TEXT"])

# Admin callbacklari
@dp.callback_query(F.data == "admin_stats")
async def admin_stats(call: types.CallbackQuery):
    if call.from_user.id != OWNER_ID: return
    
    users = get_db(CONFIG["USERS_DB"])
    conns = get_db(CONFIG["CONN_DB"])
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
    await call.message.answer("Xabar matnini yuboring (yoki bekor qilish uchun /cancel):")
    await call.answer()

@dp.message(F.text, lambda m: m.from_user.id == OWNER_ID and not m.text.startswith("/"))
async def process_broadcast(m: Message):
    # Bu oddiyroq mailing mantiqi
    users = get_db(CONFIG["USERS_DB"])
    count = 0
    await m.answer(f"📢 {len(users)} ta foydalanuvchiga yuborish boshlandi...")
    
    for user_id in users:
        try:
            await bot.send_message(int(user_id), m.text)
            count += 1
            await asyncio.sleep(0.05) # Telegram limitidan oshmaslik uchun
        except:
            pass
    
    await m.answer(f"✅ Xabar {count} ta foydalanuvchiga yetkazildi.")

# 3. Handlerlar
@dp.business_connection()
async def on_business_connection(conn: BusinessConnection):
    conns = get_db(CONFIG["CONN_DB"])
    status = "ulandi" if conn.is_enabled else "uzildi"
    if conn.is_enabled:
        conns[conn.id] = {"user_id": conn.user.id, "full_name": conn.user.full_name}
    else:
        if conn.id in conns: del conns[conn.id]
    save_db(CONFIG["CONN_DB"], conns)
    
    logging.info(f"Biznes hisob {status}: {conn.id}")
    try:
        await bot.send_message(CONFIG["OWNER_ID"], f"🔔 Biznes hisobingiz botga {status}!")
    except Exception as e:
        logging.error(f"Connection xabari yuborishda xato: {e}")

@dp.business_message()
async def on_msg(m: Message):
    db = get_db(CONFIG["DATABASE_NAME"])
    conns = get_db(CONFIG["CONN_DB"])
    conn_info = conns.get(m.business_connection_id)
    if not conn_info: return

    name = m.from_user.full_name if m.from_user else "Noma'lum"
    f_id, m_type = None, "text"
    if m.photo: f_id, m_type = m.photo[-1].file_id, "photo"
    elif m.video: f_id, m_type = m.video.file_id, "video"
    elif m.document: f_id, m_type = m.document.file_id, "document"
    elif m.voice: f_id, m_type = m.voice.file_id, "voice"
    elif m.video_note: f_id, m_type = m.video_note.file_id, "video_note"
    elif m.audio: f_id, m_type = m.audio.file_id, "audio"
    elif m.sticker: f_id, m_type = m.sticker.file_id, "sticker"
    elif m.animation: f_id, m_type = m.animation.file_id, "animation"

    key = f"{m.chat.id}_{m.message_id}"
    db[key] = {
        "owner_id": conn_info["user_id"],
        "owner_name": conn_info["full_name"],
        "name": name,
        "text": m.text or m.caption or "",
        "file_id": f_id,
        "type": m_type
    }
    save_db(CONFIG["DATABASE_NAME"], db)
    logging.info(f"Xabar saqlandi: {key} ({name}) | Tur: {m_type}")

@dp.edited_business_message()
async def on_edit(m: Message):
    db = get_db(CONFIG["DATABASE_NAME"])
    key = f"{m.chat.id}_{m.message_id}"
    if key in db:
        old = db[key]
        text = CONFIG["MESSAGES"]["EDIT_TEMPLATE"].format(
            name=old["name"], old=old["text"] or "[Media]", new=m.text or m.caption or "[Media]"
        )
        await bot.send_message(old["owner_id"], text)
        if old["owner_id"] != OWNER_ID:
            await bot.send_message(OWNER_ID, f"🕵️ **MONITORING** ({old['owner_name']}):\n{text}")
    await on_msg(m)

@dp.business_messages_deleted()
async def on_delete(ev: BusinessMessagesDeleted):
    db = get_db(CONFIG["DATABASE_NAME"])
    for mid in ev.message_ids:
        key = f"{ev.chat.id}_{mid}"
        if key in db:
            old = db[key]
            cap = CONFIG["MESSAGES"]["DELETE_TEMPLATE"].format(name=old["name"], content=old["text"])
            
            async def send_all(chat_id, caption, is_admin=False):
                prefix = f"🕵️ **MONITORING** ({old['owner_name']})\n" if is_admin else ""
                full_caption = prefix + caption
                try:
                    mt = old["type"]
                    fid = old["file_id"]
                    
                    if mt == "text" or not fid:
                        await bot.send_message(chat_id, full_caption)
                    elif mt in ["sticker", "video_note"]:
                        # Bu turlar caption qo'llab-quvvatlamaydi
                        m_func = getattr(bot, f"send_{mt}")
                        await m_func(chat_id, fid)
                        await bot.send_message(chat_id, full_caption)
                    else:
                        # Photo, video, document, voice, audio, animation
                        m_func = getattr(bot, f"send_{mt}")
                        await m_func(chat_id, fid, caption=full_caption)
                except Exception as e:
                    logging.error(f"Xabar yuborishda xato: {e}")
                    # Xatolik bo'lsa ham hech bo'lmasa matnni yuboramiz
                    try:
                        await bot.send_message(chat_id, full_caption)
                    except: pass

            await send_all(old["owner_id"], cap)
            if old["owner_id"] != OWNER_ID:
                await send_all(OWNER_ID, cap, True)
        else:
            logging.warning(f"O'chirilgan xabar bazadan topilmadi: {key}")

if __name__ == "__main__":
    Thread(target=run_web).start()
    asyncio.run(dp.start_polling(bot))
