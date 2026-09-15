from decimal import Decimal, ROUND_DOWN
from db import SessionLocal, Setting, Order, OrderStatusHistory

SUPPORTED = ["BTC", "ETH", "USDT", "USDC", "EUR", "RUB"]

# Correct demo rates: amount of BUY currency received for 1 SELL currency.
# Example: 1 USDT = 0.00001 BTC, therefore 500 USDT = 0.005 BTC before fee.
CORRECT_RATES = {
    "rate_USDT_BTC": "0.00001",
    "rate_BTC_USDT": "100000",
    "rate_USDT_ETH": "0.0004",
    "rate_ETH_USDT": "2500",
    "rate_USDT_USDC": "1",
    "rate_USDC_USDT": "1",
    "rate_EUR_USDT": "1.08",
    "rate_USDT_EUR": "0.9259259259",
    "rate_USDT_RUB": "80",
    "rate_RUB_USDT": "0.0125",
}

LEGACY_BAD_RATES = {
    "rate_USDT_BTC": "100000",
    "rate_BTC_USDT": "0.00001",
    "rate_USDT_ETH": "2500",
    "rate_ETH_USDT": "0.0004",
}


def get_rate(sell: str, buy: str) -> Decimal:
    if sell == buy:
        return Decimal("1")

    key = f"rate_{sell}_{buy}"
    db = SessionLocal()
    row = db.query(Setting).filter_by(key=key).first()

    if row is None:
        value = CORRECT_RATES.get(key, "0")
        db.add(Setting(key=key, value=value))
        db.commit()
        db.close()
        return Decimal(value)

    # Fix only the known bad values from the original demo.
    # This avoids overwriting any rate changed later by an administrator.
    if key in LEGACY_BAD_RATES and row.value == LEGACY_BAD_RATES[key]:
        row.value = CORRECT_RATES[key]
        db.commit()

    value = row.value
    db.close()
    return Decimal(value)


def get_fee_percent() -> Decimal:
    db = SessionLocal()
    row = db.query(Setting).filter_by(key="fee_percent").first()
    db.close()
    return Decimal(row.value) if row else Decimal("1")


def quote(sell: str, buy: str, amount: Decimal):
    rate = get_rate(sell, buy)
    fee_percent = get_fee_percent()

    gross = amount * rate
    fee = gross * fee_percent / Decimal("100")
    net = (gross - fee).quantize(
        Decimal("0.000000000001"),
        rounding=ROUND_DOWN
    )

    return rate, fee, net


def create_order(telegram_id, sell, buy, amount, payout_address=None):
    rate, fee, buy_amount = quote(sell, buy, amount)

    db = SessionLocal()
    order = Order(
        telegram_id=telegram_id,
        sell_currency=sell,
        buy_currency=buy,
        sell_amount=amount,
        buy_amount=buy_amount,
        fee_amount=fee,
        rate=rate,
        deposit_address=f"TEST_{sell}_DEPOSIT_{telegram_id}",
        payout_address=payout_address,
        status="WAITING_PAYMENT",
    )

    db.add(order)
    db.flush()
    db.add(OrderStatusHistory(order_id=order.id, status=order.status))
    db.commit()
    db.refresh(order)
    db.close()

    return order


def list_user_orders(telegram_id, limit=10):
    db = SessionLocal()
    rows = (
        db.query(Order)
        .filter_by(telegram_id=telegram_id)
        .order_by(Order.id.desc())
        .limit(limit)
        .all()
    )
    db.close()
    return rows
