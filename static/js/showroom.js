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

    // Dile göre indirim mesajı
    function getDiscountMessage(pallets, piecesPerBox, boxesPerPallet) {
        const unitsPerPallet = piecesPerBox * boxesPerPallet;

        function unitsToNext(targetPallets) {
            return Math.ceil((targetPallets - pallets) * unitsPerPallet);
        }

        // Her dil için mesaj şablonları
        const msgs = {
            en: {
                to5:   (n) => `Add ${n} more for 5% discount`,
                at5:   (n) => `5% discount active · Add ${n} more for 7%`,
                at7:   (n) => `7% discount active · Add ${n} more for 9%`,
                at9:   (n) => `9% discount active · Add ${n} more for 12%`,
                max:       `12% discount active — maximum reached`,
            },
            tr: {
                to5:   (n) => `%5 indirim için ${n} adet daha ekleyin`,
                at5:   (n) => `%5 indirim aktif · %7 için ${n} adet daha ekleyin`,
                at7:   (n) => `%7 indirim aktif · %9 için ${n} adet daha ekleyin`,
                at9:   (n) => `%9 indirim aktif · %12 için ${n} adet daha ekleyin`,
                max:       `%12 indirim aktif — maksimum indirime ulaştınız`,
            },
            de: {
                to5:   (n) => `${n} mehr hinzufügen für 5% Rabatt`,
                at5:   (n) => `5% Rabatt aktiv · ${n} mehr für 7%`,
                at7:   (n) => `7% Rabatt aktiv · ${n} mehr für 9%`,
                at9:   (n) => `9% Rabatt aktiv · ${n} mehr für 12%`,
                max:       `12% Rabatt aktiv — Maximum erreicht`,
            },
            fr: {
                to5:   (n) => `Ajoutez ${n} de plus pour 5% de remise`,
                at5:   (n) => `Remise 5% active · ${n} de plus pour 7%`,
                at7:   (n) => `Remise 7% active · ${n} de plus pour 9%`,
                at9:   (n) => `Remise 9% active · ${n} de plus pour 12%`,
                max:       `Remise 12% active — maximum atteint`,
            },
            ar: {
                to5:   (n) => `أضف ${n} المزيد للحصول على خصم 5%`,
                at5:   (n) => `خصم 5% نشط · أضف ${n} للحصول على 7%`,
                at7:   (n) => `خصم 7% نشط · أضف ${n} للحصول على 9%`,
                at9:   (n) => `خصم 9% نشط · أضف ${n} للحصول على 12%`,
                max:       `خصم 12% نشط — تم الوصول إلى الحد الأقصى`,
            },
            ru: {
                to5:   (n) => `Добавьте ещё ${n} для скидки 5%`,
                at5:   (n) => `Скидка 5% активна · Добавьте ${n} для 7%`,
                at7:   (n) => `Скидка 7% активна · Добавьте ${n} для 9%`,
                at9:   (n) => `Скидка 9% активна · Добавьте ${n} для 12%`,
                max:       `Скидка 12% активна — достигнут максимум`,
            },
            es: {
                to5:   (n) => `Añade ${n} más para un 5% de descuento`,
                at5:   (n) => `Descuento 5% activo · Añade ${n} para 7%`,
                at7:   (n) => `Descuento 7% activo · Añade ${n} para 9%`,
                at9:   (n) => `Descuento 9% activo · Añade ${n} para 12%`,
                max:       `Descuento 12% activo — máximo alcanzado`,
            },
        };

        const m = msgs[lang] || msgs['en'];

        if (pallets < 2)  return m.to5(unitsToNext(2));
        if (pallets < 4)  return m.at5(unitsToNext(4));
        if (pallets < 6)  return m.at7(unitsToNext(6));
        if (pallets < 9)  return m.at9(unitsToNext(9));
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

            const pallets  = getPallets(qty);
            const rate     = getDiscountRate(pallets);
            const discPrice = basePrice * (1 - rate);

            // Hem showroom hem de detail sayfası için container'ı bul
            const card       = control.closest('.product-card') || control.closest('.detail-info') || document;
            // Hem showroom hem de detail sayfası için fiyat elementlerini bul
            const newPriceEl = card.querySelector('.new-price') || card.querySelector('.detail-price');
            const oldPriceEl = card.querySelector('.old-price') || card.querySelector('.detail-old-price');

            if (newPriceEl) newPriceEl.textContent = formatPrice(discPrice);

            if (oldPriceEl) {
                if (rate > 0) {
                    oldPriceEl.style.display = 'inline';
                    oldPriceEl.textContent   = formatPrice(basePrice);
                } else {
                    oldPriceEl.style.display = 'none';
                }
            }

            if (msgBox) {
                msgBox.textContent = getDiscountMessage(pallets, piecesPerBox, boxesPerPallet);
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

    // ── Sepet rozeti ─────────────────────────────────────
    const badge    = document.getElementById('basket-badge');
    const inBasket = document.querySelectorAll('.in-basket-info').length;
    if (badge) {
        if (inBasket > 0) {
            badge.textContent = inBasket;
            badge.style.display = 'inline-flex';
        } else {
            badge.style.display = 'none';
        }
    }
});