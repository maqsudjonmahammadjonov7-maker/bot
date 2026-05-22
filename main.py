import asyncio
import random
import json
import os
import threading
from datetime import datetime
from typing import Dict, List, Optional
from flask import Flask, request, jsonify, render_template_string

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    KeyboardButton,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ================= FLASK APP =================
app = Flask(__name__)

# ================= CONFIG =================
TOKEN = "8823160051:AAG1CL5g4Ed60RAiFgOSOUCDtqqlyQ3HYqQ"
SUPER_ADMIN_ID = 5996676608

# Majburiy kanallar endi bo'sh ro'yxat
DEFAULT_CHANNELS = []

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ================= FILES =================
def ensure_files():
    files = {
        "users.json": {},
        "polls.json": [],
        "active_poll.json": None,
        "admins.json": [SUPER_ADMIN_ID],
        "groups.json": [],
        "blacklist.json": [],
        "feedback.json": [],
        "logs.json": [],
        "channels.json": []  # Yangi fayl: majburiy kanallar
    }
    
    for filename, default_data in files.items():
        if not os.path.exists(filename):
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(default_data, f, indent=4, ensure_ascii=False)
        else:
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        with open(filename, "w", encoding="utf-8") as fw:
                            json.dump(default_data, fw, indent=4, ensure_ascii=False)
                    else:
                        json.loads(content)
            except (json.JSONDecodeError, ValueError):
                with open(filename, "w", encoding="utf-8") as fw:
                    json.dump(default_data, fw, indent=4, ensure_ascii=False)

ensure_files()

def safe_load_json(filename: str, default_data):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return default_data
            return json.loads(content)
    except (json.JSONDecodeError, ValueError, FileNotFoundError) as e:
        print(f"⚠️ JSON decode error in {filename}: {e}")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=4, ensure_ascii=False)
        return default_data

def safe_save_json(filename: str, data):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ JSON save error in {filename}: {e}")

def load_users() -> Dict:
    return safe_load_json("users.json", {})

def save_users(data: Dict):
    safe_save_json("users.json", data)

def load_polls() -> List:
    return safe_load_json("polls.json", [])

def save_polls(data: List):
    safe_save_json("polls.json", data)

def load_active_poll() -> Optional[Dict]:
    return safe_load_json("active_poll.json", None)

def save_active_poll(data: Optional[Dict]):
    safe_save_json("active_poll.json", data)

def load_admins() -> List[int]:
    return safe_load_json("admins.json", [SUPER_ADMIN_ID])

def save_admins(data: List[int]):
    safe_save_json("admins.json", data)

def load_groups() -> List[Dict]:
    return safe_load_json("groups.json", [])

def save_groups(data: List[Dict]):
    safe_save_json("groups.json", data)

def load_blacklist() -> List[int]:
    return safe_load_json("blacklist.json", [])

def save_blacklist(data: List[int]):
    safe_save_json("blacklist.json", data)

def load_feedback() -> List[Dict]:
    return safe_load_json("feedback.json", [])

def save_feedback(data: List[Dict]):
    safe_save_json("feedback.json", data)

def load_logs() -> List[Dict]:
    return safe_load_json("logs.json", [])

def save_logs(data: List[Dict]):
    safe_save_json("logs.json", data)

def load_channels() -> List[str]:
    return safe_load_json("channels.json", [])

def save_channels(data: List[str]):
    safe_save_json("channels.json", data)

def add_log(action: str, user_id: int, details: str = ""):
    logs = load_logs()
    logs.append({
        "action": action,
        "user_id": user_id,
        "details": details,
        "timestamp": str(datetime.now())
    })
    if len(logs) > 1000:
        logs = logs[-1000:]
    save_logs(logs)

def is_admin(user_id: int) -> bool:
    admins = load_admins()
    return user_id in admins

def is_super_admin(user_id: int) -> bool:
    return user_id == SUPER_ADMIN_ID

def is_blacklisted(user_id: int) -> bool:
    blacklist = load_blacklist()
    return user_id in blacklist

def is_user_verified(user_id: int) -> bool:
    users = load_users()
    user_id_str = str(user_id)
    return users.get(user_id_str, {}).get("verified", False)

# ================= CHANNEL CHECK =================
async def check_sub(user_id: int) -> bool:
    channels = load_channels()
    if not channels:
        return True
    
    for channel in channels:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            return False
    return True

async def get_channels_keyboard():
    channels = load_channels()
    builder = InlineKeyboardBuilder()
    for ch in channels:
        builder.button(text=f"📢 {ch}", url=f"https://t.me/{ch.replace('@', '')}")
    builder.button(text="✅ Tekshirish", callback_data="check_sub")
    builder.adjust(1)
    return builder.as_markup()

# ================= STATES =================
class VerifyState(StatesGroup):
    captcha = State()

class PollState(StatesGroup):
    title = State()
    description = State()
    candidate = State()

class BroadcastState(StatesGroup):
    waiting_for_message = State()
    waiting_for_group_message = State()

class AddAdminState(StatesGroup):
    waiting_for_user_id = State()

class FeedbackState(StatesGroup):
    waiting_for_feedback = State()

class EditPollState(StatesGroup):
    waiting_for_new_title = State()
    waiting_for_new_description = State()
    waiting_for_candidate_name = State()

class ChannelState(StatesGroup):
    waiting_for_channel = State()

class ReplyFeedbackState(StatesGroup):
    waiting_for_feedback_id = State()
    waiting_for_reply_message = State()

# ================= KEYBOARDS =================
# Ixcham admin panel - tugmalar yonma-yon
def get_admin_keyboard(user_id: int):
    if is_super_admin(user_id):
        # Super admin uchun 2 qatorli ixcham menyu
        keyboard = [
            [
                KeyboardButton(text="➕ So'rovnoma"),
                KeyboardButton(text="✏️ Tahrirlash"),
                KeyboardButton(text="📊 Natijalar")
            ],
            [
                KeyboardButton(text="📢 Havola"),
                KeyboardButton(text="📨 Xabar"),
                KeyboardButton(text="👥 Guruh xabar")
            ],
            [
                KeyboardButton(text="📚 Arxiv"),
                KeyboardButton(text="👑 Adminlar"),
                KeyboardButton(text="📺 Kanallar")
            ],
            [
                KeyboardButton(text="🚫 Blacklist"),
                KeyboardButton(text="💬 Fikrlar"),
                KeyboardButton(text="📈 Statistika")
            ],
            [
                KeyboardButton(text="📋 Loglar"),
                KeyboardButton(text="💾 Backup"),
                KeyboardButton(text="🔚 Tugatish")
            ],
            [
                KeyboardButton(text="🧹 Tozalash"),
                KeyboardButton(text="🏠 Bosh menyu")
            ]
        ]
    elif is_admin(user_id):
        # Oddiy admin uchun
        keyboard = [
            [
                KeyboardButton(text="➕ So'rovnoma"),
                KeyboardButton(text="✏️ Tahrirlash"),
                KeyboardButton(text="📊 Natijalar")
            ],
            [
                KeyboardButton(text="📢 Havola"),
                KeyboardButton(text="📨 Xabar"),
                KeyboardButton(text="👥 Guruh xabar")
            ],
            [
                KeyboardButton(text="📚 Arxiv"),
                KeyboardButton(text="💬 Fikrlar"),
                KeyboardButton(text="📈 Statistika")
            ],
            [
                KeyboardButton(text="🔚 Tugatish"),
                KeyboardButton(text="🧹 Tozalash"),
                KeyboardButton(text="🏠 Bosh menyu")
            ]
        ]
    else:
        keyboard = [[KeyboardButton(text="🏠 Bosh menyu")]]
    
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def user_menu():
    keyboard = [
        [KeyboardButton(text="🗳 Ovoz berish"), KeyboardButton(text="📊 Natijalar")],
        [KeyboardButton(text="💬 Fikr bildirish"), KeyboardButton(text="ℹ️ Ma'lumot")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def phone_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text="📱 Telefon raqam yuborish", request_contact=True),
            KeyboardButton(text="🔙 Bekor qilish")
        ]],
        resize_keyboard=True
    )

async def vote_kb(poll: Dict):
    builder = InlineKeyboardBuilder()
    for c in poll["candidates"]:
        builder.button(
            text=f"🗳 {c['name']} ({c['votes']})", 
            callback_data=f"vote_{c['id']}"
        )
    builder.adjust(1)
    builder.button(text="🔄 Yangilash", callback_data="refresh_vote")
    builder.adjust(1)
    return builder.as_markup()

