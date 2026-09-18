import os, asyncio, uuid
from pathlib import Path
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from database import Database
from locales import t

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in .env")

db = Database()
bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
router = Router()
MEDIA = Path(__file__).resolve().parent / "media"
MEDIA.mkdir(exist_ok=True)


def menu(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang,"photo"), callback_data="test:photo"), InlineKeyboardButton(text=t(lang,"video"), callback_data="test:video")],
        [InlineKeyboardButton(text=t(lang,"profile"), callback_data="profile"), InlineKeyboardButton(text=t(lang,"buy"), callback_data="buy")],
        [InlineKeyboardButton(text=t(lang,"support"), url="https://t.me/beIosheeev_kyc")]])


@router.message(CommandStart())
async def start(m: Message):
    old = db.get_user(m.from_user.id)
    db.upsert_user(m.from_user.id, m.from_user.username, m.from_user.first_name, m.from_user.last_name)
    db.add_message(m.from_user.id, m.message_id, "incoming", "text", "/start")
    if not old:
        db.add_action(m.from_user.id, "start", "Первый вход; выдано 5 тикетов")
    else:
        db.add_action(m.from_user.id, "start", "Повторный запуск")
    u = db.get_user(m.from_user.id); lang = u["language"] or "ru"
    await m.answer(t(lang,"welcome"), reply_markup=menu(lang))


@router.callback_query(F.data == "profile")
async def profile(c: CallbackQuery):
    u = db.get_user(c.from_user.id); lang = u["language"] or "ru"
    db.add_action(c.from_user.id, "profile", "Открыт профиль")
    text = (f"👤 <b>Профиль</b>\n\n🆔 ID: <code>{u['telegram_id']}</code>\n"
            f"👋 Username: {'@'+u['username'] if u['username'] else '—'}\n"
            f"🌐 Язык: {lang.upper()}\n🎫 Баланс: <b>{u['tickets']}</b>\n📱 Телефон: {u['phone'] or '—'}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang,"phone"), callback_data="phone")],
        [InlineKeyboardButton(text=t(lang,"buy"), callback_data="buy")],
        [InlineKeyboardButton(text=t(lang,"back"), callback_data="back")]])
    await c.message.edit_text(text, reply_markup=kb); await c.answer()


@router.callback_query(F.data == "phone")
async def phone(c: CallbackQuery):
    u = db.get_user(c.from_user.id); lang = u["language"] or "ru"
    if u["phone_verified"]:
        await c.answer("Бонус уже получен.", show_alert=True); return
    db.add_action(c.from_user.id, "phone_request", "Запрошен контакт")
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=t(lang,"share"), request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
    await c.message.answer("📱 Нажми кнопку ниже и отправь свой номер.", reply_markup=kb); await c.answer()


@router.message(F.content_type == ContentType.CONTACT)
async def contact(m: Message):
    u = db.get_user(m.from_user.id)
    if not u: return
    db.add_message(m.from_user.id, m.message_id, "incoming", "contact", m.contact.phone_number)
    if m.contact.user_id != m.from_user.id:
        db.add_action(m.from_user.id, "phone_rejected", "Контакт другого пользователя")
        await m.answer("Отправь свой контакт через кнопку Telegram."); return
    if db.verify_phone(m.from_user.id, m.contact.phone_number):
        db.add_action(m.from_user.id, "phone_verified", "Подтверждён номер; начислено 10 тикетов")
        await m.answer("🎁 Номер подтверждён. Начислено <b>10 тикетов</b>.", reply_markup=menu(u["language"] or "ru"))
    else:
        await m.answer("Бонус уже получен.")


@router.callback_query(F.data == "buy")
async def buy(c: CallbackQuery):
    u = db.get_user(c.from_user.id); lang = u["language"] or "ru"
    db.add_action(c.from_user.id, "buy_open", "Открыт раздел покупки")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟️ 5 тикетов — $2 (ТЕСТ)", callback_data="buy:test")],
        [InlineKeyboardButton(text=t(lang,"back"), callback_data="back")]])
    await c.message.edit_text("🎫 <b>Покупка тикетов</b>\n\n5 тикетов — $2.\n\n⚠️ Тестовый режим: кнопка начисляет 5 тикетов.", reply_markup=kb); await c.answer()


@router.callback_query(F.data == "buy:test")
async def buytest(c: CallbackQuery):
    u = db.get_user(c.from_user.id); lang = u["language"] or "ru"
    db.change_tickets(c.from_user.id, 5); db.add_action(c.from_user.id, "ticket_purchase_demo", "Тестовая покупка: +5")
    await c.message.edit_text("✅ Тестовая покупка: <b>+5 тикетов</b>.", reply_markup=menu(lang)); await c.answer()


@router.callback_query(F.data == "back")
async def back(c: CallbackQuery):
    u = db.get_user(c.from_user.id); lang = u["language"] or "ru"
    db.add_action(c.from_user.id, "menu", "Возврат в главное меню")
    await c.message.edit_text(t(lang,"welcome"), reply_markup=menu(lang)); await c.answer()


@router.callback_query(F.data == "test:photo")
async def photo_test(c: CallbackQuery):
    db.add_action(c.from_user.id, "photo_generation_test", "Нажата кнопка фото")
    await c.answer(t((db.get_user(c.from_user.id)["language"] or "ru"),"test_photo"), show_alert=True)


@router.callback_query(F.data == "test:video")
async def video_test(c: CallbackQuery):
    db.add_action(c.from_user.id, "video_generation_test", "Нажата кнопка видео")
    await c.answer(t((db.get_user(c.from_user.id)["language"] or "ru"),"test_video"), show_alert=True)


@router.message(F.photo)
async def photo(m: Message):
    db.upsert_user(m.from_user.id, m.from_user.username, m.from_user.first_name, m.from_user.last_name)
    p = m.photo[-1]; folder = MEDIA / str(m.from_user.id); folder.mkdir(parents=True, exist_ok=True)
    path = folder / (uuid.uuid4().hex + ".jpg")
    await bot.download(p, destination=path)
    photo_id = db.add_photo(m.from_user.id, p.file_id, p.file_unique_id, str(path), m.caption or "", m.message_id, "incoming")
    db.add_message(m.from_user.id, m.message_id, "incoming", "photo", m.caption or "")
    db.add_action(m.from_user.id, "photo_received", f"Фото #{photo_id} сохранено; message_id={m.message_id}")
    await m.answer("🧪 Фото получено и сохранено в истории. Генерация пока отключена.")


@router.message()
async def any_message(m: Message):
    if not db.get_user(m.from_user.id):
        db.upsert_user(m.from_user.id, m.from_user.username, m.from_user.first_name, m.from_user.last_name)
    text = m.text or m.caption or ""
    ctype = str(m.content_type)
    db.add_message(m.from_user.id, m.message_id, "incoming", ctype, text[:4000])
    db.add_action(m.from_user.id, "message", f"type={ctype}; {text[:1000]}")


async def run_bot():
    dp = Dispatcher(); dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)
