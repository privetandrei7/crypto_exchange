import asyncio, os
from decimal import Decimal
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from services import SUPPORTED, quote, create_order, list_user_orders

TOKEN=os.getenv('BOT_TOKEN','')
STATUS_LABELS={'WAITING_PAYMENT':'Ожидаем оплату','PAYMENT_DETECTED':'Оплата обнаружена','CONFIRMING':'Подтверждение','CONFIRMED':'Подтверждено','PAYOUT_PENDING':'Ожидает выплаты','PAID':'Выплачено','COMPLETED':'Завершено','CANCELLED':'Отменено','EXPIRED':'Истёк срок','MANUAL_REVIEW':'Ручная проверка'}
dp=Dispatcher()

def kb_currencies(prefix='sell'):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c,callback_data=f'{prefix}:{c}') for c in SUPPORTED[i:i+3]] for i in range(0,len(SUPPORTED),3)])

@dp.message(CommandStart())
async def start(m:Message):
    await m.answer('👋 Добро пожаловать в Crypto Exchange Demo.\n\nВыберите валюту, которую отдаёте.',reply_markup=kb_currencies('sell'))

@dp.callback_query(F.data.startswith('sell:'))
async def choose_sell(c:CallbackQuery):
    sell=c.data.split(':',1)[1]; await c.message.edit_text(f'Отдаёте: {sell}\n\nВыберите валюту получения.',reply_markup=kb_currencies(f'buy:{sell}')); await c.answer()

@dp.callback_query(F.data.startswith('buy:'))
async def choose_buy(c:CallbackQuery):
    _,sell,buy=c.data.split(':');
    await c.message.edit_text(f'Обмен: {sell} → {buy}\n\nНапишите сумму одним сообщением, например: 500');
    await c.answer()
    dp.workflow_data[f'pair_{c.from_user.id}']=(sell,buy)

@dp.message(F.text)
async def amount(m:Message):
    pair=dp.workflow_data.get(f'pair_{m.from_user.id}')
    if not pair:return
    try: amount=Decimal(m.text.replace(',','.')); assert amount>0
    except: await m.answer('Введите положительную сумму, например 500.');return
    sell,buy=pair; rate,fee,net=quote(sell,buy,amount)
    o=create_order(m.from_user.id,sell,buy,amount)
    await m.answer(f'✅ Заявка #{o.id} создана\n\n{amount} {sell} → {net} {buy}\nКомиссия: {fee}\nКурс: {rate}\n\nСтатус: {STATUS_LABELS[o.status]}\nТестовый адрес депозита: {o.deposit_address}')

@dp.message(Command('orders'))
async def orders(m:Message):
    rows=list_user_orders(m.from_user.id)
    if not rows: await m.answer('У вас пока нет заявок.');return
    await m.answer('\n\n'.join(f'#{o.id}: {o.sell_amount} {o.sell_currency} → {o.buy_amount} {o.buy_currency}\n{STATUS_LABELS.get(o.status,o.status)}' for o in rows))

async def main():
    if not TOKEN: raise RuntimeError('BOT_TOKEN is not set')
    bot=Bot(TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__=='__main__': asyncio.run(main())
