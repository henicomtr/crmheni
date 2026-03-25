import os
import warnings
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

CATEGORIES = [
    "Cilt Bakım",
    "Saç Bakım",
    "Kişisel Bakım",
    "Makyaj",
    "Parfüm",
    "Ortam Kokuları",
    "Genel Temizlik",
    "Çamaşır Yıkama",
    "Bulaşık Yıkama",
    "Temizlik Malzemeleri",
    "Ambalaj",
    "Kozmetik Hammadde",
    "Temizlik Hammadde"
]

PALLETS_PER_20FT = 13
PALLETS_PER_40FT = 24

# JWT ayarları — üretimde .env ile geçersiz kılınmalı
_DEFAULT_SECRET = "degistirilmedi-bu-deger-production-icin-tehlikeli"
SECRET_KEY = os.getenv("SECRET_KEY", _DEFAULT_SECRET)
ALGORITHM = "HS256"

# Varsayılan anahtar üretimde kullanılıyorsa geliştiriciyi uyar
if SECRET_KEY == _DEFAULT_SECRET:
    warnings.warn(
        "⚠️  SECRET_KEY ayarlanmamış! .env dosyasına güçlü bir değer ekle.",
        stacklevel=2
    )