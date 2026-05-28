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

# Debug modu — .env'de DEBUG=true olursa aktif
DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

# Proforma — para birimine göre banka hesap bilgileri
BANK_ACCOUNTS = {
    "TRY": {
        "name": "TÜRKİYE HALK BANKASI A.Ş.",
        "iban": "TR480001200935100010263677",
        "swift": "TRHBTR2A",
    },
    "USD": {
        "name": "TÜRKİYE HALK BANKASI A.Ş.",
        "iban": "TR910001200935100053000812",
        "swift": "TRHBTR2A",
    },
    "EUR": {
        "name": "TÜRKİYE HALK BANKASI A.Ş.",
        "iban": "TR440001200935100058000650",
        "swift": "TRHBTR2A",
    },
    "GBP": {
        "name": "TÜRKİYE HALK BANKASI A.Ş.",
        "iban": "TR340001200935100055000038",
        "swift": "TRHBTR2A",
    },
}