import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Boolean
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class OrderStatus(enum.Enum):
    PENDING = "pending"
    MATCHED = "matched"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String)
    full_name = Column(String)
    cpf = Column(String, unique=True)
    birth_date = Column(String)
    is_verified = Column(Boolean, default=False)
    is_registered = Column(Boolean, default=False)
    is_suspended = Column(Boolean, default=False)
    rating = Column(Float, default=5.0)
    total_reviews = Column(Integer, default=0)
    completed_trades = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class Program(Base):
    __tablename__ = "programs"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    banner_url = Column(String) 
    is_active = Column(Boolean, default=True)

class Setting(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(String, nullable=False)

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    program_id = Column(Integer, ForeignKey("programs.id")) 
    order_type = Column(String) 
    quantity = Column(Integer)
    price_per_thousand = Column(Float)
    total_value = Column(Float)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING)
    accepted_proposal_id = Column(Integer, ForeignKey("offer_proposals.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")
    program = relationship("Program")
    accepted_proposal = relationship("OfferProposal", foreign_keys=[accepted_proposal_id])

class ProposalStatus(enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

class OfferProposal(Base):
    __tablename__ = "offer_proposals"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    price_per_thousand = Column(Float, nullable=False)
    status = Column(Enum(ProposalStatus), default=ProposalStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sender = relationship("User", foreign_keys=[sender_id])
    recipient = relationship("User", foreign_keys=[recipient_id])
    order = relationship("Order", foreign_keys=[order_id])

class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])
    order = relationship("Order")

class TradeStatus(enum.Enum):
    OPEN = "open"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class TradeSession(Base):
    __tablename__ = "trade_sessions"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(Enum(TradeStatus), default=TradeStatus.OPEN)
    buyer_confirmed = Column(Boolean, default=False)
    seller_confirmed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    order = relationship("Order")
    buyer = relationship("User", foreign_keys=[buyer_id])
    seller = relationship("User", foreign_keys=[seller_id])
    messages = relationship("TradeMessage", back_populates="session", cascade="all, delete-orphan")

class TradeMessage(Base):
    __tablename__ = "trade_messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("trade_sessions.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("TradeSession", back_populates="messages")
    sender = relationship("User")