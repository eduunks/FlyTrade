import os
import json
import urllib.parse
import urllib.request
from fastapi import FastAPI, Depends, HTTPException, Header, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
import shutil
from uuid import uuid4

from src.database.connection import SessionLocal, get_db
from src.database.models import User, Order, Setting, Program, OrderStatus, TradeSession, TradeMessage, TradeStatus, Feedback
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI(title="FlyTrade Admin API")

os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

templates = Jinja2Templates(directory=os.path.join("src", "web", "templates"))

class SettingUpdate(BaseModel):
    value: str

class UserStatusUpdate(BaseModel):
    is_suspended: bool

class ProgramCreate(BaseModel):
    name: str
    banner_url: Optional[str] = None
    is_active: bool = True

class ProgramUpdate(BaseModel):
    name: Optional[str] = None
    banner_url: Optional[str] = None
    is_active: Optional[bool] = None

@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    template_path = os.path.join("src", "web", "templates", "admin.html")
    
    if not os.path.exists(template_path):
        return f"Erro: Arquivo não encontrado em {template_path}"
        
    with open(template_path, "r") as f:
        return f.read()

@app.get("/admin/dashboard-stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    total_volume = db.query(func.sum(Order.total_value)).filter(Order.status == OrderStatus.COMPLETED).scalar() or 0
    
    orders_by_program = db.query(
        Program.name, 
        func.count(Order.id).label("count"),
        func.sum(Order.quantity).label("miles")
    ).join(Order).group_by(Program.name).all()

    top_buyers = db.query(User).order_by(User.completed_trades.desc()).limit(5).all()

    return {
        "total_volume": total_volume,
        "programs_chart": [{"name": p.name, "value": p.count, "miles": p.miles} for p in orders_by_program],
        "top_users": [{"name": u.full_name, "trades": u.completed_trades} for u in top_buyers]
    }

@app.get("/admin/search-users")
def search_users(q: str = "", db: Session = Depends(get_db)):
    query = db.query(User)
    if q:
        query = query.filter(User.full_name.ilike(f"%{q}%") | User.cpf.ilike(f"%{q}%") | User.username.ilike(f"%{q}%"))
    return query.all()

@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total_users = db.query(User).count()
    total_orders = db.query(Order).count()
    active_programs = db.query(Program).filter(Program.is_active == True).count()
    
    return {
        "total_users": total_users,
        "total_orders": total_orders,
        "active_programs": active_programs
    }

@app.get("/users")
def list_users(db: Session = Depends(get_db)):
    return db.query(User).all()

@app.patch("/users/{user_id}/status")
def update_user_status(user_id: int, status_update: UserStatusUpdate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_suspended = status_update.is_suspended
    db.commit()
    return {"message": "User status updated"}

@app.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    return db.query(Setting).all()

@app.patch("/settings/{key}")
def update_setting(key: str, update: SettingUpdate, db: Session = Depends(get_db)):
    setting = db.query(Setting).filter(Setting.key == key).first()
    if not setting:
        setting = Setting(key=key, value=update.value)
        db.add(setting)
    else:
        setting.value = update.value
    
    db.commit()
    return {"message": f"Setting {key} updated"}

@app.get("/api/programs")
def get_programs(db: Session = Depends(get_db)):
    return db.query(Program).order_by(Program.name).all()

@app.post("/api/programs")
def create_program(program: ProgramCreate, db: Session = Depends(get_db)):
    existing = db.query(Program).filter(func.lower(Program.name) == func.lower(program.name)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Program already exists")
        
    new_program = Program(
        name=program.name.upper(), 
        banner_url=program.banner_url,
        is_active=program.is_active
    )
    db.add(new_program)
    db.commit()
    return {"message": "Program created successfully"}

@app.patch("/api/programs/{program_id}")
def update_program(program_id: int, program_update: ProgramUpdate, db: Session = Depends(get_db)):
    program = db.query(Program).filter(Program.id == program_id).first()
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")
        
    if program_update.name is not None:
        program.name = program_update.name.upper()
    if program_update.banner_url is not None:
        program.banner_url = program_update.banner_url
    if program_update.is_active is not None:
        program.is_active = program_update.is_active
        
    db.commit()
    return {"message": "Program updated successfully"}

class TradeMessageCreate(BaseModel):
    sender_telegram_id: int
    content: str

@app.get("/trade/{session_id}", response_class=HTMLResponse)
async def trade_page(session_id: int):
    template_path = os.path.join("src", "web", "templates", "chat.html")
    if not os.path.exists(template_path):
        return f"Erro: Arquivo não encontrado em {template_path}"
    with open(template_path, "r") as f:
        return f.read().replace("{{SESSION_ID}}", str(session_id))

@app.get("/api/trade_sessions/{session_id}")
def get_trade_session(session_id: int, db: Session = Depends(get_db)):
    session = db.query(TradeSession).filter(TradeSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return {
        "id": session.id,
        "order_id": session.order_id,
        "status": session.status.value,
        "buyer_id": session.buyer.telegram_id,
        "seller_id": session.seller.telegram_id,
        "buyer_confirmed": session.buyer_confirmed,
        "seller_confirmed": session.seller_confirmed,
    }

@app.get("/api/trade_sessions/{session_id}/messages")
def get_trade_messages(session_id: int, db: Session = Depends(get_db)):
    messages = db.query(TradeMessage).filter(TradeMessage.session_id == session_id).order_by(TradeMessage.created_at).all()
    return [
        {
            "id": m.id,
            "sender_id": m.sender.telegram_id,
            "sender_name": m.sender.full_name or m.sender.username or "Usuário",
            "content": m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]

@app.post("/api/trade_sessions/{session_id}/messages")
def post_trade_message(session_id: int, payload: TradeMessageCreate, db: Session = Depends(get_db)):
    session = db.query(TradeSession).filter(TradeSession.id == session_id).first()
    if not session or session.status != TradeStatus.OPEN:
        raise HTTPException(status_code=404, detail="Sessão de negociação não disponível")
    sender = db.query(User).filter(User.telegram_id == payload.sender_telegram_id).first()
    if not sender:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    recipient = session.seller if sender.id == session.buyer_id else session.buyer
    if sender.id not in (session.buyer_id, session.seller_id):
        raise HTTPException(status_code=403, detail="Você não participa desta sessão")

    message = TradeMessage(session_id=session_id, sender_id=sender.id, content=payload.content)
    db.add(message)
    db.commit()

    telegram_token = os.getenv("TELEGRAM_TOKEN")
    if telegram_token:
        text = (
            f"💬 <b>{sender.full_name or sender.username or 'Usuário'}</b>\n"
            f"{payload.content}"
        )
        url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        data = {
            "chat_id": recipient.telegram_id,
            "text": text,
            "parse_mode": "HTML"
        }
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode())
        try:
            with urllib.request.urlopen(req) as resp:
                resp.read()
        except Exception:
            pass

    return {"message": "Mensagem enviada"}

@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    ext = file.filename.split(".")[-1]
    filename = f"{uuid4().hex}.{ext}"
    filepath = os.path.join("uploads", filename)
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    return {"url": f"{base_url}/uploads/{filename}"}

@app.get("/profile/{user_id}", response_class=HTMLResponse)
async def user_profile(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    orders_owner = db.query(Order).filter(Order.user_id == user.id, Order.status == OrderStatus.COMPLETED).all()
    
    from src.database.models import OfferProposal, ProposalStatus
    accepted_proposals = db.query(OfferProposal).filter(
        OfferProposal.sender_id == user.id,
        OfferProposal.status == ProposalStatus.ACCEPTED
    ).all()
    
    accepted_order_ids = [p.order_id for p in accepted_proposals]
    orders_proposer = db.query(Order).filter(
        Order.id.in_(accepted_order_ids), 
        Order.status == OrderStatus.COMPLETED
    ).all()
    
    all_completed_orders = list(set(orders_owner + orders_proposer))
    
    lifetime_miles = sum(o.quantity for o in all_completed_orders)
    recent_miles = sum(o.quantity for o in all_completed_orders if o.created_at >= thirty_days_ago)
    
    feedbacks = db.query(Feedback).filter(Feedback.to_user_id == user.id).order_by(Feedback.created_at.desc()).limit(10).all()
    
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user,
        "lifetime_miles": lifetime_miles,
        "recent_miles": recent_miles,
        "feedbacks": feedbacks
    })

@app.post("/programs")
def add_program_legacy(name: str, db: Session = Depends(get_db)):
    new_program = Program(name=name.upper())
    db.add(new_program)
    db.commit()
    return {"message": "Program added"}
