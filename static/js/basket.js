document.addEventListener("DOMContentLoaded", function () {

    const CONTAINER_20 = 13;
    const CONTAINER_40 = 24;

    const UI    = (typeof window.BASKET_UI !== 'undefined') ? window.BASKET_UI : {};
    const lang  = UI.lang   || 'en';
    const rates = UI.rates  || { USD_TRY: 43.5, EUR_TRY: 47.0, EUR_USD: 1.08 };

    // ── İndirim hesabı (backend ile birebir) ─────────────
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

    // ── Her ürün satırı: canlı hesaplama ─────────────────
    document.querySelectorAll('.basket-item').forEach(item => {

        const piecesPerBox   = parseInt(item.dataset.piecesPerBox)   || 1;
        const boxesPerPallet = parseInt(item.dataset.boxesPerPallet) || 1;
        const originalPrice  = parseFloat(item.dataset.originalPrice) || 0;

        const qtyInput      = item.querySelector('[data-type="quantity"]');
        const boxesInput    = item.querySelector('[data-type="boxes"]');
        const palletsInput  = item.querySelector('[data-type="pallets"]');
        const totalPriceEl  = item.querySelector('.item-total-price');
        const unitPriceEl   = item.querySelector('.item-unit-price');
        const oldPriceEl    = item.querySelector('.item-old-price');
        const discTagEl     = item.querySelector('.discount-tag');
        const hiddenQty     = item.querySelector('.update-qty-hidden');

        function refreshRow() {
            const qty = Math.max(parseInt(qtyInput.value) || 0, 0);

            const boxes   = Math.floor(qty / piecesPerBox);
            const pallets = boxes / boxesPerPallet;

            if (boxesInput)   boxesInput.value   = boxes;
            if (palletsInput) palletsInput.value = pallets.toFixed(2);

            // İndirim hesapla
            const rate      = getDiscountRate(pallets);
            const unitPrice = originalPrice * (1 - rate);

            // Fiyat gösterimi
            if (unitPriceEl) {
                const parts = unitPriceEl.textContent.split('/');
                const suffix = parts.length > 1 ? ' / ' + parts.slice(1).join('/').trim() : '';
                unitPriceEl.textContent = formatCurrency(unitPrice) + suffix;
            }

            if (oldPriceEl) {
                if (rate > 0) {
                    oldPriceEl.style.display = 'inline';
                    oldPriceEl.textContent   = formatCurrency(originalPrice);
                } else {
                    oldPriceEl.style.display = 'none';
                }
            }

            if (discTagEl) {
                if (rate > 0) {
                    discTagEl.style.display  = 'inline';
                    discTagEl.textContent    = `−%${Math.round(rate * 100)}`;
                } else {
                    discTagEl.style.display  = 'none';
                }
            }

            // Satır toplam
            const rowTotal = qty * unitPrice;
            if (totalPriceEl) totalPriceEl.textContent = formatCurrency(rowTotal);

            // Güncelle formuna qty yaz (sunucuya gönderim için)
            if (hiddenQty) hiddenQty.value = qty;

            // data-unit-price'ı güncelle (recalculate için)
            item.dataset.unitPrice = unitPrice;

            recalculateTotals();
        }

        // Adet değişince otomatik güncelle
        let debounceTimer;
        function onQtyChange() {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                refreshRow();
                // Sunucuya otomatik POST et (form submit)
                const updateForm = item.querySelector('.update-form');
                if (updateForm) updateForm.submit();
            }, 800); // 800ms bekleme — kullanıcı yazmayı bitirince gönder
        }

        if (qtyInput) {
            qtyInput.addEventListener('change', onQtyChange);
            qtyInput.addEventListener('input',  refreshRow);  // anlık görsel güncelleme
        }
    });

    // ── Tüm sepet toplamı + lojistik ─────────────────────
    function recalculateTotals() {

        let totalPrice   = 0;
        let totalBoxes   = 0;
        let totalPallets = 0;

        document.querySelectorAll('.basket-item').forEach(item => {
            const originalPrice  = parseFloat(item.dataset.originalPrice) || 0;
            const piecesPerBox   = parseInt(item.dataset.piecesPerBox)    || 1;
            const boxesPerPallet = parseInt(item.dataset.boxesPerPallet)  || 1;

            const qtyInput = item.querySelector('[data-type="quantity"]');
            const qty      = Math.max(parseInt(qtyInput?.value) || 0, 0);

            const boxes   = Math.floor(qty / piecesPerBox);
            const pallets = boxes / boxesPerPallet;
            const rate    = getDiscountRate(pallets);
            const unit    = originalPrice * (1 - rate);

            totalPrice   += qty * unit;
            totalBoxes   += boxes;
            totalPallets += pallets;
        });

        // Footer toplam
        const totalEl = document.getElementById('basket-total');
        if (totalEl) totalEl.textContent = formatCurrency(totalPrice);

        // Lojistik sayaçları
        setText('total-boxes',   totalBoxes);
        setText('total-pallets', totalPallets.toFixed(2));

        // Doluluk oranları
        const pct20 = Math.min((totalPallets / CONTAINER_20) * 100, 100);
        const pct40 = Math.min((totalPallets / CONTAINER_40) * 100, 100);

        setFill('progress-fill-20', pct20);
        setFill('progress-fill-40', pct40);
        setText('percent-20', pct20.toFixed(1) + '%');
        setText('percent-40', pct40.toFixed(1) + '%');

        // Kalan palet
        const rem20El = document.querySelector('[id^="remaining-pallets-20"], [id="remaining_pallets_20"]') 
                      || document.querySelectorAll('.logistics-row span')[7];
        const rem40El = document.querySelector('[id^="remaining-pallets-40"], [id="remaining_pallets_40"]')
                      || document.querySelectorAll('.logistics-row span')[9];
        
        // HTML'deki statik kalan palet alanlarını güncelle
        const logRows = document.querySelectorAll('.logistics-row');
        logRows.forEach(row => {
            const spans = row.querySelectorAll('span');
            if (spans.length >= 2) {
                const label = spans[0].textContent || '';
                if (label.includes('20FT') && label.includes('kalan')) {
                    spans[1].textContent = Math.max(CONTAINER_20 - totalPallets, 0).toFixed(1);
                }
                if (label.includes('40FT') && label.includes('kalan')) {
                    spans[1].textContent = Math.max(CONTAINER_40 - totalPallets, 0).toFixed(1);
                }
            }
        });

        // Önerilen konteyner
        const recEl = document.getElementById('recommended-container');
        if (recEl) {
            if (totalPallets === 0)               recEl.textContent = '—';
            else if (totalPallets <= CONTAINER_20) recEl.textContent = '20FT';
            else if (totalPallets <= CONTAINER_40) recEl.textContent = '40FT';
            else                                   recEl.textContent = 'MULTI';
        }
    }

    function setText(id, val) {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    }

    function setFill(id, pct) {
        const el = document.getElementById(id);
        if (el) el.style.width = pct.toFixed(1) + '%';
    }

    // İlk yüklemede hesapla
    recalculateTotals();
});