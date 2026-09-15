import asyncio
import os
from decimal import Decimal, InvalidOperation
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db import SessionLocal, User, Order, init_db
from services import SUPPORTED, quote, create_order, list_user_orders

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
dp = Dispatcher()
STATUS_LABELS = {
    "WAITING_PAYMENT": "Ожидаем оплату", "PAYMENT_DETECTED": "Оплата обнаружена",
    "CONFIRMING": "Подтверждение", "CONFIRMED": "Подтверждено",
    "PAYOUT_PENDING": "Ожидает выплаты", "PAID": "Выплачено",
    "COMPLETED": "Завершено", "CANCELLED": "Отменено",
    "EXPIRED": "Истёк срок", "MANUAL_REVIEW": "Ручная проверка"
}


def fmt_num(value, max_decimals=8):
    try:
        n = Decimal(str(value))
    except Exception:
        return str(value)
    text = format(n.quantize(Decimal(1).scaleb(-max_decimals)), 'f').rstrip('0').rstrip('.')
    return text or '0'


def fmt_money(value, currency):
    return fmt_num(value, 8 if currency in ('BTC','ETH') else 2) + ' ' + currency


def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="💱 Обменять", callback_data="exchange")
    kb.button(text="📊 Курсы", callback_data="rates")
    kb.button(text="📋 Мои заявки", callback_data="orders")
    kb.button(text="❓ Помощь", callback_data="help")
    kb.adjust(1, 2, 1)
    return kb.as_markup()


def currencies(prefix):
    kb = InlineKeyboardBuilder()
    for c in SUPPORTED:
        kb.button(text=c, callback_data=f"{prefix}:{c}")
    kb.adjust(3, 2)
    return kb.as_markup()


def confirm_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data="confirm")
    kb.button(text="❌ Отмена", callback_data="cancel")
    kb.adjust(2)
    return kb.as_markup()


@dp.message(CommandStart())
async def start(message: Message):
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=message.from_user.id).first()
    if not user:
        db.add(User(telegram_id=message.from_user.id, username=message.from_user.username))
        db.commit()
    payload = (message.text or "").split(maxsplit=1)
    if len(payload) == 2 and payload[1].startswith("order_"):
        try:
            order_id = int(payload[1].split("_", 1)[1])
        except ValueError:
            order_id = None
        if order_id:
            order = db.get(Order, order_id)
            if order:
                order.telegram_id = message.from_user.id
                db.commit()
                await message.answer(
                    f"🔗 <b>Заявка #{order.id} привязана к вашему Telegram</b>\n\n"
                    f"{order.sell_amount} {order.sell_currency} → {order.buy_amount} {order.buy_currency}\n"
                    f"Статус: <b>{STATUS_LABELS.get(order.status, order.status)}</b>\n\n"
                    "Теперь изменения статуса этой заявки будут приходить сюда.",
                    parse_mode="HTML"
                )
                db.close()
                return
    db.close()
    await message.answer(
        "🪙 <b>CRYPTO EXCHANGE — DEMO</b>\n\n"
        "Тестовый прототип обменника. Реальных криптоплатежей нет.",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "exchange")
async def exchange(call: CallbackQuery):
    await call.message.edit_text("Что отдаёте?", reply_markup=currencies("sell"))
    await call.answer()


@dp.callback_query(F.data.startswith("sell:"))
async def sell_selected(call: CallbackQuery):
    sell = call.data.split(":")[1]
    await call.message.edit_text(
        f"Отдаёте: <b>{sell}</b>\n\nЧто хотите получить?",
        reply_markup=currencies(f"buy:{sell}"),
        parse_mode="HTML"
    )
    await call.answer()


@dp.callback_query(F.data.startswith("buy:"))
async def buy_selected(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) != 3:
        await call.answer("Ошибка выбора валюты.", show_alert=True)
        return

    _, sell, buy = parts
    PENDING[call.from_user.id] = {"sell": sell, "buy": buy}

    await call.message.edit_text(
        f"Отдаёте: <b>{sell}</b>\n"
        f"Получаете: <b>{buy}</b>\n\n"
        "Введите сумму, например: <code>500</code>",
        parse_mode="HTML"
    )
    await call.answer()


