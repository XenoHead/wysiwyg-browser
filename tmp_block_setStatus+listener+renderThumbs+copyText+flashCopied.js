    };

    window.runDiscogsAdd = async function () {
        if (!selectedFiles.length) {
            setStatus('Add at least one scanned image first.', 'err');
            return;
        }
        buildBtn.disabled = true;
        setStatus('Extracting data from images (Gemini)...');
        results.innerHTML = '';
        const url = API_BASE + '/api/adds/discogs';
        console.log('Discogs add -> POST', url, 'images:', selectedFiles.length);
        try {
            const fd = new FormData();
            selectedFiles.forEach(f => fd.append('images', f, f.name));
            const resp = await fetch(url, { method: 'POST', body: fd });
            console.log('Discogs add <- status', resp.status, resp.statusText);
            const data = await resp.json();
            console.log('Discogs add <- body', data);
            if (data.status === 'success') {
                const tables = data.tables || {};
                if (data.phase === 'ocr_only') {
                    // Phase 1: just show the raw OCR text for verification.
                    results.innerHTML = '';
                    const h = document.createElement('div');
                    h.className = 'section-title';
                    h.textContent = 'Raw Extraction (verify OCR text)';
                    results.appendChild(h);
                    const ta = document.createElement('textarea');
                    ta.className = 'field-val';
                    ta.style.height = '320px';
                    ta.value = (data.extracted && (data.extracted.raw_text || JSON.stringify(data.extracted, null, 2))) || '';
                    results.appendChild(ta);
                    setStatus('OCR captured. Verify the text below, then we enable table-building.', 'ok');
                } else {
                    renderTables(tables);
                    const n = Object.keys(tables).length;
                    const totalRows = Object.values(tables).reduce((a, r) => a + (Array.isArray(r) ? r.length : 0), 0);
                    if (n === 0 || totalRows === 0) {
                        setStatus('Gemini responded but produced no table data. Try again or check the images.', 'err');
                    } else {
                        setStatus('Built ' + n + ' tables (' + totalRows + ' rows).', 'ok');
                    }
                }
            } else {
                setStatus('Error: ' + (data.message || 'Unknown error'), 'err');