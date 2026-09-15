import os
from decimal import Decimal
from db import SessionLocal, User, Order, OrderStatusHistory, Setting

LEGACY_BAD_RATES = {
    "rate_USDT_BTC": "100000", "rate_BTC_USDT": "0.00001",
    "rate_USDT_ETH": "2500", "rate_ETH_USDT": "0.0004",
}

def get_setting(key, default=None):
    with SessionLocal() as db:
        x = db.get(Setting, key)
        return x.value if x else default

def set_setting(key, value):
    with SessionLocal() as db:
        x = db.get(Setting, key)
        if x: x.value = str(value)
        else: db.add(Setting(key=key, value=str(value)))
        db.commit()

def get_rate(sell, buy):
    key = f"rate_{sell}_{buy}"
    v = get_setting(key)
    if v is None: return Decimal("0")
    if key in LEGACY_BAD_RATES and v == LEGACY_BAD_RATES[key]:
        from db import DEFAULTS
        v = DEFAULTS[key]
        set_setting(key, v)
    return Decimal(str(v))

def get_fee_percent(): return Decimal(str(get_setting("fee_percent", "1.0")))

def calc_exchange(sell, buy, amount):
    amount = Decimal(str(amount)); rate = get_rate(sell, buy)
    gross = amount * rate; fee = gross * get_fee_percent() / Decimal("100")
    return gross - fee, fee, rate

def create_order(sell, buy, amount, telegram_id=None, username=None):
    buy_amount, fee, rate = calc_exchange(sell, buy, amount)
    with SessionLocal() as db:
        user = None
        if telegram_id:
            user = db.query(User).filter_by(telegram_id=str(telegram_id)).first()
            if not user:
                user = User(telegram_id=str(telegram_id), username=username); db.add(user); db.flush()
        order = Order(user_id=user.id if user else None, telegram_id=str(telegram_id) if telegram_id else None,
                      username=username, sell_currency=sell, buy_currency=buy, sell_amount=amount,
                      buy_amount=buy_amount, fee_amount=fee, rate=rate, status="WAITING_PAYMENT")
        db.add(order); db.flush(); db.add(OrderStatusHistory(order_id=order.id, status=order.status)); db.commit(); db.refresh(order)
        return order

def set_order_status(order_id, status):
    with SessionLocal() as db:
        order = db.get(Order, order_id)
        if not order: return None
        order.status = status
        db.add(OrderStatusHistory(order_id=order.id, status=status)); db.commit(); db.refresh(order)
        return order
