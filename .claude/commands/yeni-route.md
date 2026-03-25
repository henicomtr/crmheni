# Yeni Route / Endpoint Ekle

Bu komutu çalıştırdığında aşağıdaki adımları sırayla uygula. **Her adımda onay al, sonrakine geçme.**

---

## Adım 1 — Endpoint Bilgilerini Topla

Kullanıcıya şunları sor:
1. Endpoint ne iş yapacak? (kısa açıklama)
2. HTTP metodu nedir? (GET / POST / PUT / DELETE)
3. URL path'i nedir? (ör: `/admin/products/{id}/duplicate`)
4. Admin paneli mi, showroom mu? (`routes_admin.py` mi, `routes_showroom.py` mi?)
5. Veritabanı işlemi var mı? Hangi tablo(lar)?
6. Çok dilli içerik (translations) gerekiyor mu?
7. Response tipi nedir? (Jinja2 template mi, JSON mu, redirect mi?)

---

## Adım 2 — Plan Sun

Kod yazmadan önce şu formatı kullan:

```
📋 PLAN
─────────────────────────────
Eklenecek fonksiyon : create_product_duplicate()
Dosya               : app/routes_admin.py
Etkilenen tablolar  : products, product_translations
Yan etkiler         : Yok
Tahmini satır sayısı: ~40 satır
─────────────────────────────
Onaylıyor musun?
```

---

## Adım 3 — Kodu Yaz

Onay alındıktan sonra şu şablonu kullan:

```python
@router.{metod}("{path}")
async def {fonksiyon_adi}(
    # gerekli parametreler
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin)  # admin route ise
):
    """
    {Ne yaptığını Türkçe açıkla}
    """
    # İş mantığı buraya
    pass
```

**Kurallar:**
- Fonksiyon adı fiil ile başlamalı: `get_`, `create_`, `update_`, `delete_`
- Tüm yorumlar Türkçe
- Hata durumları `HTTPException` ile yönetilmeli
- Admin route'larında mutlaka JWT kontrolü olmalı

---

## Adım 4 — Özet Rapor

Kod bittikten sonra şunu yaz:

```
✅ TAMAMLANDI
─────────────────────────────
Eklenen fonksiyon : create_product_duplicate()
Dosya             : app/routes_admin.py
Test et           : POST /admin/products/5/duplicate
Dikkat            : translations tablosunu da kopyalar
─────────────────────────────
```