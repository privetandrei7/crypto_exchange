import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from db import SessionLocal, Order, Setting, User, OrderStatusHistory, AdminComment, init_db
from services import SUPPORTED, quote, create_order

init_db()
app = FastAPI(title="Crypto Exchange Demo Admin")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "change-me"))
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def fmt_num(value, max_decimals=8, min_decimals=0, grouping=False):
    """Compact financial number formatting: removes meaningless trailing zeros."""
    if value is None:
        return "—"
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    q = Decimal(1).scaleb(-max_decimals)
    d = d.quantize(q)
    text = format(d, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if min_decimals:
        if "." not in text:
            text += "."
        text += "0" * max(0, min_decimals - len(text.split(".", 1)[1]))
    if grouping:
        whole, dot, frac = text.partition(".")
        sign = ""
        if whole.startswith("-"):
            sign, whole = "-", whole[1:]
        groups = []
        while whole:
            groups.append(whole[-3:])
            whole = whole[:-3]
        text = sign + " ".join(reversed(groups)) + (dot + frac if dot else "")
    return text


templates.env.filters["fmt"] = fmt_num
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

STATUSES = [
    "WAITING_PAYMENT", "PAYMENT_DETECTED", "CONFIRMING", "CONFIRMED",
    "PAYOUT_PENDING", "PAID", "COMPLETED", "CANCELLED", "EXPIRED", "MANUAL_REVIEW"
]
STATUS_LABELS = {
    "WAITING_PAYMENT": "Ожидаем оплату",
    "PAYMENT_DETECTED": "Оплата обнаружена",
    "CONFIRMING": "Подтверждение",
    "CONFIRMED": "Подтверждено",
    "PAYOUT_PENDING": "Ожидает выплаты",
    "PAID": "Выплачено",
    "COMPLETED": "Завершено",
    "CANCELLED": "Отменено",
    "EXPIRED": "Истёк срок",
    "MANUAL_REVIEW": "Ручная проверка",
}

RATE_KEYS = [
    ("rate_USDT_BTC", "USDT → BTC"),
    ("rate_BTC_USDT", "BTC → USDT"),
    ("rate_USDT_ETH", "USDT → ETH"),
    ("rate_ETH_USDT", "ETH → USDT"),
    ("rate_USDT_USDC", "USDT → USDC"),
    ("rate_USDC_USDT", "USDC → USDT"),
    ("rate_EUR_USDT", "EUR → USDT"),
    ("rate_USDT_EUR", "USDT → EUR"),
    ("rate_USDT_RUB", "USDT → RUB"),
    ("rate_RUB_USDT", "RUB → USDT"),
]


def is_admin(request: Request):
    return request.session.get("admin") is True


def redirect_login():
    return RedirectResponse("/admin/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})


@app.get("/api/rates")
def api_rates():
    result = {}
    for sell in SUPPORTED:
        for buy in SUPPORTED:
            if sell == buy:
                result[f"{sell}-{buy}"] = "1"
            else:
                rate, _, _ = quote(sell, buy, Decimal("1"))
                if rate > 0:
                    result[f"{sell}-{buy}"] = str(rate)
    from services import get_fee_percent
    return {"ok": True, "fee_percent": str(get_fee_percent()), "rates": result}


@app.get("/api/quote")
def api_quote(sell: str, buy: str, amount: str):
    sell, buy = sell.upper(), buy.upper()
    if sell not in SUPPORTED or buy not in SUPPORTED:
        return JSONResponse({"ok": False, "error": "Неподдерживаемая валюта."}, status_code=400)
    try:
        value = Decimal(amount.replace(",", "."))
        if value <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        return JSONResponse({"ok": False, "error": "Некорректная сумма."}, status_code=400)
    rate, fee, net = quote(sell, buy, value)
    return {"ok": True, "sell": sell, "buy": buy, "amount": str(value), "rate": str(rate), "fee": str(fee), "fee_percent": str(fee / (value * rate) * 100 if value * rate else 0), "receive": str(net)}


@app.post("/api/orders")
async def api_create_order(request: Request):
    try:
        data = await request.json()
        sell = str(data.get("sell", "")).upper()
        buy = str(data.get("buy", "")).upper()
        amount = Decimal(str(data.get("amount", "")).replace(",", "."))
        payout_address = str(data.get("payout_address", "")).strip() or None
        if sell not in SUPPORTED or buy not in SUPPORTED or amount <= 0:
            raise ValueError
    except (ValueError, InvalidOperation, TypeError):
        return JSONResponse({"ok": False, "error": "Проверьте валюты и сумму."}, status_code=400)
    order = create_order(0, sell, buy, amount, payout_address=payout_address)
    return {"ok": True, "order": {"id": order.id, "sell": order.sell_currency, "buy": order.buy_currency, "sell_amount": str(order.sell_amount), "buy_amount": str(order.buy_amount), "fee": str(order.fee_amount), "rate": str(order.rate), "deposit_address": order.deposit_address, "payout_address": order.payout_address, "status": order.status, "created_at": order.created_at.isoformat()}, "telegram_link": f"https://t.me/kupiusdtbot?start=order_{order.id}"}


@app.get("/api/orders/{order_id}")
def api_order(order_id: int):
    db = SessionLocal(); order = db.get(Order, order_id); db.close()
    if not order:
        return JSONResponse({"ok": False, "error": "Заявка не найдена."}, status_code=404)
    return {"ok": True, "order": {"id": order.id, "sell": order.sell_currency, "buy": order.buy_currency, "sell_amount": str(order.sell_amount), "buy_amount": str(order.buy_amount), "fee": str(order.fee_amount), "rate": str(order.rate), "deposit_address": order.deposit_address, "payout_address": order.payout_address, "status": order.status, "status_label": STATUS_LABELS.get(order.status, order.status), "telegram_id": order.telegram_id, "created_at": order.created_at.isoformat()}}


@app.get("/order/{order_id}", response_class=HTMLResponse)
def public_order_page(request: Request, order_id: int):
    return templates.TemplateResponse(request, "order.html", {"request": request, "order_id": order_id})


@app.get("/admin/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": None})


@app.post("/admin/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    expected_user = os.getenv("ADMIN_USER", "admin")
    expected_password = os.getenv("ADMIN_PASSWORD", "change-this-password")
    if username == expected_user and password == expected_password:
        request.session["admin"] = True
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": "Неверный логин или пароль."})


@app.get("/admin/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    if not is_admin(request):
        return redirect_login()

    db = SessionLocal()
    orders = db.query(Order).order_by(Order.id.desc()).limit(100).all()
    users = db.query(User).order_by(User.id.desc()).limit(30).all()
    settings = {x.key: x.value for x in db.query(Setting).all()}
    from services import get_rate
    for a, b in [("USDT", "BTC"), ("BTC", "USDT"), ("USDT", "ETH"), ("ETH", "USDT")]:
        get_rate(a, b)
    settings = {x.key: x.value for x in db.query(Setting).all()}

    stats = {
        "orders_total": db.query(Order).count(),
        "waiting": db.query(Order).filter(Order.status == "WAITING_PAYMENT").count(),
        "completed": db.query(Order).filter(Order.status == "COMPLETED").count(),
        "users": db.query(User).count(),
    }
    db.close()

    return templates.TemplateResponse(request, "admin.html", {
        "request": request,
        "orders": orders,
        "users": users,
        "settings": settings,
        "stats": stats,
        "statuses": STATUSES,
        "status_labels": STATUS_LABELS,
        "rate_keys": RATE_KEYS,
    })


def notify_telegram(order: Order):
    if not order.telegram_id or order.telegram_id <= 0:
        return
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return
    import asyncio
    from aiogram import Bot
    label = STATUS_LABELS.get(order.status, order.status)
    sell_amount = fmt_num(order.sell_amount, 8, 2, True)
    buy_amount = fmt_num(order.buy_amount, 8, 2, True)
    text = f"🔔 <b>Заявка #{order.id}</b>\n\nСтатус: <b>{label}</b>\n\n{sell_amount} {order.sell_currency} → {buy_amount} {order.buy_currency}"
    async def send():
        bot = Bot(token)
        try:
            await bot.send_message(order.telegram_id, text, parse_mode="HTML")
        finally:
            await bot.session.close()
    try:
        asyncio.run(send())
    except Exception:
        pass


@app.get("/admin/orders/{order_id}", response_class=HTMLResponse)
def admin_order_detail(request: Request, order_id: int):
    if not is_admin(request):
        return redirect_login()

    db = SessionLocal()
    order = db.get(Order, order_id)
    user = None
    if order and order.telegram_id and order.telegram_id > 0:
        user = db.query(User).filter(User.telegram_id == order.telegram_id).first()
    fee_percent = db.query(Setting).filter(Setting.key == "fee_percent").first()
    fee_percent_value = fee_percent.value if fee_percent else "1.0"
    history = db.query(OrderStatusHistory).filter_by(order_id=order_id).order_by(OrderStatusHistory.created_at.asc()).all()
    if order and not history:
        history = [OrderStatusHistory(order_id=order.id, status=order.status, created_at=order.created_at)]
    comments = db.query(AdminComment).filter_by(order_id=order_id).order_by(AdminComment.created_at.desc()).all()
    orders_total = db.query(Order).count()
    db.close()

    if not order:
        return HTMLResponse("Заявка не найдена", status_code=404)

    return templates.TemplateResponse(request, "admin_order.html", {
        "request": request,
        "order": order,
        "user": user,
        "fee_percent": fee_percent_value,
        "status_labels": STATUS_LABELS,
        "statuses": STATUSES,
        "history": history,
        "comments": comments,
        "orders_total": orders_total,
    })


@app.post("/admin/orders/{order_id}/status")
def change_status(request: Request, order_id: int, status: str = Form(...)):
    if not is_admin(request):
        return redirect_login()
    if status not in STATUSES:
        return RedirectResponse("/admin", status_code=303)

    db = SessionLocal()
    order = db.get(Order, order_id)
    if order:
        changed = order.status != status
        order.status = status
        if changed:
            db.add(OrderStatusHistory(order_id=order.id, status=status))
        db.commit()
        db.refresh(order)
        notify_telegram(order)
    db.close()
    return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)


@app.post("/admin/orders/{order_id}/quick-status")
def quick_status(request: Request, order_id: int, status: str = Form(...)):
    if not is_admin(request):
        return redirect_login()
    if status not in STATUSES:
        return RedirectResponse("/admin#orders", status_code=303)
    db = SessionLocal()
    order = db.get(Order, order_id)
    if order:
        changed = order.status != status
        order.status = status
        if changed:
            db.add(OrderStatusHistory(order_id=order.id, status=status))
        db.commit()
        db.refresh(order)
        notify_telegram(order)
    db.close()
    return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)


@app.post("/admin/orders/{order_id}/comment")
def add_comment(request: Request, order_id: int, text: str = Form("")):
    if not is_admin(request):
        return redirect_login()
    text = text.strip()[:1000]
    db = SessionLocal()
    order = db.get(Order, order_id)
    if order and text:
        db.add(AdminComment(order_id=order_id, text=text))
        db.commit()
    db.close()
    return RedirectResponse(f"/admin/orders/{order_id}#comment", status_code=303)


@app.post("/admin/orders/{order_id}/delete")
def delete_order(request: Request, order_id: int):
    if not is_admin(request):
        return redirect_login()
    db = SessionLocal()
    order = db.get(Order, order_id)
    if order:
        db.query(OrderStatusHistory).filter_by(order_id=order_id).delete(synchronize_session=False)
        db.query(AdminComment).filter_by(order_id=order_id).delete(synchronize_session=False)
        db.delete(order)
        db.commit()
    db.close()
    return RedirectResponse("/admin#orders", status_code=303)


@app.post("/admin/settings")
def update_settings(request: Request, fee_percent: str = Form(...)):
    if not is_admin(request):
        return redirect_login()

    try:
        value = Decimal(fee_percent.replace(",", "."))
        if value < 0 or value > 100:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        return RedirectResponse("/admin?error=fee#settings", status_code=303)

    db = SessionLocal()
    row = db.query(Setting).filter_by(key="fee_percent").first()
    if row is None:
        row = Setting(key="fee_percent", value=str(value))
        db.add(row)
    else:
        row.value = str(value)
    db.commit()
    db.close()
    return RedirectResponse("/admin#settings", status_code=303)


@app.post("/admin/rates")
async def update_rates(request: Request):
    if not is_admin(request):
        return redirect_login()

    form = await request.form()
    db = SessionLocal()
    try:
        for key, _label in RATE_KEYS:
            raw = str(form.get(key, "")).replace(",", ".").strip()
            if not raw:
                continue
            value = Decimal(raw)
            if value <= 0:
                raise InvalidOperation
            row = db.query(Setting).filter_by(key=key).first()
            if row is None:
                db.add(Setting(key=key, value=str(value)))
            else:
                row.value = str(value)
        db.commit()
    except (InvalidOperation, ValueError):
        db.rollback()
    finally:
        db.close()
    return RedirectResponse("/admin#rates", status_code=303)
