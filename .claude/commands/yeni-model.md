# Yeni Veritabanı Modeli Ekle

Bu komutu çalıştırdığında aşağıdaki adımları sırayla uygula. **Her adımda onay al, sonrakine geçme.**

---

## Adım 1 — Model Bilgilerini Topla

Kullanıcıya şunları sor:
1. Tablonun adı ne olacak? (ör: `supplier_invoices`)
2. Hangi alanlar olacak? (alan adı + veri tipi)
3. Başka tablolarla ilişki var mı? (ForeignKey)
4. Çok dilli içerik gerekiyor mu? (ayrı `_translations` tablosu gerekir mi?)
5. Timestamp alanları gerekiyor mu? (`created_at`, `updated_at`)

---

## Adım 2 — Plan Sun

Kod yazmadan önce şu formatı kullan:

```
📋 PLAN
─────────────────────────────
Model adı          : SupplierInvoice
Tablo adı          : supplier_invoices
Eklenecek dosyalar : app/models.py
Migration gerekli  : Evet — main.py'e ALTER TABLE eklenecek
İlişkiler          : suppliers tablosuna ForeignKey
Yan etkiler        : Yok
─────────────────────────────
Onaylıyor musun?
```

---

## Adım 3 — Model Kodunu Yaz

Onay alındıktan sonra şu şablonu kullan:

```python
class {ModelAdi}(Base):
    """
    {Ne sakladığını Türkçe açıkla}
    """
    __tablename__ = "{tablo_adi}"

    id = Column(Integer, primary_key=True, index=True)
    # alanlar buraya — PostgreSQL uyumlu tipler kullan
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişkiler
    # ornek_id = Column(Integer, ForeignKey("ornekler.id"))
    # ornek = relationship("Ornek", back_populates="{tablo_adi}")
```

**Kurallar:**
- Tablo ve alan adları `snake_case`
- SQLite'a özgü tipler kullanma (`AUTOINCREMENT` vb.) — PostgreSQL uyumlu kal
- Çok dilli model gerekiyorsa `{ModelAdi}Translation` sınıfını da ekle

---

## Adım 4 — Migration Ekle

`app/main.py` içindeki migration bloğuna şunu ekle:

```python
# {ModelAdi} tablosu için migration — {tarih}
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE {tablo_adi} ADD COLUMN {yeni_alan} {tip}"))
        conn.commit()
except Exception:
    pass  # Kolon zaten varsa atla
```

---

## Adım 5 — Özet Rapor

```
✅ TAMAMLANDI
─────────────────────────────
Model              : SupplierInvoice
Tablo              : supplier_invoices
Değişen dosyalar   : app/models.py, app/main.py
Sonraki adım       : Bu model için route eklemek ister misin? (/yeni-route)
─────────────────────────────
```