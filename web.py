import os
from decimal import Decimal, InvalidOperation
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from db import SessionLocal, Order, Setting, User, OrderStatusHistory, AdminComment
from services import SUPPORTED, quote, create_order, get_fee_percent, get_rate

app=FastAPI(title="Crypto Exchange Demo")
app.add_middleware(SessionMiddleware,secret_key=os.getenv("SECRET_KEY","change-me"))
STATUS_LABELS={"WAITING_PAYMENT":"Ожидаем оплату","PAYMENT_DETECTED":"Оплата обнаружена","CONFIRMING":"Подтверждение","CONFIRMED":"Подтверждено","PAYOUT_PENDING":"Ожидает выплаты","PAID":"Выплачено","COMPLETED":"Завершено","CANCELLED":"Отменено","EXPIRED":"Истёк срок","MANUAL_REVIEW":"Ручная проверка"}
STATUSES=list(STATUS_LABELS)

HOME='''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Crypto Exchange</title><style>*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#f5f7fb;color:#18202a}.wrap{max-width:1100px;margin:auto;padding:24px}.hero{background:#111827;color:white;border-radius:24px;padding:42px;margin-bottom:22px}.hero h1{font-size:42px;margin:0 0 12px}.card{background:white;border-radius:20px;padding:24px;box-shadow:0 8px 30px #0000000d;margin-bottom:18px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}input,select,button{width:100%;padding:14px;border-radius:12px;border:1px solid #d7dce5;font-size:16px}button{background:#111827;color:#fff;border:0;cursor:pointer}.muted{color:#697386}.result{margin-top:15px;padding:16px;background:#f1f5f9;border-radius:14px}.links a{color:#2563eb;margin-right:16px}@media(max-width:700px){.grid{grid-template-columns:1fr}.hero h1{font-size:32px}}</style></head><body><div class="wrap"><div class="hero"><h1>Crypto Exchange</h1><p>Демонстрационный обмен криптовалют. Быстрый расчёт и создание тестовой заявки.</p><div class="links"><a href="/admin" style="color:#93c5fd">Админка</a></div></div><div class="card"><h2>Обмен</h2><div class="grid"><div><label>Отдаёте</label><select id="sell">%s</select></div><div><label>Получаете</label><select id="buy">%s</select></div></div><p><label>Сумма</label><input id="amount" type="number" min="0" step="any" value="100"></p><button onclick="calc()">Рассчитать</button><div id="out" class="result">Введите сумму и нажмите «Рассчитать».</div><p><button onclick="create()">Создать тестовую заявку</button></p><div id="order"></div></div><div class="card"><h3>Статус заявки</h3><input id="oid" placeholder="Номер заявки"><button onclick="track()" style="margin-top:10px">Проверить</button><div id="track"></div></div></div><script>const sell=document.getElementById('sell'),buy=document.getElementById('buy');async function calc(){let a=amount.value;let r=await fetch(`/api/quote?sell=${sell.value}&buy=${buy.value}&amount=${a}`);let j=await r.json();out.innerHTML=j.ok?`Курс: <b>${j.rate}</b><br>Комиссия: ${j.fee}<br>Получите: <b>${j.receive} ${j.buy}</b>`:`${j.error}`}async function create(){let r=await fetch('/api/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sell:sell.value,buy:buy.value,amount:amount.value})});let j=await r.json();order.innerHTML=j.ok?`<div class="result">Заявка <b>#${j.order.id}</b> создана. Статус: ${j.order.status}</div>`:`${j.error}`;if(j.ok)oid.value=j.order.id}async function track(){let r=await fetch('/api/orders/'+oid.value);let j=await r.json();track.innerHTML=j.ok?`<div class="result">Заявка #${j.order.id}: <b>${j.order.status_label}</b><br>${j.order.sell_amount} ${j.order.sell} → ${j.order.buy_amount} ${j.order.buy}</div>`:j.error}</script></body></html>''' % (''.join(f'<option>{x}</option>' for x in SUPPORTED),''.join(f'<option>{x}</option>' for x in SUPPORTED))

def admin_ok(request): return request.session.get("admin") is True

def login_html(error=''):
    return f'''<!doctype html><html lang="ru"><meta name="viewport" content="width=device-width,initial-scale=1"><body style="font-family:Arial;max-width:420px;margin:80px auto;padding:20px"><h1>Вход в админку</h1><form method="post"><input name="username" placeholder="Логин" style="width:100%;padding:12px;margin:6px 0"><input name="password" type="password" placeholder="Пароль" style="width:100%;padding:12px;margin:6px 0"><button style="width:100%;padding:12px">Войти</button></form><p>{error}</p></body></html>'''

@app.get("/",response_class=HTMLResponse)
def home(): return HOME

@app.get("/api/rates")
def rates():
    return {"ok":True,"fee_percent":str(get_fee_percent()),"rates":{f"{a}-{b}":str(get_rate(a,b)) for a in SUPPORTED for b in SUPPORTED}}

@app.get("/api/quote")
def api_quote(sell:str,buy:str,amount:str):
    sell,buy=sell.upper(),buy.upper()
    try: value=Decimal(amount.replace(',','.')); assert value>0
    except: return JSONResponse({"ok":False,"error":"Некорректная сумма."},status_code=400)
    if sell not in SUPPORTED or buy not in SUPPORTED:return JSONResponse({"ok":False,"error":"Неподдерживаемая валюта."},status_code=400)
    rate,fee,net=quote(sell,buy,value)
    return {"ok":True,"sell":sell,"buy":buy,"amount":str(value),"rate":str(rate),"fee":str(fee),"receive":str(net)}

