
(function () {
    const API_BASE = '';
    const imgInput = document.getElementById('imgInput');
    const thumbList = document.getElementById('thumbList');
    const statusEl = document.getElementById('status');
    const results = document.getElementById('results');
    const buildBtn = document.getElementById('buildBtn');
    let lastText = '';

    // Theme from localStorage if present.
    try {
        const t = localStorage.getItem('wysiwyg_theme');
        if (t === 'dark') document.body.classList.add('dark');
    } catch (e) {}

    function setStatus(msg, kind) {
        statusEl.textContent = msg || '';
        statusEl.className = 'status' + (kind ? ' ' + kind : '');
    }

    // Track selected File objects.
    let selectedFiles = [];
    imgInput.addEventListener('change', () => {
        for (const f of imgInput.files) {
            if (selectedFiles.length >= 8) {
                setStatus('Maximum of 8 images reached.', 'err');
                break;
            }
            selectedFiles.push(f);
        }
        renderThumbs();
        imgInput.value = '';
    });

    function renderThumbs() {
        thumbList.innerHTML = '';
        selectedFiles.forEach((f, i) => {
            const div = document.createElement('div');
            div.className = 'thumb';
            const url = URL.createObjectURL(f);
            const img = document.createElement('img');
            img.src = url;
            const rm = document.createElement('button');
            rm.className = 'rm';
            rm.textContent = '✕';
            rm.onclick = () => { URL.revokeObjectURL(url); selectedFiles.splice(i, 1); renderThumbs(); };
            div.appendChild(img); div.appendChild(rm);
            thumbList.appendChild(div);
        });
        document.getElementById('imgCount').textContent = selectedFiles.length;
    }

    async function copyText(text) {
        try { await navigator.clipboard.writeText(text); }
        catch (e) { /* ignore */ }
    }
    function flashCopied(btn) {
        const old = btn.textContent;
        btn.textContent = '✓';
        setTimeout(() => { btn.textContent = old; }, 900);
    }

    // Render the 8 tables as sections with per-field rows + Copy buttons.
    function renderTables(tables) {
        results.innerHTML = '';
        const sectionOrder = Object.keys(tables);
        for (const title of sectionOrder) {
            const rows = tables[title] || [];
            const h = document.createElement('div');
            h.className = 'section-title';
            h.textContent = title;
            results.appendChild(h);
            for (const row of rows) {
                // Tracklist rows are objects {Track, Title, Time}
                if (row && typeof row === 'object' && !Array.isArray(row)) {
                    const track = row.Track || '';
                    let title = (row.Title || '').replace(/\*\*(.+?)\*\*/g, '$1');
                    const time = row.Time || '';
                    const r = document.createElement('div');
                    r.className = 'field-row';
                    const lbl = document.createElement('div');
                    lbl.className = 'field-label';
                    lbl.textContent = (title && title.startsWith('**')) ? 'Section' : (track ? 'Track ' + track : '');
                    const val = document.createElement('textarea');
                    val.className = 'field-val';
                    val.value = title + (time ? '  [' + time + ']' : '');
                    val.rows = 1;
                    r.appendChild(lbl); r.appendChild(val);
                    if (String(title).trim()) {
                        const btn = document.createElement('button');
                        btn.className = 'copy-one';
                        btn.textContent = 'Copy';
                        btn.onclick = async () => { await copyText(val.value); flashCopied(btn); };
                        r.appendChild(btn);
                    }
                    results.appendChild(r);
                    continue;
                }
                if (!Array.isArray(row) || row.length < 2) continue;
                const label = row[0];
                const value = row[1];
                if (value === '-' && label === '-') {
                    // visual separator row
                    const sep = document.createElement('div');
                    sep.style.height = '6px';
                    results.appendChild(sep);
                    continue;
                }
                // Header rows (Item/Value, Role/Artist) render as a styled header.
                if ((label === 'Item' && value === 'Value') || (label === 'Role' && value === 'Artist')) {
                    const hd = document.createElement('div');
                    hd.style.cssText = 'font-size:11px;font-weight:700;color:var(--muted);margin:2px 0 4px;text-transform:uppercase;letter-spacing:0.03em;';
                    hd.textContent = label + ' / ' + value;
                    results.appendChild(hd);
                    continue;
                }
                const r = document.createElement('div');
                r.className = 'field-row';
                const lbl = document.createElement('div');
                lbl.className = 'field-label';
                lbl.textContent = label;
                const val = document.createElement('textarea');
                val.className = 'field-val';
                val.value = value == null ? '' : String(value);
                val.rows = Math.max(1, Math.min(8, Math.ceil(val.value.length / 60)));
                r.appendChild(lbl); r.appendChild(val);
                if (value !== '-' && String(value).trim() !== '') {
                    const btn = document.createElement('button');
                    btn.className = 'copy-one';
                    btn.textContent = 'Copy';
                    btn.onclick = async () => { await copyText(val.value); flashCopied(btn); };
                    r.appendChild(btn);
                }
                results.appendChild(r);
            }

        lastText = results.innerText;
    }

    window.copyAll = function () {
        let out = '';
        results.querySelectorAll('.section-title').forEach(sec => {
            out += '\n' + sec.textContent + '\n';
            let n = sec.nextElementSibling;
            while (n && !n.classList.contains('section-title')) {
                if (n.classList.contains('field-row')) {
                    const l = n.querySelector('.field-label')?.textContent || '';
                    const v = n.querySelector('.field-val')?.value || '';
                    if (v.trim()) out += l + ': ' + v + '\n';
                }
                n = n.nextElementSibling;
            }
        });
        copyText(out.trim());
        setStatus('Copied all tables to clipboard.', 'ok');
    };

    ;

    window.toggleDaPin = function () {
        const w = document.getElementById('daWrap');
        const btn = document.getElementById('daPinBtn');
        const on = w.classList.toggle('pinned');
        btn.textContent = on ? '📌 Always on top: ON' : '📌 Always on top: OFF';
    };
})();
