import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from src.database.models import Base, Setting, User

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./flytrade.db")

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    if inspector.has_table("orders"):
        columns = [col["name"] for col in inspector.get_columns("orders")]
        if "accepted_proposal_id" not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE orders ADD COLUMN accepted_proposal_id INTEGER"))
                conn.commit()
                print("[DB] Coluna accepted_proposal_id adicionada à tabela orders")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def bootstrap_data(db):
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    if admin_id:
        admin_id = int(admin_id)
        admin_user = db.query(User).filter(User.telegram_id == admin_id).first()
        if not admin_user:
            admin_user = User(telegram_id=admin_id, username="SuperAdmin")
            db.add(admin_user)
    
    default_settings = {
        "currency_symbol": "$",
        "currency_position": "before",
        "thousand_separator": ",",
        "decimal_separator": ".",
        "buy_channel_id": "",
        "sell_channel_id": ""
    }

    for key, value in default_settings.items():
        exists = db.query(Setting).filter(Setting.key == key).first()
        if not exists:
            new_setting = Setting(key=key, value=value)
            db.add(new_setting)
    
    db.commit()