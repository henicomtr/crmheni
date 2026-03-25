from sqlalchemy import create_engine
print("4 - Baglantiyi test ediyorum...")
engine = create_engine("sqlite:///./test_gecici.db", connect_args={"check_same_thread": False})
with engine.connect() as conn:
    print("5 - Baglanti OK")