@app.post("/api/orders")
async def api_create(request:Request):
    try:
        d=await request.json(); sell=str(d.get('sell','')).upper(); buy=str(d.get('buy','')).upper(); amount=Decimal(str(d.get('amount','')).replace(',','.'))
        if sell not in SUPPORTED or buy not in SUPPORTED or amount<=0: raise ValueError
    except: return JSONResponse({"ok":False,"error":"Проверьте валюты и сумму."},status_code=400)
    order=create_order(0,sell,buy,amount,payout_address=None)
    return {"ok":True,"order":{"id":order.id,"sell":order.sell_currency,"buy":order.buy_currency,"sell_amount":str(order.sell_amount),"buy_amount":str(order.buy_amount),"fee":str(order.fee_amount),"rate":str(order.rate),"deposit_address":order.deposit_address,"payout_address":order.payout_address,"status":order.status}}

@app.get("/api/orders/{order_id}")
def api_order(order_id:int):
    db=SessionLocal();o=db.get(Order,order_id);db.close()
    if not o:return JSONResponse({"ok":False,"error":"Заявка не найдена."},status_code=404)
    return {"ok":True,"order":{"id":o.id,"sell":o.sell_currency,"buy":o.buy_currency,"sell_amount":str(o.sell_amount),"buy_amount":str(o.buy_amount),"fee":str(o.fee_amount),"rate":str(o.rate),"status":o.status,"status_label":STATUS_LABELS.get(o.status,o.status)}}

@app.get("/order/{order_id}",response_class=HTMLResponse)
def order_page(order_id:int): return HTMLResponse(HOME+f'<script>oid.value={order_id};track()</script>')

@app.get("/admin/login",response_class=HTMLResponse)
def login_page(): return login_html()

@app.post("/admin/login")
def login(request:Request,username:str=Form(...),password:str=Form(...)):
    if username==os.getenv("ADMIN_USER","admin") and password==os.getenv("ADMIN_PASSWORD","change-this-password"):
        request.session["admin"]=True;return RedirectResponse('/admin',303)
    return HTMLResponse(login_html('Неверный логин или пароль.'))

@app.get("/admin/logout")
def logout(request:Request): request.session.clear();return RedirectResponse('/admin/login',303)

@app.get("/admin",response_class=HTMLResponse)
def admin(request:Request):
    if not admin_ok(request):return RedirectResponse('/admin/login',303)
    db=SessionLocal();orders=db.query(Order).order_by(Order.id.desc()).limit(100).all();users=db.query(User).count();total=db.query(Order).count();completed=db.query(Order).filter_by(status='COMPLETED').count();waiting=db.query(Order).filter_by(status='WAITING_PAYMENT').count();db.close()
    rows=''.join(f'<tr><td><a href="/admin/orders/{o.id}">#{o.id}</a></td><td>{o.sell_amount} {o.sell_currency} → {o.buy_amount} {o.buy_currency}</td><td>{STATUS_LABELS.get(o.status,o.status)}</td></tr>' for o in orders)
    return HTMLResponse(f'''<!doctype html><html lang="ru"><meta name="viewport" content="width=device-width,initial-scale=1"><body style="font-family:Arial;max-width:1100px;margin:30px auto;padding:20px"><h1>Crypto Exchange — админка</h1><p>Заявок: {total} · Ожидают: {waiting} · Завершено: {completed} · Пользователей: {users}</p><p><a href="/">Сайт</a> · <a href="/admin/logout">Выйти</a></p><table border="1" cellpadding="12" cellspacing="0" width="100%"><tr><th>ID</th><th>Обмен</th><th>Статус</th></tr>{rows}</table></body></html>''')

@app.get("/admin/orders/{order_id}",response_class=HTMLResponse)
def detail(request:Request,order_id:int):
    if not admin_ok(request):return RedirectResponse('/admin/login',303)
    db=SessionLocal();o=db.get(Order,order_id);hist=db.query(OrderStatusHistory).filter_by(order_id=order_id).order_by(OrderStatusHistory.created_at).all();db.close()
    if not o:return HTMLResponse('Заявка не найдена',404)
    buttons=' '.join(f'<form method="post" action="/admin/orders/{o.id}/status" style="display:inline"><input type="hidden" name="status" value="{s}"><button>{STATUS_LABELS[s]}</button></form>' for s in STATUSES)
    history='<br>'.join(f'{h.created_at}: {STATUS_LABELS.get(h.status,h.status)}' for h in hist)
    return HTMLResponse(f'''<!doctype html><html lang="ru"><meta name="viewport" content="width=device-width,initial-scale=1"><body style="font-family:Arial;max-width:900px;margin:30px auto;padding:20px"><p><a href="/admin">← Админка</a></p><h1>Заявка #{o.id}</h1><h2>{o.sell_amount} {o.sell_currency} → {o.buy_amount} {o.buy_currency}</h2><p>Статус: <b>{STATUS_LABELS.get(o.status,o.status)}</b></p><p>Тестовый адрес депозита: {o.deposit_address}</p><h3>Изменить статус</h3>{buttons}<h3>История</h3><p>{history}</p></body></html>''')

@app.post("/admin/orders/{order_id}/status")
def status(request:Request,order_id:int,status:str=Form(...)):
    if not admin_ok(request):return RedirectResponse('/admin/login',303)
    if status not in STATUSES:return RedirectResponse(f'/admin/orders/{order_id}',303)
    db=SessionLocal();o=db.get(Order,order_id)
    if o:
        o.status=status;db.add(OrderStatusHistory(order_id=o.id,status=status));db.commit()
    db.close();return RedirectResponse(f'/admin/orders/{order_id}',303)
