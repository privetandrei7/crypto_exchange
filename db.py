from datetime import datetime
from decimal import Decimal
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text, Numeric, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./exchange.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, index=True)
    username = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    telegram_id = Column(String, nullable=True)
    username = Column(String, nullable=True)
    sell_currency = Column(String, nullable=False)
    buy_currency = Column(String, nullable=False)
    sell_amount = Column(Numeric(30, 12), nullable=False)
    buy_amount = Column(Numeric(30, 12), nullable=False)
    fee_amount = Column(Numeric(30, 12), nullable=False)
    rate = Column(Numeric(30, 12), nullable=False)
    status = Column(String, default="WAITING_PAYMENT", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class AdminComment(Base):
    __tablename__ = "admin_comments"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    comment = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Setting(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)

SUPPORTED = ["BTC", "ETH", "USDT", "USDC", "EUR", "RUB"]
DEFAULTS = {
    "fee_percent": "1.0",
    "rate_USDT_BTC": "0.00001", "rate_BTC_USDT": "100000",
    "rate_USDT_ETH": "0.0004", "rate_ETH_USDT": "2500",
    "rate_USDT_USDC": "1", "rate_USDC_USDT": "1",
    "rate_EUR_USDT": "1.08", "rate_USDT_EUR": "0.9259259259",
    "rate_USDT_RUB": "80", "rate_RUB_USDT": "0.0125",
}

def _migrate_history(conn):
    insp = inspect(conn)
    if "order_status_history" not in insp.get_table_names(): return
    cols = [c["name"] for c in insp.get_columns("order_status_history")]
    if "status" in cols and "new_status" not in cols: return
    rows = conn.execute(text("SELECT * FROM order_status_history ORDER BY id")).mappings().all()
    conn.execute(text("ALTER TABLE order_status_history RENAME TO order_status_history_legacy"))
    OrderStatusHistory.__table__.create(conn)
    for r in rows:
        status = r.get("status") or r.get("new_status") or r.get("old_status") or "WAITING_PAYMENT"
        conn.execute(text("INSERT INTO order_status_history (id, order_id, status, created_at) VALUES (:id,:order_id,:status,:created_at)"), {
            "id": r.get("id"), "order_id": r.get("order_id"), "status": status,
            "created_at": r.get("created_at") or datetime.utcnow()
        })
    conn.execute(text("DROP TABLE order_status_history_legacy"))

def _migrate_comments(conn):
    if "admin_comments" not in inspect(conn).get_table_names(): return
    cols = [c["name"] for c in inspect(conn).get_columns("admin_comments")]
    for name, ddl in [("comment", "TEXT"), ("created_at", "DATETIME")]:
        if name not in cols: conn.execute(text(f"ALTER TABLE admin_comments ADD COLUMN {name} {ddl}"))

def init_db():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        _migrate_history(conn)
        _migrate_comments(conn)
        for k,v in DEFAULTS.items():
            if conn.execute(text("SELECT 1 FROM settings WHERE key=:k"), {"k":k}).first() is None:
                conn.execute(text("INSERT INTO settings(key,value) VALUES(:k,:v)"), {"k":k,"v":v})
        for oid in [r[0] for r in conn.execute(text("SELECT id FROM orders")).all()]:
            if conn.execute(text("SELECT 1 FROM order_status_history WHERE order_id=:o LIMIT 1"), {"o":oid}).first() is None:
                st = conn.execute(text("SELECT status FROM orders WHERE id=:o"), {"o":oid}).scalar() or "WAITING_PAYMENT"
                conn.execute(text("INSERT INTO order_status_history(order_id,status) VALUES(:o,:s)"), {"o":oid,"s":st})

init_db()
