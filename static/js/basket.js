document.addEventListener("DOMContentLoaded", function () {

    const CONTAINER_20 = 13;
    const CONTAINER_40 = 24;

    const UI    = (typeof window.BASKET_UI !== 'undefined') ? window.BASKET_UI : {};
    const lang  = UI.lang   || 'en';
    const rates = UI.rates  || { USD_TRY: 43.5, EUR_TRY: 47.0, EUR_USD: 1.08 };

    // ── İndirim hesabı ────────────────────────────────────
    function getDiscountRate(pallets) {
        if (pallets >= 9) return 0.12;
        if (pallets >= 6) return 0.09;
        if (pallets >= 4) return 0.07;
        if (pallets >= 2) return 0.05;
        return 0;
    }

    // USD fiyatını dile göre formatla
    function formatCurrency(usd) {
        if (lang === 'tr') {
            const val = usd * (rates.USD_TRY || 43.5);
            return val.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₺';
        } else if (lang === 'de' || lang === 'fr') {
            const val = usd / (rates.EUR_USD || 1.08);
            return val.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
        } else {
            return '$' + usd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }
    }

    // ── Tek bir basket-item satırını güncelle ─────────────
    function refreshItem(item) {
        var piecesPerBox   = parseInt(item.getAttribute('data-pieces-per-box'))   || 1;
        var boxesPerPallet = parseInt(item.getAttribute('data-boxes-per-pallet')) || 1;
        var originalPrice  = parseFloat(item.getAttribute('data-original-price')) || 0;

        var palletsInput = item.querySelector('[data-type="pallets"]');
        var qtyInput     = item.querySelector('[data-type="quantity"]');
        var boxesInput   = item.querySelector('[data-type="boxes"]');
        var totalPriceEl = item.querySelector('.item-total-price');
        var unitPriceEl  = item.querySelector('.item-unit-price');
        var oldPriceEl   = item.querySelector('.item-old-price');
        var discTagEl    = item.querySelector('.discount-tag');
        var hiddenQty    = item.querySelector('.update-qty-hidden');

        if (!palletsInput) return;

        // Palet girişinden tam sayı hesapla (min 1)
        var pallets = parseInt(palletsInput.value, 10);
        if (!pallets || pallets < 1) pallets = 1;

        var qty   = pallets * boxesPerPallet * piecesPerBox;
        var boxes = pallets * boxesPerPallet;

        // Readonly alanları güncelle
        if (qtyInput)   qtyInput.value  = qty;
        if (boxesInput) boxesInput.value = boxes;

        // Sunucuya gönderilecek gizli qty alanını güncelle
        if (hiddenQty) hiddenQty.value = qty;

        // İndirim hesapla
        var rate      = getDiscountRate(pallets);
        var unitPrice = originalPrice * (1 - rate);

        // Birim fiyat güncelle
        if (unitPriceEl) {
            var parts  = unitPriceEl.textContent.split('/');
            var suffix = parts.length > 1 ? ' / ' + parts.slice(1).join('/').trim() : '';
            unitPriceEl.textContent = formatCurrency(unitPrice) + suffix;
        }

        // Eski fiyat (indirimli gösterim)
        if (oldPriceEl) {
            if (rate > 0) {
                oldPriceEl.style.display = 'inline';
                oldPriceEl.textContent   = formatCurrency(originalPrice);
            } else {
                oldPriceEl.style.display = 'none';
            }
        }

        // İndirim etiketi
        if (discTagEl) {
            if (rate > 0) {
                discTagEl.style.display = 'inline';
                discTagEl.textContent   = '-' + Math.round(rate * 100) + '%';
            } else {
                discTagEl.style.display = 'none';
            }
        }

        // Satır toplamı
        if (totalPriceEl) {
            totalPriceEl.textContent = formatCurrency(qty * unitPrice);
        }
    }

    // ── Tüm sepet toplamı + lojistik simülasyonu ──────────
    function recalculateTotals() {
        var totalPrice   = 0;
        var totalBoxes   = 0;
        var totalPallets = 0;

        var items = document.querySelectorAll('.basket-item');
        for (var i = 0; i < items.length; i++) {
            var item = items[i];
            var piecesPerBox   = parseInt(item.getAttribute('data-pieces-per-box'))   || 1;
            var boxesPerPallet = parseInt(item.getAttribute('data-boxes-per-pallet')) || 1;
            var originalPrice  = parseFloat(item.getAttribute('data-original-price')) || 0;

            var palletsInput = item.querySelector('[data-type="pallets"]');
            if (!palletsInput) continue;

            var pallets = parseInt(palletsInput.value, 10);
            if (!pallets || pallets < 1) pallets = 1;

            var qty  = pallets * boxesPerPallet * piecesPerBox;
            var rate = getDiscountRate(pallets);
            var unit = originalPrice * (1 - rate);

            totalPrice   += qty * unit;
            totalBoxes   += pallets * boxesPerPallet;
            totalPallets += pallets;
        }

        // Sepet toplamı
        var totalEl = document.getElementById('basket-total');
        if (totalEl) totalEl.textContent = formatCurrency(totalPrice);

        // Lojistik sayaçları
        var boxesEl = document.getElementById('total-boxes');
        if (boxesEl) boxesEl.textContent = totalBoxes;

        var palletsEl = document.getElementById('total-pallets');
        if (palletsEl) palletsEl.textContent = totalPallets.toFixed(2);

        // Doluluk oranları
        var pct20 = Math.min((totalPallets / CONTAINER_20) * 100, 100);
        var pct40 = Math.min((totalPallets / CONTAINER_40) * 100, 100);

        var fill20 = document.getElementById('progress-fill-20');
        if (fill20) fill20.style.width = pct20.toFixed(1) + '%';
        var fill40 = document.getElementById('progress-fill-40');
        if (fill40) fill40.style.width = pct40.toFixed(1) + '%';

        var pct20El = document.getElementById('percent-20');
        if (pct20El) pct20El.textContent = pct20.toFixed(1) + '%';
        var pct40El = document.getElementById('percent-40');
        if (pct40El) pct40El.textContent = pct40.toFixed(1) + '%';

        // Kalan palet alanlarını güncelle (label metni içinde "kalan" geçenleri bul)
        var logRows = document.querySelectorAll('.logistics-row');
        for (var j = 0; j < logRows.length; j++) {
            var spans = logRows[j].querySelectorAll('span');
            if (spans.length >= 2) {
                var label = spans[0].textContent || '';
                if (label.indexOf('20FT') !== -1 && label.indexOf('kalan') !== -1) {
                    spans[1].textContent = Math.max(CONTAINER_20 - totalPallets, 0).toFixed(1);
                }
                if (label.indexOf('40FT') !== -1 && label.indexOf('kalan') !== -1) {
                    spans[1].textContent = Math.max(CONTAINER_40 - totalPallets, 0).toFixed(1);
                }
            }
        }

        // Önerilen konteyner
        var recEl = document.getElementById('recommended-container');
        if (recEl) {
            if (totalPallets === 0)                recEl.textContent = '—';
            else if (totalPallets <= CONTAINER_20) recEl.textContent = '20FT';
            else if (totalPallets <= CONTAINER_40) recEl.textContent = '40FT';
            else                                   recEl.textContent = 'MULTI';
        }
    }

    // ── Event delegation: tüm palet input değişikliklerini yakala ──
    var saveTimers = {};

    document.addEventListener('input', function (e) {
        var target = e.target;
        if (!target || target.getAttribute('data-type') !== 'pallets') return;

        var item = target.closest('.basket-item');
        if (!item) return;

        // Satırı güncelle
        refreshItem(item);

        // Toplam ve lojistiği güncelle
        recalculateTotals();

        // Sunucuya debounce ile gönder
        var productId = item.getAttribute('data-product-id') || '';
        clearTimeout(saveTimers[productId]);
        saveTimers[productId] = setTimeout(function () {
            var updateForm = item.querySelector('.update-form');
            if (updateForm) updateForm.submit();
        }, 800);
    });

    // ── İlk yüklemede tüm satırları ve toplamı hesapla ───
    var allItems = document.querySelectorAll('.basket-item');
    for (var k = 0; k < allItems.length; k++) {
        refreshItem(allItems[k]);
    }
    recalculateTotals();
});
