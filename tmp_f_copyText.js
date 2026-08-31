async function copyText(text) {
        try { await navigator.clipboard.writeText(text); }
        catch (e) { /* ignore */ }
    }