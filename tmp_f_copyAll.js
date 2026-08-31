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
    }