PENDING = {}


@dp.message(F.text)
async def amount_message(message: Message):
    state = PENDING.get(message.from_user.id)
    if not state or "buy" not in state or state.get("buy") is None:
        return
    try:
        amount = Decimal(message.text.replace(",", ".").strip())
        if amount <= 0:
            raise InvalidOperation
    except InvalidOperation:
        await message.answer("Введите положительное число, например 500.")
        return
    sell, buy = state["sell"], state["buy"]
    rate, fee, net = quote(sell, buy, amount)
    if rate <= 0:
        await message.answer("Для этой пары пока нет тестового курса.")
        return
    state["amount"] = amount
    PENDING[message.from_user.id] = state
    await message.answer(
        f"💱 <b>Расчёт</b>\n\n"
        f"Вы отдаёте: {amount} {sell}\n"
        f"Курс: {rate} {buy}/{sell}\n"
        f"Комиссия: {fee} {buy}\n"
        f"Получаете: <b>{net} {buy}</b>\n\n"
        "Тестовая заявка. Реальной оплаты не требуется.",
        reply_markup=confirm_keyboard(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "confirm")
async def confirm(call: CallbackQuery):
    state = PENDING.get(call.from_user.id)
    if not state or "amount" not in state:
        await call.answer("Заявка устарела.", show_alert=True)
        return
    order = create_order(call.from_user.id, state["sell"], state["buy"], state["amount"])
    PENDING.pop(call.from_user.id, None)
    await call.message.edit_text(
        f"✅ <b>Заявка #{order.id} создана</b>\n\n"
        f"Отдаёте: {fmt_money(order.sell_amount, order.sell_currency)}\n"
        f"Получаете: {fmt_money(order.buy_amount, order.buy_currency)}\n\n"
        f"Тестовый адрес депозита:\n<code>{order.deposit_address}</code>\n\n"
        "Статус: ⏳ Ожидаем оплату\n\n"
        "<i>Это demo — переводить средства не нужно.</i>",
        parse_mode="HTML"
    )
    await call.answer()


@dp.callback_query(F.data == "cancel")
async def cancel(call: CallbackQuery):
    PENDING.pop(call.from_user.id, None)
    await call.message.edit_text("Операция отменена.", reply_markup=main_menu())
    await call.answer()


@dp.callback_query(F.data == "orders")
async def orders(call: CallbackQuery):
    rows = list_user_orders(call.from_user.id)
    if not rows:
        text = "📋 Заявок пока нет."
    else:
        lines = ["📋 <b>Мои заявки</b>\n"]
        for o in rows:
            lines.append(f"#{o.id} — {fmt_money(o.sell_amount, o.sell_currency)} → {fmt_money(o.buy_amount, o.buy_currency)} — <b>{o.status}</b>")
        text = "\n".join(lines)
    await call.message.edit_text(text, reply_markup=main_menu(), parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data == "rates")
async def rates(call: CallbackQuery):
    pairs = [("USDT","BTC"), ("BTC","USDT"), ("USDT","ETH"), ("ETH","USDT"), ("USDT","USDC"), ("USDC","USDT"), ("EUR","USDT"), ("USDT","EUR"), ("USDT","RUB"), ("RUB","USDT")]
    lines = ["📊 <b>Тестовые курсы</b>\n"]
    for a,b in pairs:
        r,_,_ = quote(a,b,Decimal("1"))
        lines.append(f"1 {a} = {fmt_num(r, 8)} {b}")
    await call.message.edit_text("\n".join(lines), reply_markup=main_menu(), parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data == "help")
async def help_cb(call: CallbackQuery):
    await call.message.edit_text(
        "❓ <b>Помощь</b>\n\n"
        "Это демонстрационный обменник.\n"
        "Все адреса и курсы тестовые. Реальные переводы отключены.",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )
    await call.answer()


async def run_bot():
    init_db()
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в .env")
    bot = Bot(BOT_TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run_bot())