def captcha_retry_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Qayta urinish", callback_data="retry_captcha")]
        ]
    )

def back_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🏠 Bosh menyu")]],
        resize_keyboard=True
    )

# ================= CHANNEL MANAGEMENT =================
@dp.message(F.text == "📺 Kanallar")
async def manage_channels(message: Message):
    if not is_super_admin(message.from_user.id):
        await message.answer("❌ Bu funksiya faqat SUPER ADMIN uchun!")
        return
    
    channels = load_channels()
    text = "📺 <b>Majburiy kanallar</b>\n\n"
    
    if channels:
        for i, ch in enumerate(channels, 1):
            text += f"{i}. {ch}\n"
    else:
        text += "❌ Hech qanday majburiy kanal mavjud emas\n\n"
    
    text += f"\n📊 Jami: {len(channels)} ta kanal"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Kanal qo'shish", callback_data="add_channel")
    if channels:
        builder.button(text="❌ Kanal o'chirish", callback_data="remove_channel")
    builder.button(text="🔙 Orqaga", callback_data="back_to_admin")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "add_channel")
async def add_channel_start(call: CallbackQuery, state: FSMContext):
    if not is_super_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    await state.set_state(ChannelState.waiting_for_channel)
    await call.message.answer(
        "📺 <b>Kanal qo'shish</b>\n\n"
        "Kanal username'ini @ bilan birga yuboring.\n"
        "Masalan: @my_channel\n\n"
        "❌ Bekor qilish uchun /cancel",
        parse_mode=ParseMode.HTML
    )
    await call.answer()

@dp.message(ChannelState.waiting_for_channel)
async def add_channel_finish(message: Message, state: FSMContext):
    if not is_super_admin(message.from_user.id):
        return
    
    channel = message.text.strip()
    
    if not channel.startswith("@"):
        await message.answer("❌ Kanal username'i @ bilan boshlanishi kerak!\nMasalan: @my_channel")
        return
    
    channels = load_channels()
    
    if channel in channels:
        await message.answer("❌ Bu kanal allaqachon qo'shilgan!")
        await state.clear()
        return
    
    # Kanal mavjudligini tekshirish
    try:
        await bot.get_chat(channel)
    except Exception:
        await message.answer(f"❌ Kanal topilmadi yoki bot kanalda admin emas!\nKanal: {channel}\n\nBotni kanalga admin qilib qo'shing va qaytadan urinib ko'ring.")
        return
    
    channels.append(channel)
    save_channels(channels)
    add_log("add_channel", message.from_user.id, f"Kanal qo'shildi: {channel}")
    
    await state.clear()
    await message.answer(f"✅ Kanal qo'shildi: {channel}\n\nEndi foydalanuvchilar ushbu kanalga obuna bo'lmasa botdan foydalana olmaydi.")
    await manage_channels(message)

