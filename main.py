import asyncio
import os
import sqlite3
import re
from datetime import datetime
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    FSInputFile
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import A4

# ================= LOAD ENV =================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ================= DATABASE =================
conn = sqlite3.connect("cvify.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY,
    full_name TEXT,
    phone TEXT,
    joined TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS cvs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    file_name TEXT,
    created_at TEXT
)
""")

conn.commit()

# ================= STATES =================
class CVForm(StatesGroup):
    full_name = State()
    email = State()
    phone = State()
    address = State()
    education = State()
    experience = State()
    skills = State()

class BroadcastState(StatesGroup):
    message = State()

# ================= KEYBOARDS =================
def contact_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📞 Kontakt yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="📢 Broadcast")],
            [KeyboardButton(text="👥 Foydalanuvchilar")],
            [KeyboardButton(text="📄 CV lar")],
            [KeyboardButton(text="🔙 Orqaga")]
        ],
        resize_keyboard=True
    )

# ================= START =================
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "Assalomu alaykum!\n\n"
        "CVifyBot ga xush kelibsiz 🚀\n\n"
        "Davom etish uchun telefon raqamingizni yuboring:",
        reply_markup=contact_keyboard()
    )

# ================= CONTACT =================
@dp.message(F.contact)
async def get_contact(message: Message, state: FSMContext):

    if message.contact.user_id != message.from_user.id:
        return await message.answer("Iltimos, o‘zingizning kontaktni yuboring.")

    phone = message.contact.phone_number
    full_name = message.from_user.full_name

    cursor.execute("""
        INSERT OR REPLACE INTO users(id, full_name, phone, joined)
        VALUES(?,?,?,?)
    """, (message.from_user.id, full_name, phone, datetime.now().strftime("%Y-%m-%d")))
    conn.commit()

    for admin in ADMIN_IDS:
        await bot.send_message(
            admin,
            f"🆕 Yangi foydalanuvchi\n\n👤 {full_name}\n📞 {phone}"
        )

    await message.answer("Ism familiyangizni kiriting:")
    await state.set_state(CVForm.full_name)

# ================= CV FLOW =================
@dp.message(CVForm.full_name)
async def cv_fullname(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("Email (namuna@gmail.com):")
    await state.set_state(CVForm.email)

@dp.message(CVForm.email)
async def cv_email(message: Message, state: FSMContext):
    email = message.text.strip()
    pattern = r"^[a-zA-Z0-9._%+-]+@gmail\.com$"

    if not re.match(pattern, email):
        return await message.answer("❌ Email noto‘g‘ri.\nNamuna: namuna@gmail.com")

    await state.update_data(email=email)
    await message.answer("Telefon raqamingiz:")
    await state.set_state(CVForm.phone)

@dp.message(CVForm.phone)
async def cv_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("Yashash manzilingiz:")
    await state.set_state(CVForm.address)

@dp.message(CVForm.address)
async def cv_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    await message.answer("Ta'limingiz:")
    await state.set_state(CVForm.education)

@dp.message(CVForm.education)
async def cv_education(message: Message, state: FSMContext):
    await state.update_data(education=message.text)
    await message.answer("Ish tajribangiz:")
    await state.set_state(CVForm.experience)

@dp.message(CVForm.experience)
async def cv_experience(message: Message, state: FSMContext):
    await state.update_data(experience=message.text)
    await message.answer("Ko‘nikmalar (vergul bilan):")
    await state.set_state(CVForm.skills)

# ================= PDF =================
@dp.message(CVForm.skills)
async def generate_cv(message: Message, state: FSMContext):
    await state.update_data(skills=message.text)
    data = await state.get_data()

    file_name = f"{data['full_name'].replace(' ', '_')}_CV.pdf"
    doc = SimpleDocTemplate(file_name, pagesize=A4)
    elements = []

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=26,
        textColor=colors.HexColor("#1F4E79"),
        alignment=1,
        spaceAfter=15
    )

    section_style = ParagraphStyle(
        'SectionStyle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.white,
        backColor=colors.HexColor("#2E86C1"),
        spaceBefore=15,
        spaceAfter=8
    )

    normal_style = styles['Normal']

    elements.append(Paragraph(data['full_name'], title_style))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#2E86C1")))
    elements.append(Spacer(1, 0.3 * inch))

    elements.append(Paragraph(f"<b>Email:</b> {data['email']}", normal_style))
    elements.append(Paragraph(f"<b>Phone:</b> {data['phone']}", normal_style))
    elements.append(Paragraph(f"<b>Address:</b> {data['address']}", normal_style))
    elements.append(Spacer(1, 0.3 * inch))

    elements.append(Paragraph("EDUCATION", section_style))
    elements.append(Paragraph(data['education'], normal_style))

    elements.append(Paragraph("EXPERIENCE", section_style))
    elements.append(Paragraph(data['experience'], normal_style))

    elements.append(Paragraph("SKILLS", section_style))
    for skill in data['skills'].split(","):
        elements.append(Paragraph(f"• {skill.strip()}", normal_style))

    doc.build(elements)

    cursor.execute(
        "INSERT INTO cvs(user_id, file_name, created_at) VALUES(?,?,?)",
        (message.from_user.id, file_name, datetime.now().strftime("%Y-%m-%d"))
    )
    conn.commit()

    pdf = FSInputFile(file_name)
    await message.answer_document(pdf, caption="🎉 Professional CV tayyor!")

    await state.clear()

# ================= ADMIN =================
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("Siz admin emassiz.")
    await message.answer("Admin panel", reply_markup=admin_keyboard())

@dp.message(F.text == "📊 Statistika")
async def statistics(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM cvs")
    cvs_count = cursor.fetchone()[0]

    await message.answer(
        f"📊 STATISTIKA\n\n👥 Jami userlar: {users_count}\n📄 Yaratilgan CV: {cvs_count}"
    )

@dp.message(F.text == "👥 Foydalanuvchilar")
async def show_users(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    cursor.execute("SELECT id, full_name, phone FROM users")
    users = cursor.fetchall()

    if not users:
        return await message.answer("Userlar yo‘q.")

    text = "👥 FOYDALANUVCHILAR:\n\n"
    for user in users:
        text += f"🆔 {user[0]}\n👤 {user[1]}\n📞 {user[2]}\n\n"

    await message.answer(text)

@dp.message(F.text == "📄 CV lar")
async def show_cvs(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    cursor.execute("""
        SELECT users.full_name, cvs.file_name
        FROM cvs
        JOIN users ON users.id = cvs.user_id
        ORDER BY cvs.id DESC
        LIMIT 10
    """)
    cvs = cursor.fetchall()

    if not cvs:
        return await message.answer("CV lar yo‘q.")

    for name, file_name in cvs:
        if os.path.exists(file_name):
            pdf = FSInputFile(file_name)
            await message.answer_document(pdf, caption=f"📄 {name} ning CV si")

@dp.message(F.text == "📢 Broadcast")
async def broadcast_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Yuboriladigan xabarni kiriting:")
    await state.set_state(BroadcastState.message)

@dp.message(BroadcastState.message)
async def send_broadcast(message: Message, state: FSMContext):

    if message.text == "🔙 Orqaga":
        await state.clear()
        return await message.answer("Admin panel", reply_markup=admin_keyboard())

    cursor.execute("SELECT id FROM users")
    users = cursor.fetchall()

    sent = 0
    for user in users:
        try:
            await bot.send_message(user[0], message.text)
            sent += 1
        except:
            pass

    await message.answer(f"Broadcast yuborildi.\nYuborilganlar: {sent}")
    await state.clear()

# ================= RUN =================
async def main():
    print("CVifyBot ishga tushdi 🚀")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())