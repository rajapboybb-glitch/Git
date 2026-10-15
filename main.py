import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web, ClientSession
import yt_dlp

# --- SOZLAMALAR ---
BOT_TOKEN = "8958554064:AAEECvtT4QmjKTnzJQd8keBSjjWqh_W4KI0"
ADMIN_ID = 8738813282  # O'zingizning Telegram ID ingizni kiriting

# Render berganda avtomat PORT oladi, bo'lmasa 8080 ishlatadi
PORT = int(os.environ.get("PORT", 8080))
# Render platformasidagi veb saytingiz manzili (Render'da yaratilgach o'zgartirasiz)
RENDER_APP_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)

# --- MA'LUMOTLAR BAZASI ---
users = set()
channels = [] 

# --- STATES (Holatlar) ---
class AdminState(StatesGroup):
    add_channel_id = State()
    add_channel_url = State()
    broadcast_msg = State()

# --- KLAVIATURALAR ---
def get_admin_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Kanallar boshqaruvi")],
            [KeyboardButton(text="✉️ Xabar yuborish"), KeyboardButton(text="❌ Yopish")]
        ],
        resize_keyboard=True
    )

def get_channels_manage_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_channel")],
            [InlineKeyboardButton(text="📋 Kanallar ro'yxati / O'chirish", callback_data="list_channels")]
        ]
    )

async def check_subscriptions(user_id: int):
    not_subscribed = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch['id'], user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_subscribed.append(ch)
        except Exception:
            pass
    return not_subscribed

def get_sub_keyboard(not_subbed_channels):
    buttons = []
    for idx, ch in enumerate(not_subbed_channels, start=1):
        buttons.append([InlineKeyboardButton(text=f"➕ {idx}-Kanalga obuna bo'lish", url=ch['url'])])
    buttons.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- HANDLERLAR (FOYDALANUVCHI) ---

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    users.add(message.from_user.id)
    
    not_subbed = await check_subscriptions(message.from_user.id)
    if not_subbed:
        await message.answer(
            "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:",
            reply_markup=get_sub_keyboard(not_subbed)
        )
        return

    await message.answer(
        f"Assalomu alaykum, {message.from_user.full_name}!\n\n"
        "📹 Video yuklab olish uchun menga **Instagram, TikTok, YouTube** va boshqa platformalardan havola (link) yuboring."
    )

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(call: types.CallbackQuery):
    not_subbed = await check_subscriptions(call.from_user.id)
    if not_subbed:
        await call.answer("❌ Hamma kanallarga obuna bo'lmadingiz!", show_alert=True)
    else:
        await call.message.delete()
        await call.message.answer("✅ Rahmat! Endi video havolasini yuborishingiz mumkin.")

# --- ADMIN PANEL HANDLERLARI ---

