from fastapi import APIRouter

router = APIRouter()

@router.post("/webhook/test")
def webhook_test():
    return {"status": "ok"}

from fastapi import Depends
from sqlalchemy.orm import Session
from .database import get_db
from .models import Message

@router.post("/webhook/test-message")
def test_message(db: Session = Depends(get_db)):
    msg = Message(
        sender="WhatsApp",
        content="Test mesajı geldi"
    )
    db.add(msg)
    db.commit()
    return {"status": "saved"}
