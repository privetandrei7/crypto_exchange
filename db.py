import os
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import create_engine, String, Integer, DateTime, Numeric, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./exchange.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, index=True)
    sell_currency: Mapped[str] = mapped_column(String(20))
    buy_currency: Mapped[str] = mapped_column(String(20))
    sell_amount: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    buy_amount: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    rate: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    deposit_address: Mapped[str] = mapped_column(String(255))
    payout_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="WAITING_PAYMENT")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class AdminComment(Base):
    __tablename__ = "admin_comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, index=True)
    text: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class Setting(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    value: Mapped[str] = mapped_column(String(255))
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)

DEFAULTS = {"fee_percent":"1.0","rate_USDT_BTC":"0.00001","rate_BTC_USDT":"100000","rate_USDT_ETH":"0.0004","rate_ETH_USDT":"2500","rate_USDT_USDC":"1","rate_USDC_USDT":"1","rate_EUR_USDT":"1.08","rate_USDT_EUR":"0.9259259259","rate_USDT_RUB":"80","rate_RUB_USDT":"0.0125"}

def _columns(conn, table): return {row[1] for row in conn.exec_driver_sql(f'PRAGMA table_info("{table}")').fetchall()}

def _migrate_history(conn):
    tables={r[0] for r in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "order_status_history" not in tables: return
    cols=_columns(conn,"order_status_history"); canonical={"id","order_id","status","created_at"}
    if not (bool({"old_status","new_status"}&cols) or not canonical.issubset(cols)): return
    rows=conn.exec_driver_sql('SELECT * FROM "order_status_history" ORDER BY id').mappings().all()
    states={r["id"]:(r["status"],r["created_at"]) for r in conn.exec_driver_sql('SELECT id,status,created_at FROM "orders"').mappings().all()} if "orders" in tables else {}
    conn.exec_driver_sql('DROP TABLE IF EXISTS "order_status_history_new"')
    conn.exec_driver_sql('CREATE TABLE "order_status_history_new" (id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, status VARCHAR(40) NOT NULL, created_at DATETIME)')
    for r in rows:
        status=r.get("status") or r.get("new_status") or r.get("old_status") or (states.get(r.get("order_id"),("WAITING_PAYMENT",None))[0])
        created=r.get("created_at") or states.get(r.get("order_id"),(None,None))[1]
        conn.exec_driver_sql('INSERT INTO "order_status_history_new" (id,order_id,status,created_at) VALUES (?,?,?,?)',(r.get("id"),r.get("order_id"),status,created))
    conn.exec_driver_sql('DROP TABLE "order_status_history"'); conn.exec_driver_sql('ALTER TABLE "order_status_history_new" RENAME TO "order_status_history"')

def _migrate_comments(conn):
    tables={r[0] for r in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "admin_comments" not in tables:return
    cols=_columns(conn,"admin_comments")
    for name,typ in {"order_id":"INTEGER","text":"VARCHAR(1000)","created_at":"DATETIME"}.items():
        if name not in cols: conn.exec_driver_sql(f'ALTER TABLE "admin_comments" ADD COLUMN "{name}" {typ}')

def _sqlite_migrate_schema():
    if not DATABASE_URL.startswith("sqlite"):return
    with engine.begin() as conn:_migrate_history(conn);_migrate_comments(conn)

def init_db():
    Base.metadata.create_all(engine);_sqlite_migrate_schema();db=SessionLocal()
    try:
        for key,value in DEFAULTS.items():
            if db.query(Setting).filter_by(key=key).first() is None:db.add(Setting(key=key,value=value))
        existing_orders=db.query(Order).all();existing_history={r.order_id for r in db.query(OrderStatusHistory.order_id).all()}
        for order in existing_orders:
            if order.id not in existing_history:db.add(OrderStatusHistory(order_id=order.id,status=order.status,created_at=order.created_at))
        db.commit()
    finally:db.close()

def get_setting(key,default=None):
    db=SessionLocal()
    try:
        row=db.query(Setting).filter_by(key=key).first();return row.value if row else default
    finally:db.close()

init_db()
