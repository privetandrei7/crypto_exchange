from decimal import Decimal, ROUND_DOWN
from db import SessionLocal, Setting, Order, OrderStatusHistory, User
import json, threading, time, os
from urllib.request import Request, urlopen

TRADE_CURRENCIES = ["BTC", "ETH", "USDT", "USDC", "RUB"]
RUB_PAIRS = {
    ("USDT", "RUB"), ("RUB", "USDT"),
    ("BTC", "RUB"), ("RUB", "BTC"),
    ("ETH", "RUB"), ("RUB", "ETH"),
    ("USDC", "RUB"), ("RUB", "USDC"),
}
SUPPORTED = TRADE_CURRENCIES
RAPIRA_RATES_URL = "https://api.rapira.net/open/market/rates"
RAPIRA_CACHE_TTL = 15
_RAPIRA_CACHE = {"expires": 0.0, "data": {}}
_RAPIRA_LOCK = threading.Lock()
FALLBACK_RATES = {"rate_USDT_RUB": "80", "rate_RUB_USDT": "0.0125"}


def is_allowed_pair(sell: str, buy: str) -> bool:
    return (sell.upper(), buy.upper()) in RUB_PAIRS


def _fetch_rapira_rates():
    now = time.monotonic()
    if now < _RAPIRA_CACHE["expires"]:
        return _RAPIRA_CACHE["data"]
    with _RAPIRA_LOCK:
        now = time.monotonic()
        if now < _RAPIRA_CACHE["expires"]:
            return _RAPIRA_CACHE["data"]
        try:
            request = Request(RAPIRA_RATES_URL, headers={"Accept": "application/json", "User-Agent": "crypto-exchange-demo/1.0"})
            with urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            rows = payload.get("data", [])
            data = {str(row.get("symbol")): row for row in rows if row.get("symbol")}
            if data:
                _RAPIRA_CACHE["data"] = data
                _RAPIRA_CACHE["expires"] = time.monotonic() + RAPIRA_CACHE_TTL
            return _RAPIRA_CACHE["data"]
        except Exception:
            return _RAPIRA_CACHE["data"]


def _market(symbol: str, side: str):
    row = _fetch_rapira_rates().get(symbol)
    if not row:
        return None
    value = Decimal(str(row.get("bidPrice" if side == "bid" else "askPrice", 0)))
    return value if value > 0 else None


def _save_rate(key: str, value: Decimal):
    db = SessionLocal()
    try:
        row = db.query(Setting).filter_by(key=key).first()
        text = str(value)
        if row is None:
            db.add(Setting(key=key, value=text))
        elif row.value != text:
            row.value = text
        db.commit()
    finally:
        db.close()
    return value


def _rapira_rate(sell: str, buy: str):
    if not is_allowed_pair(sell, buy):
        return None
    if (sell, buy) == ("USDT", "RUB"):
        return _market("USDT/RUB", "bid")
    if (sell, buy) == ("RUB", "USDT"):
        ask = _market("USDT/RUB", "ask")
        return Decimal("1") / ask if ask else None
    if sell in {"BTC", "ETH", "USDC"} and buy == "RUB":
        asset = _market(f"{sell}/USDT", "bid")
        usdt = _market("USDT/RUB", "bid")
        return asset * usdt if asset and usdt else None
    if sell == "RUB" and buy in {"BTC", "ETH", "USDC"}:
        asset = _market(f"{buy}/USDT", "ask")
        usdt = _market("USDT/RUB", "ask")
        return Decimal("1") / (asset * usdt) if asset and usdt else None
    return None


def get_rate(sell: str, buy: str) -> Decimal:
    sell, buy = sell.upper(), buy.upper()
    if not is_allowed_pair(sell, buy):
        return Decimal("0")
    if sell == buy:
        return Decimal("1")
    key = f"rate_{sell}_{buy}"
    live = _rapira_rate(sell, buy)
    if live is not None and live > 0:
        return _save_rate(key, live)
    db = SessionLocal()
    try:
        row = db.query(Setting).filter_by(key=key).first()
        if row:
            return Decimal(row.value)
        value = FALLBACK_RATES.get(key, "0")
        db.add(Setting(key=key, value=value))
        db.commit()
        return Decimal(value)
    finally:
        db.close()


def get_fee_percent() -> Decimal:
    db = SessionLocal()
    try:
        row = db.query(Setting).filter_by(key="fee_percent").first()
        return Decimal(row.value) if row else Decimal("2")
    finally:
        db.close()


def quote(sell: str, buy: str, amount: Decimal):
    rate = get_rate(sell, buy)
    if rate <= 0:
        return Decimal("0"), Decimal("0"), Decimal("0")
    fee_percent = get_fee_percent()
    gross = amount * rate
    fee = gross * fee_percent / Decimal("100")
    net = (gross - fee).quantize(Decimal("0.000000000001"), rounding=ROUND_DOWN)
    return rate, fee, net


def _notify_admin_new_order(order):
    """Send an immediate Telegram notification to the exchange administrator."""
    admin_id = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not admin_id or not token:
        return
    try:
        public_base = os.getenv("PUBLIC_BASE_URL", "").strip() or os.getenv("RENDER_EXTERNAL_URL", "").strip()
        link = f"\n\n🔗 <a href=\"{public_base.rstrip('/')}/admin/orders/{order.id}\">Открыть заявку в админке</a>" if public_base else ""
        text = (
            f"🚨 <b>НОВАЯ ЗАЯВКА #{order.id}</b>\n\n"
            f"{order.sell_amount} {order.sell_currency} → {order.buy_amount} {order.buy_currency}\n"
            f"Комиссия: {order.fee_amount} {order.buy_currency}\n"
            f"Статус: <b>Ожидаем оплату</b>"
            f"{link}"
        )
        payload = json.dumps({"chat_id": admin_id, "text": text, "parse_mode": "HTML"}).encode("utf-8")
        request = Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "crypto-exchange-demo/1.0"},
            method="POST",
        )
        with urlopen(request, timeout=5):
            pass
    except Exception:
        pass


def notify_admin_new_order(order):
    # Do not slow down order creation waiting for Telegram.
    threading.Thread(target=_notify_admin_new_order, args=(order,), daemon=True).start()


def create_order(telegram_id, sell, buy, amount, payout_address=None):
    sell, buy = sell.upper(), buy.upper()
    if not is_allowed_pair(sell, buy):
        raise ValueError("Разрешены только пары с RUB.")
    rate, fee, buy_amount = quote(sell, buy, amount)
    if rate <= 0:
        raise ValueError("Для этой пары сейчас нет курса.")
    db = SessionLocal()
    try:
        user_id = int(telegram_id or 0)
        if user_id > 0:
            user = db.query(User).filter_by(telegram_id=user_id).first()
            if user is None:
                db.add(User(telegram_id=user_id, username=None))
                db.flush()
        order = Order(telegram_id=user_id, sell_currency=sell, buy_currency=buy, sell_amount=amount,
                      buy_amount=buy_amount, fee_amount=fee, rate=rate,
                      deposit_address=f"TEST_{sell}_DEPOSIT_{user_id}", payout_address=payout_address,
                      status="WAITING_PAYMENT")
        db.add(order)
        db.flush()
        db.add(OrderStatusHistory(order_id=order.id, status=order.status))
        db.commit()
        db.refresh(order)
        notify_admin_new_order(order)
        return order
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def list_user_orders(telegram_id, limit=10):
    db = SessionLocal()
    try:
        return db.query(Order).filter_by(telegram_id=telegram_id).order_by(Order.id.desc()).limit(limit).all()
    finally:
        db.close()
