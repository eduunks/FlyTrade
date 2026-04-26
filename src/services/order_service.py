from sqlalchemy.orm import Session
from src.database.models import Order, OrderStatus

def attempt_match_order(db: Session, order_id: int, version: int):
    order = db.query(Order).filter(
        Order.id == order_id, 
        Order.version == version,
        Order.status == OrderStatus.PENDING
    ).first()
    
    if not order:
        return False
        
    order.status = OrderStatus.MATCHED
    order.version += 1
    db.commit()
    return True