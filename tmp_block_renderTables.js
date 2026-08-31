        } catch (e) {
            setStatus('Network error: ' + e, 'err');
            console.error('Discogs add fetch failed:', e);
        } finally {
            buildBtn.disabled = false;
        }
    };

    window.toggleDaPin = function () {
        const w = document.getElementById('daWrap');
        const btn = document.getElementById('daPinBtn');
        const on = w.classList.toggle('pinned');
        btn.textContent = on ? '📌 Always on top: ON' : '📌 Always on top: OFF';
    };
})();
