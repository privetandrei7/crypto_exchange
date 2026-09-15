import os
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import create_engine, String, Integer, DateTime, Numeric, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./exchange.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

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

DEFAULTS = {"fee_percent": "2.0", "rate_USDT_RUB": "80", "rate_RUB_USDT": "0.0125"}

def _sqlite_migrate_schema():
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.begin() as conn:
        tables = {r[0] for r in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "order_status_history" in tables:
            cols = {r[1] for r in conn.exec_driver_sql('PRAGMA table_info("order_status_history")').fetchall()}
            canonical = {"id", "order_id", "status", "created_at"}
            if not canonical.issubset(cols) or {"old_status", "new_status"} & cols:
                rows = conn.exec_driver_sql('SELECT * FROM "order_status_history" ORDER BY id').mappings().all()
                conn.exec_driver_sql('DROP TABLE IF EXISTS "order_status_history_new"')
                conn.exec_driver_sql('CREATE TABLE "order_status_history_new" (id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, status VARCHAR(40) NOT NULL, created_at DATETIME)')
                for r in rows:
                    status = r.get("status") or r.get("new_status") or r.get("old_status") or "WAITING_PAYMENT"
                    conn.exec_driver_sql('INSERT INTO "order_status_history_new" (id,order_id,status,created_at) VALUES (?,?,?,?)', (r.get("id"), r.get("order_id"), status, r.get("created_at")))
                conn.exec_driver_sql('DROP TABLE "order_status_history"')
                conn.exec_driver_sql('ALTER TABLE "order_status_history_new" RENAME TO "order_status_history"')
        if "admin_comments" in tables:
            cols = {r[1] for r in conn.exec_driver_sql('PRAGMA table_info("admin_comments")').fetchall()}
            for name, typ in {"order_id":"INTEGER", "text":"VARCHAR(1000)", "created_at":"DATETIME"}.items():
                if name not in cols:
                    conn.exec_driver_sql(f'ALTER TABLE "admin_comments" ADD COLUMN "{name}" {typ}')

def init_db():
    Base.metadata.create_all(engine)
    _sqlite_migrate_schema()
    db = SessionLocal()
    try:
        for key, value in DEFAULTS.items():
            row = db.query(Setting).filter_by(key=key).first()
            if row is None:
                db.add(Setting(key=key, value=value))
            elif key == "fee_percent" and row.value == "1.0":
                row.value = "2.0"
        # Rebuild the user directory from all historical Telegram orders.
        existing_users = {u.telegram_id for u in db.query(User).all()}
        for order in db.query(Order).filter(Order.telegram_id > 0).all():
            if order.telegram_id not in existing_users:
                db.add(User(telegram_id=order.telegram_id, username=None, created_at=order.created_at))
                existing_users.add(order.telegram_id)
        existing_history = {r[0] for r in db.query(OrderStatusHistory.order_id).all()}
        for order in db.query(Order).all():
            if order.id not in existing_history:
                db.add(OrderStatusHistory(order_id=order.id, status=order.status, created_at=order.created_at))
        db.commit()
    finally:
        db.close()

def get_setting(key: str, default: str | None = None) -> str | None:
    db = SessionLocal()
    try:
        row = db.query(Setting).filter_by(key=key).first()
        return row.value if row else default
    finally:
        db.close()

init_db()
