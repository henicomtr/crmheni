import bcrypt
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from .config import SECRET_KEY, ALGORITHM

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None

# Web oturumu: son işlemden itibaren bu süre geçerse otomatik çıkış
ACCESS_TOKEN_EXPIRE_MINUTES = 10
# PWA oturumu: kullanıcı manuel çıkış yapana kadar 24 saat geçerli
ACCESS_TOKEN_EXPIRE_PWA_HOURS = 24

def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )

def create_token(data: dict, expires_delta: Optional[timedelta] = None, pwa_mode: bool = False):
    """Admin girişi için JWT token oluşturur. PWA oturumlarında 24 saatlik token verilir."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    elif pwa_mode:
        expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_PWA_HOURS)
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # PWA bilgisini payload'a göm; middleware yenileme kararını buna göre verir
    to_encode.update({"exp": expire, "pwa": pwa_mode})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt