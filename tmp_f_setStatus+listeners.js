function setStatus(msg, kind) {
        statusEl.textContent = msg || '';
        statusEl.className = 'status' + (kind ? ' ' + kind : '');
    }