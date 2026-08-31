
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
    )();
