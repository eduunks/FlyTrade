from src.database.connection import SessionLocal
from src.database.models import Setting

def get_setting(key: str, default: str) -> str:
    db = SessionLocal()
    setting = db.query(Setting).filter(Setting.key == key).first()
    db.close()
    return setting.value if setting else default