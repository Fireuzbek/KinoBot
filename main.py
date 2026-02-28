import asyncio
import logging
import os
from datetime import datetime, timedelta
import aiosqlite
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, \
    InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.filters import CommandStart, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ==========================================
# 1. SOZLAMALAR VA BAZA
# ==========================================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(admin_id) for admin_id in os.getenv("ADMIN_IDS", "").split(",") if admin_id.isdigit()]
DB_NAME = "database.sqlite"


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, username TEXT, fullname TEXT, phone TEXT, join_date DATE
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS movies (
            code INTEGER PRIMARY KEY, name TEXT, language TEXT, quality TEXT, 
            genre TEXT, description TEXT, file_id TEXT, views_count INTEGER DEFAULT 0
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS forced_channels (
            chat_id TEXT PRIMARY KEY, url TEXT
        )""")
        await db.commit()


async def execute_db(query: str, params: tuple = ()):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(query, params)
        await db.commit()
        return cursor


async def fetch_db(query: str, params: tuple = (), fetchall=False):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(query, params)
        return await cursor.fetchall() if fetchall else await cursor.fetchone()


# ==========================================
# 2. STATE VA FILTRLAR
# ==========================================
class MovieState(StatesGroup):
    code = State();
    name = State();
    language = State();
    quality = State()
    genre = State();
    description = State();
    file_id = State()


class ChannelState(StatesGroup):
    chat_id = State();
    url = State()


class BroadcastState(StatesGroup):
    text = State()


class IsAdmin(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id in ADMIN_IDS


# ==========================================
# 3. KLAVIATURALAR
# ==========================================
admin_main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎬 Kino qo'shish"), KeyboardButton(text="🗑 Kino o'chirish")],
        [KeyboardButton(text="📢 Kanal qo'shish"), KeyboardButton(text="❌ Kanal o'chirish")],
        [KeyboardButton(text="✉️ Hammaga xabar"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="👥 Foydalanuvchilar")]
    ], resize_keyboard=True
)

contact_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]],
    resize_keyboard=True, one_time_keyboard=True
)


def force_sub_kb(channels: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i, channel in enumerate(channels, 1):
        builder.row(InlineKeyboardButton(text=f"📢 {i}-kanalga obuna bo'lish", url=channel[1]))
    builder.row(InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub"))
    return builder.as_markup()


# ==========================================
# 4. ADMIN ROUTER
# ==========================================
admin_router = Router()
admin_router.message.filter(IsAdmin())


@admin_router.message(F.text == "/admin")
async def admin_start(message: Message):
    await message.answer("Admin paneliga xush kelibsiz!", reply_markup=admin_main_kb)


@admin_router.message(F.text == "📊 Statistika")
async def show_stats(message: Message):
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)
    total = (await fetch_db("SELECT COUNT(*) FROM users"))[0]
    today_users = (await fetch_db("SELECT COUNT(*) FROM users WHERE join_date = ?", (today,)))[0]
    week_users = (await fetch_db("SELECT COUNT(*) FROM users WHERE join_date >= ?", (week_ago,)))[0]
    top_movie = await fetch_db("SELECT name, views_count FROM movies ORDER BY views_count DESC LIMIT 1")
    top_m_text = f"«{top_movie[0]}» ({top_movie[1]} ta ko'rish)" if top_movie else "Hali kino yo'q"
    text = f"📈 <b>Bot Statistikasi:</b>\n\n👥 Jami: {total}\n👤 Bugun: {today_users}\n📅 Oxirgi 7 kun: {week_users}\n🏆 Top kino: {top_m_text}"
    await message.answer(text, parse_mode="HTML")


@admin_router.message(F.text == "👥 Foydalanuvchilar")
async def list_users(message: Message):
    users = await fetch_db("SELECT id, fullname, username, phone FROM users ORDER BY join_date DESC LIMIT 50",
                           fetchall=True)

    if not users:
        return await message.answer("Foydalanuvchilar topilmadi.")

    text = "📂 <b>Foydalanuvchilar ro'yxati (oxirgi 50 ta):</b>\n\n"
    for u in users:
        user_link = f"@{u[2]}" if u[2] else "yo'q"
        text += (f"👤 <b>Ism:</b> {u[1]}\n"
                 f"🆔 <b>ID:</b> <code>{u[0]}</code>\n"
                 f"🔗 <b>User:</b> {user_link}\n"
                 f"📞 <b>Tel:</b> {u[3]}\n"
                 f"────────────────────\n")

    if len(text) > 4096:
        for x in range(0, len(text), 4096):
            await message.answer(text[x:x + 4096], parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


# --- KANAL BOSHQARUVI ---
@admin_router.message(F.text == "📢 Kanal qo'shish")
async def add_channel_start(message: Message, state: FSMContext):
    await message.answer("Kanal ID sini yuboring (masalan: -100123456789):")
    await state.set_state(ChannelState.chat_id)


@admin_router.message(ChannelState.chat_id)
async def add_channel_id(message: Message, state: FSMContext):
    await state.update_data(chat_id=message.text)
    await message.answer("Kanal linkini yuboring (masalan: https://t.me/kanal_link):")
    await state.set_state(ChannelState.url)


@admin_router.message(ChannelState.url)
async def add_channel_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    await execute_db("INSERT OR REPLACE INTO forced_channels (chat_id, url) VALUES (?, ?)",
                     (data['chat_id'], message.text))
    await message.answer("✅ Kanal majburiy obunaga qo'shildi!")
    await state.clear()


@admin_router.message(F.text == "❌ Kanal o'chirish")
async def delete_channel_start(message: Message):
    channels = await fetch_db("SELECT chat_id FROM forced_channels", fetchall=True)
    if not channels: return await message.answer("Kanallar yo'q.")

    builder = InlineKeyboardBuilder()
    for ch in channels:
        builder.row(InlineKeyboardButton(text=f"❌ {ch[0]}", callback_data=f"del_ch_{ch[0]}"))
    await message.answer("O'chirmoqchi bo'lgan kanalingizni tanlang:", reply_markup=builder.as_markup())


@admin_router.callback_query(F.data.startswith("del_ch_"))
async def delete_channel_finish(call: CallbackQuery):
    chat_id = call.data.replace("del_ch_", "")
    await execute_db("DELETE FROM forced_channels WHERE chat_id = ?", (chat_id,))
    await call.answer("Kanal o'chirildi", show_alert=True)
    await call.message.delete()


# --- HAMMAGA XABAR ---
@admin_router.message(F.text == "✉️ Hammaga xabar")
async def broadcast_start(message: Message, state: FSMContext):
    await message.answer("Xabar matnini yuboring (rasm yoki video ham mumkin):")
    await state.set_state(BroadcastState.text)


@admin_router.message(BroadcastState.text)
async def broadcast_finish(message: Message, state: FSMContext, bot: Bot):
    users = await fetch_db("SELECT id FROM users", fetchall=True)
    count = 0
    msg = await message.answer(f"Xabar yuborilmoqda: 0/{len(users)}")

    for user in users:
        try:
            await message.copy_to(chat_id=user[0])
            count += 1
            if count % 10 == 0:
                await msg.edit_text(f"Xabar yuborilmoqda: {count}/{len(users)}")
        except:
            pass
        await asyncio.sleep(0.05)

    await message.answer(f"✅ Xabar {count} ta foydalanuvchiga yuborildi!")
    await state.clear()


# --- KINO O'CHIRISH ---
@admin_router.message(F.text == "🗑 Kino o'chirish")
async def delete_movie_start(message: Message, state: FSMContext):
    await message.answer("O'chirmoqchi bo'lgan kino kodini yuboring:")
    await state.set_state("waiting_for_del_code")


@admin_router.message(F.state == "waiting_for_del_code")
async def delete_movie_finish(message: Message, state: FSMContext):
    res = await execute_db("DELETE FROM movies WHERE code = ?", (message.text,))
    await message.answer("✅ Kino o'chirildi!" if res.rowcount > 0 else "❌ Bu kod bilan kino topilmadi.")
    await state.clear()


# --- KINO QO'SHISH ---
@admin_router.message(F.text == "🎬 Kino qo'shish")
async def add_movie_start(message: Message, state: FSMContext):
    await message.answer("Kino kodini kiriting:")
    await state.set_state(MovieState.code)


@admin_router.message(MovieState.code)
async def add_movie_code(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Faqat raqam kiriting!")
    await state.update_data(code=int(message.text))
    await message.answer("Kino nomini kiriting:")
    await state.set_state(MovieState.name)


@admin_router.message(MovieState.name)
async def add_movie_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Kino tilini kiriting:")
    await state.set_state(MovieState.language)


@admin_router.message(MovieState.language)
async def add_movie_lang(message: Message, state: FSMContext):
    await state.update_data(language=message.text)
    await message.answer("Sifatini kiriting:")
    await state.set_state(MovieState.quality)


@admin_router.message(MovieState.quality)
async def add_movie_quality(message: Message, state: FSMContext):
    await state.update_data(quality=message.text)
    await message.answer("Janrini kiriting:")
    await state.set_state(MovieState.genre)


@admin_router.message(MovieState.genre)
async def add_movie_genre(message: Message, state: FSMContext):
    await state.update_data(genre=message.text)
    await message.answer("Tavsifini kiriting:")
    await state.set_state(MovieState.description)


@admin_router.message(MovieState.description)
async def add_movie_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Video faylni yuboring:")
    await state.set_state(MovieState.file_id)


@admin_router.message(MovieState.file_id, F.video)
async def add_movie_file(message: Message, state: FSMContext):
    data = await state.get_data()
    await execute_db(
        "INSERT OR REPLACE INTO movies (code, name, language, quality, genre, description, file_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (data['code'], data['name'], data['language'], data['quality'], data['genre'], data['description'],
         message.video.file_id)
    )
    await message.answer("✅ Kino muvaffaqiyatli saqlandi!")
    await state.clear()


# ==========================================
# 5. USER ROUTER
# ==========================================
user_router = Router()


async def check_sub(user_id: int, bot: Bot):
    channels = await fetch_db("SELECT chat_id, url FROM forced_channels", fetchall=True)
    unsubbed = []
    for ch in channels:
        try:
            # Kanal ID raqam bo'lsa uni stringga o'tkazamiz
            chat_id = str(ch[0]).strip()
            # Bot admin bo'lishi shart!
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status in ['left', 'kicked']:
                unsubbed.append(ch)
        except Exception as e:
            # Agar bot kanalda admin bo'lmasa yoki ID xato bo'lsa bu yerga tushadi
            logging.error(f"Kanalda xatolik: {ch[0]} - {e}")
    return unsubbed


@user_router.message(CommandStart())
async def cmd_start(message: Message):
    user = await fetch_db("SELECT phone FROM users WHERE id = ?", (message.from_user.id,))
    if not user or not user[0]:
        return await message.answer(
            f"Assalomu alaykum, {message.from_user.full_name}!\n"
            f"Botdan foydalanish uchun telefon raqamingizni yuboring:",
            reply_markup=contact_kb
        )
    await message.answer("Kino kodini yuboring.")


@user_router.message(F.contact)
async def get_contact(message: Message, bot: Bot):
    if message.contact.user_id != message.from_user.id:
        return await message.answer("Iltimos, o'zingizni telefon raqamingizni yuboring!")

    await execute_db("INSERT OR REPLACE INTO users (id, username, fullname, phone, join_date) VALUES (?, ?, ?, ?, ?)",
                     (message.from_user.id, message.from_user.username, message.from_user.full_name,
                      message.contact.phone_number, datetime.now().date()))

    await message.answer("✅ Muvaffaqiyatli ro'yxatdan o'tdingiz!", reply_markup=ReplyKeyboardRemove())


@user_router.callback_query(F.data == "check_sub")
async def check_sub_callback(call: CallbackQuery, bot: Bot):
    unsubbed = await check_sub(call.from_user.id, bot)
    if unsubbed:
        await call.answer("Hali hamma kanallarga obuna bo'lmadingiz!", show_alert=True)
    else:
        await call.message.delete()
        await call.message.answer("✅ Obuna tasdiqlandi. Kino kodini yuborishingiz mumkin.")


@user_router.message(F.text)
async def search_movie(message: Message, bot: Bot):
    user = await fetch_db("SELECT id FROM users WHERE id = ?", (message.from_user.id,))
    if not user:
        return await message.answer("Iltimos, avval /start buyrug'ini bosing!", reply_markup=contact_kb)

    # Obunani tekshirish (Admin bo'lsa tekshirmaymiz)
    if message.from_user.id not in ADMIN_IDS:
        unsubbed = await check_sub(message.from_user.id, bot)
        if unsubbed:
            return await message.answer("Botdan foydalanish uchun kanallarga obuna bo'ling:",
                                        reply_markup=force_sub_kb(unsubbed))

    movie = await fetch_db("SELECT * FROM movies WHERE code = ? OR name LIKE ?", (message.text, f"%{message.text}%"))
    if movie:
        await execute_db("UPDATE movies SET views_count = views_count + 1 WHERE code = ?", (movie[0],))
        cap = f"🎬Nomi {movie[1]}\n👁 Korishlar {movie[7] + 1} marta ko'rildi\n🔢 Kodi:  {movie[0]}"
        await message.answer_video(video=movie[6], caption=cap)
    else:
        await message.answer("Kechirasiz, bunday kod yoki nomli kino topilmadi.")


# ==========================================
# 6. MAIN
# ==========================================
async def main():
    await init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_routers(admin_router, user_router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())