@dp.message(F.text == "/admin", F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    await message.answer("👑 Admin panelga xush kelibsiz!", reply_markup=get_admin_main_kb())

@dp.message(F.text == "❌ Yopish", F.from_user.id == ADMIN_ID)
async def close_admin(message: types.Message):
    await message.answer("Admin panel yopildi.", reply_markup=types.ReplyKeyboardRemove())

@dp.message(F.text == "📊 Statistika", F.from_user.id == ADMIN_ID)
async def stats_cmd(message: types.Message):
    await message.answer(f"📊 **Bot statistikasi:**\n\nJami foydalanuvchilar: **{len(users)}** ta\nMajburiy kanallar: **{len(channels)}** ta")

@dp.message(F.text == "📢 Kanallar boshqaruvi", F.from_user.id == ADMIN_ID)
async def channels_manage(message: types.Message):
    await message.answer("📢 Majburiy obunalar bo'limi:", reply_markup=get_channels_manage_kb())

@dp.callback_query(F.data == "add_channel")
async def add_channel_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Kanal ID'sini kiriting (masalan: `-1001234567890`).\n\n*Eslatma: Bot ushbu kanalda ADMIN bo'lishi shart!*")
    await state.set_state(AdminState.add_channel_id)
    await call.answer()

@dp.message(AdminState.add_channel_id)
async def process_channel_id(message: types.Message, state: FSMContext):
    await state.update_data(ch_id=message.text.strip())
    await message.answer("Endi kanalga taklif havolasini (link) kiriting (masalan: `https://t.me/kanal_nomi`):")
    await state.set_state(AdminState.add_channel_url)

@dp.message(AdminState.add_channel_url)
async def process_channel_url(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ch_id = data['ch_id']
    ch_url = message.text.strip()
    
    channels.append({'id': ch_id, 'url': ch_url})
    await state.clear()
    await message.answer("✅ Kanal muvaffaqiyatli qo'shildi!", reply_markup=get_admin_main_kb())

@dp.callback_query(F.data == "list_channels")
async def list_channels_call(call: types.CallbackQuery):
    if not channels:
        await call.message.answer("Hozircha hech qanday kanal qo'shilmagan.")
        return
    
    kb = []
    for idx, ch in enumerate(channels):
        kb.append([InlineKeyboardButton(text=f"❌ O'chirish: {ch['id']}", callback_data=f"del_ch_{idx}")])
    
    await call.message.answer("Qo'shilgan kanallar ro'yxati (o'chirish uchun tugmani bosing):", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("del_ch_"))
async def delete_channel(call: types.CallbackQuery):
    idx = int(call.data.split("_")[2])
    if idx < len(channels):
        removed = channels.pop(idx)
        await call.answer("Kanal o'chirildi!", show_alert=True)
        await call.message.edit_text(f"Kanal ({removed['id']}) o'chirib tashlandi.")

@dp.message(F.text == "✉️ Xabar yuborish", F.from_user.id == ADMIN_ID)
async def broadcast_start(message: types.Message, state: FSMContext):
    await message.answer("Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yuboring:")
    await state.set_state(AdminState.broadcast_msg)

@dp.message(AdminState.broadcast_msg)
async def broadcast_process(message: types.Message, state: FSMContext):
    count = 0
    for u_id in users:
        try:
            await message.copy_to(chat_id=u_id)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await state.clear()
    await message.answer(f"✅ Xabar **{count}** ta foydalanuvchiga muvaffaqiyatli yuborildi!")

# --- VIDEO VA AUDIO YUKLASH TIZIMI ---

@dp.message(F.text.startswith("http"))
async def handle_media_link(message: types.Message):
    users.add(message.from_user.id)
    
    not_subbed = await check_subscriptions(message.from_user.id)
    if not_subbed:
        await message.answer(
            "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:",
            reply_markup=get_sub_keyboard(not_subbed)
        )
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎬 Video yuklash", callback_data=f"dl_vid"),
                InlineKeyboardButton(text="🎵 MP3 Audio yuklash", callback_data=f"dl_aud")
            ]
        ]
    )
    
    await message.reply("Formatni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.in_(["dl_vid", "dl_aud"]))
async def download_media(call: types.CallbackQuery):
    url = call.message.reply_to_message.text.strip()
    is_audio = call.data == "dl_aud"
    
    status_msg = await call.message.edit_text("⏳ Yuklanmoqda, iltimos kuting...")
    
    file_id = f"file_{call.from_user.id}"
    out_tmpl = f"{file_id}.%(ext)s"
    
    ydl_opts = {
        'outtmpl': out_tmpl,
        'quiet': True,
        'no_warnings': True,
    }

    if is_audio:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([url]))
        
        downloaded_file = None
        for f in os.listdir("."):
            if f.startswith(file_id):
                downloaded_file = f
                break

        if downloaded_file:
            await status_msg.edit_text("📤 Fayl Telegramga yuklanmoqda...")
            media_file = FSInputFile(downloaded_file)
            
            if is_audio or downloaded_file.endswith(".mp3"):
                await call.message.answer_audio(audio=media_file, caption="🎵 @SizningBotiz_bot orqali yuklab olindi")
            else:
                await call.message.answer_video(video=media_file, caption="🎬 @SizningBotiz_bot orqali yuklab olindi")
            
            await status_msg.delete()
            os.remove(downloaded_file)
        else:
            await status_msg.edit_text("❌ Videoni yuklab bo'lmadi. Havolani tekshirib qaytadan urinib ko'ring.")
            
    except Exception as e:
        logging.error(e)
        await status_msg.edit_text("❌ Xatolik yuz berdi yoki bu havola qo'llab-quvvatlanmaydi.")


# =========================================================
# --- SOXTA VEB-SAYT VA AUTO-PING TIZIMI (Render uchun) ---
# =========================================================

async def handle_web_request(request):
    """Saytga kurganda ko'rinadigan soxta sahifa"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head><title>Bot Server</title></head>
    <body style="font-family: Arial; text-align: center; margin-top: 50px;">
        <h1>🤖 Telegram Bot Server Live!</h1>
        <p>Status: <b style="color: green;">Active & Running 24/7</b></p>
    </body>
    </html>
    """
    return web.Response(text=html_content, content_type='text/html')

async def keep_alive():
    """Server o'chib qolmasligi uchun har 10 daqiqada o'ziga o'zi so'rov yuboradi"""
    await asyncio.sleep(10)
    while True:
        if RENDER_APP_URL:
            try:
                async with ClientSession() as session:
                    async with session.get(RENDER_APP_URL) as resp:
                        logging.info(f"Ping yuborildi. Status: {resp.status}")
            except Exception as e:
                logging.error(f"Pingda xatolik: {e}")
        await asyncio.sleep(600)  # Har 10 daqiqada (600 soniya) bir marta

# --- ISHGA TUSHIRISH ---
async def main():
    # 1. Soxta Veb Saytni sozlash
    app = web.Application()
    app.router.add_get('/', handle_web_request)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logging.info(f"Veb-server {PORT}-portda ishga tushdi.")

    # 2. Auto-ping'ni orqa fonda ishga tushirish
    asyncio.create_task(keep_alive())

    # 3. Bot Polling funksiyasini ishga tushirish
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    