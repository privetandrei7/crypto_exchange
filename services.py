from decimal import Decimal, ROUND_DOWN
from db import SessionLocal, Setting, Order, OrderStatusHistory

import json
import threading
import time
from urllib.request import Request, urlopen

SUPPORTED = ["BTC", "ETH", "USDT", "USDC", "EUR", "RUB"]

# Rapira public market-data API.
RAPIRA_RATES_URL = "https://api.rapira.net/open/market/rates"
RAPIRA_CACHE_TTL = 15  # seconds; keeps us comfortably below Rapira's limits.
_RAPIRA_CACHE = {"expires": 0.0, "data": {}}
_RAPIRA_LOCK = threading.Lock()

# Local fallback rates are used only when Rapira does not publish a pair
# or when the public API is temporarily unavailable.
FALLBACK_RATES = {
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


def _fetch_rapira_rates():
    """Return Rapira market rows keyed by symbol, cached for a few seconds."""
    now = time.monotonic()
    if now < _RAPIRA_CACHE["expires"]:
        return _RAPIRA_CACHE["data"]

    with _RAPIRA_LOCK:
        now = time.monotonic()
        if now < _RAPIRA_CACHE["expires"]:
            return _RAPIRA_CACHE["data"]

        request = Request(
            RAPIRA_RATES_URL,
            headers={"Accept": "application/json", "User-Agent": "crypto-exchange-demo/1.0"},
        )
        try:
            with urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            rows = payload.get("data", [])
            data = {str(row.get("symbol")): row for row in rows if row.get("symbol")}
            if data:
                _RAPIRA_CACHE["data"] = data
                _RAPIRA_CACHE["expires"] = time.monotonic() + RAPIRA_CACHE_TTL
            return _RAPIRA_CACHE["data"]
        except Exception:
            # Keep the last successful snapshot for a short outage.
            return _RAPIRA_CACHE["data"]


def _rapira_rate(sell: str, buy: str):
    """Return live executable-side rate for supported Rapira pairs.

    Rapira publishes e.g. BTC/USDT where askPrice is the price to buy BTC
    with USDT and bidPrice is the price received when selling BTC for USDT.
    """
    if sell == buy:
        return Decimal("1")

    # API symbols are quoted as ASSET/BASE, while our pair is SELL -> BUY.
    direct_symbols = {
        ("USDT", "RUB"): "USDT/RUB",
        ("BTC", "USDT"): "BTC/USDT",
        ("ETH", "USDT"): "ETH/USDT",
        ("USDC", "USDT"): "USDC/USDT",
    }

    symbol = direct_symbols.get((sell, buy))
    if symbol:
        row = _fetch_rapira_rates().get(symbol)
        if row:
            bid = Decimal(str(row.get("bidPrice", 0)))
            if bid > 0:
                return bid

    # Reverse direction: SELL the base currency and BUY the quoted asset.
    reverse = direct_symbols.get((buy, sell))
    if reverse:
        row = _fetch_rapira_rates().get(reverse)
        if row:
            ask = Decimal(str(row.get("askPrice", 0)))
            if ask > 0:
                return Decimal("1") / ask

    return None


def get_rate(sell: str, buy: str) -> Decimal:
    if sell == buy:
        return Decimal("1")

    key = f"rate_{sell}_{buy}"

    # Market pairs come directly from Rapira. Persist the latest successful
    # value so the admin panel can display exactly the rate used by orders.
    live = _rapira_rate(sell, buy)
    if live is not None and live > 0:
        db = SessionLocal()
        row = db.query(Setting).filter_by(key=key).first()
        value = str(live)
        if row is None:
            db.add(Setting(key=key, value=value))
        elif row.value != value:
            row.value = value
        db.commit()
        db.close()
        return live

    # EUR and any pair not published by Rapira use the saved/local fallback.
    db = SessionLocal()
    row = db.query(Setting).filter_by(key=key).first()
    if row is None:
        value = FALLBACK_RATES.get(key, "0")
        db.add(Setting(key=key, value=value))
        db.commit()
        db.close()
        return Decimal(value)

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