@dp.callback_query(F.data == "remove_channel")
async def remove_channel_list(call: CallbackQuery):
    if not is_super_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    channels = load_channels()
    if not channels:
        await call.answer("❌ Hech qanday kanal yo'q!", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    for ch in channels:
        builder.button(text=f"❌ {ch}", callback_data=f"remove_ch_{ch}")
    builder.adjust(1)
    builder.button(text="🔙 Orqaga", callback_data="back_to_channels")
    
    await call.message.answer("❌ O'chiriladigan kanalni tanlang:", reply_markup=builder.as_markup())
    await call.answer()

@dp.callback_query(F.data.startswith("remove_ch_"))
async def remove_channel_confirm(call: CallbackQuery):
    if not is_super_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    channel = call.data.replace("remove_ch_", "")
    channels = load_channels()
    
    if channel in channels:
        channels.remove(channel)
        save_channels(channels)
        add_log("remove_channel", call.from_user.id, f"Kanal o'chirildi: {channel}")
        await call.message.answer(f"✅ Kanal o'chirildi: {channel}")
    else:
        await call.message.answer("❌ Kanal topilmadi!")
    
    await call.answer()
    await manage_channels(call.message)

@dp.callback_query(F.data == "back_to_channels")
async def back_to_channels(call: CallbackQuery):
    await manage_channels(call.message)
    await call.answer()

@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin(call: CallbackQuery):
    await call.message.delete()
    await call.message.answer("🏠 Bosh menyu", reply_markup=get_admin_keyboard(call.from_user.id))
    await call.answer()

# ================= START =================
@dp.message(CommandStart())
async def start_command(message: Message):
    user_id = message.from_user.id
    
    if is_blacklisted(user_id):
        await message.answer("🚫 Siz botdan foydalanish uchun bloklangansiz!")
        return
    
    users = load_users()
    user_id_str = str(user_id)

    if user_id_str not in users:
        users[user_id_str] = {
            "phone": None,
            "verified": False,
            "votes": None,
            "joined_at": str(datetime.now()),
            "username": message.from_user.username,
            "full_name": message.from_user.full_name
        }
        save_users(users)
        add_log("new_user", user_id, f"Yangi foydalanuvchi: {message.from_user.full_name}")

    sub = await check_sub(user_id)
    channels = load_channels()
    
    if not sub and channels:
        await message.answer(
            "❌ Botdan foydalanish uchun kanallarga obuna bo'lishingiz kerak!",
            reply_markup=await get_channels_keyboard()
        )
        return

    # Agar foydalanuvchi allaqachon tasdiqlangan bo'lsa, qayta ro'yxatdan o'tkazilmaydi
    if users[user_id_str].get("verified"):
        if is_admin(user_id):
            await message.answer("✅ Xush kelibsiz! Admin panel", reply_markup=get_admin_keyboard(user_id))
        else:
            await message.answer("✅ Xush kelibsiz!", reply_markup=user_menu())
    else:
        await message.answer(
            "📱 Botdan foydalanish uchun telefon raqamingizni yuboring",
            reply_markup=phone_kb()
        )

# ================= CONTACT & CAPTCHA =================
@dp.message(F.contact)
async def contact(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Agar foydalanuvchi allaqachon tasdiqlangan bo'lsa, qayta captcha so'ralmaydi
    if is_user_verified(user_id):
        await message.answer("✅ Siz allaqachon ro'yxatdan o'tgansiz!", reply_markup=user_menu() if not is_admin(user_id) else get_admin_keyboard(user_id))
        return
    
    phone = message.contact.phone_number
    
    users = load_users()
    user_id_str = str(user_id)
    users[user_id_str]["phone"] = phone
    save_users(users)

    a, b = random.randint(1, 9), random.randint(1, 9)
    await state.update_data(answer=a + b)
    await state.set_state(VerifyState.captcha)
    await message.answer(
        f"🤖 Robot emasligingizni tasdiqlang\n\n{a} + {b} = ?",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(VerifyState.captcha)
async def captcha(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Agar captcha davomida tasdiqlangan bo'lib qolsa
    if is_user_verified(user_id):
        await state.clear()
        await message.answer("✅ Siz allaqachon tasdiqlangansiz!", reply_markup=user_menu() if not is_admin(user_id) else get_admin_keyboard(user_id))
        return
    
    data = await state.get_data()
    
    if not message.text or not message.text.strip().isdigit():
        await message.answer("❌ Iltimos, son kiriting!", reply_markup=captcha_retry_kb())
        return
    
    if int(data["answer"]) == int(message.text.strip()):
        users = load_users()
        users[str(user_id)]["verified"] = True
        save_users(users)
        await state.clear()
        
        add_log("verified", user_id, "Foydalanuvchi tasdiqlandi")
        
        if is_admin(user_id):
            await message.answer("✅ Tasdiqlandi! Admin panel", reply_markup=get_admin_keyboard(user_id))
        else:
            await message.answer("✅ Tasdiqlandi!", reply_markup=user_menu())
    else:
        a, b = random.randint(1, 9), random.randint(1, 9)
        await state.update_data(answer=a + b)
        await message.answer(
            f"❌ Xato! Qayta urinib ko'ring.\n\n{a} + {b} = ?",
            reply_markup=captcha_retry_kb()
        )

@dp.callback_query(F.data == "retry_captcha")
async def retry_captcha(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    
    if is_user_verified(user_id):
        await state.clear()
        await call.message.edit_text("✅ Siz allaqachon tasdiqlangansiz!")
        await call.answer()
        return
    
    await state.set_state(VerifyState.captcha)
    a, b = random.randint(1, 9), random.randint(1, 9)
    await state.update_data(answer=a + b)
    await call.message.edit_text(
        f"🤖 Robot emasligingizni tasdiqlang\n\n{a} + {b} = ?"
    )
    await call.answer()

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(call: CallbackQuery):
    user_id = call.from_user.id
    sub = await check_sub(user_id)
    
    if sub:
        # Agar foydalanuvchi allaqachon tasdiqlangan bo'lsa
        if is_user_verified(user_id):
            await call.message.delete()
            await call.message.answer(
                "✅ Obuna tasdiqlandi!",
                reply_markup=user_menu() if not is_admin(user_id) else get_admin_keyboard(user_id)
            )
        else:
            await call.message.delete()
            await call.message.answer(
                "✅ Obuna tasdiqlandi!\n\n📱 Telefon raqamingizni yuboring",
                reply_markup=phone_kb()
            )
    else:
        await call.answer("❌ Siz hali obuna bo'lmadingiz!", show_alert=True)

# ================= MAIN MENU BACK =================
@dp.message(F.text == "🏠 Bosh menyu")
async def back_to_main_menu(message: Message):
    user_id = message.from_user.id
    users = load_users()
    user_id_str = str(user_id)
    
    if not users.get(user_id_str, {}).get("verified"):
        await message.answer("❌ Avval ro'yxatdan o'ting! /start")
        return
    
    if is_admin(user_id):
        await message.answer("🏠 Bosh menyu - Admin panel", reply_markup=get_admin_keyboard(user_id))
    else:
        await message.answer("🏠 Bosh menyu", reply_markup=user_menu())

@dp.message(F.text == "🔙 Bekor qilish")
async def cancel_operation(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Bekor qilindi!",
        reply_markup=ReplyKeyboardRemove()
    )
    await start_command(message)

# ================= CREATE POLL =================
@dp.message(F.text == "➕ So'rovnoma")
async def create_poll(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Bu funksiya faqat adminlar uchun!")
        return

    active = load_active_poll()
    if active:
        await message.answer(
            "⚠️ Hozirda faol so'rovnoma mavjud!\n"
            "Avval uni tugating: 🔚 Tugatish"
        )
        return

    await state.set_state(PollState.title)
    await message.answer("📝 So'rovnoma nomini kiriting:", reply_markup=back_kb())

@dp.message(PollState.title)
async def poll_title(message: Message, state: FSMContext):
    if message.text == "🏠 Bosh menyu":
        await state.clear()
        await back_to_main_menu(message)
        return
        
    await state.update_data(title=message.text)
    await state.set_state(PollState.description)
    await message.answer("📄 Tavsif kiriting:", reply_markup=back_kb())

@dp.message(PollState.description)
async def poll_desc(message: Message, state: FSMContext):
    if message.text == "🏠 Bosh menyu":
        await state.clear()
        await back_to_main_menu(message)
        return
        
    await state.update_data(description=message.text, candidates=[])
    await state.set_state(PollState.candidate)

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tayyor", callback_data="finish_poll")
    
    await message.answer("👤 Birinchi nomzod nomini kiriting:", reply_markup=builder.as_markup())

@dp.message(PollState.candidate)
async def add_candidate(message: Message, state: FSMContext):
    if message.text == "🏠 Bosh menyu":
        await state.clear()
        await back_to_main_menu(message)
        return
        
    data = await state.get_data()
    candidates = data.get("candidates", [])
    candidate_id = len(candidates) + 1
    candidates.append({"id": candidate_id, "name": message.text, "votes": 0})
    await state.update_data(candidates=candidates)

    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Yana qo'shish", callback_data="add_more")
    builder.button(text="✅ Tayyor", callback_data="finish_poll")
    builder.adjust(2)
    
    await message.answer(f"✅ Nomzod qo'shildi: {message.text}", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "add_more")
async def add_more(call: CallbackQuery, state: FSMContext):
    await call.message.answer("👤 Yangi nomzod nomini kiriting:")
    await call.answer()

@dp.callback_query(F.data == "finish_poll")
async def finish_poll(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    candidates = data.get("candidates", [])

    if len(candidates) < 2:
        await call.answer("❌ Kamida 2 ta nomzod bo'lishi kerak!", show_alert=True)
        return

    poll_id = datetime.now().timestamp()
    active_poll = {
        "id": poll_id,
        "title": data["title"],
        "description": data["description"],
        "created_at": str(datetime.now()),
        "status": "active",
        "candidates": candidates
    }

    save_active_poll(active_poll)
    await state.clear()
    add_log("create_poll", call.from_user.id, f"So'rovnoma yaratildi: {data['title']}")
    await call.message.answer("✅ So'rovnoma yaratildi va faollashtirildi!", reply_markup=get_admin_keyboard(call.from_user.id))
    await call.answer()

# ================= VOTE =================
@dp.message(F.text == "🗳 Ovoz berish")
async def vote_menu(message: Message):
    user_id = message.from_user.id
    
    if is_blacklisted(user_id):
        await message.answer("🚫 Siz botdan foydalanish uchun bloklangansiz!")
        return
    
    active_poll = load_active_poll()
    if not active_poll:
        await message.answer("❌ Hozirda faol so'rovnoma mavjud emas!")
        return

    sub = await check_sub(user_id)
    channels = load_channels()
    
    if not sub and channels:
        await message.answer("❌ Kanallarga obuna bo'ling!", reply_markup=await get_channels_keyboard())
        return

    users = load_users()
    user_id_str = str(user_id)
    
    if not users.get(user_id_str, {}).get("verified"):
        await message.answer("❌ Avval ro'yxatdan o'ting! /start")
        return

    # Ovoz berish faqat 1 marta - tekshirish
    if users[user_id_str].get("votes") == active_poll["id"]:
        await message.answer("❌ Siz allaqachon ovoz bergansiz! Bir marta ovoz berish mumkin.")
        return

    total_votes = sum(c['votes'] for c in active_poll['candidates'])
    
    text = (
        f"🗳 <b>{active_poll['title']}</b>\n\n"
        f"📄 {active_poll['description']}\n\n"
        f"📊 Jami ovozlar: {total_votes}\n\n"
        f"👇 <b>Nomzod tanlang:</b>"
    )
    await message.answer(text, reply_markup=await vote_kb(active_poll))

@dp.callback_query(F.data.startswith("vote_"))
async def vote(call: CallbackQuery):
    user_id = call.from_user.id
    
    if is_blacklisted(user_id):
        await call.answer("🚫 Siz bloklangansiz!", show_alert=True)
        return
    
    try:
        candidate_id = int(call.data.split("_")[1])
    except (IndexError, ValueError):
        await call.answer("❌ Xatolik yuz berdi!", show_alert=True)
        return
        
    active_poll = load_active_poll()
    if not active_poll:
        await call.answer("❌ So'rovnoma tugatilgan!", show_alert=True)
        return

    sub = await check_sub(user_id)
    channels = load_channels()
    
    if not sub and channels:
        await call.message.delete()
        await call.message.answer("❌ Kanallarga obuna bo'ling!", reply_markup=await get_channels_keyboard())
        return

    users = load_users()
    user_id_str = str(user_id)

    # Ovoz berish faqat 1 marta - tekshirish
    if users.get(user_id_str, {}).get("votes") == active_poll["id"]:
        await call.answer("❌ Siz allaqachon ovoz bergansiz! Bir marta ovoz berish mumkin.", show_alert=True)
        return

    candidate = next((c for c in active_poll["candidates"] if c["id"] == candidate_id), None)
    if not candidate:
        await call.answer("❌ Nomzod topilmadi!", show_alert=True)
        return

    candidate["votes"] += 1
    users[user_id_str]["votes"] = active_poll["id"]
    save_users(users)
    save_active_poll(active_poll)
    
    add_log("vote", user_id, f"Ovoz berildi: {active_poll['title']} -> {candidate['name']}")

    total_votes = sum(c['votes'] for c in active_poll['candidates'])
    candidates_list = "\n".join([f"• {c['name']} - {c['votes']} ovoz" for c in active_poll['candidates']])
    
    await call.message.edit_text(
        f"🗳 <b>{active_poll['title']}</b>\n\n"
        f"✅ Siz <b>{candidate['name']}</b> nomzodiga ovoz berdingiz!\n\n"
        f"📊 <b>Jami ovozlar:</b> {total_votes}\n\n"
        f"📋 <b>Hozirgi natijalar:</b>\n{candidates_list}",
        reply_markup=await vote_kb(active_poll)
    )
    await call.answer("✅ Ovoz qabul qilindi!", show_alert=True)

@dp.callback_query(F.data == "refresh_vote")
async def refresh_vote(call: CallbackQuery):
    active_poll = load_active_poll()
    if not active_poll:
        await call.answer("❌ So'rovnoma mavjud emas!", show_alert=True)
        return
    
    total_votes = sum(c['votes'] for c in active_poll['candidates'])
    
    text = (
        f"🗳 <b>{active_poll['title']}</b>\n\n"
        f"📄 {active_poll['description']}\n\n"
        f"📊 Jami ovozlar: {total_votes}\n\n"
        f"👇 <b>Nomzod tanlang:</b>"
    )
    await call.message.edit_text(text, reply_markup=await vote_kb(active_poll))
    await call.answer("🔄 Yangilandi!")

# ================= RESULTS =================
@dp.message(F.text == "📊 Natijalar")
async def results(message: Message):
    active_poll = load_active_poll()
    if not active_poll:
        await message.answer("❌ Faol so'rovnoma mavjud emas!")
        return

    total = sum(c["votes"] for c in active_poll["candidates"])
    
    if total == 0:
        await message.answer("📊 Hali hech qanday ovoz berilmagan!")
        return
    
    text = f"📊 <b>{active_poll['title']}</b>\n\n"
    
    sorted_candidates = sorted(active_poll["candidates"], key=lambda x: x["votes"], reverse=True)
    
    for i, c in enumerate(sorted_candidates, 1):
        percent = round((c["votes"] / total) * 100, 1)
        bar_length = int(percent // 5)
        bar = "█" * bar_length + "░" * (20 - bar_length)
        
        medal = ""
        if i == 1:
            medal = "🥇 "
        elif i == 2:
            medal = "🥈 "
        elif i == 3:
            medal = "🥉 "
        
        text += f"{medal}<b>{c['name']}</b>\n{bar} {percent}% ({c['votes']} ovoz)\n\n"

    text += f"📊 <b>Jami ovozlar:</b> {total}"
    await message.answer(text)

# ================= FEEDBACK =================
@dp.message(F.text == "💬 Fikr bildirish")
async def feedback_start(message: Message, state: FSMContext):
    if is_blacklisted(message.from_user.id):
        await message.answer("🚫 Siz botdan foydalanish uchun bloklangansiz!")
        return
    
    await state.set_state(FeedbackState.waiting_for_feedback)
    await message.answer(
        "💬 Fikr va takliflaringizni yozing:\n\n"
        "Bot haqida fikrlaringiz, xatoliklar yoki takliflaringiz bo'lsa yozing.",
        reply_markup=back_kb()
    )

@dp.message(FeedbackState.waiting_for_feedback)
async def feedback_save(message: Message, state: FSMContext):
    if message.text == "🏠 Bosh menyu":
        await state.clear()
        await back_to_main_menu(message)
        return
    
    feedbacks = load_feedback()
    feedback_id = len(feedbacks) + 1
    feedbacks.append({
        "id": feedback_id,
        "user_id": message.from_user.id,
        "username": message.from_user.username,
        "full_name": message.from_user.full_name,
        "message": message.text,
        "created_at": str(datetime.now()),
        "replied": False,
        "reply": None,
        "replied_at": None,
        "replied_by": None
    })
    save_feedback(feedbacks)
    
    add_log("feedback", message.from_user.id, f"Fikr qoldirildi: {message.text[:50]}...")
    
    await state.clear()
    await message.answer("✅ Fikringiz uchun rahmat! Administratorlar ko'rib chiqishadi va javob berishadi.")
    
    admins = load_admins()
    for admin_id in admins:
        try:
            builder = InlineKeyboardBuilder()
            builder.button(text="💬 Javob berish", callback_data=f"reply_feedback_{feedback_id}")
            builder.button(text="👁 Ko'rish", callback_data=f"view_feedback_{feedback_id}")
            builder.adjust(1)
            
            await bot.send_message(
                admin_id,
                f"💬 <b>Yangi fikr #{feedback_id}</b>\n\n"
                f"👤 Foydalanuvchi: {message.from_user.full_name}\n"
                f"🆔 ID: {message.from_user.id}\n"
                f"📝 Xabar: {message.text}\n\n"
                f"📅 Vaqt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                reply_markup=builder.as_markup()
            )
        except Exception:
            pass

# Admin fikrlarga javob berish
@dp.message(F.text == "💬 Fikrlar")
async def view_feedbacks(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Bu funksiya faqat adminlar uchun!")
        return
    
    feedbacks = load_feedback()
    if not feedbacks:
        await message.answer("💬 Hech qanday fikr yo'q!")
        return
    
    # Javob berilmagan fikrlarni birinchi chiqarish
    unreplied = [fb for fb in feedbacks if not fb.get("replied", False)]
    replied = [fb for fb in feedbacks if fb.get("replied", False)]
    
    text = "💬 <b>Fikrlar ro'yxati</b>\n\n"
    
    if unreplied:
        text += "🟡 <b>Javob berilmaganlar:</b>\n"
        for fb in unreplied[-5:]:
            text += f"#{fb['id']} - {fb['full_name']}: {fb['message'][:40]}...\n"
    
    if replied:
        text += "\n✅ <b>Javob berilganlar:</b>\n"
        for fb in replied[-5:]:
            text += f"#{fb['id']} - {fb['full_name']}: {fb['message'][:30]}...\n"
    
    text += f"\n📊 Jami: {len(feedbacks)} ta fikr (🟡 {len(unreplied)} ta javobsiz)"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Barcha fikrlar", callback_data="list_all_feedbacks")
    builder.button(text="🟡 Javobsizlar", callback_data="list_unreplied_feedbacks")
    builder.button(text="🔙 Orqaga", callback_data="back_to_admin")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "list_all_feedbacks")
async def list_all_feedbacks(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    feedbacks = load_feedback()
    if not feedbacks:
        await call.message.answer("💬 Hech qanday fikr yo'q!")
        await call.answer()
        return
    
    builder = InlineKeyboardBuilder()
    for fb in reversed(feedbacks[-20:]):
        status = "✅" if fb.get("replied", False) else "🟡"
        builder.button(text=f"{status} #{fb['id']} - {fb['full_name'][:15]}", callback_data=f"view_feedback_{fb['id']}")
    builder.adjust(1)
    builder.button(text="🔙 Orqaga", callback_data="back_to_feedback_menu")
    
    await call.message.edit_text("📋 <b>Barcha fikrlar</b>", reply_markup=builder.as_markup())
    await call.answer()

@dp.callback_query(F.data == "list_unreplied_feedbacks")
async def list_unreplied_feedbacks(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    feedbacks = load_feedback()
    unreplied = [fb for fb in feedbacks if not fb.get("replied", False)]
    
    if not unreplied:
        await call.message.answer("✅ Barcha fikrlarga javob berilgan!")
        await call.answer()
        return
    
    builder = InlineKeyboardBuilder()
    for fb in unreplied:
        builder.button(text=f"🟡 #{fb['id']} - {fb['full_name'][:15]}", callback_data=f"reply_feedback_{fb['id']}")
    builder.adjust(1)
    builder.button(text="🔙 Orqaga", callback_data="back_to_feedback_menu")
    
    await call.message.edit_text("🟡 <b>Javob berilmagan fikrlar</b>", reply_markup=builder.as_markup())
    await call.answer()

@dp.callback_query(F.data.startswith("view_feedback_"))
async def view_single_feedback(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    try:
        feedback_id = int(call.data.split("_")[2])
    except (IndexError, ValueError):
        await call.answer("❌ Xatolik!", show_alert=True)
        return
    
    feedbacks = load_feedback()
    feedback = next((fb for fb in feedbacks if fb["id"] == feedback_id), None)
    
    if not feedback:
        await call.answer("❌ Fikr topilmadi!", show_alert=True)
        return
    
    text = (
        f"💬 <b>Fikr #{feedback['id']}</b>\n\n"
        f"👤 Foydalanuvchi: {feedback['full_name']}\n"
        f"🆔 ID: {feedback['user_id']}\n"
        f"📝 Xabar: {feedback['message']}\n"
        f"📅 Vaqt: {feedback['created_at']}\n"
    )
    
    if feedback.get("replied", False):
        text += f"\n✅ <b>Javob:</b>\n{feedback['reply']}\n"
        text += f"👨‍💼 Javob bergan: {feedback['replied_by']}\n"
        text += f"📅 Javob vaqti: {feedback['replied_at']}\n"
    
    builder = InlineKeyboardBuilder()
    if not feedback.get("replied", False):
        builder.button(text="💬 Javob berish", callback_data=f"reply_feedback_{feedback_id}")
    builder.button(text="🔙 Orqaga", callback_data="back_to_feedback_list")
    
    await call.message.edit_text(text, reply_markup=builder.as_markup())
    await call.answer()

@dp.callback_query(F.data.startswith("reply_feedback_"))
async def reply_feedback_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    try:
        feedback_id = int(call.data.split("_")[2])
    except (IndexError, ValueError):
        await call.answer("❌ Xatolik!", show_alert=True)
        return
    
    feedbacks = load_feedback()
    feedback = next((fb for fb in feedbacks if fb["id"] == feedback_id), None)
    
    if not feedback:
        await call.answer("❌ Fikr topilmadi!", show_alert=True)
        return
    
    if feedback.get("replied", False):
        await call.answer("⚠️ Bu fikrga allaqachon javob berilgan!", show_alert=True)
        return
    
    await state.update_data(reply_feedback_id=feedback_id, reply_user_id=feedback["user_id"])
    await state.set_state(ReplyFeedbackState.waiting_for_reply_message)
    
    await call.message.answer(
        f"💬 <b>Javob yozish - Fikr #{feedback_id}</b>\n\n"
        f"Foydalanuvchi: {feedback['full_name']}\n"
        f"Xabar: {feedback['message']}\n\n"
        f"📝 Javob matnini yuboring:\n\n"
        f"❌ Bekor qilish uchun /cancel",
        parse_mode=ParseMode.HTML
    )
    await call.answer()

@dp.message(ReplyFeedbackState.waiting_for_reply_message)
async def reply_feedback_send(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Bekor qilindi!", reply_markup=get_admin_keyboard(message.from_user.id))
        return
    
    data = await state.get_data()
    feedback_id = data.get("reply_feedback_id")
    user_id = data.get("reply_user_id")
    reply_text = message.text
    
    if not feedback_id or not user_id:
        await state.clear()
        await message.answer("❌ Xatolik yuz berdi!")
        return
    
    feedbacks = load_feedback()
    feedback = next((fb for fb in feedbacks if fb["id"] == feedback_id), None)
    
    if not feedback or feedback.get("replied", False):
        await state.clear()
        await message.answer("❌ Fikr topilmadi yoki allaqachon javob berilgan!")
        return
    
    # Javobni saqlash
    feedback["replied"] = True
    feedback["reply"] = reply_text
    feedback["replied_at"] = str(datetime.now())
    feedback["replied_by"] = message.from_user.full_name
    save_feedback(feedbacks)
    
    # Foydalanuvchiga javob yuborish
    try:
        await bot.send_message(
            user_id,
            f"💬 <b>Admin javobi</b>\n\n"
            f"Sizning fikringizga javob:\n\n"
            f"📝 {reply_text}\n\n"
            f"🤝 Fikringiz uchun rahmat!",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await message.answer(f"⚠️ Foydalanuvchiga xabar yuborib bo'lmadi: {e}")
    
    add_log("reply_feedback", message.from_user.id, f"Fikr #{feedback_id} ga javob berildi")
    
    await state.clear()
    await message.answer(
        f"✅ Javob yuborildi!\n\n"
        f"📝 Fikr #{feedback_id}\n"
        f"👤 Foydalanuvchi ID: {user_id}\n"
        f"💬 Javob: {reply_text}",
        reply_markup=get_admin_keyboard(message.from_user.id)
    )

@dp.callback_query(F.data == "back_to_feedback_menu")
async def back_to_feedback_menu(call: CallbackQuery):
    await view_feedbacks(call.message)
    await call.answer()

@dp.callback_query(F.data == "back_to_feedback_list")
async def back_to_feedback_list(call: CallbackQuery):
    await list_all_feedbacks(call)
    await call.answer()

# ================= BLACKLIST =================
@dp.message(F.text == "🚫 Blacklist")
async def blacklist_menu(message: Message):
    if not is_super_admin(message.from_user.id):
        await message.answer("❌ Bu funksiya faqat SUPER ADMIN uchun!")
        return
    
    blacklist = load_blacklist()
    text = f"🚫 <b>Blacklist</b>\n\nBloklangan foydalanuvchilar ({len(blacklist)}):\n"
    for uid in blacklist:
        text += f"• `{uid}`\n"
    
    await message.answer(text)

# ================= ADMIN MANAGEMENT =================
@dp.message(F.text == "👑 Adminlar")
async def admin_management(message: Message):
    if not is_super_admin(message.from_user.id):
        await message.answer("❌ Bu funksiya faqat SUPER ADMIN uchun!")
        return
    
    admins = load_admins()
    text = f"👑 <b>Adminlar ro'yxati</b>\n\n"
    for admin in admins:
        star = " ⭐" if admin == SUPER_ADMIN_ID else ""
        text += f"• `{admin}`{star}\n"
    text += f"\n📊 Jami: {len(admins)} ta admin"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Admin qo'shish", callback_data="add_admin")
    if len(admins) > 1:
        builder.button(text="❌ Admin o'chirish", callback_data="remove_admin")
    builder.button(text="🔙 Orqaga", callback_data="back_to_admin")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "add_admin")
async def add_admin_start(call: CallbackQuery, state: FSMContext):
    if not is_super_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    await state.set_state(AddAdminState.waiting_for_user_id)
    await call.message.answer("👑 Admin qo'shish\n\nYangi adminning Telegram ID sini yuboring:\n\n(ID ni bilish uchun foydalanuvchi @userinfobot ga murojaat qilishi mumkin)")
    await call.answer()

@dp.message(AddAdminState.waiting_for_user_id)
async def add_admin_finish(message: Message, state: FSMContext):
    if not is_super_admin(message.from_user.id):
        return
    
    try:
        admin_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Noto'g'ri ID! Iltimos, faqat raqamlardan iborat ID yuboring.")
        return
    
    admins = load_admins()
    
    if admin_id in admins:
        await message.answer("❌ Bu foydalanuvchi allaqachon admin!")
        await state.clear()
        return
    
    admins.append(admin_id)
    save_admins(admins)
    add_log("add_admin", message.from_user.id, f"Admin qo'shildi: {admin_id}")
    
    await state.clear()
    await message.answer(f"✅ Admin qo'shildi: `{admin_id}`")
    
    # Yangi adminga xabar yuborish
    try:
        await bot.send_message(admin_id, "👑 Siz botga admin qilib tayinlandingiz!\n/start")
    except Exception:
        pass
    
    await admin_management(message)

@dp.callback_query(F.data == "remove_admin")
async def remove_admin_list(call: CallbackQuery):
    if not is_super_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    admins = load_admins()
    other_admins = [a for a in admins if a != SUPER_ADMIN_ID]
    
    if not other_admins:
        await call.answer("❌ O'chirish uchun boshqa adminlar yo'q!", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    for admin in other_admins:
        builder.button(text=f"❌ {admin}", callback_data=f"remove_admin_{admin}")
    builder.adjust(1)
    builder.button(text="🔙 Orqaga", callback_data="back_to_admin_management")
    
    await call.message.answer("❌ O'chiriladigan adminni tanlang:", reply_markup=builder.as_markup())
    await call.answer()

@dp.callback_query(F.data.startswith("remove_admin_"))
async def remove_admin_confirm(call: CallbackQuery):
    if not is_super_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    try:
        admin_id = int(call.data.replace("remove_admin_", ""))
    except ValueError:
        await call.answer("❌ Xatolik!", show_alert=True)
        return
    
    admins = load_admins()
    
    if admin_id not in admins:
        await call.message.answer("❌ Admin topilmadi!")
        await call.answer()
        return
    
    if admin_id == SUPER_ADMIN_ID:
        await call.message.answer("❌ Super Adminni o'chirib bo'lmaydi!")
        await call.answer()
        return
    
    admins.remove(admin_id)
    save_admins(admins)
    add_log("remove_admin", call.from_user.id, f"Admin o'chirildi: {admin_id}")
    
    await call.message.answer(f"✅ Admin o'chirildi: `{admin_id}`")
    
    # O'chirilgan adminga xabar yuborish
    try:
        await bot.send_message(admin_id, "❌ Sizning admin huquqlaringiz olib tashlandi!")
    except Exception:
        pass
    
    await call.answer()
    await admin_management(call.message)

@dp.callback_query(F.data == "back_to_admin_management")
async def back_to_admin_management(call: CallbackQuery):
    await admin_management(call.message)
    await call.answer()

# ================= LOGS =================
@dp.message(F.text == "📋 Loglar")
async def view_logs(message: Message):
    if not is_super_admin(message.from_user.id):
        await message.answer("❌ Bu funksiya faqat SUPER ADMIN uchun!")
        return
    
    logs = load_logs()
    if not logs:
        await message.answer("📋 Hech qanday log yo'q!")
        return
    
    log_text = "📋 <b>So'nggi 20 ta log</b>\n\n"
    for log in logs[-20:]:
        log_text += f"• {log['timestamp']}\n  {log['action']} - User: {log['user_id']}\n  {log['details']}\n\n"
    
    if len(log_text) > 4000:
        log_text = log_text[:4000] + "..."
    
    await message.answer(log_text)

# ================= BACKUP =================
@dp.message(F.text == "💾 Backup")
async def create_backup(message: Message):
    if not is_super_admin(message.from_user.id):
        await message.answer("❌ Bu funksiya faqat SUPER ADMIN uchun!")
        return
    
    backup_dir = "backups"
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    files_to_backup = ["users.json", "polls.json", "active_poll.json", "admins.json", "groups.json", "blacklist.json", "feedback.json", "logs.json", "channels.json"]
    
    for filename in files_to_backup:
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    data = json.load(f)
                with open(f"{backup_dir}/{timestamp}_{filename}", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
            except Exception:
                pass
    
    add_log("backup", message.from_user.id, f"Backup yaratildi: {timestamp}")
    await message.answer(f"✅ Backup yaratildi!\n📁 Papka: {backup_dir}/\n🕐 Vaqt: {timestamp}")

# ================= ARCHIVE =================
@dp.message(F.text == "📚 Arxiv")
async def view_archive(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Bu funksiya faqat adminlar uchun!")
        return
    
    polls = load_polls()
    if not polls:
        await message.answer("❌ Arxivda hech qanday so'rovnoma yo'q!")
        return
    
    text = "📚 <b>Arxivlangan so'rovnomalar</b>\n\n"
    for i, poll in enumerate(reversed(polls[-10:]), 1):
        total = sum(c["votes"] for c in poll["candidates"])
        text += f"{i}. {poll['title']} - {total} ovoz\n"
    
    await message.answer(text)

# ================= SHARE POLL LINK =================
@dp.message(F.text == "📢 Havola")
async def share_poll_link(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Bu funksiya faqat adminlar uchun!")
        return

    active_poll = load_active_poll()
    if not active_poll:
        await message.answer("❌ Faol so'rovnoma mavjud emas!")
        return

    bot_info = await bot.get_me()
    share_text = (
        f"🗳 <b>{active_poll['title']}</b>\n\n"
        f"📄 {active_poll['description']}\n\n"
        f"🔗 <b>So'rovnoma havolasi:</b>\n"
        f"https://t.me/{bot_info.username}?start=poll_{active_poll['id']}\n\n"
        f"⚠️ Havolani bosish orqali ovoz berishingiz mumkin!"
    )
    
    await message.answer(share_text)

# ================= END POLL =================
@dp.message(F.text == "🔚 Tugatish")
async def end_poll(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Bu funksiya faqat adminlar uchun!")
        return

    active_poll = load_active_poll()
    if not active_poll:
        await message.answer("❌ Faol so'rovnoma mavjud emas!")
        return

    total = sum(c["votes"] for c in active_poll["candidates"])
    
    results_text = f"📊 <b>{active_poll['title']}</b> - YAKUNIY NATIJALAR\n\n"
    
    if total > 0:
        sorted_candidates = sorted(active_poll["candidates"], key=lambda x: x["votes"], reverse=True)
        
        results_text += "🏆 <b>ENG KO'P OVOZ OLLGANLAR:</b>\n"
        for i, c in enumerate(sorted_candidates[:3], 1):
            percent = round((c["votes"] / total) * 100, 1)
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, "•")
            results_text += f"{medal} {c['name']} - {c['votes']} ovoz ({percent}%)\n"
        
        results_text += f"\n📋 <b>TO'LIQ JADVAL:</b>\n"
        for i, c in enumerate(sorted_candidates, 1):
            percent = round((c["votes"] / total) * 100, 1)
            results_text += f"{i}. {c['name']}: {c['votes']} ovoz ({percent}%)\n"
        
        results_text += f"\n📊 <b>Jami ovozlar:</b> {total}"
    else:
        results_text += "❌ Hech qanday ovoz berilmagan!"
    
    await message.answer(results_text)
    
    polls = load_polls()
    active_poll["ended_at"] = str(datetime.now())
    active_poll["final_results"] = results_text
    polls.append(active_poll)
    save_polls(polls)
    save_active_poll(None)
    
    add_log("end_poll", message.from_user.id, f"So'rovnoma tugatildi: {active_poll['title']}")
    
    await message.answer("✅ So'rovnoma tugatildi va arxivlandi!")

# ================= BROADCAST =================
@dp.message(F.text == "📨 Xabar")
async def broadcast_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Bu funksiya faqat adminlar uchun!")
        return
    await state.set_state(BroadcastState.waiting_for_message)
    await message.answer("📨 Foydalanuvchilarga yuboriladigan xabar matnini yuboring:", reply_markup=back_kb())

@dp.message(BroadcastState.waiting_for_message)
async def broadcast_send(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    if message.text == "🏠 Bosh menyu":
        await state.clear()
        await back_to_main_menu(message)
        return
    
    users = load_users()
    text = message.text
    if not text:
        await message.answer("❌ Xabar matnini yuboring!")
        return
        
    sent, failed = 0, 0
    status_msg = await message.answer("📤 Xabar yuborilmoqda...")

    for user_id, user_data in users.items():
        if is_blacklisted(int(user_id)):
            continue
        try:
            await bot.send_message(int(user_id), text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await state.clear()
    add_log("broadcast", message.from_user.id, f"Xabar yuborildi: {sent} ta foydalanuvchiga")
    await status_msg.edit_text(
        f"✅ Xabar yuborildi!\n\n"
        f"📨 Yuborildi: {sent}\n"
        f"❌ Xato: {failed}"
    )

@dp.message(F.text == "👥 Guruh xabar")
async def group_broadcast_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Bu funksiya faqat adminlar uchun!")
        return
    
    groups = load_groups()
    if not groups:
        await message.answer("❌ Bot hali hech qanday guruhga qo'shilmagan!")
        return
    
    await state.set_state(BroadcastState.waiting_for_group_message)
    await message.answer(
        f"📢 Guruhlarga yuboriladigan xabar matnini yuboring.\n\n"
        f"📊 Bot {len(groups)} ta guruhda mavjud:",
        reply_markup=back_kb()
    )

@dp.message(BroadcastState.waiting_for_group_message)
async def group_broadcast_send(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    if message.text == "🏠 Bosh menyu":
        await state.clear()
        await back_to_main_menu(message)
        return
    
    groups = load_groups()
    text = message.text
    
    if not text:
        await message.answer("❌ Xabar matnini yuboring!")
        return
    
    sent, failed = 0, 0
    status_msg = await message.answer("📤 Xabar guruhlarga yuborilmoqda...")
    
    for group in groups:
        try:
            await bot.send_message(group["id"], text)
            sent += 1
            await asyncio.sleep(0.5)
        except Exception:
            failed += 1
    
    await state.clear()
    add_log("group_broadcast", message.from_user.id, f"Guruhlarga xabar yuborildi: {sent} ta guruhga")
    await status_msg.edit_text(
        f"✅ Xabar yuborildi!\n\n"
        f"📨 Yuborildi: {sent}\n"
        f"❌ Xato: {failed}\n"
        f"📊 Jami guruhlar: {len(groups)}"
    )

# ================= EDIT POLL =================
@dp.message(F.text == "✏️ Tahrirlash")
async def edit_poll_start(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Bu funksiya faqat adminlar uchun!")
        return
    
    active_poll = load_active_poll()
    if not active_poll:
        await message.answer("❌ Faol so'rovnoma mavjud emas!")
        return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Nomi", callback_data="edit_title")
    builder.button(text="📄 Tavsifi", callback_data="edit_description")
    builder.button(text="👤 Nomzod qo'shish", callback_data="add_candidate_existing")
    builder.button(text="❌ Nomzod o'chirish", callback_data="remove_candidate")
    builder.button(text="🔙 Orqaga", callback_data="back_to_admin")
    builder.adjust(2)
    
    await message.answer(
        f"✏️ <b>So'rovnoma tahrirlash</b>\n\n"
        f"📌 Hozirgi so'rovnoma: {active_poll['title']}\n\n"
        f"Qanday o'zgartirish kiritmoqchisiz?",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "edit_title")
async def edit_title_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    await state.set_state(EditPollState.waiting_for_new_title)
    await call.message.answer("📝 Yangi so'rovnoma nomini kiriting:")
    await call.answer()

@dp.message(EditPollState.waiting_for_new_title)
async def edit_title_finish(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    active_poll = load_active_poll()
    if active_poll:
        old_title = active_poll["title"]
        active_poll["title"] = message.text
        save_active_poll(active_poll)
        add_log("edit_poll", message.from_user.id, f"Nomi o'zgartirildi: {old_title} -> {message.text}")
        await message.answer(f"✅ So'rovnoma nomi o'zgartirildi: {message.text}")
    else:
        await message.answer("❌ So'rovnoma topilmadi!")
    
    await state.clear()

@dp.callback_query(F.data == "edit_description")
async def edit_description_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    await state.set_state(EditPollState.waiting_for_new_description)
    await call.message.answer("📄 Yangi tavsifni kiriting:")
    await call.answer()

@dp.message(EditPollState.waiting_for_new_description)
async def edit_description_finish(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    active_poll = load_active_poll()
    if active_poll:
        active_poll["description"] = message.text
        save_active_poll(active_poll)
        add_log("edit_poll", message.from_user.id, "Tavsif o'zgartirildi")
        await message.answer("✅ So'rovnoma tavsifi o'zgartirildi!")
    else:
        await message.answer("❌ So'rovnoma topilmadi!")
    
    await state.clear()

@dp.callback_query(F.data == "add_candidate_existing")
async def add_candidate_existing(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    await state.set_state(EditPollState.waiting_for_candidate_name)
    await call.message.answer("👤 Yangi nomzod nomini kiriting:")
    await call.answer()

@dp.message(EditPollState.waiting_for_candidate_name)
async def add_candidate_existing_finish(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    active_poll = load_active_poll()
    if active_poll:
        new_id = max([c["id"] for c in active_poll["candidates"]]) + 1
        active_poll["candidates"].append({
            "id": new_id,
            "name": message.text,
            "votes": 0
        })
        save_active_poll(active_poll)
        add_log("edit_poll", message.from_user.id, f"Yangi nomzod qo'shildi: {message.text}")
        await message.answer(f"✅ Yangi nomzod qo'shildi: {message.text}")
    else:
        await message.answer("❌ So'rovnoma topilmadi!")
    
    await state.clear()

@dp.callback_query(F.data == "remove_candidate")
async def remove_candidate_list(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    active_poll = load_active_poll()
    if not active_poll:
        await call.answer("❌ So'rovnoma topilmadi!", show_alert=True)
        return
    
    if len(active_poll["candidates"]) <= 2:
        await call.answer("❌ Kamida 2 ta nomzod bo'lishi kerak!", show_alert=True)
        return    
    builder = InlineKeyboardBuilder()
    for c in active_poll["candidates"]:
        builder.button(text=f"❌ {c['name']}", callback_data=f"remove_cand_{c['id']}")
    builder.adjust(1)
    builder.button(text="🔙 Orqaga", callback_data="back_to_edit_poll")
    builder.adjust(1)
    
    await call.message.answer("❌ O'chiriladigan nomzodni tanlang:", reply_markup=builder.as_markup())
    await call.answer()

@dp.callback_query(F.data.startswith("remove_cand_"))
async def remove_candidate_confirm(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    try:
        candidate_id = int(call.data.split("_")[2])
    except (IndexError, ValueError):
        await call.answer("❌ Xatolik!", show_alert=True)
        return
    
    active_poll = load_active_poll()
    if not active_poll:
        await call.answer("❌ So'rovnoma topilmadi!", show_alert=True)
        return
    
    if len(active_poll["candidates"]) <= 2:
        await call.answer("❌ Kamida 2 ta nomzod bo'lishi kerak!", show_alert=True)
        return
    
    removed = [c for c in active_poll["candidates"] if c["id"] == candidate_id]
    active_poll["candidates"] = [c for c in active_poll["candidates"] if c["id"] != candidate_id]
    save_active_poll(active_poll)
    
    if removed:
        add_log("edit_poll", call.from_user.id, f"Nomzod o'chirildi: {removed[0]['name']}")
    
    await call.message.answer("✅ Nomzod o'chirildi!")
    await call.answer()

@dp.callback_query(F.data == "back_to_edit_poll")
async def back_to_edit_poll(call: CallbackQuery):
    await edit_poll_start(call.message)
    await call.answer()

# ================= RESET VOTES =================
@dp.message(F.text == "🧹 Tozalash")
async def reset_votes(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Bu funksiya faqat adminlar uchun!")
        return

    active_poll = load_active_poll()
    if not active_poll:
        await message.answer("❌ Faol so'rovnoma mavjud emas!")
        return

    for c in active_poll["candidates"]:
        c["votes"] = 0

    users = load_users()
    for user_id in users:
        if users[user_id].get("votes") == active_poll["id"]:
            users[user_id]["votes"] = None
    save_users(users)
    save_active_poll(active_poll)
    
    add_log("reset_votes", message.from_user.id, "Barcha ovozlar tozalandi")
    await message.answer("✅ Barcha ovozlar tozalandi!")

# ================= STATISTICS =================
@dp.message(F.text == "📈 Statistika")
async def stats(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Bu funksiya faqat adminlar uchun!")
        return

    users = load_users()
    active_poll = load_active_poll()
    polls = load_polls()
    admins = load_admins()
    groups = load_groups()
    blacklist = load_blacklist()
    feedbacks = load_feedback()
    logs = load_logs()
    channels = load_channels()

    verified_count = sum(1 for u in users.values() if u.get("verified"))
    voted_count = sum(1 for u in users.values() if u.get("votes") is not None)
    total_votes = sum(c["votes"] for c in active_poll["candidates"]) if active_poll else 0

    await message.answer(
        f"📊 <b>Bot statistikasi</b>\n\n"
        f"👥 Umumiy foydalanuvchilar: {len(users)}\n"
        f"✅ Tasdiqlanganlar: {verified_count}\n"
        f"🗳 Ovoz berganlar: {voted_count}\n"
        f"📊 Joriy ovozlar: {total_votes}\n"
        f"🗂 Arxivlangan so'rovnomalar: {len(polls)}\n"
        f"👑 Adminlar soni: {len(admins)}\n"
        f"👥 Guruhlar soni: {len(groups)}\n"
        f"📺 Majburiy kanallar: {len(channels)}\n"
        f"🚫 Blacklist: {len(blacklist)}\n"
        f"💬 Fikrlar: {len(feedbacks)}\n"
        f"📋 Loglar: {len(logs)}"
    )

# ================= INFO =================
@dp.message(F.text == "ℹ️ Ma'lumot")
async def info(message: Message):
    active_poll = load_active_poll()
    poll_status = "✅ Faol" if active_poll else "❌ Faol emas"
    
    users = load_users()
    verified = sum(1 for u in users.values() if u.get("verified"))
    channels = load_channels()
    
    channels_text = "\n".join([f"• {ch}" for ch in channels]) if channels else "❌ Hech qanday majburiy kanal yo'q"
    
    await message.answer(
        f"🤖 <b>Bot haqida ma'lumot</b>\n\n"
        f"Bu bot orqali so'rovnomalarda ishtirok etishingiz mumkin.\n\n"
        f"📌 <b>Qanday ishlaydi:</b>\n"
        f"1️⃣ Kanallarga obuna bo'ling (agar mavjud bo'lsa)\n"
        f"2️⃣ Telefon raqam yuboring\n"
        f"3️⃣ Captchani yeching\n"
        f"4️⃣ Ovoz bering (faqat 1 marta)\n\n"
        f"📊 <b>Xususiyatlar:</b>\n"
        f"• Real vaqtda natijalar\n"
        f"• Bir marta ovoz berish\n"
        f"• Avtomatik obuna tekshiruvi\n"
        f"• So'rovnoma havolasi\n"
        f"• Fikr bildirish va admin javobi\n"
        f"• So'rovnoma tahrirlash\n\n"
        f"📺 <b>Majburiy kanallar:</b>\n{channels_text}\n\n"
        f"📊 So'rovnoma holati: {poll_status}\n"
        f"👥 Ro'yxatdan o'tganlar: {verified}"
    )

# ================= HELP =================
@dp.message(Command("help"))
async def help_command(message: Message):
    if is_admin(message.from_user.id):
        text = (
            "🤖 <b>Admin yordam</b>\n\n"
            "📌 <b>Asosiy buyruqlar:</b>\n"
            "➕ So'rovnoma - Yangi so'rovnoma yaratish\n"
            "✏️ Tahrirlash - So'rovnoma nomi/tavsifini o'zgartirish\n"
            "📊 Natijalar - Joriy natijalarni ko'rish\n"
            "📢 Havola - So'rovnoma linkini olish\n"
            "📨 Xabar - Barcha foydalanuvchilarga xabar\n"
            "👥 Guruh xabar - Guruhlarga xabar yuborish\n"
            "📚 Arxiv - Tugatilgan so'rovnomalar\n"
            "👑 Adminlar - Admin qo'shish/o'chirish (faqat Super Admin)\n"
            "📺 Kanallar - Majburiy kanallar (faqat Super Admin)\n"
            "🚫 Blacklist - Foydalanuvchini bloklash (faqat Super Admin)\n"
            "💬 Fikrlar - Foydalanuvchi fikrlarini ko'rish va javob berish\n"
            "📈 Statistika - Bot statistikasi\n"
            "📋 Loglar - Tizim loglari (faqat Super Admin)\n"
            "💾 Backup - Ma'lumotlar backup (faqat Super Admin)\n"
            "🔚 Tugatish - Faol so'rovnomani tugatish\n"
            "🧹 Tozalash - Barcha ovozlarni tozalash\n"
            "🏠 Bosh menyu - Asosiy menyuga qaytish"
        )
    else:
        text = (
            "🤖 <b>Foydalanuvchi yordam</b>\n\n"
            "📌 <b>Buyruqlar:</b>\n"
            "/start - Botni ishga tushirish\n"
            "/help - Yordam\n\n"
            "📌 <b>Menyu tugmalari:</b>\n"
            "🗳 Ovoz berish - So'rovnomada ovoz berish (faqat 1 marta)\n"
            "📊 Natijalar - Joriy natijalarni ko'rish\n"
            "💬 Fikr bildirish - Bot haqida fikr qoldirish\n"
            "ℹ️ Ma'lumot - Bot haqida ma'lumot\n\n"
            "⚠️ <b>Eslatma:</b> Bir marta ovoz berganingizdan keyin qayta ovoz berolmaysiz!"
        )
    
    await message.answer(text)

# ================= GROUP HANDLER =================
@dp.my_chat_member()
async def track_groups(event):
    if event.chat.type in ["group", "supergroup"]:
        groups = load_groups()
        group_ids = [g["id"] for g in groups]
        
        if event.chat.id not in group_ids:
            groups.append({
                "id": event.chat.id,
                "title": event.chat.title,
                "added_at": str(datetime.now())
            })
            save_groups(groups)
            add_log("group_add", 0, f"Guruh qo'shildi: {event.chat.title} ({event.chat.id})")
            print(f"✅ Guruh qo'shildi: {event.chat.title} ({event.chat.id})")

@dp.message(F.left_chat_member)
async def remove_group(message: Message):
    if message.left_chat_member and message.left_chat_member.id == (await bot.get_me()).id:
        groups = load_groups()
        groups = [g for g in groups if g["id"] != message.chat.id]
        save_groups(groups)
        add_log("group_remove", 0, f"Guruhdan chiqarildi: {message.chat.id}")
        print(f"❌ Guruhdan chiqarildi: {message.chat.id}")

# ================= AUTO SUBSCRIPTION CHECK =================
async def auto_subscription_check():
    while True:
        try:
            await asyncio.sleep(60)
            users = load_users()
            channels = load_channels()
            
            if not channels:
                await asyncio.sleep(60)
                continue
            
            for user_id, user_data in users.items():
                if user_data.get("verified") and not is_blacklisted(int(user_id)):
                    sub = await check_sub(int(user_id))
                    if not sub:
                        try:
                            await bot.send_message(
                                int(user_id),
                                "⚠️ <b>Diqqat!</b>\n\n"
                                "Siz majburiy kanallarni tark etdingiz!\n"
                                "Botdan foydalanish uchun qayta obuna bo'ling:",
                                reply_markup=await get_channels_keyboard()
                            )
                        except Exception:
                            pass
                    await asyncio.sleep(0.05)
        except Exception as e:
            print(f"Auto check error: {e}")
            await asyncio.sleep(60)

# ================= GROUP MESSAGE HANDLER =================
@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def group_message_handler(message: Message):
    pass

# ================= ERROR HANDLER =================
@dp.message()
async def handle_unknown(message: Message):
    if message.chat.type in ["group", "supergroup"]:
        return
    
    if is_admin(message.from_user.id):
        await message.answer("❌ Noto'g'ri buyruq! Iltimos, menudan foydalaning.", 
                           reply_markup=get_admin_keyboard(message.from_user.id))
    else:
        await message.answer("❌ Noto'g'ri buyruq! Iltimos, menudan foydalaning.", 
                           reply_markup=user_menu())

# ================= FLASK WEB ROUTES =================
@app.route('/')
def index():
    users = load_users()
    active_poll = load_active_poll()
    total_votes = sum(c["votes"] for c in active_poll["candidates"]) if active_poll else 0
    channels = load_channels()
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Bot Dashboard</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container { max-width: 1200px; margin: 0 auto; }
            .header {
                background: white;
                border-radius: 20px;
                padding: 30px;
                margin-bottom: 30px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            }
            h1 { color: #667eea; font-size: 2em; }
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .stat-card {
                background: white;
                border-radius: 20px;
                padding: 25px;
                text-align: center;
            }
            .stat-value { 
                font-size: 2.5em; 
                font-weight: bold; 
                color: #667eea;
            }
            .poll-card {
                background: white;
                border-radius: 20px;
                padding: 30px;
                margin-bottom: 30px;
            }
            .poll-title { font-size: 1.5em; margin-bottom: 15px; }
            .progress-bar {
                background: #e0e0e0;
                border-radius: 10px;
                overflow: hidden;
                height: 8px;
                margin-top: 8px;
            }
            .progress-fill {
                background: linear-gradient(90deg, #667eea, #764ba2);
                height: 100%;
            }
            table {
                width: 100%;
                background: white;
                border-radius: 20px;
                overflow: hidden;
            }
            th, td { padding: 12px; text-align: left; }
            th { background: #667eea; color: white; }
            tr { border-bottom: 1px solid #eee; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🤖 So'rovnoma Bot Dashboard</h1>
                <p>Real vaqtda statistika</p>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{{ users_count }}</div>
                    <div>Foydalanuvchilar</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ verified_count }}</div>
                    <div>Tasdiqlanganlar</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ voted_count }}</div>
                    <div>Ovoz berganlar</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ total_votes }}</div>
                    <div>Jami ovozlar</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ channels_count }}</div>
                    <div>Majburiy kanallar</div>
                </div>
            </div>
            
            {% if active_poll %}
            <div class="poll-card">
                <h2 class="poll-title">📋 {{ active_poll.title }}</h2>
                <p>{{ active_poll.description }}</p>
                <h3>🏆 Natijalar:</h3>
                {% for c in active_poll.candidates %}
                <div>
                    <div>{{ c.name }} - {{ c.votes }} ovoz</div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {{ (c.votes / total_votes * 100) if total_votes > 0 else 0 }}%"></div>
                    </div>
                </div>
                {% endfor %}
            </div>
            {% endif %}
            
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Ism</th>
                        <th>Holat</th>
                        <th>Ovoz</th>
                    </tr>
                </thead>
                <tbody>
                    {% for user in users[:20] %}
                    <tr>
                        <td>{{ user.id }}</td>
                        <td>{{ user.name[:20] }}</td>
                        <td>{% if user.verified %}✅ Tasdiqlangan{% else %}⏳ Kutilmoqda{% endif %}</td>
                        <td>{% if user.voted %}✅ Bergan{% else %}❌ Bermagan{% endif %}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <script>
            setInterval(() => location.reload(), 30000);
        </script>
    </body>
    </html>
    ''', 
    users_count=len(users),
    verified_count=sum(1 for u in users.values() if u.get("verified")),
    voted_count=sum(1 for u in users.values() if u.get("votes") is not None),
    total_votes=total_votes,
    active_poll=active_poll,
    channels_count=len(channels),
    users=[{"id": uid, "name": u.get("full_name", "Noma'lum"), "verified": u.get("verified"), "voted": u.get("votes") is not None} for uid, u in list(users.items())[:20]]
    )

# ================= FLASK RUN =================
def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# ================= MAIN =================
async def main():
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    asyncio.create_task(auto_subscription_check())
    
    print("=" * 60)
    print("🤖 BOT MUVAFFAQIYATLI ISHGA TUSHDI")
    print("=" * 60)
    print(f"👑 Super Admin ID: {SUPER_ADMIN_ID}")
    print(f"📅 Vaqt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🌐 Web Dashboard: http://localhost:5000")
    print("=" * 60)
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"Bot polling error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
