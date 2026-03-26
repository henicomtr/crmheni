document.addEventListener("DOMContentLoaded", function () {

    // ── UI metinleri (template'den gelir) ────────────────
    const UI    = (typeof window.SHOWROOM_UI !== 'undefined') ? window.SHOWROOM_UI : {};
    const lang  = UI.lang   || 'en';
    const rates = UI.rates  || { USD_TRY: 43.5, EUR_TRY: 47.0, EUR_USD: 1.08 };

    // USD cinsinden fiyatı dile göre formatla
    function formatPrice(usd) {
        if (lang === 'tr') {
            const try_ = usd * (rates.USD_TRY || 43.5);
            return try_.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₺';
        } else if (lang === 'de' || lang === 'fr' || lang === 'ru' || lang === 'es') {
            const eur = usd / (rates.EUR_USD || 1.08);
            return eur.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
        } else {
            return '$' + usd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }
    }

    // ── İndirim Kademeleri ───────────────────────────────
    function getDiscountRate(pallets) {
        if (pallets >= 9) return 0.12;
        if (pallets >= 6) return 0.09;
        if (pallets >= 4) return 0.07;
        if (pallets >= 2) return 0.05;
        return 0;
    }

    // Sadece bir sonraki indirim kademesi için teşvik mesajı
    // Aktif indirim mesajda gösterilmez — rozette görünür
    function getDiscountMessage(pallets, piecesPerBox, boxesPerPallet) {
        const unitsPerPallet = piecesPerBox * boxesPerPallet;

        function unitsToNext(targetPallets) {
            return Math.ceil((targetPallets - pallets) * unitsPerPallet);
        }

        // Her dil için mesaj şablonları — sadece bir sonraki hedef
        const msgs = {
            en: {
                to5:  (n) => `Add ${n} more for 5% discount`,
                to7:  (n) => `Add ${n} more for 7% discount`,
                to9:  (n) => `Add ${n} more for 9% discount`,
                to12: (n) => `Add ${n} more for 12% discount`,
                max:       ``,
            },
            tr: {
                to5:  (n) => `%5 indirim için ${n} adet daha ekleyin`,
                to7:  (n) => `%7 indirim için ${n} adet daha ekleyin`,
                to9:  (n) => `%9 indirim için ${n} adet daha ekleyin`,
                to12: (n) => `%12 indirim için ${n} adet daha ekleyin`,
                max:       ``,
            },
            de: {
                to5:  (n) => `${n} mehr hinzufügen für 5% Rabatt`,
                to7:  (n) => `${n} mehr hinzufügen für 7% Rabatt`,
                to9:  (n) => `${n} mehr hinzufügen für 9% Rabatt`,
                to12: (n) => `${n} mehr hinzufügen für 12% Rabatt`,
                max:       ``,
            },
            fr: {
                to5:  (n) => `Ajoutez ${n} de plus pour 5% de remise`,
                to7:  (n) => `Ajoutez ${n} de plus pour 7% de remise`,
                to9:  (n) => `Ajoutez ${n} de plus pour 9% de remise`,
                to12: (n) => `Ajoutez ${n} de plus pour 12% de remise`,
                max:       ``,
            },
            ar: {
                to5:  (n) => `أضف ${n} المزيد للحصول على خصم 5%`,
                to7:  (n) => `أضف ${n} المزيد للحصول على خصم 7%`,
                to9:  (n) => `أضف ${n} المزيد للحصول على خصم 9%`,
                to12: (n) => `أضف ${n} المزيد للحصول على خصم 12%`,
                max:       ``,
            },
            ru: {
                to5:  (n) => `Добавьте ещё ${n} для скидки 5%`,
                to7:  (n) => `Добавьте ещё ${n} для скидки 7%`,
                to9:  (n) => `Добавьте ещё ${n} для скидки 9%`,
                to12: (n) => `Добавьте ещё ${n} для скидки 12%`,
                max:       ``,
            },
            es: {
                to5:  (n) => `Añade ${n} más para un 5% de descuento`,
                to7:  (n) => `Añade ${n} más para un 7% de descuento`,
                to9:  (n) => `Añade ${n} más para un 9% de descuento`,
                to12: (n) => `Añade ${n} más para un 12% de descuento`,
                max:       ``,
            },
        };

        const m = msgs[lang] || msgs['en'];

        if (pallets < 2)  return m.to5(unitsToNext(2));
        if (pallets < 4)  return m.to7(unitsToNext(4));
        if (pallets < 6)  return m.to9(unitsToNext(6));
        if (pallets < 9)  return m.to12(unitsToNext(9));
        return m.max;
    }

    // ── Form Döngüsü ─────────────────────────────────────
    document.querySelectorAll('.quantity-control').forEach(control => {

        const form = control.closest('form');
        const plusBtn  = control.querySelector('.plus');
        const minusBtn = control.querySelector('.minus');
        const input    = control.querySelector('.quantity-input');
        const msgBox   = form ? form.querySelector('.message-box') : null;

        if (!input) return;

        const basePrice    = parseFloat(input.dataset.price)     || 0;
        const minQty       = parseInt(input.dataset.min)         || 1;
        const increment    = parseInt(input.dataset.increment)   || 1;
        const piecesPerBox = parseInt(input.dataset.box)         || 1;
        const boxesPerPallet = parseInt(input.dataset.palletBox) || 1;

        function getPallets(qty) {
            return (qty / piecesPerBox) / boxesPerPallet;
        }

        function updateUI() {
            let qty = parseInt(input.value) || minQty;
            if (qty < minQty) { qty = minQty; input.value = qty; }

            const pallets   = getPallets(qty);
            const rate      = getDiscountRate(pallets);
            const discPrice = basePrice * (1 - rate);

            // Hem showroom hem de detail sayfası için container'ı bul
            const card       = control.closest('.product-card') || control.closest('.detail-info') || document;
            const newPriceEl = card.querySelector('.new-price') || card.querySelector('.detail-price');
            const oldPriceEl = card.querySelector('.old-price') || card.querySelector('.detail-old-price');

            // Fiyat verisi varsa fiyat alanını güncelle
            if (basePrice > 0) {
                if (newPriceEl) newPriceEl.textContent = formatPrice(discPrice);
                if (oldPriceEl) {
                    if (rate > 0) {
                        oldPriceEl.style.display = 'inline';
                        oldPriceEl.textContent   = formatPrice(basePrice);
                    } else {
                        oldPriceEl.style.display = 'none';
                    }
                }
            }

            // Aktif indirim rozetini sağ üst köşede güncelle (showroom ve detail sayfası)
            const imgDiv = card.querySelector('.product-image') || document.querySelector('.detail-image-wrap');
            if (imgDiv) {
                let overlay = imgDiv.querySelector('.card-disc-overlay');
                if (rate > 0) {
                    if (!overlay) {
                        // Rozet yoksa oluştur
                        overlay = document.createElement('div');
                        overlay.className = 'card-disc-overlay';
                        imgDiv.appendChild(overlay);
                    }
                    overlay.textContent = `-${Math.round(rate * 100)}%`;
                    overlay.style.display = 'flex';
                } else if (overlay) {
                    // İndirim yoksa rozeti gizle
                    overlay.style.display = 'none';
                }
            }

            // Mesaj kutusunu güncelle — sadece bir sonraki hedef
            if (msgBox) {
                const msg = getDiscountMessage(pallets, piecesPerBox, boxesPerPallet);
                msgBox.textContent = msg;
                msgBox.classList.remove('discount-hint', 'discount-active', 'discount-max');
                if (pallets >= 9) {
                    // Maksimum indirimde mesaj kutusu gizlenir
                    msgBox.style.display = 'none';
                } else if (pallets >= 2) {
                    msgBox.style.display = '';
                    msgBox.classList.add('discount-hint');
                } else {
                    msgBox.style.display = '';
                    msgBox.classList.add('discount-hint');
                }
            }
        }

        if (plusBtn) {
            plusBtn.addEventListener('click', () => {
                input.value = parseInt(input.value) + increment;
                updateUI();
            });
        }

        if (minusBtn) {
            minusBtn.addEventListener('click', () => {
                const cur = parseInt(input.value);
                if (cur - increment >= minQty) {
                    input.value = cur - increment;
                    updateUI();
                }
            });
        }

        input.addEventListener('change', () => {
            let qty = parseInt(input.value) || minQty;
            if (qty < minQty) {
                qty = minQty;
            } else {
                const rem = (qty - minQty) % increment;
                if (rem) qty -= rem;
            }
            input.value = qty;
            updateUI();
        });

        updateUI();
    });

    // ── Sepet Rozeti Güncelleme (yardımcı fonksiyon) ─────
    function updateBasketBadge(count) {
        const badge = document.getElementById('basket-badge');
        if (!badge) return;
        if (count > 0) {
            badge.textContent = count;
            badge.style.display = 'inline-flex';
        } else {
            badge.style.display = 'none';
        }
    }

    // ── Sepet rozeti referansı (AJAX güncellemeleri için) ─
    // Sayfa yükünde badge'i server-render edilmiş değeriyle bırak;
    // sadece AJAX işlemleri sonrası updateBasketBadge() çağrılır.
    const badge = document.getElementById('basket-badge');

    // ── Sepete Ekle — AJAX ile sayfa yenilemeden işle ────
    document.querySelectorAll('.card-form').forEach(form => {
        form.addEventListener('submit', function (e) {
            e.preventDefault();

            const formData = new FormData(form);
            const btn = form.querySelector('.add-to-cart-btn');

            // Butonu geçici olarak devre dışı bırak
            if (btn) btn.disabled = true;

            fetch(form.action, {
                method: 'POST',
                body: formData,
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin',
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    updateBasketBadge(data.cart_count);

                    // Sepet miktarını input'a yansıt — sepet-kart entegrasyonu
                    const qtyInput = form.querySelector('.quantity-input');
                    if (qtyInput && data.qty !== undefined) {
                        qtyInput.dataset.cartQty = data.qty;
                    }

                    // Kısa başarı geri bildirimi — buton metni geçici değişir
                    if (btn) {
                        const origText = btn.textContent;
                        btn.textContent = '✓';
                        btn.style.background = 'linear-gradient(135deg, #16a34a 0%, #15803d 100%)';
                        setTimeout(() => {
                            btn.textContent = origText;
                            btn.style.background = '';
                            btn.disabled = false;
                        }, 1200);
                    }
                }
            })
            .catch(() => {
                // Hata durumunda normal form submit yap
                if (btn) btn.disabled = false;
                form.submit();
            });
        });
    });
});
