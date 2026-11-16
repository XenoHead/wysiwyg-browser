let data = {};
let mediaFormats = {};

// --- INITIALIZATION & EVENT LISTENERS ---
document.addEventListener('DOMContentLoaded', () => {
    // Force hard reload once on start to ensure latest version (same as Refresh button)
    if (!sessionStorage.getItem('force_refreshed')) {
        sessionStorage.setItem('force_refreshed', 'true');
        location.reload(true);
        return;
    }
    initializeDropdowns();
    loadAppVersion();
    loadProfile();
    loadMediaFormats();
    loadCounters();
    loadVariableConditions(); // Load saved persistent conditions
    setupSaveConditionsButton(); // Create save button and enable if admin file is present
    const footerYear = document.getElementById('footerYear');
    if (footerYear) footerYear.textContent = new Date().getFullYear();

    // Setup Event Listeners
    setupEventListeners();
    initHotkeys();

    // Hide the "Settings Editor" menu option if the admin file (allpass.json)
    // is not present in the working directory.
    fetch('/allpass.json?t=' + new Date().getTime())
        .then(r => { if (!r.ok) { const b = document.getElementById('editorBtn'); if (b) b.style.display = 'none'; } })
        .catch(() => { const b = document.getElementById('editorBtn'); if (b) b.style.display = 'none'; });

    // Listen for scrape URLs pushed from the browser extension (SSE bridge).
    // Works in browser mode without the native PySide6 window.
    if (typeof EventSource !== 'undefined') {
        try {
            const es = new EventSource('/api/extension-scrape/stream');
            es.onmessage = (e) => {
                try {
                    const payload = JSON.parse(e.data);
                    const targetUrl = payload && payload.url;
                    if (!targetUrl) return;
                    const urlInput = document.getElementById('discogsUrlInput');
                    const scrapeBtn = document.getElementById('scrapeBtn');
                    if (urlInput && scrapeBtn) {
                        urlInput.value = targetUrl;
                        urlInput.dispatchEvent(new Event('input', { bubbles: true }));
                        scrapeBtn.click();
                    }
                } catch (_) { /* ignore malformed events */ }
            };
            es.onerror = () => { /* browser auto-reconnects */ };
        } catch (_) { /* EventSource unsupported */ }
    }

    // Initialize Theme
    const savedTheme = localStorage.getItem('wysiwyg_theme');
    if (savedTheme === 'dark') {
        document.body.setAttribute('data-theme', 'dark');
    }

    // Initialize Dock Scanner Preference
    const dockPref = localStorage.getItem('wysiwyg_dock_scanner');
    if (dockPref === 'true') {
        document.getElementById('dockScanner').checked = true;
    }

    // Initialize Auto Generate Preference
    const autoGenPref = localStorage.getItem('wysiwyg_auto_generate');
    if (autoGenPref !== null && document.getElementById('autoGenerateToggle')) {
        document.getElementById('autoGenerateToggle').checked = autoGenPref === 'true';
    }
});

// Wire the padlock buttons to toggle their hidden lock checkboxes and reflect state.
function setupLockPadlocks() {
    const pairs = [
        { btn: 'lockSkuBtn', box: 'lockSku' },
        { btn: 'lockDescBtn', box: 'lockDesc' }
    ];
    pairs.forEach(({ btn, box }) => {
        const btnEl = document.getElementById(btn);
        const boxEl = document.getElementById(box);
        if (!btnEl || !boxEl) return;

        const sync = () => {
            const locked = boxEl.checked;
            btnEl.textContent = locked ? '🔒' : '🔓';
            btnEl.classList.toggle('locked', locked);
            btnEl.title = locked ? 'Unlock' : 'Lock';
        };

        // Initialize from the checkbox's current state.
        sync();

        btnEl.addEventListener('click', () => {
            boxEl.checked = !boxEl.checked;
            sync();
        });

        // Keep the icon in sync if the checkbox is changed elsewhere in code.
        boxEl.addEventListener('change', sync);
    });
}

function setupEventListeners() {
    function addClickListener(id, callback) {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('click', callback);
        } else {
            console.warn(`Element with ID '${id}' not found for click listener.`);
        }
    }

    // --- Top Nav ---
    addClickListener('runUberPasteBtn', runUberPaste);
    addClickListener('runWysiScanBtn', runWysiScan);
    addClickListener('addsToggleBtn', toggleAddsSubmenu);
    addClickListener('addsAmazonBtn', openAddsAmazon);
    addClickListener('addsDiscogsBtn', openAddsDiscogs);
    addClickListener('hotkeysBtn', openHotkeysModal);
    addClickListener('themeBtn', toggleTheme);
    addClickListener('refreshBtn', () => location.reload(true));
    addClickListener('updateMenusBtn', updateMenus);
    addClickListener('editorBtn', openEditor);
    addClickListener('shutdownBtn', shutdownApp);
    document.getElementById('dockScanner')?.addEventListener('change', (e) => {
        localStorage.setItem('wysiwyg_dock_scanner', e.target.checked);
    });
    document.getElementById('autoGenerateToggle')?.addEventListener('change', (e) => {
        localStorage.setItem('wysiwyg_auto_generate', e.target.checked);
    });

    // --- Modals ---
    addClickListener('closePasswordModalBtn', closePasswordModal);
    addClickListener('submitPasswordBtn', submitPassword);
    document.getElementById('adminPasswordInput')?.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') submitPassword();
    });
    addClickListener('closeShutdownModalBtn', closeShutdownModal);
    addClickListener('confirmShutdownBtn', confirmShutdown);
    addClickListener('cancelShutdownBtn', closeShutdownModal);
    addClickListener('closeRequestModalBtn', closeRequestModal);
    addClickListener('submitRequestBtn', submitRequest);
    addClickListener('cancelRequestBtn', closeRequestModal);

    addClickListener('closeUpdateMenusModalBtn', closeUpdateMenusModal);
    addClickListener('cancelUpdateMenusBtn', closeUpdateMenusModal);
    addClickListener('confirmUpdateMenusBtn', confirmUpdateMenus);
    document.getElementById('chkUpdateConditions')?.addEventListener('change', function () {
        const mergeContainer = document.getElementById('mergeConditionsContainer');
        const chkMerge = document.getElementById('chkMergeConditions');
        if (this.checked) {
            if (mergeContainer) mergeContainer.style.display = 'flex';
            if (chkMerge) chkMerge.disabled = false;
        } else {
            if (mergeContainer) mergeContainer.style.display = 'none';
            if (chkMerge) {
                chkMerge.checked = false;
                chkMerge.disabled = true;
            }
        }
    });

    addClickListener('openCalcBtn', openCalcModal);
    addClickListener('closeCalcModalBtn', closeCalcModal);
    addClickListener('calculateBtn', runCalculator);

    setupLockPadlocks();

    // --- Hamburger Drawer Menu ---
    function setupHamburgerDrawer() {
        const drawer = document.getElementById('hamburgerDrawer');
        const overlay = document.getElementById('drawerOverlay');
        const openBtn = document.getElementById('hamburgerBtn');
        const closeBtn = document.getElementById('drawerCloseBtn');
        if (!drawer || !overlay) return;

        const openDrawer = () => {
            drawer.classList.add('open');
            drawer.setAttribute('aria-hidden', 'false');
            overlay.style.display = 'block';
        };
        const closeDrawer = () => {
            drawer.classList.remove('open');
            drawer.setAttribute('aria-hidden', 'true');
            overlay.style.display = 'none';
        };

        openBtn?.addEventListener('click', (e) => { e.stopPropagation(); openDrawer(); });
        closeBtn?.addEventListener('click', closeDrawer);
        overlay.addEventListener('click', closeDrawer);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && drawer.classList.contains('open')) closeDrawer();
        });

        // Safety net: if the drawer is logically closed but the overlay is somehow left
        // visible (e.g. an exception during a child-window close in the webview), the next
        // click anywhere on the page clears it so the UI can never get "locked up".
        document.addEventListener('click', () => {
            if (!drawer.classList.contains('open') && overlay.style.display !== 'none') {
                overlay.style.display = 'none';
            }
        }, true);

        // Close the drawer after most in-drawer actions fire (e.g. Refresh, Editor, Shut Down).
        // But NOT the counter +1 buttons or the Edit Counters button — those should keep the
        // drawer open so you can tap multiple times / edit without reopening.
        drawer.querySelectorAll('button').forEach((btn) => {
            if (btn.classList.contains('counter-button') || btn.id === 'editCountersBtn') return;
            if (btn.id === 'addsToggleBtn') return; // keep drawer open while expanding the Adds submenu
            btn.addEventListener('click', () => {
                // Defer so the action's own handler runs first
                setTimeout(closeDrawer, 0);
            });
        });
    }
    setupHamburgerDrawer();

    // --- Calculator Live Auto-Populate & Enter Key ---
    ['calcCompPrice', 'calcCompShip'].forEach(id => {
        const el = document.getElementById(id);
        el?.addEventListener('input', () => {
            const compPriceEl = document.getElementById('calcCompPrice');
            const compShipEl = document.getElementById('calcCompShip');
            const ourPriceEl = document.getElementById('calcOurPrice');

            const cp = parseFloat(compPriceEl.value) || 0;
            const cs = parseFloat(compShipEl.value) || 0;
            const ct = cp + cs;

            localStorage.setItem('wysiwyg_calc_comp_price', compPriceEl.value);
            localStorage.setItem('wysiwyg_calc_comp_ship', compShipEl.value);

            if (ct > 0) {
                document.getElementById('calcCompTotal').value = ct.toFixed(2); // This is auto-calculated, no need to save
                document.getElementById('calcOurPrice').value = (ct - 9).toFixed(2);
            } else {
                document.getElementById('calcCompTotal').value = '';
                document.getElementById('calcOurPrice').value = '';
            }
        });
    });
    const ourPriceEl = document.getElementById('calcOurPrice');
    if (ourPriceEl) {
        ourPriceEl.addEventListener('input', () => {
            localStorage.setItem('wysiwyg_calc_our_price', ourPriceEl.value);
        });
    }
    ['calcCondition', 'calcCompPrice', 'calcCompShip', 'calcOurPrice'].forEach(id => {
        document.getElementById(id)?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                runCalculator();
            }
        });
    });

    // --- Banners & Titles ---
    addClickListener('updateBanner', runInstaller);
    addClickListener('appTitle', showChangelogModal);

    // --- Tabs ---
    document.querySelectorAll('.tab-btn').forEach(button => {
        button.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.style.display = 'none');
            button.classList.add('active');
            const tabId = button.getAttribute('data-tab');
            document.getElementById(tabId).style.display = 'block';

            const scraperSection = document.getElementById('scraperSection');
            if (scraperSection) {
                scraperSection.style.display = (tabId === 'listingTool') ? 'block' : 'none';
            }

            if (tabId === 'futureTool') {
                const genBtn = document.getElementById('htmlGenBtn');
                if (genBtn) genBtn.click();
            }
        });
    });

    // --- Scraper ---
    // Mirror the current Discogs URL into localStorage so Adds > Amazon's
    // "Pull from WYSIWYG" button can grab whatever is in this box. Both pages are
    // served from the same origin, so they share localStorage.
    const rememberDiscogsUrl = (value) => {
        const v = (value || '').trim();
        if (!v) return; // never blank out a previously stored URL
        try { localStorage.setItem('wysiwyg_last_discogs_url', v); } catch (e) { }
    };
    document.getElementById('discogsUrlInput')?.addEventListener('click', async function () {
        if (document.getElementById('autoPasteToggle').checked) {
            try {
                const text = await navigator.clipboard.readText();
                if (text) this.value = text;
                rememberDiscogsUrl(this.value);
            } catch (err) {
                console.error('Autopaste failed:', err);
            }
        }
    });
    document.getElementById('discogsUrlInput')?.addEventListener('input', function () {
        rememberDiscogsUrl(this.value);
    });

    // --- Market Lookup Tab ---
    addClickListener('runMarketSearchBtn', runMarketSearch);
    addClickListener('resetLookupBtn', resetLookup);

    // --- Builder Tab ---
    addClickListener('saveProfileBtn', saveProfile);
    addClickListener('generateBtn', generateListingData);
    addClickListener('clearBtn', fullReset);
    addClickListener('scrapeBtn', () => {
        if (document.getElementById('lockSku')) document.getElementById('lockSku').checked = false;
        if (document.getElementById('lockDesc')) document.getElementById('lockDesc').checked = false;
    });

    // --- Reset All before every scrape ---
    // Manual click, Enter in the URL box, the SSE bridge and the Chrome extension
    // (which clicks #scrapeBtn) all end up as a submit on this form. The listener
    // sits on document in the CAPTURE phase so it runs before htmx's own handler
    // and can hold the request back until Reset All has finished - otherwise a
    // leftover value from the previous item could land on the incoming scrape.
    const scrapeForm = document.querySelector('form[hx-post="/scrape"]');
    if (scrapeForm) {
        document.addEventListener('submit', async (ev) => {
            if (ev.target !== scrapeForm) return;

            const urlEl = document.getElementById('discogsUrlInput');
            const pendingUrl = (urlEl ? urlEl.value : '').trim();
            // Nothing to scrape: let the browser show the field's "required" hint.
            if (!pendingUrl) return;

            ev.preventDefault();
            ev.stopPropagation();

            try {
                // Keep the URL box itself so the value can never be lost mid-reset.
                await fullReset({ keepUrl: true });
            } catch (err) {
                console.error('Reset All before scrape failed:', err);
            }
            if (urlEl) urlEl.value = pendingUrl;

            // Send it directly rather than re-submitting the form: no second
            // submit event to re-enter this handler, no constraint validation to
            // cancel silently, and the URL travels with the request.
            if (window.htmx && typeof htmx.ajax === 'function') {
                htmx.ajax('POST', '/scrape', {
                    source: scrapeForm,
                    target: '#scraperOutput',
                    swap: 'innerHTML',
                    values: { url: pendingUrl }
                });
            } else {
                scrapeForm.requestSubmit();
            }
        }, true);
    }

    document.getElementById('conditionOfMedia')?.addEventListener('change', function () {
        if (!this.value) document.getElementById('mediaDescriptionText').value = "";
        updateDynamicColors();
    });
    document.getElementById('skuFlag')?.addEventListener('change', updateDynamicColors);
    document.querySelectorAll('input[name="media_modifier"]').forEach(radio => {
        radio.addEventListener('change', updateDynamicColors);
    });
    document.getElementById('sleeveCondition')?.addEventListener('change', function () {
        if (!this.value) document.getElementById('sleeveDesc').value = "";
        updateDynamicColors();
    });
    updateDynamicColors();

    // --- Output Area ---
    addClickListener('copySkuBtn', (e) => copyField('outputSku', e.currentTarget));
    addClickListener('copyDescBtn', (e) => copyField('outputDesc', e.currentTarget));
    addClickListener('copyOurPriceBtn', (e) => copyField('calcOurPrice', e.currentTarget));
    addClickListener('openListingsFolderBtn', openListingsFolder);
    addClickListener('reportsBtn', openReportsModal);
    addClickListener('aboutBtn', () => fetch('/show-about', { method: 'POST' }));
    addClickListener('editCountersBtn', openCounterEditor);

    // Counter buttons are rendered dynamically (in the hamburger drawer); use event delegation.
    const counterGroupEl = document.getElementById('drawerCounterGroup');
    if (counterGroupEl) {
        counterGroupEl.addEventListener('click', (e) => {
            const btn = e.target.closest('.counter-button');
            if (!btn) return;
            incrementCounter(btn.dataset.serverKey, btn);
        });
    }
    // --- Details Tab ---
    addClickListener('copyLivePreviewBtn', copyLivePreview);
    addClickListener('copyHtmlBtn', copyGeneratedHtml);

    // Live Preview is editable; every change is mirrored into the HTML CODE box
    document.getElementById('htmlPreview')?.addEventListener('input', syncLivePreviewToCode);
    document.querySelectorAll('.live-preview-fmt-btn').forEach(btn => {
        // Keep the preview's text selection when clicking a toolbar button
        btn.addEventListener('mousedown', (e) => e.preventDefault());
        btn.addEventListener('click', () => applyLivePreviewFormat(btn.dataset.cmd));
    });
    document.addEventListener('selectionchange', updateLivePreviewToolbarState);

    // --- Footer ---
    addClickListener('openRequestModalBtn', openRequestModal);

    // --- Service Status Polling ---
    // Check status every 5 seconds to reduce system load
    setInterval(updateServiceStatus, 5000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) updateServiceStatus(); });
}


// --- ASYNC & API FUNCTIONS ---

async function runUberPaste() {
    try {
        const resp = await fetch('/run-uberpaste', { method: 'POST' });
        const res = await resp.json();
        if (res.status === 'success') {
            updateServiceStatus();
        } else {
            customAlert('Could not start UberPaste: ' + res.message);
        }
    } catch (e) {
        customAlert('Failed to connect to server to run UberPaste: ' + e);
    }
}

function toggleAddsSubmenu() {
    const items = document.getElementById('addsSubmenuItems');
    const toggle = document.getElementById('addsToggleBtn');
    if (!items || !toggle) return;
    const willShow = items.style.display === 'none';
    items.style.display = willShow ? 'block' : 'none';
    const ico = toggle.querySelector('.drawer-ico');
    if (ico) ico.textContent = willShow ? '➖' : '➕';
}

let _addsAmazonWindow = null;
let _addsDiscogsWindow = null;
async function openAddsAmazon() {
    try {
        const url = '/adds/amazon';
        _addsAmazonWindow = window.open(url, 'AddsAmazonWindow', 'width=820,height=820,resizable=yes,scrollbars=yes,status=yes');
        if (_addsAmazonWindow) {
            _addsAmazonWindow.focus();
        } else {
            customAlert('Popup window was blocked by the browser. Please allow popups for this site.');
        }
    } catch (e) {
        customAlert('Failed to open Adds > Amazon: ' + e);
    }
}

async function openAddsDiscogs() {
    try {
        const url = '/adds/discogs';
        // Reuse the existing window if it's still open, but ALWAYS reload it so the
        // browser picks up code fixes. A focused old window would otherwise keep
        // running stale DOM/JS even though the server sends no-cache headers. The
        // last extract is restored from localStorage on reload, so nothing is lost.
        if (_addsDiscogsWindow && !_addsDiscogsWindow.closed) {
            try { _addsDiscogsWindow.location.reload(); } catch (e) { /* ignore */ }
            _addsDiscogsWindow.focus();
            return;
        }
        _addsDiscogsWindow = window.open(url, 'AddsDiscogsWindow', 'width=900,height=860,resizable=yes,scrollbars=yes,status=yes');
        if (_addsDiscogsWindow) {
            _addsDiscogsWindow.focus();
        } else {
            customAlert('Popup window was blocked by the browser. Please allow popups for this site.');
        }
    } catch (e) {
        customAlert('Failed to open Adds > Discogs: ' + e);
    }
}

async function updateServiceStatus() {
    // Nothing to update while the tab is in the background.
    if (document.hidden) return;
    try {
        // 1. Check Backend Services (Server-side check)
        const resp = await fetch('/api/service-status');
        const status = await resp.json();

        const wysiBtn = document.getElementById('runWysiScanBtn');
        if (wysiBtn) {
            if (status.wysiscan) {
                wysiBtn.disabled = true;
                wysiBtn.style.opacity = "0.5";
                wysiBtn.title = "WysiScan is already running";
                wysiBtn.style.border = "2px solid #28a745";
            } else {
                wysiBtn.disabled = false;
                wysiBtn.style.opacity = "1";
                wysiBtn.title = "Open WysiScan";
                wysiBtn.style.border = "";
            }
        }

        const uberBtn = document.getElementById('runUberPasteBtn');
        if (uberBtn) {
            if (status.uberpaste) {
                uberBtn.disabled = true;
                uberBtn.style.opacity = "0.5";
                uberBtn.title = "UberPaste is already running";
                uberBtn.style.border = "2px solid #28a745";
            } else {
                uberBtn.disabled = false;
                uberBtn.style.opacity = "1";
                uberBtn.title = "Launch UberPaste";
                uberBtn.style.border = "";
            }
        }
    } catch (e) {
        // Silent fail if server is unreachable or a transient error occurs
    }
}

async function runWysiScan() {
    // Open the tab/window IMMEDIATELY (synchronously) so the browser counts it as a
    // user gesture. /run-wysiscan can take several seconds while the packaged
    // scanner extracts, and Chrome blocks window.open() once the gesture expires.
    const dock = document.getElementById('dockScanner')?.checked ?? true;
    let wysiScanWindow;
    if (dock) {
        wysiScanWindow = window.open('about:blank', '_blank');
    } else {
        const windowFeatures = "width=1200,height=900,resizable=yes,scrollbars=yes,status=yes";
        wysiScanWindow = window.open('about:blank', 'WysiScanWindow', windowFeatures);
    }

    if (!wysiScanWindow) {
        customAlert('Popup window was blocked by the browser. Please allow popups for this site.');
        return;
    }

    try {
        wysiScanWindow.document.title = 'WysiScan';
        wysiScanWindow.document.body.innerHTML =
            '<p style="font-family:sans-serif;font-size:14px;padding:24px;">Starting WysiScan…</p>';
    } catch (e) { /* cross-origin placeholder is fine */ }

    try {
        // Ask the main server to launch the WysiScan server
        const resp = await fetch('/run-wysiscan', { method: 'POST' });
        const res = await resp.json();

        if (res.status === 'success') {
            wysiScanWindow.location.href = 'http://127.0.0.1:8010/';
            wysiScanWindow.focus();
        } else {
            try { wysiScanWindow.close(); } catch (e) { }
            customAlert('Could not start WysiScan: ' + res.message);
        }
    } catch (e) {
        try { wysiScanWindow.close(); } catch (e2) { }
        customAlert('Failed to connect to server to run WysiScan: ' + e);
    }
}

async function setupSaveConditionsButton() {
    // The "Save Variable Conditions" feature requires the admin file (allpass.json)
    // to be present in the working directory. If it is missing, the button is not
    // created at all (hidden), and the feature is effectively disabled.
    const anchorElement = document.getElementById('trackTimeInfo');
    if (!anchorElement || document.getElementById('saveVariableConditionsBtn')) return;

    // Check for the admin file first; only show the button if it exists.
    let adminFilePresent = false;
    try {
        const response = await fetch('/allpass.json?t=' + new Date().getTime());
        adminFilePresent = response.ok;
    } catch (e) {
        adminFilePresent = false;
    }
    if (!adminFilePresent) {
        // No admin file -> feature disabled, button hidden.
        return;
    }

    // Create the button (enabled, since the admin file is present).
    const saveBtn = document.createElement('button');
    saveBtn.id = 'saveVariableConditionsBtn';
    saveBtn.title = 'Save Variable Conditions';
    saveBtn.innerHTML = '💾'; // Save icon

    saveBtn.style.marginLeft = '0';
    saveBtn.style.padding = '0 5px';
    saveBtn.style.fontSize = '1em';
    saveBtn.style.lineHeight = '1';
    saveBtn.style.height = '22px';
    saveBtn.style.boxSizing = 'border-box';
    saveBtn.style.display = 'inline-flex';
    saveBtn.style.alignItems = 'center';
    saveBtn.style.justifyContent = 'center';
    saveBtn.style.cursor = 'pointer';
    saveBtn.style.border = '1px solid #28a745';
    saveBtn.style.borderRadius = '3px';
    saveBtn.style.backgroundColor = '#28a745';
    saveBtn.style.color = 'white';

    anchorElement.insertAdjacentElement('afterend', saveBtn);

    saveBtn.addEventListener('click', (e) => {
        e.preventDefault();
        saveVariableConditions();
    });
}

async function loadAppVersion() {
    try {
        const resp = await fetch('/api/version?t=' + new Date().getTime());
        const v = await resp.json();
        const vStr = `${v.major}.${v.minor}.${v.patch}.${v.build || 0}`;

        // Detect Dev Mode based on port 8009
        const isDev = window.location.port === '8009';
        const appName = isDev ? "WYSIWYG DEV" : "WYSIWYG";

        if (isDev) {
            // Add visual indicators for Dev Mode
            document.body.style.borderTop = "5px solid #ff9800";
            const nav = document.querySelector('nav') || document.querySelector('.navbar');
            if (nav) nav.style.borderBottom = "1px solid #ff9800";
        }

        document.title = `${appName} - ${vStr}`;
        const titleEl = document.getElementById('appTitleText');

        let titleHtml = `${appName} - v${vStr}`;
        if (isDev) {
            titleHtml = `<span style="color: #ff9800;">🛠️ ${titleHtml}</span>`;
        }

        document.getElementById('updateBanner').style.display = 'none';
        if (titleEl) titleEl.innerHTML = titleHtml;

        // Update check happens after load so startup never waits on the network share.
        checkServerUpdate();
    } catch (e) { console.error("Version load failed", e); }
}

async function checkServerUpdate() {
    try {
        const resp = await fetch('/api/server-version');
        const r = await resp.json();
        if (!r.update_available) return;
        const banner = document.getElementById('updateBanner');
        if (banner) banner.style.display = 'block';
        const titleEl = document.getElementById('appTitleText');
        if (titleEl) {
            titleEl.innerHTML += ` <span onclick="event.stopPropagation(); runInstaller()" style="cursor:pointer; background: #ffc107; color: #000; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; margin-left: 10px; border: 1px solid #000; vertical-align: middle;" title="Click to run installer">* UPDATE AVAILABLE *</span>`;
        }
    } catch (e) { /* offline / share unavailable is not an error */ }
}

function runInstaller() {
    customConfirm("Ready to update? This will close the app and run the installer.", async () => {
        try {
            await fetch('/run-installer', { method: 'POST' });
            window.close();
            document.body.innerHTML = "<div style='display:flex;justify-content:center;align-items:center;height:100vh;flex-direction:column;font-family:Arial;text-align:center;'><h1>🚀 Update Started</h1><p>The installer is running.</p><p>The application will close automatically.</p><p>You can close this tab.</p></div>";
        } catch (e) { customAlert("Failed to run installer: " + e); }
    });
}

async function showChangelogModal() {
    try {
        const resp = await fetch('/api/changelog');
        const data = await resp.json();
        const entries = data.entries.length ? data.entries.join('\n\n') : "No changelog entries found.";
        showModal('Version History', `<pre style="font-family:inherit; white-space:pre-wrap;">${entries}</pre>`, [{ text: 'Close', primary: true }]);
    } catch (e) {
        customAlert("Failed to load changelog.");
    }
}

async function openUpdateFolder() {
    try {
        await fetch('/open-update-folder', { method: 'POST' });
    } catch (e) {
        customAlert("Failed to open update folder.");
    }
}

async function runMarketSearch() {
    const payload = {
        artist: document.getElementById('lookupArtist').value,
        title: document.getElementById('lookupTitle').value,
        upc: document.getElementById('lookupUPC').value
    };

    const resultsDiv = document.getElementById('lookupResults');
    resultsDiv.innerHTML = "<p>Generating Marketplace Links...</p>";

    try {
        const resp = await fetch('/market-search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        // Use .text() instead of .json() to avoid the "Unexpected Token" crash
        const htmlResult = await resp.text();
        resultsDiv.innerHTML = htmlResult;

    } catch (error) {
        resultsDiv.innerHTML = `<p style="color:red;">Connection Error: ${error}</p>`;
    }
}

async function initializeDropdowns() {
    try {
        const resp = await fetch('/settings');
        if (!resp.ok) console.warn("Settings load failed:", resp.status);
        data = await resp.json();

        const idMap = {
            "conditionOfMedia": "Condition of Media",
            "formatTags": "Format Tags",
            "edition": "Edition",
            "mediaFormat": "Media Format",
            "sleevePackaging": "Sleeve Packaging",
            "sleeveCondition": "Sleeve/Artwork/Insert Condition",
            "skuFlag": "SKU Flags",
            "packagingFeature": "Packaging Feature",
            "preFM": "Pre FM",
            "postFM": "Post FM",
            "weightSpeed": "Weight/Speed"
        };

        Object.keys(idMap).forEach(htmlId => {
            if (data[idMap[htmlId]]) {
                populateDropdown(htmlId, data[idMap[htmlId]]);
            }
        });

        // Restore skuFlag from profile after dropdown is populated
        const skuFlag = localStorage.getItem('wysiwyg_profile_sku_flag');
        if (skuFlag && document.getElementById('skuFlag')) {
            document.getElementById('skuFlag').value = skuFlag;
        }
        updateDynamicColors();
    } catch (e) { console.error("Failed to load settings.", e); }
}

async function loadMediaFormats() {
    try {
        const resp = await fetch('/media_formats.json');
        if (resp.ok) {
            mediaFormats = await resp.json();
        }
    } catch (e) { console.error("Failed to load media formats.", e); }
}

async function openEditor() {
    try {
        const response = await fetch('/allpass.json?t=' + new Date().getTime());
        if (!response.ok) {
            customAlert("Configuration Error: Password file (allpass.json) not found.");
            return;
        }

        const rawText = await response.text();

        // Try parsing as JSON first (new format)
        try {
            storedPasswords = JSON.parse(rawText);
        } catch (e) {
            // Fallback for legacy plain text
            let text = rawText.trim();
            if (text.startsWith("EDITOR_PASSWORD=")) {
                text = text.split('=')[1].trim();
            }
            storedPasswords = { editor: text };
        }

        document.getElementById('passwordModal').style.display = 'block';
        document.getElementById('adminPasswordInput').value = '';
        document.getElementById('adminPasswordInput').focus();
    } catch (e) {
        customAlert("Error accessing security file: " + e.message);
    }
}

function updateMenus() {
    const modal = document.getElementById('updateMenusModal');
    if (!modal) return;
    const chkMenus = document.getElementById('chkUpdateMenus');
    if (chkMenus) chkMenus.checked = true;
    const chkCond = document.getElementById('chkUpdateConditions');
    if (chkCond) chkCond.checked = false;
    const chkMerge = document.getElementById('chkMergeConditions');
    if (chkMerge) {
        chkMerge.checked = false;
        chkMerge.disabled = true;
    }
    const mergeContainer = document.getElementById('mergeConditionsContainer');
    if (mergeContainer) mergeContainer.style.display = 'none';
    modal.style.display = 'block';
}

function closeUpdateMenusModal() {
    const modal = document.getElementById('updateMenusModal');
    if (modal) modal.style.display = 'none';
}

async function confirmUpdateMenus() {
    const doMenus = document.getElementById('chkUpdateMenus')?.checked;
    const doConditions = document.getElementById('chkUpdateConditions')?.checked;
    const doMerge = document.getElementById('chkMergeConditions')?.checked;

    if (!doMenus && !doConditions) {
        customAlert("Please select at least one option to update.");
        return;
    }

    closeUpdateMenusModal();

    try {
        let messages = [];
        let anySuccess = false;

        if (doMenus) {
            const resp = await fetch('/update-menus', { method: 'POST' });
            const res = await resp.json();
            messages.push(res.message || (res.status === 'success' ? 'Menus updated.' : 'Menu update failed.'));
            if (res.status === 'success') anySuccess = true;
        }

        if (doConditions) {
            const respCond = await fetch(`/api/merge-conditions?merge=${doMerge}`, { method: 'POST' });
            const resCond = await respCond.json();
            if (resCond.status === 'success') {
                messages.push(resCond.message || 'Conditions updated.');
                anySuccess = true;
            } else {
                messages.push("Condition Update Failed: " + (resCond.message || 'Unknown error'));
            }
        }

        customAlert(messages.join("\n\n"));
        if (anySuccess) {
            location.reload();
        }
    } catch (e) {
        customAlert("Error: " + e);
    }
}

async function submitRequest() {
    const name = document.getElementById('reqName').value.trim();
    const request = document.getElementById('reqText').value.trim();

    if (!request) {
        customAlert("Please enter a request.");
        return;
    }

    try {
        const resp = await fetch('/submit-request', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, request })
        });
        const res = await resp.json();
        if (res.status === 'success') {
            customAlert("Request submitted!");
            document.getElementById('reqName').value = "";
            document.getElementById('reqText').value = "";
            closeRequestModal();
        } else {
            customAlert("Error: " + res.message);
        }
    } catch (e) {
        customAlert("Submission failed: " + e);
    }
}

// --- Counter buttons (config-driven, editable) ---
const COUNTER_CONFIG_KEY = 'wysiwyg_counter_config';
const COUNTER_CONFIG_VERSION = 2; // bump to discard a stale saved config
const MAX_COUNTERS = 6; // 4 defaults + up to 2 more
const DEFAULT_COUNTERS = [
    { id: 'cnt_listed', label: 'LI', serverKey: 'Listed', color: '#28a745' },
    { id: 'cnt_amazon', label: 'AA', serverKey: 'Amazon Adds', color: '#007bff' },
    { id: 'cnt_discogs', label: 'DA', serverKey: 'Discogs Adds', color: '#17a2b8' },
    { id: 'cnt_dupes', label: 'DU', serverKey: 'Duplicates', color: '#fd7e14' }
];

let counterConfig = [];

function loadCounterConfig() {
    try {
        const raw = localStorage.getItem(COUNTER_CONFIG_KEY);
        if (raw) {
            const parsed = JSON.parse(raw);
            // Discard stale configs (e.g. ones with extraneous "New 2/New 3" entries)
            // by requiring a matching version.
            if (parsed && parsed.version === COUNTER_CONFIG_VERSION && Array.isArray(parsed.counters)) {
                counterConfig = parsed.counters;
            }
        }
    } catch (e) { /* ignore */ }
    if (!Array.isArray(counterConfig) || counterConfig.length === 0) {
        counterConfig = JSON.parse(JSON.stringify(DEFAULT_COUNTERS));
    }
}

function saveCounterConfig() {
    try {
        localStorage.setItem(COUNTER_CONFIG_KEY, JSON.stringify({
            version: COUNTER_CONFIG_VERSION,
            counters: counterConfig
        }));
    } catch (e) { /* ignore */ }
}

function renderCounterButtons() {
    const group = document.getElementById('drawerCounterGroup');
    if (!group) return;
    group.innerHTML = '';
    const container = document.createElement('div');
    container.className = 'counter-button-container';
    counterConfig.forEach(c => {
        const b = document.createElement('button');
        b.className = 'counter-button';
        b.dataset.serverKey = c.serverKey;
        b.style.backgroundColor = c.color;
        b.title = (c.label ? c.label + ' ' : '') + '+' + c.serverKey + ' (click to +1)';
        b.innerHTML = `${c.label || '?'}<br>0`;
        container.appendChild(b);
    });
    group.appendChild(container);
}

async function loadCounters() {
    loadCounterConfig();
    renderCounterButtons();
    try {
        const resp = await fetch('/api/get-counters');
        const counts = await resp.json();
        updateCounterUI(counts);
    } catch (e) { console.error(e); }
}

async function incrementCounter(serverKey, btn) {
    const originalHTML = btn.innerHTML;
    btn.innerText = "⏳";
    try {
        const resp = await fetch('/api/increment-counter', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: serverKey, label: serverKey })
        });
        const res = await resp.json();
        if (res.status === 'success') {
            btn.innerText = "✅";
            // Daily count only updates the server tally + the button's own
            // number. It must NOT touch the description field.
            setTimeout(() => {
                updateCounterUI(res.counts);
            }, 500);
        } else {
            customAlert("Error: " + res.message);
            btn.innerHTML = originalHTML;
        }
    } catch (e) {
        console.error(e);
        btn.innerHTML = originalHTML;
    }
}

function updateCounterUI(counts) {
    if (!Array.isArray(counterConfig)) return;
    counterConfig.forEach(c => {
        const btn = document.querySelector(`#drawerCounterGroup .counter-button[data-server-key="${CSS.escape(c.serverKey)}"]`);
        if (btn) btn.innerHTML = `${c.label || '?'}<br>${counts[c.serverKey] || 0}`;
    });
}

function commitCounterEditorInputs() {
    document.querySelectorAll('.ctr-label').forEach(inp => {
        const i = parseInt(inp.dataset.idx, 10);
        if (counterConfig[i]) counterConfig[i].label = inp.value;
    });
    document.querySelectorAll('.ctr-color').forEach(inp => {
        const i = parseInt(inp.dataset.idx, 10);
        if (counterConfig[i]) counterConfig[i].color = inp.value;
    });
    document.querySelectorAll('.ctr-key').forEach(inp => {
        const i = parseInt(inp.dataset.idx, 10);
        const key = inp.value.trim();
        // Keep the previous key when cleared, otherwise the button would
        // increment nothing (the server tallies by this text).
        if (counterConfig[i] && key) counterConfig[i].serverKey = key;
    });
}

function refreshCounterEditor(focusFileText) {
    commitCounterEditorInputs();
    saveCounterConfig();
    renderCounterButtons();
    openCounterEditor(focusFileText);
}

function deleteCounter(idx) {
    if (counterConfig.length <= 1) return;
    counterConfig.splice(idx, 1);
    refreshCounterEditor();
}

function moveCounter(idx, dir) {
    const target = idx + dir;
    if (target < 0 || target >= counterConfig.length) return;
    const tmp = counterConfig[idx];
    counterConfig[idx] = counterConfig[target];
    counterConfig[target] = tmp;
    refreshCounterEditor();
}

function openCounterEditor(focusFileText) {
    loadCounterConfig();
    const esc = (s) => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
    const capStyle = 'font-size:10px; color:var(--secondary-color); font-weight:bold;';
    let body = '<div style="display:flex; flex-direction:column; gap:8px;">';
    counterConfig.forEach((c, i) => {
        const upDisabled = i === 0 ? 'disabled' : '';
        const downDisabled = i === counterConfig.length - 1 ? 'disabled' : '';
        body += `<div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap; border:1px solid var(--border-color,#ccc); border-radius:6px; padding:6px;">
            <button type="button" class="ctr-move" data-idx="${i}" data-dir="-1" ${upDisabled} style="border:none; background:#6c757d; color:#fff; border-radius:4px; cursor:pointer; padding:4px 7px; font-size:11px;" onclick="moveCounter(${i}, -1)" ${upDisabled}>▲</button>
            <button type="button" class="ctr-move" data-idx="${i}" data-dir="1" ${downDisabled} style="border:none; background:#6c757d; color:#fff; border-radius:4px; cursor:pointer; padding:4px 7px; font-size:11px;" onclick="moveCounter(${i}, 1)" ${downDisabled}>▼</button>
            <input type="color" value="${esc(c.color)}" data-idx="${i}" class="ctr-color" style="width:32px; height:28px; border:none; background:none; cursor:pointer;">
            <span style="${capStyle}">LABEL</span>
            <input type="text" value="${esc(c.label)}" data-idx="${i}" class="ctr-label" placeholder="Button text" style="width:60px; padding:4px; font-size:12px;">
            <span style="${capStyle}">FILE TEXT</span>
            <input type="text" value="${esc(c.serverKey)}" data-idx="${i}" class="ctr-key" placeholder="Text written to file" style="width:120px; padding:4px; font-size:12px;">
            ${counterConfig.length > 1 ? `<button type="button" class="ctr-del" data-idx="${i}" style="border:none; background:#dc3545; color:#fff; background:#dc3545; border-radius:4px; cursor:pointer; padding:4px 8px; font-size:11px;" onclick="deleteCounter(${i})">Delete</button>` : ''}
        </div>`;
    });
    body += '</div>';
    const canAdd = counterConfig.length < MAX_COUNTERS;
    showModal('Edit Counters', body, [
        ...(canAdd ? [{ text: '+ Add Counter', primary: false, onClick: () => {
            commitCounterEditorInputs();
            counterConfig.push({ id: 'cnt_' + Date.now(), label: 'NEW', serverKey: 'New ' + (counterConfig.length + 1), color: '#6c757d' });
            refreshCounterEditor(true);
        } }] : []),
        { text: 'Cancel', primary: false, onClick: closeModal },
        { text: 'Save', primary: true, onClick: () => {
            commitCounterEditorInputs();
            saveCounterConfig();
            renderCounterButtons();
            loadCounters();
            closeModal();
        } }
    ]);
    if (focusFileText) {
        setTimeout(() => {
            const inputs = document.querySelectorAll('.ctr-key');
            if (inputs.length) inputs[inputs.length - 1].focus();
        }, 0);
    }
}

async function openListingsFolder() {
    try {
        await fetch('/open-listings-folder', { method: 'POST' });
    } catch (e) {
        console.error(e);
    }
}

function openReportsModal() {
    const body = '<textarea id="reportTextArea" rows="6" placeholder="Type your report here..." style="width:100%; box-sizing:border-box; padding:8px; font-size:13px; resize:vertical; border:1px solid var(--border-color,#ccc); border-radius:4px;"></textarea>';
    showModal('Reports', body, [
        { text: 'Cancel', primary: false, onClick: closeModal },
        { text: 'OK', primary: true, onClick: submitReport }
    ]);
    setTimeout(() => { const ta = document.getElementById('reportTextArea'); if (ta) ta.focus(); }, 0);
}

async function submitReport() {
    const ta = document.getElementById('reportTextArea');
    const text = ta ? ta.value.trim() : '';
    if (!text) {
        customAlert('Please enter some report text.');
        return;
    }
    try {
        const resp = await fetch('/api/add-report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        const res = await resp.json();
        if (res.status === 'success') {
            customAlert('Report saved.');
        } else {
            customAlert('Error: ' + (res.message || 'Could not save report.'));
        }
    } catch (e) {
        console.error(e);
        customAlert('Error: could not reach the server.');
    }
}


// --- Hot Keys System ---
const HOTKEY_ACTIONS = [
    { id: 'menu', label: 'Open Menu', run: () => { const b = document.getElementById('hamburgerBtn'); if (b) b.click(); } },
    { id: 'wysiscan', label: 'WysiScan', run: () => runWysiScan() },
    { id: 'amazonAdds', label: 'Amazon Adds', run: () => openAddsAmazon() },
    { id: 'discogsAdds', label: 'Discogs Adds', run: () => openAddsDiscogs() },
    { id: 'calc', label: 'Cost Calculator', run: () => openCalcModal() },
    { id: 'conditionsBoth', label: 'Conditions (Both, Current Type)', run: () => openConditionsBothCurrentType() },
    { id: 'refresh', label: 'Refresh', run: () => location.reload(true) },
    { id: 'reports', label: 'Reports', run: () => openReportsModal() },
    { id: 'shutdown', label: 'Shut Down', run: () => shutdownApp() }
];
const HOTKEY_DEFAULTS = {
    menu: 'Ctrl+Shift+M',
    wysiscan: 'Ctrl+Shift+W',
    amazonAdds: 'Ctrl+Shift+A',
    discogsAdds: 'Ctrl+Shift+D',
    calc: 'Ctrl+Shift+C',
    conditionsBoth: 'Ctrl+Shift+K',
    refresh: 'F5',
    reports: 'Ctrl+Shift+R',
    shutdown: 'Ctrl+Shift+X'
};
const HOTKEY_STORAGE = 'wysiwyg_hotkeys';
let hotkeyCapture = null; // { id, btnEl } when capturing

function loadHotkeys() {
    try {
        const saved = localStorage.getItem(HOTKEY_STORAGE);
        if (saved) return Object.assign({}, HOTKEY_DEFAULTS, JSON.parse(saved));
    } catch (e) { /* ignore */ }
    return Object.assign({}, HOTKEY_DEFAULTS);
}

function saveHotkeys(map) {
    try { localStorage.setItem(HOTKEY_STORAGE, JSON.stringify(map)); } catch (e) { /* ignore */ }
}

function formatHotkey(parts) {
    if (!parts || !parts.length) return '—';
    const mods = [];
    if (parts.includes('Ctrl')) mods.push('Ctrl');
    if (parts.includes('Alt')) mods.push('Alt');
    if (parts.includes('Shift')) mods.push('Shift');
    const key = parts.find(p => !['Ctrl', 'Alt', 'Shift'].includes(p));
    return [...mods, key].filter(Boolean).join('+');
}

function hotkeyMatches(parts, e) {
    const combo = new Set(parts);
    const pressed = new Set();
    if (e.ctrlKey || e.metaKey) pressed.add('Ctrl');
    if (e.altKey) pressed.add('Alt');
    if (e.shiftKey) pressed.add('Shift');
    let key = e.key;
    if (key === ' ') key = 'Space';
    else if (key.length === 1) key = key.toUpperCase();
    pressed.add(key);
    // Must match exactly (same modifiers + key), ignoring extra modifiers.
    const reqMods = ['Ctrl', 'Alt', 'Shift'].filter(m => combo.has(m));
    const hasCtrl = combo.has('Ctrl');
    const hasAlt = combo.has('Alt');
    const hasShift = combo.has('Shift');
    if (e.ctrlKey !== hasCtrl) return false;
    if (e.altKey !== hasAlt) return false;
    if (e.shiftKey !== hasShift) return false;
    const comboKey = [...combo].find(p => !['Ctrl', 'Alt', 'Shift'].includes(p));
    let eKey = e.key;
    if (eKey === ' ') eKey = 'Space';
    else if (eKey.length === 1) eKey = eKey.toUpperCase();
    return eKey === comboKey;
}

function openHotkeysModal() {
    const modal = document.getElementById('hotkeysModal');
    const list = document.getElementById('hotkeysList');
    const map = loadHotkeys();
    list.innerHTML = '';
    HOTKEY_ACTIONS.forEach(action => {
        const row = document.createElement('div');
        row.className = 'hk-row';
        const label = document.createElement('span');
        label.className = 'hk-label';
        label.textContent = action.label;
        const btn = document.createElement('button');
        btn.className = 'hk-key-btn';
        btn.textContent = formatHotkey((map[action.id] || '').split('+'));
        btn.addEventListener('click', () => startHotkeyCapture(action.id, btn));
        row.appendChild(label);
        row.appendChild(btn);
        list.appendChild(row);
    });
    modal.style.display = 'flex';
}

function startHotkeyCapture(id, btnEl) {
    if (hotkeyCapture) cancelCapture();
    hotkeyCapture = { id, btnEl };
    document.querySelectorAll('.hk-key-btn.capturing').forEach(b => b.classList.remove('capturing'));
    btnEl.classList.add('capturing');
    btnEl.textContent = '…';
    const hint = document.getElementById('hotkeysHint');
    if (hint) hint.style.display = 'block';
}

function cancelCapture() {
    if (!hotkeyCapture) return;
    hotkeyCapture.btnEl.classList.remove('capturing');
    hotkeyCapture = null;
    const hint = document.getElementById('hotkeysHint');
    if (hint) hint.style.display = 'none';
    // Refresh the displayed keys
    const map = loadHotkeys();
    openHotkeysModal();
}

function commitCapture(e) {
    e.preventDefault();
    if (!hotkeyCapture) return;
    let key = e.key;
    if (key === ' ') key = 'Space';
    else if (key.length === 1) key = key.toUpperCase();
    // Ignore bare modifier presses
    if (['Control', 'Alt', 'Shift', 'Meta'].includes(e.key)) return;
    const parts = [];
    if (e.ctrlKey || e.metaKey) parts.push('Ctrl');
    if (e.altKey) parts.push('Alt');
    if (e.shiftKey) parts.push('Shift');
    parts.push(key);
    const combo = parts.join('+');
    const map = loadHotkeys();
    map[hotkeyCapture.id] = combo;
    saveHotkeys(map);
    cancelCapture();
}

function closeHotkeysModal() {
    if (hotkeyCapture) cancelCapture();
    const modal = document.getElementById('hotkeysModal');
    if (modal) modal.style.display = 'none';
}

function initHotkeys() {
    // Close buttons
    document.getElementById('closeHotkeysBtn')?.addEventListener('click', closeHotkeysModal);
    document.getElementById('closeHotkeysDoneBtn')?.addEventListener('click', closeHotkeysModal);
    document.getElementById('resetHotkeysBtn')?.addEventListener('click', () => {
        saveHotkeys(Object.assign({}, HOTKEY_DEFAULTS));
        openHotkeysModal();
    });
    // Global key handler
    document.addEventListener('keydown', (e) => {
        if (hotkeyCapture) {
            if (e.key === 'Escape') { e.__hotkeyEscape = true; cancelCapture(); return; }
            commitCapture(e);
            return;
        }
        // Don't fire hotkeys while typing in a form field (avoid misfires).
        const t = e.target;
        if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return;
        const map = loadHotkeys();
        for (const action of HOTKEY_ACTIONS) {
            const combo = map[action.id];
            if (combo && hotkeyMatches(combo.split('+'), e)) {
                e.preventDefault();
                action.run();
                return;
            }
        }
    });

    // Escape closes the topmost open modal / context menu
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape' || e.__hotkeyEscape) return;

        const menu = document.getElementById('customContextMenu');
        if (menu && menu.style.display !== 'none') {
            menu.style.display = 'none';
            e.preventDefault();
            return;
        }

        const openModals = Array.from(document.querySelectorAll('.modal'))
            .filter(m => m.style.display !== 'none' && getComputedStyle(m).display !== 'none');
        if (!openModals.length) return;

        openModals.sort((a, b) =>
            (parseInt(getComputedStyle(b).zIndex, 10) || 0) - (parseInt(getComputedStyle(a).zIndex, 10) || 0));
        const top = openModals[0];
        const closeBtn = top.querySelector('.close-btn');
        if (closeBtn) closeBtn.click();
        else top.style.display = 'none';
        e.preventDefault();
    });
}


// --- Custom Modal System ---
function showModal(title, bodyHtml, buttons) {
    const overlay = document.getElementById('genericModal');
    const titleEl = document.getElementById('genericModalTitle');
    const bodyEl = document.getElementById('genericModalBody');
    const actionsEl = document.getElementById('genericModalActions');

    titleEl.innerText = title;
    bodyEl.innerHTML = bodyHtml;
    actionsEl.innerHTML = '';

    buttons.forEach(btn => {
        const b = document.createElement('button');
        b.innerText = btn.text;
        b.style.cssText = "padding: 8px 15px; border-radius: 4px; cursor: pointer; border: none; font-weight: bold;";
        if (btn.primary) {
            b.style.backgroundColor = "var(--primary-color)";
            b.style.color = "white";
        } else {
            b.style.backgroundColor = "var(--secondary-color)";
            b.style.color = "white";
        }

        b.onclick = () => {
            overlay.style.display = 'none';
            if (btn.onClick) btn.onClick();
            // Return focus to the admin password box so a retry needs no click
            const pw = document.getElementById('passwordModal');
            if (pw && pw.style.display === 'block') {
                const inp = document.getElementById('adminPasswordInput');
                if (inp) { inp.focus(); inp.select(); }
            }
        };
        actionsEl.appendChild(b);
    });

    overlay.style.display = 'flex';
    // Focus the primary/OK button so Enter dismisses the dialog
    const actionBtns = actionsEl.querySelectorAll('button');
    const focusBtn = actionBtns[actionBtns.length - 1];
    if (focusBtn) setTimeout(() => focusBtn.focus(), 0);
}

function closeModal() {
    const overlay = document.getElementById('genericModal');
    if (overlay) overlay.style.display = 'none';
}

window.customHelp = function (msg) { showModal('Help', msg, [{ text: 'OK', primary: true }]); }; window.customAlert = function (msg) {
    showModal('Alert', msg, [{ text: 'OK', primary: true }]);
}

window.customConfirm = function (msg, onYes) {
    showModal('Confirm', msg, [
        { text: 'Cancel', primary: false },
        { text: 'Yes', primary: true, onClick: onYes }
    ]);
}

function openRequestModal() {
    document.getElementById('requestModal').style.display = 'block';
    document.getElementById('reqName').focus();
}

function closeRequestModal() {
    document.getElementById('requestModal').style.display = 'none';
}

// --- CALCULATOR MODAL ---
let costCalcData = null;
async function openCalcModal() {
    document.getElementById('calcModal').style.display = 'flex';

    // Load saved values instead of clearing
    document.getElementById('calcCompPrice').value = localStorage.getItem('wysiwyg_calc_comp_price') || '';
    document.getElementById('calcCompShip').value = localStorage.getItem('wysiwyg_calc_comp_ship') || '';
    document.getElementById('calcOurPrice').value = localStorage.getItem('wysiwyg_calc_our_price') || '';

    if (!costCalcData) {
        // Load condition data only once
        try {
            const resp = await fetch('/api/cost_calc.json');
            if (resp.ok) {
                const data = await resp.json();
                costCalcData = data.Cost_calulation || [];
                const sel = document.getElementById('calcCondition');
                sel.innerHTML = '';
                costCalcData.forEach(item => {
                    const opt = document.createElement('option');
                    if (item === "Like New") opt.selected = true; // Default to Like New
                    opt.value = item; opt.textContent = item;
                    sel.appendChild(opt);
                });
            }
        } catch (e) { console.error("Failed to load cost_calc.json", e); }
    }
}
function closeCalcModal() {
    document.getElementById('calcModal').style.display = 'none';
    // Clear calculated fields on close
    document.getElementById('calcCompTotal').value = '';
    document.getElementById('calcOurTotal').value = '';
}
function runCalculator() {
    const condition = document.getElementById('calcCondition').value;
    const compPrice = parseFloat(document.getElementById('calcCompPrice').value) || 0;
    const compShip = parseFloat(document.getElementById('calcCompShip').value) || 0;
    const compTotal = compPrice + compShip;

    let ourPrice = parseFloat(document.getElementById('calcOurPrice').value);

    if (condition === "Like New") {
        document.getElementById('calcCompTotal').value = compTotal.toFixed(2);

        if (isNaN(ourPrice)) {
            ourPrice = compTotal - 9;
            document.getElementById('calcOurPrice').value = ourPrice.toFixed(2);
        }

        document.getElementById('calcOurTotal').value = (ourPrice + 7).toFixed(2);
    }
}

// --- PERSISTENT VARIABLE CONDITIONS ---

function saveVariableConditions() {
    const mediaCondition = getVal('conditionOfMedia');
    const isOOP = document.getElementById('oopToggle').checked;

    // Persist to disk via the server (only succeeds when allpass.json is present).
    fetch('/api/save-variable-conditions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ media_condition: mediaCondition, is_oop: isOOP })
    }).catch(e => console.error('Failed to persist variable conditions:', e));

    // Also cache in localStorage for instant client-side restore.
    localStorage.setItem('wysiwyg_variable_media_condition', mediaCondition);
    localStorage.setItem('wysiwyg_variable_is_oop', String(isOOP));

    const btn = document.getElementById('saveVariableConditionsBtn');
    if (btn) {
        const originalHTML = btn.innerHTML;
        btn.innerHTML = '✅';
        setTimeout(() => {
            btn.innerHTML = originalHTML;
        }, 1500);
    }
}

async function loadVariableConditions() {
    // Prefer the persisted server value (allpass.json) when the admin file is present,
    // otherwise fall back to the localStorage cache.
    let mediaCondition = localStorage.getItem('wysiwyg_variable_media_condition') || "";
    let isOOP = localStorage.getItem('wysiwyg_variable_is_oop');

    try {
        const resp = await fetch('/api/variable-conditions?t=' + new Date().getTime());
        if (resp.ok) {
            const data = await resp.json();
            if (typeof data.media_condition === 'string') {
                mediaCondition = data.media_condition;
                // Mirror into localStorage so the cache stays in sync.
                localStorage.setItem('wysiwyg_variable_media_condition', mediaCondition);
            }
            if (typeof data.is_oop === 'boolean') {
                isOOP = String(data.is_oop);
                localStorage.setItem('wysiwyg_variable_is_oop', isOOP);
            }
        }
    } catch (e) {
        // Network error -> just use the localStorage cache.
    }

    if (mediaCondition) {
        const select = document.getElementById('conditionOfMedia');
        const modifiers = ['+', '-'];
        let baseValue = mediaCondition;
        let modifierValue = "";

        if (modifiers.includes(mediaCondition.slice(-1))) {
            baseValue = mediaCondition.slice(0, -1);
            modifierValue = mediaCondition.slice(-1);
        }
        select.value = baseValue;
        const radio = document.querySelector(`input[name="media_modifier"][value="${modifierValue}"]`);
        if (radio) {
            radio.checked = true;
        } else {
            // If modifier not found, check the "none" radio
            const noneRadio = document.querySelector('input[name="media_modifier"][value=""]');
            if (noneRadio) noneRadio.checked = true;
        }
    }

    if (isOOP !== null) {
        document.getElementById('oopToggle').checked = (isOOP === 'true');
    }
    updateDynamicColors();
}

// --- UI & FORM LOGIC ---

function resetLookup() {
    const ids = ['lookupArtist', 'lookupTitle', 'lookupUPC', 'lookupCat', 'lookupLabel'];
    ids.forEach(id => document.getElementById(id).value = "");
    document.getElementById('lookupFormat').selectedIndex = 0;
    document.getElementById('lookupCondition').selectedIndex = 0;
    document.getElementById('lookupResults').innerHTML = '<p style="text-align: center; color: #666;">Enter details above to see market data.</p>';
}

function populateDropdown(id, arr) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = '<option value="">-- None --</option>';
    arr.forEach(item => {
        const opt = document.createElement('option');
        opt.value = item; opt.textContent = item;
        el.appendChild(opt);
    });
}

function updateDynamicColors() {
    const mediaCond = document.getElementById('conditionOfMedia');
    const mediaDesc = document.getElementById('mediaDescriptionText');
    const sleeveCond = document.getElementById('sleeveCondition');
    const sleeveDesc = document.getElementById('sleeveDesc');

    // Media Logic
    if (!mediaCond.value) {
        mediaCond.classList.add('bg-media-red');
    } else {
        mediaCond.classList.remove('bg-media-red');
    }
    const mediaCondValue = mediaCond.value.toLowerCase();
    const mediaMod = document.querySelector('input[name="media_modifier"]:checked')?.value || "";

    const isFactory = mediaCondValue.includes('factory');
    const isSealed = mediaCondValue.includes('sealed');
    const isLikeNew = mediaCondValue.includes('used like new');
    const hasNMMinus = mediaCondValue.includes('(nm-)');
    const isExempt = isFactory || isSealed || (isLikeNew && mediaMod !== '-' && !hasNMMinus);

    mediaCond.style.border = "";

    if (mediaCond.value && !isExempt) {
        mediaDesc.classList.add('bg-media-red');
        mediaDesc.title = "Description required for this media condition.";
        mediaCond.style.border = "2px solid var(--danger-color)";
    } else {
        mediaDesc.classList.remove('bg-media-red');
        mediaDesc.title = "";
    }

    // Visual indicator for modifiers
    document.querySelectorAll('input[name="media_modifier"]').forEach(r => {
        r.parentElement.style.border = "1px solid transparent";
        r.parentElement.style.borderRadius = "4px";
        r.parentElement.style.backgroundColor = "transparent";
    });

    if (isLikeNew && !hasNMMinus && !isFactory && !isSealed) {
        const minusRadio = document.querySelector('input[name="media_modifier"][value="-"]');
        if (minusRadio) {
            minusRadio.parentElement.style.border = "1px solid var(--danger-color)";
            minusRadio.parentElement.style.backgroundColor = "rgba(220, 53, 69, 0.1)";
            minusRadio.parentElement.title = "Selecting this will require a description";
        }
    }

    // Sleeve Logic
    if (!sleeveCond.value) {
        sleeveCond.classList.add('bg-sleeve-red');
    } else {
        sleeveCond.classList.remove('bg-sleeve-red');
    }
    sleeveCond.style.border = "";
    if (sleeveCond.value && (sleeveCond.value.toLowerCase().includes('good') || sleeveCond.value.toLowerCase().includes('acceptable') || sleeveCond.value.toLowerCase().includes('(nm-)'))) {
        sleeveDesc.classList.add('bg-sleeve-red');
        sleeveDesc.title = "Description required for sleeve conditions of 'Good', 'Acceptable', or 'Near Mint (NM-)'.";
        sleeveCond.style.border = "2px solid var(--sleeve-border-color)";
    } else {
        sleeveDesc.classList.remove('bg-sleeve-red');
        sleeveDesc.title = "";
    }

    // SKU Flags Logic
    const skuSelect = document.getElementById('skuFlag');
    if (skuSelect) {
        if (skuSelect.value === "") {
            skuSelect.classList.remove('sku-flag-selected');
        } else {
            skuSelect.classList.add('sku-flag-selected');
        }
    }
}

let storedPasswords = {};
async function submitPassword() {
    const input = document.getElementById('adminPasswordInput').value;

    // Verify server-side so passwords can be stored hashed (PBKDF2) in allpass.json.
    try {
        const resp = await fetch('/api/verify-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: input })
        });
        if (resp.ok) {
            const res = await resp.json();
            if (res.role === 'editor') { window.open('editor', '_blank'); closePasswordModal(); return; }
            if (res.role === 'admin') { window.open('admin', '_blank'); closePasswordModal(); return; }
            customAlert("Incorrect password.");
            return;
        }
    } catch (e) { /* fall through to legacy local check */ }

    // Legacy fallback: plaintext values already loaded from allpass.json
    if (input === storedPasswords.editor) {
        window.open('editor', '_blank');
        closePasswordModal();
    } else if (storedPasswords.admin && input === storedPasswords.admin) {
        window.open('admin', '_blank');
        closePasswordModal();
    } else {
        customAlert("Incorrect password.");
    }
}

function closePasswordModal() {
    document.getElementById('passwordModal').style.display = 'none';
    storedPasswords = {};
}

function toggleTheme() {
    const body = document.body;
    const isDark = body.getAttribute('data-theme') === 'dark';
    if (isDark) {
        body.removeAttribute('data-theme');
        localStorage.setItem('wysiwyg_theme', 'light');
    } else {
        body.setAttribute('data-theme', 'dark');
        localStorage.setItem('wysiwyg_theme', 'dark');
    }
}

function getVal(id) {
    const el = document.getElementById(id);
    if (!el) return "";
    if (el.multiple) {
        let joiner = ' ';
        if (id === 'edition') {
            const selected = Array.from(el.selectedOptions).map(o => o.value).filter(v => v);
            const slashGroup = (data && data["Slash Separated Editions"]) ? data["Slash Separated Editions"] : ["Deluxe Edition", "Limited Edition", "Special Edition", "Club Edition"];

            const foundSlash = selected.filter(s => slashGroup.includes(s));
            const foundSpace = selected.filter(s => !slashGroup.includes(s));

            let parts = [];
            if (foundSlash.length > 0) {
                const prefixes = foundSlash.map(t => t.replace(" Edition", ""));
                parts.push(prefixes.join(" / ") + " Edition");
            }
            if (foundSpace.length > 0) parts.push(foundSpace.join(" "));

            return parts.join(" ");
        } else if (id === 'packagingFeature') joiner = ' & ';
        else if (id === 'sleevePackaging') joiner = ' / ';
        return Array.from(el.selectedOptions).map(o => o.value).filter(v => v).join(joiner);
    }
    if (id === 'conditionOfMedia') {
        const mod = document.querySelector('input[name="media_modifier"]:checked')?.value || "";
        return el.value ? el.value + mod : "";
    }
    if (id === 'sleeveCondition') {
        const mod = document.querySelector('input[name="sleeve_modifier"]:checked')?.value || "";
        const base = document.getElementById('sleeveCondition').value;
        return base ? base + mod : "";
    }
    return el.value.trim();
}

async function fullReset(opts) {
    const keepUrl = !!(opts && opts.keepUrl === true);
    const inputs = document.querySelectorAll('input[type="text"]:not(#boxNumber):not(#lister), input[type="url"], textarea:not(#outputDesc)');
    inputs.forEach(input => {
        // A scrape-triggered reset must not wipe the URL it is about to use.
        if (keepUrl && input.id === 'discogsUrlInput') return;
        input.value = "";
    });
    const selects = document.querySelectorAll('select:not(#skuFlag)');
    selects.forEach(sel => {
        Array.from(sel.options).forEach(opt => {
            opt.selected = (opt.value === "");
        });
    });
    document.querySelectorAll('input[type="radio"][value=""]').forEach(rad => rad.checked = true);
    document.getElementById('oopToggle').checked = false;
    const customOpts = document.getElementById('customOptions');
    if (customOpts) Array.from(customOpts.options).forEach(opt => opt.selected = false);
    document.getElementById('outputSku').value = "";
    document.getElementById('outputDesc').value = "";
    if (document.getElementById('lockSku')) document.getElementById('lockSku').checked = false;
    if (document.getElementById('lockDesc')) document.getElementById('lockDesc').checked = false;

    // Clear Details Tab Elements
    document.getElementById('htmlPreview').innerHTML = "";
    document.getElementById('scraperOutput').innerHTML = "";
    document.getElementById('scraperError').innerHTML = "";

    clearCurrentItem(); // Clear the blue-bar last-item indicator on Reset All

    loadProfile(); // Revert to profile settings first (box, lister, skuFlag)
    loadVariableConditions(); // Restore saved variables after reset
    updateDynamicColors(); // Update dynamic colors using the restored values
    // Packaging may have changed (or been cleared), so re-pick the sleeve list:
    // a box set shows Box Sleeve conditions, anything else the media type's own.
    renderConditionMultiselects();
}

function saveProfile() {
    const box = document.getElementById('boxNumber').value;
    const init = document.getElementById('lister').value;
    const skuFlag = document.getElementById('skuFlag') ? document.getElementById('skuFlag').value : '';
    localStorage.setItem('wysiwyg_profile_box', box);
    localStorage.setItem('wysiwyg_profile_init', init);
    localStorage.setItem('wysiwyg_profile_sku_flag', skuFlag);
    customAlert("Profile Saved!");
}

function loadProfile() {
    const box = localStorage.getItem('wysiwyg_profile_box');
    const init = localStorage.getItem('wysiwyg_profile_init');
    if (box) document.getElementById('boxNumber').value = box;
    if (init) document.getElementById('lister').value = init;
    const skuFlag = localStorage.getItem('wysiwyg_profile_sku_flag') || "";
    if (document.getElementById('skuFlag')) {
        document.getElementById('skuFlag').value = skuFlag;
    }
}

window.loadHistoryItem = function (rawText) {
    document.querySelector('[data-tab="listingTool"]').click();
    setTimeout(() => { parsePastedData(rawText.replace(/\\n/g, '\n')); }, 150);
}

function parsePastedData(input) {
    if (!input) return;

    // 1. Reset Selects
    document.querySelectorAll('select:not(#skuFlag)').forEach(sel => {
        if (sel.multiple) Array.from(sel.options).forEach(opt => opt.selected = false);
        else sel.selectedIndex = 0;
    });

    // Restore skuFlag from profile
    const savedSkuFlag = localStorage.getItem('wysiwyg_profile_sku_flag') || "";
    if (document.getElementById('skuFlag')) {
        document.getElementById('skuFlag').value = savedSkuFlag;
    }

    // 2. Clear Description Field
    document.getElementById('mediaDescriptionText').value = "";
    document.getElementById('mediaColor').value = "";

    // 3. Reset Radio Buttons
    document.querySelectorAll('input[type="radio"][value=""]').forEach(rad => rad.checked = true);

    // 4. Clear Additional Fields
    document.getElementById('recordLabel').value = "";
    document.getElementById('Year').value = "";
    document.getElementById('country').value = "";
    document.getElementById('oopToggle').checked = false;
    document.getElementById('sleeveDesc').value = "";
    const customOpts = document.getElementById('customOptions');
    if (customOpts) Array.from(customOpts.options).forEach(opt => opt.selected = false);

    const lines = input.split('\n');
    lines.forEach(line => {
        const clean = line.replace(/\*/g, '').trim();
        const lower = clean.toLowerCase();

        if (lower.startsWith('label:')) {
            const val = clean.substring(clean.indexOf(':') + 1).trim();
            document.getElementById('recordLabel').value = val;
        }
        if (lower.startsWith('format:')) {
            const fStr = clean.split(':')[1].trim();

            let expandedFStr = fStr;
            const slashEditionRegex = /([\w\s/]+)\s(Edition)/gi;
            let match;
            // This loop is safe because we replace the matched part, preventing infinite loops on the same source string.
            while ((match = slashEditionRegex.exec(fStr)) !== null) {
                const prefixesPart = match[1]; // e.g., "Deluxe / Limited"
                const suffix = match[2]; // "Edition"
                if (prefixesPart.includes(' / ')) {
                    const prefixes = prefixesPart.split(' / ').map(p => p.trim());
                    const expandedTags = prefixes.map(p => p + " " + suffix).join(' '); // "Deluxe Edition Limited Edition"
                    expandedFStr = expandedFStr.replace(match[0], expandedTags);
                }
            }
            const formatLineEl = document.getElementById('formatLine');
            if (formatLineEl) formatLineEl.innerText = expandedFStr;
            const fLower = expandedFStr.toLowerCase();

            // Media Format Logic: Longest Match Wins
            const mSel = document.getElementById('mediaFormat');
            if (mSel) {
                const opts = Array.from(mSel.options).map(o => o.value).filter(v => v);
                // Sort by length descending to prioritize specific formats (e.g. "DVD-Video" over "DVD")
                opts.sort((a, b) => b.length - a.length);

                for (const optVal of opts) {
                    const safeVal = optVal.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                    if (new RegExp("(^|\\W|\\d+x)" + safeVal + "(\\W|$)", "i").test(fLower)) {
                        mSel.value = optVal;
                        break;
                    }
                }
                
                // Auto-populate Media Type dropdown for condition multiselects based on media format
                const conditionMediaTypeSelect = document.getElementById('conditionMediaType');
                if (conditionMediaTypeSelect) {
                    const selectedFormat = mSel.value;
                    let conditionMediaType = 'lp'; // default
                    
                    if (selectedFormat.includes('Vinyl') || selectedFormat.includes('LP') || selectedFormat === 'Vinyl') {
                        conditionMediaType = 'lp';
                    } else if (selectedFormat.includes('CD') || selectedFormat.includes('SACD') || selectedFormat.includes('DVD') || selectedFormat.includes('Blu-ray') || selectedFormat.includes('HD DVD') || selectedFormat.includes('Minidisc')) {
                        conditionMediaType = 'cd';
                    } else if (selectedFormat.includes('Cassette')) {
                        conditionMediaType = 'cassette';
                    }
                    
                    conditionMediaTypeSelect.value = conditionMediaType;
                    currentConditionMediaType = conditionMediaType;
                    
                    // Update modal category to match
                    const modalCatSelect = document.getElementById('modalCategorySelect');
                    if (modalCatSelect) modalCatSelect.value = conditionMediaType;
                    currentModalCategory = conditionMediaType;
                    
                    // Re-render condition multiselects with new media type
                    renderConditionMultiselects();
                }
            }

            ['formatTags', 'edition', 'preFM', 'postFM', 'packagingFeature', 'sleevePackaging', 'weightSpeed'].forEach(id => {
                const sel = document.getElementById(id);
                if (sel) {
                    Array.from(sel.options).forEach(opt => {
                        // Use regex for word boundary check to prevent "Repress" selecting "EP"
                        const val = opt.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                        if (opt.value && new RegExp("(^|\\W|\\d+x)" + val + "(\\W|$)", "i").test(fLower)) opt.selected = true;
                    });

                    // Fix for Maxi-Single triggering Single
                    if (id === 'formatTags' || id === 'postFM') {
                        const hasMaxi = Array.from(sel.selectedOptions).some(o => o.value.toLowerCase().includes('maxi') && o.value.toLowerCase().includes('single'));
                        if (hasMaxi) {
                            Array.from(sel.options).forEach(opt => {
                                if (opt.value.toLowerCase() === 'single') opt.selected = false;
                            });
                        }
                    }
                }
            });

            // Box Set switches the sleeve conditions to their own list, so this
            // has to re-render after the packaging values above were selected.
            renderConditionMultiselects();

            // Extract Colors to Media Description
            const colors = (data && data['Color']) ? data['Color'] : ["Gold", "Silver", "Clear", "Red", "Blue", "White", "Green", "Yellow", "Pink", "Orange", "Purple", "Splatter", "Swirl", "Marble", "Teal", "Turquoise", "Black", "Brown", "Grey", "Gray", "Coke Bottle", "Translucent", "Transparent", "Crystal", "Rainbow", "Glow In The Dark", "Glow-in-the-Dark", "Glow", "Beige", "Cream", "Tan", "Violet", "Burgundy", "Magenta", "Peach", "Lime", "Rose", "Amber", "Neon"];

            const parts = fStr.split(',').map(p => p.trim());
            const foundColors = [];

            parts.forEach(part => {
                colors.forEach(c => {
                    if (new RegExp("\\b" + c + "\\b", "i").test(part)) {
                        if (!foundColors.includes(c)) foundColors.push(c);
                    }
                });
            });

            if (foundColors.length > 0) {
                document.getElementById('mediaColor').value = foundColors.join(' & ');
            }
        }
        if (lower.startsWith('country:')) {
            const c = clean.split(':')[1].trim();
            document.getElementById('country').value = (c === "US") ? "USA" : c;
        }
        if (lower.startsWith('released:')) {
            const yr = clean.match(/\d{4}/);
            if (yr) document.getElementById('Year').value = yr[0];
        }
        if (lower.startsWith('track count:')) {
            document.getElementById('trackTimeInfo').value = clean.split(':')[1].trim();
        }
    });
    updateDynamicColors();
    loadVariableConditions(); // Restore saved variables after paste/parse
    updateDynamicColors();
}

function generateListingData() {
    // 1. Gather Inputs
    const inputs = {
        mediaCond: getVal('conditionOfMedia') || "",
        sleeveCond: getVal('sleeveCondition') || "",
        country: getVal('country').trim(),
        formatLineRaw: document.getElementById('formatLine')?.innerText || "",
        mediaDesc: document.getElementById('mediaDescriptionText').value.trim() || "",
        colorVal: document.getElementById('mediaColor').value.trim(),
        preFM: getVal('preFM'),
        weightSpeed: getVal('weightSpeed'),
        mediaFormat: getVal('mediaFormat') || "",
        postFM: getVal('postFM') || "",
        sleevePkg: getVal('sleevePackaging'),
        formatLineRaw: document.getElementById('formatLine')?.innerText || "",
        pkgFeature: getVal('packagingFeature'),
        edition: getVal('edition'),
        formatTags: getVal('formatTags'),
        year: getVal('Year'),
        label: getVal('recordLabel'),
        trackTime: getVal('trackTimeInfo'),
        sleeveDesc: getVal('sleeveDesc'),
        boxNumber: document.getElementById('boxNumber').value || '8094',
        lister: document.getElementById('lister').value || 'XX',
        skuFlag: getVal('skuFlag'),
        isOOP: document.getElementById('oopToggle').checked,
        customOptionsSelected: [
            ...Array.from(document.getElementById('lpOptions')?.selectedOptions || []).map(o => o.value),
            ...Array.from(document.getElementById('cdOptions')?.selectedOptions || []).map(o => o.value),
            ...Array.from(document.getElementById('customOptions')?.selectedOptions || []).map(o => o.value),
            ...Array.from(document.getElementById('boxSleeveOptions')?.selectedOptions || []).map(o => o.value)
        ],
        mediaCustomOptionsSelected: [
            ...Array.from(document.getElementById('mediaConditionOptions')?.selectedOptions || []).map(o => o.value)
        ]
    };

    // 2. Process Logic
    const processedCountry = processCountry(inputs.country);
    const fmtData = processFormatData(inputs);

    // 3. Assemble Description
    const desc = assembleDescription(inputs, processedCountry, fmtData);

    // 4. Generate SKU
    const skuCode = inferSkuCode(inputs.formatLineRaw, inputs.mediaFormat, inputs.sleevePkg);
    const sku = generateSku(inputs.boxNumber, inputs.lister, skuCode, inputs.mediaCond, inputs.skuFlag);

    // 5. Output & Copy
    handleOutput(sku, desc, inputs.isOOP, inputs.skuFlag);
}

// --- Helper Functions ---

function processCountry(country) {
    const hasMultipleCountries = /[&,]/.test(country);

    if (hasMultipleCountries) {
        country = country.replace(/\bUS\b/gi, 'USA');
        const countries = country.split(/[&,]/).map(c => c.trim()).filter(c => c);
        const hasUSA = countries.some(c => /^(US|USA)$/i.test(c));
        if (countries.length === 2) {
            country = countries.join(' & ');
        } else if (countries.length >= 3) {
            const last = countries.pop();
            country = countries.join(' ') + ' & ' + last;
        } else {
            country = countries.join(' & ');
        }

        if (country && country !== "USA & Canada" && !hasUSA) {
            country += " Import";
        }
    } else {
        if (country.toUpperCase() === "US") country = "USA";

        if (country && country.toUpperCase() !== "USA" && country.toLowerCase() !== "worldwide") {
            const adjectives = {
                "Europe": "European", "Germany": "German", "France": "French",
                "Japan": "Japanese", "Canada": "Canadian", "Australia": "Australian",
                "Italy": "Italian", "Spain": "Spanish", "Netherlands": "Dutch",
                "Holland": "Dutch", "Sweden": "Swedish", "Russia": "Russian",
                "Brazil": "Brazilian", "Mexico": "Mexican", "China": "Chinese",
                "Korea": "Korean", "South Korea": "South Korean", "Poland": "Polish",
                "Greece": "Greek", "Norway": "Norwegian", "Denmark": "Danish",
                "Finland": "Finnish", "Ireland": "Irish", "Portugal": "Portuguese",
                "Belgium": "Belgian", "Austria": "Austrian", "Switzerland": "Swiss",
                "UK & Europe": "UK & European", "UK": "UK"
            };
            const key = Object.keys(adjectives).find(k => k.toLowerCase() === country.toLowerCase());
            if (key) {
                country = adjectives[key];
            } else {
                const cLow = country.toLowerCase();
                if (cLow.endsWith("any")) country = country.slice(0, -1) + "an";
                else if (cLow.endsWith("ly")) country = country.slice(0, -1) + "ian";
                else if (cLow.endsWith("ada")) country = country.slice(0, -1) + "ian";
                else if (cLow.endsWith("a")) country = country + "n";
                else if (cLow.endsWith("ain")) country = country.slice(0, -3) + "anish";
                else if (cLow.endsWith("pan")) country = country + "ese";
                else if (cLow.endsWith("o")) country = country + "an";
                else if (cLow.endsWith("il")) country = country + "ian";
            }
            country += " Import";
        }
    }
    return country;
}

function processFormatData(inputs) {
    let { formatLineRaw, mediaDesc, colorVal, preFM, weightSpeed, mediaFormat, postFM, sleevePkg, pkgFeature, edition, formatTags, customOptionsSelected, sleeveDesc, sleeveCond, mediaCustomOptionsSelected } = inputs;

    // Sleeve description always reads as "with <text>": prefix it unless it already
    // starts with "with"/"With" (in which case just normalize that word to lowercase).
    if (sleeveDesc && sleeveDesc.trim() !== "") {
        const withoutWith = sleeveDesc.trim().replace(/^with\b\s*/i, "");
        sleeveDesc = withoutWith ? "with " + withoutWith : "with";
    }

    // Color
    let colorPhrase = colorVal ? `Colored (${colorVal})` : "";

    // Pre-FM & Media Format
    let extractedPreFM = "";
    let isActuallyLP = false;

    const qtyMatch = formatLineRaw.match(/(\d+x)/i);
    let quantityPrefix = qtyMatch ? qtyMatch[0] : "";

    const sizeMatch = formatLineRaw.match(/(\d{1,2}"|\bLP\b|\d+xLP|\bEP\b|\d+xEP|\bAlbum\b)/i);
    if (sizeMatch) {
        let sizeText = sizeMatch[0].toUpperCase();
        if (sizeText === "ALBUM" || sizeText === "LP") isActuallyLP = true;
        if (!preFM && sizeText !== "ALBUM") extractedPreFM = sizeText;
    }
    if (preFM) {
        extractedPreFM = preFM;
        if (preFM === "LP") isActuallyLP = true;
    }

    let mFormatDisplay = mediaFormat;
    if (mediaFormat === "Vinyl") {
        const isEP = extractedPreFM === "EP" || /\bep\b/i.test(formatLineRaw) || /\bep\b/i.test(postFM);
        // Removed extractedPreFM.includes('"') so 12" doesn't force LP
        const hasLP = isActuallyLP || extractedPreFM.includes("LP") || formatLineRaw.toLowerCase().includes("lp");

        if (hasLP) {
            mFormatDisplay = "LP Vinyl";
            if (extractedPreFM.includes("EP")) {
                extractedPreFM = extractedPreFM.replace(/\bEP\b/gi, '').trim();
            }
        }
    }

    if (quantityPrefix) {
        // If we have a size (PreFM) and it's Vinyl, put 2x on the size (2x12")
        if (extractedPreFM && mediaFormat === "Vinyl" && !mFormatDisplay.includes("LP")) {
            if (!extractedPreFM.includes(quantityPrefix)) {
                extractedPreFM = quantityPrefix + extractedPreFM;
            }
        } else if (!mFormatDisplay.includes(quantityPrefix)) {
            mFormatDisplay = quantityPrefix + mFormatDisplay;
        }
    }
    if (extractedPreFM && mFormatDisplay.toLowerCase().includes(extractedPreFM.toLowerCase())) {
        extractedPreFM = "";
    }

    // Sleeve Type Label
    let sleeveTypeLabel = "";
    // Text from the sleeve description + every selected sleeve condition.
    // "Insert" mentioned anywhere -> CD label is just "Artwork".
    // "Jcard"/"J-card"/"J Card" mentioned anywhere -> cassette label is "Artwork".
    // "sleeve" mentioned anywhere -> LP label is "Artwork" (never repeat "Sleeve").
    const sleeveConditionText = (customOptionsSelected || []).map(value => {
        try {
            const opt = JSON.parse(value);
            return `${opt.title || ''} ${opt.text || ''}`;
        } catch (e) {
            return String(value);
        }
    }).join(' ');
    const sleeveTextForRules = `${sleeveDesc || ''} ${sleeveConditionText}`;
    const sleeveMentionsInsert = /insert/i.test(sleeveTextForRules);
    const sleeveMentionsJcard = /j[\s-]?card/i.test(sleeveTextForRules);
    const sleeveMentionsSleeve = /\bsleeves?\b/i.test(sleeveTextForRules);
    if (sleeveCond.trim() !== "" && !sleevePkg) {
        if (mediaFormat === "Vinyl") sleeveTypeLabel = sleeveMentionsSleeve ? "Artwork" : "Sleeve";
        else if (mediaFormat.includes("CD") || mediaFormat.includes("DVD") || mediaFormat.includes("Blu-ray")) {
            if (sleeveMentionsInsert) {
                sleeveTypeLabel = "Artwork";
            } else {
                sleeveTypeLabel = "Artwork / Insert";
            }
        }
        else if (mediaFormat === "Cassette") sleeveTypeLabel = sleeveMentionsJcard ? "Artwork" : "JCard";
    }

    if (pkgFeature) pkgFeature = "with " + pkgFeature;
    mediaDesc = mediaDesc.replace(/[,;]/g, ' ').replace(/\s\s+/g, ' ').trim();

    // Format String Construction
    let finalFormatString = "";
    if (formatLineRaw.includes(" + ")) {
        let complex = formatLineRaw;

        let editions = [];
        const editionEl = document.getElementById('edition');
        if (editionEl) {
            editions = Array.from(editionEl.selectedOptions).map(o => o.value);
        } else {
            editions = edition.split(' / ');
        }

        editions.forEach(ed => {
            if (ed) {
                const regex = new RegExp(ed + "[,\\s]*", "gi");
                complex = complex.replace(regex, '');
            }
        });
        complex = complex.replace(/,\s*,/g, ',').replace(/^[\s,]+|[\s,]+$/g, '').trim();

        // Inject Color formatting in-place for complex formats
        if (colorVal) {
            const colors = colorVal.split(/[&,]/).map(c => c.trim()).filter(c => c);
            colors.forEach(c => {
                const regex = new RegExp(`(?<!Colored \\()\\b${c}\\b`, 'gi');
                complex = complex.replace(regex, `Colored (${c})`);
            });
        }
        finalFormatString = complex;
    } else {
        finalFormatString = [formatTags, weightSpeed, colorPhrase, extractedPreFM, mFormatDisplay, postFM].filter(x => x).join(' ');
    }
    finalFormatString = finalFormatString.replace(/Maxi-Single\s+Single/gi, "Maxi-Single").replace(/Maxi\s+Single\s+Single/gi, "Maxi Single");
    finalFormatString = finalFormatString.replace(/(\d+x)\s+/gi, '$1');
    finalFormatString = finalFormatString.replace(/,/g, '').replace(/\s\s+/g, ' ').trim();

    // Deduplicate Box Set if present in Sleeve Packaging
    if (sleevePkg && sleevePkg.toLowerCase().includes("box set")) {
        finalFormatString = finalFormatString.replace(/\bBox Set\b/gi, "").replace(/\s\s+/g, ' ').trim();
    }

    // Deduplicate Digipak if present in Sleeve Packaging
    if (sleevePkg && sleevePkg.toLowerCase().includes("digipak")) {
        finalFormatString = finalFormatString.replace(/\bDigipak\b/gi, "").replace(/\s\s+/g, ' ').trim();
    }

    // Triggerable sleeve-packaging terms that reappear in the sleeve description
    // or sleeve multiselect collapse to "Artwork" (same rule as Jcard/Sleeve):
    // packaging "Digipak" + flaw "to Digipak" -> "Artwork with ... to Digipak".
    if (sleevePkg) {
        const packagingTerms = ['Cardboard Sleeve', 'Card Sleeve', 'Cardsleeve', 'Digipak'];
        const matchedTerm = packagingTerms.find(term => {
            const re = new RegExp(`\\b${term}\\b`, 'i');
            return re.test(sleevePkg) && re.test(sleeveTextForRules);
        });
        if (matchedTerm) {
            sleevePkg = sleevePkg.replace(new RegExp(`\\b${matchedTerm}\\b`, 'gi'), 'Artwork');
        }
    }

    // Edition Logic
    // (Handled in getVal)

    // Custom Options Logic
    // Build the flaw string: first item uses " & ", subsequent items use " / "
    let conditionPhrase = ""; // will be placed contextually in the assembled string

    // --- 1. Collect media entries: text box text first, then multiselect flaws ---
    const hasMediaDesc = mediaDesc && mediaDesc.trim() !== "";
    const hasMediaCustomOptions = mediaCustomOptionsSelected && mediaCustomOptionsSelected.length > 0;
    let mediaEntries = hasMediaDesc ? [capitalizeFlawContext(stripLeadingWith(mediaDesc))] : [];
    let mediaFinalSale = "";

    if (hasMediaCustomOptions) {
        mediaCustomOptionsSelected.forEach(optJson => {
            try {
                const opt = JSON.parse(optJson);
                if (opt.title === "Final Sale") {
                    mediaFinalSale = (mediaFinalSale ? mediaFinalSale + " " : "") + opt.text;
                } else {
                    if (opt.text) mediaEntries.push(capitalizeFlawContext(opt.text));
                    else mediaEntries.push(capitalizeFlawContext(opt.title));
                }
            } catch (e) { }
        });
    }

    // Text box content is consumed into mediaconditionPhrase below
    if (hasMediaDesc) mediaDesc = "";
    const hasMediaContent = mediaEntries.length > 0 || mediaFinalSale !== "";

    // --- 2. Collect sleeve entries ---
    let sleeveEntries = [];
    if (customOptionsSelected && customOptionsSelected.length > 0) {
        customOptionsSelected.forEach(optJson => {
            try {
                const opt = JSON.parse(optJson);
                if (opt.title === "Final Sale") {
                    // Exception to the media-first rule: Final Sale from the
                    // sleeve multiselect keeps its leading position on the
                    // format string (appended bare, ahead of everything else).
                    finalFormatString += " " + opt.text;
                } else {
                    if (opt.text) sleeveEntries.push(capitalizeFlawContext(opt.text));
                    else sleeveEntries.push(capitalizeFlawContext(opt.title));
                }
            } catch (e) { }
        });
    }

    // --- 3. Place sleeve entries (description text + multiselect flaws grouped together) ---
    const hasSleeveCondition = sleeveCond && sleeveCond.trim() !== "";
    const hasSleeveDesc = sleeveDesc && sleeveDesc.trim() !== "";

    let sleeveEntriesAll = [...sleeveEntries];
    // Sleeve flaws appended to the media phrase — grouped on their own so they
    // never merge with media flaws.
    let sleeveFlawsForMedia = [];

    if (hasSleeveDesc) {
        // The description carries a "with " prefix from the size/condition rules;
        // strip it for grouping with the multiselect flaws, re-added below.
        const sleeveDescCore = capitalizeFlawContext(stripLeadingWith(sleeveDesc));
        if (sleeveDescCore) sleeveEntriesAll.unshift(sleeveDescCore);
    }

    if (sleeveEntriesAll.length > 0) {
        // Group flaws to combine duplicates / shared prefixes and contexts
        // (e.g. "water damage to Booklet/Inlay").
        const groupedSleeve = groupFlaws(sleeveEntriesAll);

        // Join: 1 item bare, 2 items with " & ", 3+ items "A / B & C"
        const combinedSleeve = joinFlawItems(groupedSleeve);

        if (hasSleeveDesc) {
            // Description text (grouped with any matching sleeve multiselect
            // flaws) stays in the sleeve-description slot.
            sleeveDesc = /^with\s/i.test(combinedSleeve) ? combinedSleeve : "with " + combinedSleeve;
        } else if (hasSleeveCondition) {
            // Sleeve cond set + sleeve desc BLANK -> goes AFTER sleevePkg.
            // Store in conditionPhrase; assembleDescription will place it after sleevePkg.
            conditionPhrase = combinedSleeve;
        } else if (sleevePkg) {
            // If there is a sleeve pack but no sleeve condition, attach
            // the condition options directly to the sleeve pack.
            sleevePkg += " with " + combinedSleeve;
        } else if (hasMediaContent) {
            // Media-first rule: the text box text / media multiselect choices
            // lead, and the sleeve multiselect choices follow them inside
            // mediaconditionPhrase instead of landing on the format string.
            // Kept separate so sleeve flaws never group with media flaws.
            sleeveFlawsForMedia = groupedSleeve;
        } else if (postFM) {
            finalFormatString += " with " + combinedSleeve;
        } else {
            finalFormatString += " with " + combinedSleeve;
        }
    }

    // --- 4. Build mediaconditionPhrase from the media entries ---
    // The Media Description text box text is the FIRST entry when entered; the
    // Media Condition multiselect choices follow, then any sleeve multiselect
    // choices appended by rule 3 (media always precedes sleeve content).
    // The phrase region gets exactly ONE "with ": it is added only when the
    // phrase does not already start with one AND the text immediately before
    // it does not already end in a with-clause.
    let mediaconditionPhrase = "";
    if (mediaEntries.length > 0 || sleeveFlawsForMedia.length > 0) {
        // Media and sleeve flaws are grouped separately (no cross-grouping),
        // then presented media-first.
        const groupedMedia = [...groupFlaws(mediaEntries), ...sleeveFlawsForMedia];

        // Join: 1 item bare, 2 items with " & ", 3+ items "A / B & C"
        let flawPhrase = joinFlawItems(groupedMedia);

        const priorEndsWithWith = /\swith\s\S/i.test(finalFormatString);
        if (!/^with\s/i.test(flawPhrase) && !priorEndsWithWith) {
            flawPhrase = "with " + flawPhrase;
        }

        mediaconditionPhrase = flawPhrase;
    }

    // Final Sale from the media multiselect keeps its bare leading text,
    // ahead of the flaw portion
    if (mediaFinalSale) {
        mediaconditionPhrase = mediaconditionPhrase
            ? mediaFinalSale + " " + mediaconditionPhrase
            : mediaFinalSale;
    }

    // A "Gatefold" packaging only needs its noun when another sleeve attribute
    // follows it: "Very Good Gatefold Sleeve with Corner creasing". With no
    // sleeve condition, no sleeve description and no sleeve flaws it stays bare
    // ("... LP Vinyl Gatefold is Out-of-Print ..."). The lookahead stops an
    // existing "Gatefold Sleeve" from becoming "Gatefold Sleeve Sleeve".
    const sleeveHasContent = hasSleeveCondition || hasSleeveDesc || sleeveEntriesAll.length > 0;
    if (sleevePkg && sleeveHasContent && /gatefold/i.test(sleevePkg)) {
        sleevePkg = sleevePkg.replace(/gatefold(?!\s*sleeve)/ig, 'Gatefold Sleeve');
    }

    return {
        finalFormatString,
        sleeveTypeLabel,
        sleevePkg,
        mediaDesc,
        sleeveDesc,
        pkgFeature,
        edition,
        conditionPhrase,
        mediaconditionPhrase
    };
}

function assembleDescription(inputs, country, fmtData) {
    let parts;

    // A bare "Gatefold" sleeve condition needs its noun, otherwise the sentence
    // reads "... LP Vinyl Gatefold with light Cellophane tearing". Only the
    // no-sleeve-description path is touched (fmtData.conditionPhrase is set only
    // then) - with a sleeve description the formatting stays exactly as it was.
    let sleeveCondText = inputs.sleeveCond;
    if (fmtData.conditionPhrase && /gatefold/i.test(sleeveCondText || '')) {
        sleeveCondText = String(sleeveCondText).replace(/gatefold(?!\s*sleeve)/ig, 'Gatefold Sleeve');
    }

    if (fmtData.conditionPhrase) {
        // Case B: sleeve condition set, sleeve desc BLANK.
        // Order: ... sleeveCond, sleeveTypeLabel, "sleevePkg with condition"
        // This produces e.g.: "Very Good+ JCard Jewel Case with cracking"
        const sleeveTail = (fmtData.sleevePkg && fmtData.sleevePkg.trim())
            ? fmtData.sleevePkg + ' with ' + fmtData.conditionPhrase
            : 'with ' + fmtData.conditionPhrase;

        parts = [
            inputs.mediaCond,
            fmtData.pkgFeature,
            fmtData.edition,
            inputs.year,
            country,
            fmtData.finalFormatString,
            fmtData.mediaconditionPhrase || '',
            fmtData.mediaDesc,
            sleeveCondText,
            fmtData.sleeveTypeLabel,
            sleeveTail ? sleeveTail : ''
        ];
    } else {
        // Case A / default: sleeve desc is set (or no conditions at all).
        // Original order preserved: sleeveCond, sleevePkg, sleeveTypeLabel, sleeveDesc
        parts = [
            inputs.mediaCond,
            fmtData.pkgFeature,
            fmtData.edition,
            inputs.year,
            country,
            fmtData.finalFormatString,
            fmtData.mediaconditionPhrase || '',
            fmtData.mediaDesc,
            sleeveCondText,
            fmtData.sleevePkg,
            fmtData.sleeveTypeLabel,
            fmtData.sleeveDesc
        ];
    }

    let desc = parts.filter(p => p && p.toString().trim() !== '').join(' ');
    desc = desc.replace(/,/g, '');

    if (inputs.isOOP) desc += ' is Out-of-Print';

    if (inputs.trackTime) desc += ' with ' + inputs.trackTime + ' Tracks';

    if (inputs.label) desc += ' - ' + inputs.label;

    desc = desc.replace(/,/g, '');
    return desc;
}


// Join grouped flaw items:
//   1 item  -> "A"
//   2 items -> "A & B"
//   3+ items -> "A / B & C" (ampersand only before the final item)
function joinFlawItems(items) {
    if (!items || items.length === 0) return "";
    if (items.length === 1) return items[0];
    if (items.length === 2) return items[0] + " & " + items[1];
    return items.slice(0, -1).join(" / ") + " & " + items[items.length - 1];
}

function stripLeadingWith(text) {
    return String(text || '').replace(/^with\s+/i, '').trim();
}

function capitalizeFlawContext(text) {
    // Capitalise the noun that follows a flaw separator in free-text descriptions:
    // "waviness/bending to back" -> "waviness/bending to Back".
    // Phrases like "to top of box" are left alone (the head word is not the noun).
    // Articles are skipped.
    let out = String(text).replace(
        /\b(to|through|on|at|near|around|along)([\s-]+)([A-Za-z][A-Za-z'-]*)(\s+of\b)?/gi,
        (match, sep, gap, word, ofPart) => {
            if (ofPart) return match;
            if (/^(a|an|the)$/i.test(word)) return match;
            return `${sep}${gap}${word.charAt(0).toUpperCase()}${word.slice(1)}`;
        });

    // Location nouns read as proper nouns when they open the phrase, optionally
    // behind an intensity adjective: "corner denting" -> "Corner denting",
    // "light corner-wear" -> "light Corner-wear".
    const cap = w => w.charAt(0).toUpperCase() + w.slice(1);
    out = out.replace(/^(\s*)(corner|edge|ring|spine)\b/i, (m, sp, loc) => `${sp}${cap(loc)}`);
    out = out.replace(
        /^(\s*(?:light|moderate|heavy|minor|major|slight|severe|significant|faint|deep|small|large|tiny)\s+)(corner|edge|ring|spine)\b/i,
        (m, sp, loc) => `${sp}${cap(loc)}`
    );
    return out;
}

function groupFlaws(flaws) {
    if (!flaws || flaws.length <= 1) return flaws;

    const separators = [' to ', ' through ', ' on '];
    // Location prefixes that can share one flaw word: Corner/Edge/Spine creasing.
    const LOCATION_CANON = {
        corner: 'Corner', corners: 'Corner',
        edge: 'Edge', edges: 'Edge',
        ring: 'Ring', rings: 'Ring',
        spine: 'Spine', spines: 'Spine'
    };

    // Helper to split a flaw into [prefix, separator, suffix].
    // Separators are whitespace/hyphen/case agnostic: "wear-to Booklet" and
    // "wear TO Booklet" both split like "wear to Booklet".
    function splitFlaw(f) {
        for (const sep of separators) {
            const m = f.match(new RegExp(`[\\s-]${sep.trim()}[\\s-]`, 'i'));
            if (m) {
                return [
                    f.slice(0, m.index).trim(),
                    sep,
                    f.slice(m.index + m[0].length).trim()
                ];
            }
        }
        const loc = f.match(/^([A-Za-z]+)\s+(.+)$/);
        if (loc) {
            const canonical = LOCATION_CANON[loc[1].toLowerCase()];
            if (canonical) return [canonical, ' ', loc[2]];
        }
        return [f, null, null];
    }

    // Case-insensitive de-dupe: keeps the first spelling seen.
    function uniqueCI(values) {
        const seen = new Set();
        return values.filter(v => {
            const key = String(v).toLowerCase();
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
    }

    // Hyphens are ignored for grouping: "ring-wear" is read as "ring wear".
    const splitWords = f => String(f).trim().split(/[\s-]+/).filter(Boolean);

    // "Corner edge creasing" -> "Corner/Edge creasing": consecutive leading
    // location words collapse into a slash set.
    const canonicalizeLocations = (f) => {
        const tokens = splitWords(f);
        const locs = [];
        let i = 0;
        while (i < tokens.length - 1 && LOCATION_CANON[tokens[i].toLowerCase()]) {
            locs.push(LOCATION_CANON[tokens[i].toLowerCase()]);
            i++;
        }
        if (locs.length < 2) return f;
        return uniqueCI(locs).join('/') + ' ' + tokens.slice(i).join(' ');
    };

    // Modifier adjectives that describe the same kind of flaw (e.g. light play,
    // light wear to Booklet) are grouped so the adjective appears only once:
    // "light play/wear to Booklet".
    const ADJECTIVE_MODIFIERS = new Set([
        'light', 'moderate', 'heavy', 'minor', 'major', 'slight', 'severe',
        'significant', 'faint', 'deep', 'small', 'large', 'tiny'
    ]);

    function splitAdjective(f) {
        const m = f.match(/^([A-Za-z]+)[\s-]+(.+)$/);
        if (!m) return null;
        if (!ADJECTIVE_MODIFIERS.has(m[1].toLowerCase())) return null;
        return [m[1], m[2]];
    }

    function groupAdjectives(list) {
        const out = [];
        const used = new Set();
        for (let i = 0; i < list.length; i++) {
            if (used.has(i)) continue;
            const parsed = splitAdjective(list[i]);
            if (!parsed) { out.push(list[i]); continue; }

            const [adj, rest] = parsed;
            const matches = [i];

            for (let j = i + 1; j < list.length; j++) {
                if (used.has(j)) continue;
                const other = splitAdjective(list[j]);
                if (!other || other[0].toLowerCase() !== adj.toLowerCase()) continue;
                matches.push(j);
            }

            if (matches.length > 1) {
                // Each subject keeps its own trailing context; only a context
                // shared by every subject may be appended once.
                const contexts = matches.map(idx => splitFlaw(splitAdjective(list[idx])[1]));
                const ctxKey = c => `${(c[1] || '').toLowerCase()}\u0000${(c[2] || '').toLowerCase()}`;
                let phrase;
                if (new Set(contexts.map(ctxKey)).size === 1) {
                    const [, sharedSep, sharedSuffix] = contexts[0];
                    const objs = uniqueCI(contexts.map(c => c[0]));
                    if (sharedSep) {
                        phrase = adj + ' ' + objs.join('/') + sharedSep + (sharedSuffix || '');
                    } else if (sharedSuffix) {
                        phrase = adj + ' ' + objs.join('/') + ' ' + sharedSuffix;
                    } else {
                        // No context: hoist a shared trailing head word so it is
                        // not repeated on every object.
                        const words = objs.map(splitWords);
                        const heads = uniqueCI(words.map(w => w[w.length - 1]));
                        const bodies = uniqueCI(words.map(w => w.slice(0, -1).join(' ')));
                        phrase = (heads.length === 1 && bodies.every(b => b))
                            ? adj + ' ' + bodies.join('/') + ' ' + heads[0]
                            : adj + ' ' + objs.join('/');
                    }
                } else {
                    // Contexts differ: hoist only the words every subject shares,
                    // then keep each subject's own context ("wear to Booklet/
                    // Cellophane tearing", "scratching to Disc/spindle-wear").
                    const subjects = uniqueCI(matches.map(idx => splitAdjective(list[idx])[1]));
                    const lists = subjects.map(splitWords);
                    const minLen = Math.min(...lists.map(t => t.length));
                    let k = 0;
                    while (k < minLen && lists.every(t => t[k].toLowerCase() === lists[0][k].toLowerCase())) k++;
                    // Strip the shared lead words from the original text so
                    // hyphens and casing survive ("spindle-wear").
                    const stripLead = (s, n) => {
                        let r = String(s).trim();
                        for (let c = 0; c < n; c++) r = r.replace(/^[^\s-]+[\s-]*/, '');
                        return r.trim();
                    };
                    const lead = (subjects[0].match(/[^\s-]+/g) || []).slice(0, k).join(' ');
                    const remainders = uniqueCI(subjects.map(s => stripLead(s, k)));
                    const nonEmpty = remainders.filter(r => r !== '');
                    const use = nonEmpty.length ? nonEmpty : remainders;

                    const ctxMatch = r => r.match(/^(to|through|on)\s+(.+)$/i);
                    const first = ctxMatch(use[0]);
                    const sharedCtx = !!first && use.every(r => {
                        const m = ctxMatch(r);
                        return m && m[1].toLowerCase() === first[1].toLowerCase();
                    });

                    if (!lead && !sharedCtx) {
                        phrase = adj + ' ' + use.join('/');
                    } else if (sharedCtx) {
                        const sepWord = first[1].toLowerCase();
                        const tails = use.map(r => ctxMatch(r)[2]);
                        phrase = adj + ' ' + (lead ? lead + ' ' + sepWord : sepWord) + ' ' + tails.join('/');
                    } else {
                        phrase = adj + ' ' + (lead ? lead + ' ' : '') + use.join('/');
                    }
                }
                out.push(phrase);
                matches.forEach(idx => used.add(idx));
            } else {
                out.push(list[i]);
                used.add(i);
            }
        }
        return out;
    }

    result = groupAdjectives(flaws.map(canonicalizeLocations));

    // Shared head word across a contexted flaw and a modifier-first flaw:
    // "tearing to Box" + "Sleeve tearing" -> "tearing to Box/Sleeve".
    // Only single-word heads (tearing, wear, creasing) participate.
    function groupSharedHeads(list) {
        const groups = [];
        const groupOf = new Array(list.length).fill(null);

        list.forEach((f, idx) => {
            const [p, s, x] = splitFlaw(f);
            if (!s || /\s/.test(p)) return;
            let g = groups.find(g => g.prefix.toLowerCase() === p.toLowerCase() && g.sep === s);
            if (!g) { g = { prefix: p, sep: s, members: [] }; groups.push(g); }
            g.members.push({ idx, part: x });
            groupOf[idx] = g;
        });

        list.forEach((f, idx) => {
            if (groupOf[idx]) return;
            const [p, s] = splitFlaw(f);
            if (s) return;
            const tokens = splitWords(f);
            if (tokens.length < 2) return;
            const head = tokens[tokens.length - 1].toLowerCase();
            // Adjective-modified flaws never join plain ones
            // ("light Cellophane tearing" stays out of "tearing to Booklet").
            if (ADJECTIVE_MODIFIERS.has(tokens[0].toLowerCase())) return;
            const modifier = tokens.slice(0, -1).join(' ');
            const g = groups.find(g => g.prefix.toLowerCase() === head);
            if (!g) return;
            g.members.push({ idx, part: modifier });
            groupOf[idx] = g;
        });

        const out = [];
        const emitted = new Set();
        list.forEach((f, idx) => {
            const g = groupOf[idx];
            if (!g || g.members.length < 2) { out.push(f); return; }
            if (emitted.has(g)) return;
            // Objects keep the order their source flaws were selected in.
            const ordered = [];
            g.members.slice().sort((a, b) => a.idx - b.idx).forEach(m => {
                String(m.part || '').split('/').map(t => t.trim()).filter(Boolean).forEach(t => {
                    if (!ordered.some(o => o.toLowerCase() === t.toLowerCase())) ordered.push(t);
                });
            });
            out.push(g.prefix + g.sep + ordered.join('/'));
            emitted.add(g);
        });
        return out;
    }

    result = groupSharedHeads(result);

    // Items sharing a trailing head word collapse together, hoisting one shared
    // leading adjective: "light Cellophane tearing" + "Sleeve tearing" ->
    // "light Cellophane/Sleeve tearing". Items with a context separator
    // (to/through/on) are left to prefix/suffix grouping.
    function groupSuffixHeads(list) {
        const describe = (f) => {
            // '/' is a grouping separator too, so an existing slash set
            // ("Corner creasing/Edge creasing") is read as one head word set.
            const tokens = String(f).trim().split(/[\/\s-]+/).filter(Boolean);
            const sep = splitFlaw(f)[1];
            // Only real contexts (to/through/on) are left to prefix/suffix
            // grouping; a location pseudo-separator still groups by head word.
            if (tokens.length < 2 || (sep && sep !== ' ')) return null;
            const head = tokens.pop();
            const body = tokens.filter(t => t.toLowerCase() !== head.toLowerCase());
            const adjs = [];
            const rest = body.slice();
            while (rest.length > 1 && ADJECTIVE_MODIFIERS.has(rest[0].toLowerCase())) adjs.push(rest.shift());
            // Keep an existing slash set as separate objects.
            const raw = /[\/]/.test(f) ? body.join('/') : body.join(' ');
            return { head, adjs, raw, core: rest.join(' ') };
        };

        const out = [];
        const used = new Set();
        for (let i = 0; i < list.length; i++) {
            if (used.has(i)) continue;
            const first = describe(list[i]);
            if (!first) { out.push(list[i]); used.add(i); continue; }

            const members = [{ idx: i, ...first }];
            for (let j = i + 1; j < list.length; j++) {
                if (used.has(j)) continue;
                const d = describe(list[j]);
                if (!d || d.head.toLowerCase() !== first.head.toLowerCase()) continue;
                members.push({ idx: j, ...d });
            }

            // Only hoist when every member that has adjectives uses the same one.
            const adjSets = [...new Set(members.filter(m => m.adjs.length).map(m => m.adjs.join(' ').toLowerCase()))];
            const hoisted = adjSets.length === 1 ? members.find(m => m.adjs.length).adjs : null;
            const values = members.map(m => (hoisted ? m.core : m.raw));

            // Existing slash sets are flattened so "Corner/Edge" + "Edge" union.
            const objects = [];
            values.forEach(v => String(v).split('/').map(t => t.trim()).filter(Boolean).forEach(t => {
                if (!objects.some(o => o.toLowerCase() === t.toLowerCase())) objects.push(t);
            }));

            if (members.length < 2 || (hoisted && values.some(v => !v))) {
                out.push(list[i]);
                used.add(i);
                continue;
            }
            out.push([...(hoisted || []), objects.join('/'), first.head].filter(x => x).join(' '));
            members.forEach(m => used.add(m.idx));
        }
        return out;
    }

    result = groupSuffixHeads(result);

    // Leading-object grouping: "sticker mark" + "sticker residue" ->
    // "sticker mark/residue". Only simple two-word flaws (no "to/through/on",
    // no locations/adjectives already merged) participate.
    function splitHeadTail(f) {
        const tokens = splitWords(f);
        if (tokens.length !== 2) return null;
        return [tokens[0], tokens[1]];
    }

    function groupLeadingObjects(list) {
        const out = [];
        const used = new Set();
        for (let i = 0; i < list.length; i++) {
            if (used.has(i)) continue;
            const first = splitHeadTail(list[i]);
            if (!first) { out.push(list[i]); continue; }
            const matches = [i];
            for (let j = i + 1; j < list.length; j++) {
                if (used.has(j)) continue;
                const other = splitHeadTail(list[j]);
                if (other && other[0].toLowerCase() === first[0].toLowerCase()) matches.push(j);
            }
            if (matches.length > 1) {
                const tails = matches.map(idx => splitHeadTail(list[idx])[1]);
                out.push(first[0] + ' ' + uniqueCI(tails).join('/'));
                matches.forEach(idx => used.add(idx));
            } else {
                out.push(list[i]);
                used.add(i);
            }
        }
        return out;
    }

    result = groupLeadingObjects(result);

    // 1. Prefix Grouping
    // Group by (prefix + separator)
    let prefixGrouped = [];
    let handled = new Set();
    for (let i = 0; i < result.length; i++) {
        if (handled.has(i)) continue;
        const [p1, s1, x1] = splitFlaw(result[i]);
        if (!s1) {
            prefixGrouped.push(result[i]);
            continue;
        }

        let matches = [i];
        for (let j = i + 1; j < result.length; j++) {
            if (handled.has(j)) continue;
            const [p2, s2, x2] = splitFlaw(result[j]);
            if (p1.toLowerCase() === p2.toLowerCase() && s1.toLowerCase() === s2.toLowerCase()) {
                matches.push(j);
            }
        }

        if (matches.length > 1) {
            const suffixes = matches.map(idx => splitFlaw(result[idx])[2]);
            const uniqueSuffixes = uniqueCI(suffixes);
            prefixGrouped.push(p1 + s1 + uniqueSuffixes.join('/'));
            matches.forEach(idx => handled.add(idx));
        } else {
            prefixGrouped.push(result[i]);
            handled.add(i);
        }
    }

    // 2. Suffix Grouping
    // Group by suffix. Suffixes that share a slash-set merge as well, so a
    // suffix expanded by an earlier pass still groups with a plain suffix:
    // "Box" + "Box/Sleeve" -> "Box/Sleeve".
    result = prefixGrouped;
    let suffixGrouped = [];
    handled = new Set();

    const suffixParts = (x) => String(x || '').split('/').map(t => t.trim()).filter(Boolean);
    const suffixRelated = (union, other) => {
        const U = union.map(t => t.toLowerCase());
        const O = other.map(t => t.toLowerCase());
        if (!U.length || !O.length) return false;
        return O.every(t => U.includes(t)) || U.every(t => O.includes(t));
    };

    for (let i = 0; i < result.length; i++) {
        if (handled.has(i)) continue;
        const [p1, s1, x1] = splitFlaw(result[i]);
        if (!x1) {
            suffixGrouped.push(result[i]);
            continue;
        }

        // Grow the suffix set until no further suffix is a subset/superset.
        let union = suffixParts(x1);
        let matches = [i];
        let grew = true;
        while (grew) {
            grew = false;
            for (let j = i + 1; j < result.length; j++) {
                if (handled.has(j) || matches.includes(j)) continue;
                const [p2, s2, x2] = splitFlaw(result[j]);
                if (!x2) continue;
                if (!suffixRelated(union, suffixParts(x2))) continue;
                matches.push(j);
                union = uniqueCI([...union, ...suffixParts(x2)]);
                grew = true;
            }
        }
        const mergedSuffix = union.join('/');

        if (matches.length > 1) {
            // Share a common leading word across prefixes:
            // "Promo Stamp" + "Promo Sticker" -> "Promo Stamp/Sticker"
            const mergeSharedPrefix = (prefixes) => {
                const uniq = uniqueCI(prefixes);
                if (uniq.length < 2) return uniq.join('/');
                const tokenLists = uniq.map(splitWords);
                const minLen = Math.min(...tokenLists.map(t => t.length));
                let k = 0;
                while (k < minLen - 1 && tokenLists.every(t => t[k].toLowerCase() === tokenLists[0][k].toLowerCase())) k++;
                if (k === 0) return uniq.join('/');
                const common = tokenLists[0].slice(0, k).join(' ');
                const tails = tokenLists.map(t => t.slice(k).join(' '));
                return common + ' ' + tails.join('/');
            };

            // Group by separator within this suffix group
            let sepMap = new Map(); // separator -> [prefixes]
            matches.forEach(idx => {
                const [p, s, x] = splitFlaw(result[idx]);
                if (!sepMap.has(s)) sepMap.set(s, []);
                sepMap.get(s).push(p);
            });

            let combinedParts = [];
            let spaceParts = [];
            for (let [sep, prefixes] of sepMap.entries()) {
                const uniquePrefixes = uniqueCI(prefixes);
                if (sep === ' ') {
                    // Location prefixes (Corner / Edge) share the flaw word:
                    // "Corner creasing" + "Edge creasing" -> "Corner/Edge creasing"
                    spaceParts.push(mergeSharedPrefix(uniquePrefixes) + ' ' + mergedSuffix);
                } else {
                    combinedParts.push(mergeSharedPrefix(uniquePrefixes) + sep.trimEnd());
                }
            }
            // Join parts with / and append the suffix
            if (spaceParts.length) {
                suffixGrouped.push(spaceParts.join(' / '));
            } else {
                suffixGrouped.push(combinedParts.join('/') + ' ' + mergedSuffix);
            }
            matches.forEach(idx => handled.add(idx));
        } else {
            suffixGrouped.push(result[i]);
            handled.add(i);
        }
    }

    return suffixGrouped;
}

function inferSkuCode(rawLine, mediaFormat, sleevePkg) {
    const combined = (rawLine + " " + mediaFormat + " " + (sleevePkg || "")).toLowerCase();

    // 1. BOX SETS
    const typesToCheck = ["lp", "cd", "cassette", "7\"", "12\"", "dvd", "vhs", "reel"];
    let typeCount = 0;
    typesToCheck.forEach(t => { if (combined.includes(t)) typeCount++; });

    if (combined.includes("box set") || typeCount >= 3) {
        // Check for Mixed Media
        let mixedCount = 0;
        if (combined.includes("vinyl") || combined.includes("lp") || combined.includes("7\"") || combined.includes("12\"") || combined.includes("10\"")) mixedCount++;
        if (combined.includes("cd") || combined.includes("sacd")) mixedCount++;
        if (combined.includes("dvd")) mixedCount++;
        if (combined.includes("blu-ray") || combined.includes("blue ray")) mixedCount++;
        if (combined.includes("cassette") || combined.includes("mc")) mixedCount++;
        if (combined.includes("vhs")) mixedCount++;
        if (mixedCount >= 2) return "MEDIABOX";

        if (combined.includes("vinyl") || combined.includes("lp") || combined.includes("7\"") || combined.includes("12\"")) return "VINYLBOX";
        if (combined.includes("blu-ray") || combined.includes("blue ray")) return "BRBOX";
        if (combined.includes("dvd")) return "DVDBOX";
        if (combined.includes("vhs")) return "VHSBOX";
        if (combined.includes("cd")) return "CDBOX";
        if (combined.includes("cassette") || combined.includes("mc")) return "CASSBOX";
        return "VINYLBOX";
    }

    // 2. MIXED MEDIA (Highest Count Wins + First in List Tie-Breaker)
    if (combined.includes("+")) {
        const getCount = (str, regex) => {
            const parts = str.split('+');
            let total = 0;
            for (let part of parts) {
                if (regex.test(part)) {
                    const qtyMatch = part.match(/(\d+)x/i);
                    total += qtyMatch ? parseInt(qtyMatch[1]) : 1;
                }
            }
            return total;
        };

        const rCD = /(?:^|\s|\d+x)(cd|sacd|cdr|hdcd)\b/i;
        const rDVD = /(?:^|\s|\d+x)(dvd|dvd-video|dvd-audio)\b/i;
        const rBD = /(?:^|\s|\d+x)(blu-ray|blue ray|bd)\b/i;
        const rVinyl = /(?:^|\s|\d+x)(vinyl|lp)\b|7"|12"|10"/i;
        const rCass = /(?:^|\s|\d+x)(cassette|mc|tape)\b/i;

        const cCD = getCount(combined, rCD);
        const cDVD = getCount(combined, rDVD);
        const cBD = getCount(combined, rBD);
        const cVinyl = getCount(combined, rVinyl);
        const cCass = getCount(combined, rCass);

        const counts = [
            { code: "CD", count: cCD, regex: rCD },
            { code: "DVD", count: cDVD, regex: rDVD },
            { code: "BLURAY", count: cBD, regex: rBD },
            { code: "VINYL", count: cVinyl, regex: rVinyl },
            { code: "CASS", count: cCass, regex: rCass }
        ];
        counts.sort((a, b) => b.count - a.count);

        if (counts[0].count > 0) {
            if (counts[0].count > counts[1].count) return counts[0].code;
            // Tie-breaker: First in list wins
            const idx0 = combined.search(counts[0].regex);
            const idx1 = combined.search(counts[1].regex);
            if (idx0 !== -1 && idx1 !== -1) return idx0 < idx1 ? counts[0].code : counts[1].code;
        }
    }

    // 2. LEGACY / VIDEO
    if (combined.includes("reel")) return "REEL";
    if (combined.includes("8-track")) return "8TRACK";
    if (combined.includes("blu-ray")) return "BLURAY";
    if (combined.includes("dvd")) return "DVD";
    if (combined.includes("vhs")) return "VHS";

    // 3. SINGLES
    const singleSignals = ["7\"", "12\"", "10\"", "single", "maxi-single"];
    const hasSignal = singleSignals.some(s => combined.includes(s));
    const isAlbum = combined.includes("lp") || combined.includes("album");

    if (hasSignal && !isAlbum) {
        if (combined.includes("cd")) return "CDS";
        if (combined.includes("cassette") || combined.includes("mc") || combined.includes("tape")) return "CASSS";
        return "VINYLS";
    }

    // 4. CORE FORMATS
    if (combined.includes("cd")) return "CD";
    if (combined.includes("cassette") || combined.includes("mc")) return "CASS";
    if (combined.includes("vinyl") || combined.includes("lp")) return "VINYL";

    // 5. FALLBACK - JSON LOOKUP
    if (typeof mediaFormats !== 'undefined' && mediaFormats) {
        for (const [category, sub] of Object.entries(mediaFormats)) {
            if (category === "release_descriptions_and_attributes") continue;
            let formats = Array.isArray(sub) ? sub : Object.values(sub).flat();
            for (const fmt of formats) {
                if (combined.includes(fmt.toLowerCase())) {
                    if (category === 'digital_file_formats') return "FILE";
                    if (category === 'video_formats') return "VIDEO";
                    if (category === 'niche_and_historical_formats') return "RARE";
                    if (category === 'digital_optical_media') return "OPTICAL";
                    if (category === 'physical_audio_analog') return "ANALOG";
                }
            }
        }
    }
    return "UNKN";
}

function generateSku(box, lister, code, mediaCond, flag) {
    const status = (mediaCond || "").includes("Factory") ? "NEW" : "USED";
    const now = new Date();
    let hours = now.getHours();
    let displayHours = hours % 12 || 12;

    return `${box || '8094'}-${(lister || 'XX').toUpperCase()}${now.getFullYear()}-${(now.getMonth() + 1).toString().padStart(2, '0')}${now.getDate().toString().padStart(2, '0')}-${code}-${status}-${displayHours.toString().padStart(2, '0')}${now.getMinutes().toString().padStart(2, '0')}${flag}`;
}

function handleOutput(sku, desc, isOOP, flag) {
    const suppressSuffix = ['RSDO', 'B', '70', '86', '-RSDO', '-B', '-70', '-86'].includes(flag);
    let copyText = "";

    const lockSku = document.getElementById('lockSku')?.checked || false;
    const lockDesc = document.getElementById('lockDesc')?.checked || false;

    if (!lockSku) {
        if (!isOOP && !suppressSuffix) {
            document.getElementById('outputSku').value = sku + "-O";
        } else {
            document.getElementById('outputSku').value = sku;
        }
    }

    if (!lockDesc) {
        document.getElementById('outputDesc').value = desc;
    }

    const finalSku = document.getElementById('outputSku').value;
    const finalDesc = document.getElementById('outputDesc').value;
    copyText = `${finalSku}\n${finalDesc}`;

    const btn = document.getElementById('generateBtn');
    const originalText = btn.innerText;
    btn.innerText = "✅ Generated!";
    btn.style.backgroundColor = "#1e7e34";
    setTimeout(() => {
        btn.innerText = originalText;
        btn.style.backgroundColor = "";
    }, 1500);
}

function handleScrapeResult() {
    const errorDiv = document.getElementById('scraperError');
    const output = document.getElementById('scraperOutput');
    errorDiv.innerHTML = ""; // Clear previous messages

    if (document.getElementById('lockSku')) document.getElementById('lockSku').checked = false;
    if (document.getElementById('lockDesc')) document.getElementById('lockDesc').checked = false;

    // Check if the response was a script (success) or an error div.
    if (output && output.querySelector('script')) {
        // Success case. The script handles all DOM updates. Do nothing here to avoid race conditions.
    } else if (output && output.innerHTML.trim()) {
        // Error case. The server sent back an error message to display.
        errorDiv.innerHTML = output.innerHTML;
    } else {
        // Fallback for an empty or unexpected error response.
        errorDiv.innerHTML = `<div style="background:#ffebee; border:1px solid #c62828; color:#c62828; padding:10px; border-radius:4px; font-size:11px;"><strong>Scrape Failed.</strong> An unknown error occurred.</div>`;
    }
}

// --- Current Item indicator (top-right of the blue title bar) ---
// Mirrors the WysiScan "last result persists" pattern: the most recently
// scraped item (Artist - Album) is shown in the bar and survives a refresh.
const CURRENT_ITEM_KEY = 'wysiwyg_current_item';
function setCurrentItem(text) {
    const el = document.getElementById('currentItem');
    if (!el) return;
    const v = (text || '').toString().trim();
    if (!v) { el.innerHTML = '&nbsp;'; el.style.opacity = '0.55'; return; }
    el.textContent = v;
    el.style.opacity = '1';
    try { localStorage.setItem(CURRENT_ITEM_KEY, v); } catch (e) {}
}
function restoreCurrentItem() {
    let v = '';
    try { v = localStorage.getItem(CURRENT_ITEM_KEY) || ''; } catch (e) {}
    setCurrentItem(v);
}
// Clear the blue-bar "current item" indicator (text + persisted key). Used on
// page refresh and the Reset All button so a stale item from a prior session
// never lingers in the title bar.
function clearCurrentItem() {
    const el = document.getElementById('currentItem');
    if (el) { el.innerHTML = '&nbsp;'; el.style.opacity = '0.55'; }
    try { localStorage.removeItem(CURRENT_ITEM_KEY); } catch (e) {}
}

function shutdownApp() {
    document.getElementById('shutdownModal').style.display = 'block';
}

function closeShutdownModal() {
    document.getElementById('shutdownModal').style.display = 'none';
}

function confirmShutdown() {
    fetch('/shutdown', { method: 'POST' }).then(() => {
        // Try to close the tab. This only works for tabs opened by script
        // (e.g. the UberPaste popup). For a user-opened tab the browser
        // blocks it, so we blank the page instead of leaving "System Offline" up.
        window.close();
        setTimeout(() => {
            if (!window.closed) {
                window.location.replace('about:blank');
            }
        }, 300);
    }).catch(() => {
        window.location.replace('about:blank');
    });
}

function copyGeneratedHtml() {
    const copyText = document.getElementById("htmlOutputBox");
    // Ensure we select the text for the clipboard
    copyText.select();

    navigator.clipboard.writeText(copyText.value)
        .then(() => {
            const btn = document.getElementById("copyHtmlBtn");
            const originalText = btn.innerHTML;
            btn.innerHTML = "✅ Copied!";
            btn.style.background = "#007bff";

            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.style.background = "#28a745";
            }, 2000);
        })
        .catch(err => customAlert("Copy failed: " + err));
}

function copyField(id, btn) {
    const el = document.getElementById(id);
    el.select();
    navigator.clipboard.writeText(el.value).then(() => {
        const originalText = btn.innerText;
        btn.innerText = "Copied!";
        btn.style.backgroundColor = "#28a745";
        setTimeout(() => {
            btn.innerText = originalText;
            btn.style.backgroundColor = "var(--secondary-color)";
        }, 1500);
    });
}

// --- Live Preview editing (contenteditable) ---

function syncLivePreviewToCode() {
    const preview = document.getElementById('htmlPreview');
    const codeBox = document.getElementById('htmlOutputBox');
    if (!preview || !codeBox) return;
    codeBox.value = preview.innerHTML;
}

function updateLivePreviewToolbarState() {
    const preview = document.getElementById('htmlPreview');
    if (!preview) return;
    const selection = document.getSelection();
    const inPreview = selection && selection.anchorNode && preview.contains(selection.anchorNode);
    document.querySelectorAll('.live-preview-fmt-btn').forEach(btn => {
        let active = false;
        if (inPreview) {
            try {
                active = document.queryCommandState(btn.dataset.cmd);
            } catch (e) {
                active = false;
            }
        }
        btn.classList.toggle('active', !!active);
    });
}

function applyLivePreviewFormat(command) {
    const preview = document.getElementById('htmlPreview');
    if (!preview) return;
    preview.focus();
    try {
        document.execCommand('styleWithCSS', false, 'false');
        document.execCommand(command, false, null);
    } catch (e) {
        console.error('Format command failed:', command, e);
    }
    syncLivePreviewToCode();
    updateLivePreviewToolbarState();
}

function copyLivePreview() {
    const previewEl = document.getElementById('htmlPreview');
    if (!previewEl) return;

    navigator.clipboard.writeText(previewEl.innerText).then(() => {
        const btn = document.getElementById('copyLivePreviewBtn');
        const originalText = btn.innerText;
        btn.innerText = "✅ Copied!";
        setTimeout(() => {
            btn.innerText = originalText;
        }, 2000);
    }).catch(err => customAlert("Copy failed: " + err));
}

function resetScraperTab() {
    customConfirm("Clear all scraper fields?", () => {
        document.querySelector('input[name="url"]').value = "";
        document.getElementById('scraperOutput').innerHTML = "";
        document.getElementById('htmlOutputBox').value = "";
        document.getElementById('htmlPreview').innerHTML = "";
    });
}

function updateCounterUIDeprecated() {}

// --- Custom Options Logic ---

let customOptionsData = { cassette: [], cd: [], lp: [], media: [], mediaCondition: [], boxSleeve: [] };
let editingCustomOptionIndex = -1;
let editingCustomOption = null;
let customOptionCopyDraft = false;
let currentModalCategory = 'cassette';
let customOptionsSearchTerm = '';
let currentConditionMediaType = 'lp'; // Track current media type for condition dropdowns
let conditionPickerViewMode = 'single'; // 'single' or 'dual'
let conditionPickerSingleSource = 'media'; // 'media' | 'sleeve' - which single column the "Both" toggle returns to

// The search bar must always filter the list that is currently open, never
// switch it to a different list. Every picker-open function registers its own
// redraw callback here so the search input handler can re-render that view.
let conditionPickerRedraw = null;

function conditionPickerQuery() {
    const el = document.getElementById('conditionPickerSearch');
    return (el?.value || '').trim().toLowerCase();
}

function conditionPickerMatch(opt, query) {
    if (!query) return true;
    return ((opt.title || '') + ' ' + (opt.text || '')).toLowerCase().includes(query);
}

function dedupeCustomOptions() {
    Object.keys(customOptionsData).forEach(cat => {
        const arr = customOptionsData[cat];
        if (!Array.isArray(arr)) return;
        const seen = new Map();
        const keep = [];
        arr.forEach(item => {
            if (!item) return;
            const key = [item.title, item.text, item.media_type || ''].join('|||');
            const existing = seen.get(key);
            if (existing) {
                if (item.favorite) existing.favorite = true;
                return;
            }
            seen.set(key, item);
            keep.push(item);
        });
        if (keep.length !== arr.length) {
            arr.length = 0;
            keep.forEach(i => arr.push(i));
        }
    });
}

function sortCustomOptionsData() {
    dedupeCustomOptions();
    Object.keys(customOptionsData).forEach(cat => {
        customOptionsData[cat].sort((a, b) => {
            const aFav = a.favorite ? 1 : 0;
            const bFav = b.favorite ? 1 : 0;
            if (aFav !== bFav) return bFav - aFav; // Favorites first
            return a.title.localeCompare(b.title); // Alphabetical secondary
        });
    });
}

async function loadCustomOptions() {
    try {
        const response = await fetch('/api/conditions?t=' + Date.now(), { cache: 'no-store' });
        if (response.ok) {
            customOptionsData = await response.json();
            // Ensure all keys exist
            if (!customOptionsData.cassette) customOptionsData.cassette = [];
            if (!customOptionsData.cd) customOptionsData.cd = [];
            if (!customOptionsData.lp) customOptionsData.lp = [];
            if (!customOptionsData.media) customOptionsData.media = [];
            if (!customOptionsData.mediaCondition) customOptionsData.mediaCondition = [];
            if (!customOptionsData.boxSleeve) customOptionsData.boxSleeve = [];
            sortCustomOptionsData();
        }
    } catch (e) {
        console.error("Failed to load conditions from server:", e);
        // Fallback to defaults if server fails and nothing in data
        if (customOptionsData.cassette.length === 0) {
            customOptionsData.cassette = [
                { title: "Tearing", text: "cellophane tearing" },
                { title: "Cracking", text: "Jewel Case cracking" },
                { title: "Final Sale", text: "( final sale - can't verify matrix/pressing/label variant due to seal )" }
            ];
            sortCustomOptionsData();
        }
    }
    renderCustomOptionsSelect();
}

async function saveCustomOptions() {
    sortCustomOptionsData();
    try {
        await fetch('/api/save-conditions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(customOptionsData)
        });
    } catch (e) {
        console.error("Failed to save conditions to server:", e);
    }
}


function renderCustomOptionsSelect() {
    const configs = [
        { id: 'customOptions', key: 'cassette' },
        { id: 'cdOptions', key: 'cd' },
        { id: 'lpOptions', key: 'lp' },
        { id: 'boxSleeveOptions', key: 'boxSleeve' }
    ];

    configs.forEach(config => {
        const select = document.getElementById(config.id);
        if (!select) return;

        // Match by title/text key instead of entire JSON string to handle 'favorite' toggle correctly
        const selectedKeys = Array.from(select.selectedOptions).map(o => {
            try {
                const d = JSON.parse(o.value);
                return d.title + '|||' + d.text;
            } catch (e) { return ''; }
        });

        select.innerHTML = '';

        (customOptionsData[config.key] || []).forEach((opt) => {
            const option = document.createElement('option');
            const val = JSON.stringify(opt);
            option.value = val;
            option.text = (opt.favorite ? '⭐ ' : '') + opt.title;
            if (selectedKeys.includes(opt.title + '|||' + opt.text)) {
                option.selected = true;
            }
            select.appendChild(option);
        });
    });

    // Also render the new Media Condition / Sleeve Condition multiselects based on current media type
    renderConditionMultiselects();
}

// A box set gets the Box Sleeve condition list instead of LP / CD / Cassette.
// Sleeve Packaging is a multiselect, so any selected value that reads "Box Set"
// (or "Boxset") switches the sleeve conditions over.
function isBoxSetSelected() {
    const sel = document.getElementById('sleevePackaging');
    if (!sel) return false;
    return Array.from(sel.selectedOptions).some(o => /box\s*set/i.test(o.value || ''));
}

function effectiveSleeveType() {
    return isBoxSetSelected() ? 'boxSleeve' : currentConditionMediaType;
}

// The box list reads "BOXSET" (one word) wherever a type name is shown.
function sleeveConditionLabel(type) {
    return (type === 'boxSleeve') ? 'BOXSET' : String(type || '').toUpperCase();
}

function renderConditionMultiselects() {
    const mediaSelect = document.getElementById('mediaConditionOptions');
    const sleeveSelect = document.getElementById('sleeveConditionOptions');
    const mediaTypeSelect = document.getElementById('conditionMediaType');
    
    if (!mediaSelect || !sleeveSelect || !mediaTypeSelect) return;
    
    // Update current media type from dropdown
    currentConditionMediaType = mediaTypeSelect.value;
    
    // A box set has its own sleeve condition list, so that is the one shown.
    const visibleSleeveType = effectiveSleeveType();
    
    // Every media type is present in the list so the All Types picker can toggle
    // any column; only the current type's entries are shown.
    const mediaConditionData = (customOptionsData.mediaCondition || [])
        .map(opt => ({ opt, type: opt.media_type || currentConditionMediaType }));
    // Box Sleeve is a fourth sleeve column: it is offered in Sleeve (All Types)
    // and never in the normal per-type multiselect, but its options live in the
    // same list so the picker can toggle them like any other type.
    const sleeveData = ['lp', 'cd', 'cassette', 'boxSleeve']
        .flatMap(type => (customOptionsData[type] || []).map(opt => ({ opt, type })));
    
    // Helper to render a multiselect
    const renderSelect = (select, selectedKeys, data, visibleType) => {
        select.innerHTML = '';
        data.forEach(({ opt, type }) => {
            const option = document.createElement('option');
            const val = JSON.stringify(opt);
            option.value = val;
            option.text = (opt.favorite ? '⭐ ' : '') + opt.title;
            option.dataset.mediaType = type;
            option.hidden = type !== visibleType;
            if (selectedKeys.includes(opt.title + '|||' + opt.text)) {
                option.selected = true;
            }
            select.appendChild(option);
        });
    };
    
    // Get currently selected keys from the new multiselects (to preserve selection on re-render)
    const mediaSelectedKeys = Array.from(mediaSelect.selectedOptions).map(o => {
        try {
            const d = JSON.parse(o.value);
            return d.title + '|||' + d.text;
        } catch (e) { return ''; }
    });
    const sleeveSelectedKeys = Array.from(sleeveSelect.selectedOptions).map(o => {
        try {
            const d = JSON.parse(o.value);
            return d.title + '|||' + d.text;
        } catch (e) { return ''; }
    });
    
    renderSelect(mediaSelect, mediaSelectedKeys, mediaConditionData, currentConditionMediaType);
    renderSelect(sleeveSelect, sleeveSelectedKeys, sleeveData, visibleSleeveType);
    
    // Sync to hidden legacy multiselects
    syncConditionMultiselectsToLegacy();
}

function syncConditionMultiselectsToLegacy() {
    const sleeveSelect = document.getElementById('sleeveConditionOptions');
    if (!sleeveSelect) return;

    const legacyByType = {
        lp: document.getElementById('lpOptions'),
        cd: document.getElementById('cdOptions'),
        cassette: document.getElementById('customOptions'),
        boxSleeve: document.getElementById('boxSleeveOptions')
    };

    // Selections may come from any media type, so distribute them per type.
    const selectedByType = { lp: [], cd: [], cassette: [], boxSleeve: [] };
    Array.from(sleeveSelect.selectedOptions).forEach(o => {
        try {
            const d = JSON.parse(o.value);
            const type = o.dataset.mediaType || currentConditionMediaType;
            if (selectedByType[type]) selectedByType[type].push(d.title + '|||' + d.text);
        } catch (e) {}
    });

    Object.entries(legacyByType).forEach(([type, legacySelect]) => {
        if (!legacySelect) return;
        Array.from(legacySelect.options).forEach(opt => {
            try {
                const d = JSON.parse(opt.value);
                opt.selected = selectedByType[type].includes(d.title + '|||' + d.text);
            } catch (e) {}
        });
    });
}

function resetCustomOptionsSearchAndFocus() {
    customOptionsSearchTerm = '';
    const input = document.getElementById('customOptionsSearch');
    if (input) input.value = '';
    renderCustomOptionsModalList();
    if (input) setTimeout(() => input.focus(), 0);
}

function renderCustomOptionsModalList() {
    const list = document.getElementById('customOptionsList');
    if (!list) return;
    // Both categories always show media type filter
    const mediaTypeFilter = document.getElementById('modalMediaTypeFilter');
    const newOptionMediaTypeContainer = document.getElementById('newOptionMediaTypeContainer');
    if (mediaTypeFilter) mediaTypeFilter.style.display = 'block';
    if (newOptionMediaTypeContainer) newOptionMediaTypeContainer.style.display = 'block';

    // Auto-populate media type from main form's media format if not already set
    const modalMediaTypeSelect = document.getElementById('modalMediaTypeSelect');
    const conditionMediaTypeSelect = document.getElementById('conditionMediaType');
    if (modalMediaTypeSelect && conditionMediaTypeSelect && !modalMediaTypeSelect.dataset.userChanged) {
        // Box Set shows sleeve conditions only, so follow that in the editor too.
        modalMediaTypeSelect.value = effectiveSleeveType();
    }

    // Get data based on category
    let currentData;
    const selectedMediaType = modalMediaTypeSelect?.value || currentConditionMediaType;

    // Box Set has no media conditions, so that category is not offered while it
    // is selected - the list is always the Box Sleeve one.
    const modalCategorySelect = document.getElementById('modalCategorySelect');
    const isBoxType = selectedMediaType === 'boxSleeve';
    if (modalCategorySelect) {
        const mediaCatOption = Array.from(modalCategorySelect.options).find(o => o.value === 'mediaCondition');
        if (mediaCatOption) mediaCatOption.hidden = isBoxType;
        if (isBoxType) {
            currentModalCategory = 'sleeveCondition';
            modalCategorySelect.value = 'sleeveCondition';
        }
    }
    const newOptionMediaTypeSelect = document.getElementById('newOptionMediaType');
    if (newOptionMediaTypeSelect) newOptionMediaTypeSelect.value = selectedMediaType;
    
    if (currentModalCategory === 'mediaCondition') {
        // Filter mediaCondition by selected media type
        currentData = (customOptionsData.mediaCondition || []).filter(opt => opt.media_type === selectedMediaType);
    } else if (currentModalCategory === 'sleeveCondition') {
        // Filter sleeve conditions (lp, cd, cassette arrays) by selected media type
        currentData = customOptionsData[selectedMediaType] || [];
    } else {
        currentData = [];
    }

    const hasAnyOptions = currentData && currentData.length > 0;
    if (customOptionsSearchTerm) {
        const term = customOptionsSearchTerm.toLowerCase();
        currentData = (currentData || []).filter(opt =>
            (opt.title || '').toLowerCase().includes(term) ||
            (opt.text || '').toLowerCase().includes(term));
    }

    list.innerHTML = '';

    if (!currentData || currentData.length === 0) {
        list.innerHTML = hasAnyOptions
            ? '<div style="font-size: 11px; color: #666; text-align: center;">No matches for this search.</div>'
            : '<div style="font-size: 11px; color: #666; text-align: center;">No options found for this category. Add one below.</div>';
        return;
    }

    currentData.forEach((opt, index) => {
        const item = document.createElement('div');
        item.style.cssText = 'display:flex; justify-content:space-between; align-items:center; padding:4px 5px; border-bottom:1px solid var(--border-color); gap:3px;';

        if (editingCustomOption === opt) {
            item.style.backgroundColor = 'var(--wysiwyg-blue-light, #e6f0ff)';
        }

        const textCol = document.createElement('div');
        textCol.style.cssText = 'font-size:11px; flex-grow:1; cursor:pointer; min-width:0;';
        textCol.title = 'Click to Edit';
        textCol.onclick = () => editCustomOption(opt);
        // Show media_type for mediaCondition entries
        let mediaTypeDisplay = '';
        if (currentModalCategory === 'mediaCondition' && opt.media_type) {
            mediaTypeDisplay = `<br><span style="color:#0066cc; font-size:10px;">[${opt.media_type.toUpperCase()}]</span>`;
        }
        // For sleeveCondition, show which media type it belongs to
        if (currentModalCategory === 'sleeveCondition') {
            const typeLabel = sleeveConditionLabel(selectedMediaType);
            mediaTypeDisplay = `<br><span style="color:#0066cc; font-size:10px;">[${typeLabel}]</span>`;
        }
        textCol.innerHTML = `<strong>${opt.title}</strong><br><span style="color:#666;">${opt.text}</span>${mediaTypeDisplay}`;

        const starBtn = document.createElement('button');
        starBtn.innerHTML = opt.favorite ? '⭐' : '☆';
        starBtn.title = opt.favorite ? 'Remove from Favorites' : 'Add to Favorites';
        starBtn.className = 'nav-btn';
        starBtn.style.cssText = 'padding:2px 5px; height:20px; font-size:10px; flex-shrink:0; cursor:pointer;';
        starBtn.onclick = (e) => toggleFavoriteCustomOption(e, opt);

        const delBtn = document.createElement('button');
        delBtn.innerHTML = '❌';
        delBtn.title = 'Delete Option';
        delBtn.className = 'nav-btn';
        delBtn.style.cssText = 'padding:2px 5px; color:var(--danger-color); height:20px; font-size:10px; flex-shrink:0;';
        delBtn.onclick = (e) => deleteCustomOption(e, opt);

        item.appendChild(textCol);
        item.appendChild(starBtn);
        item.appendChild(delBtn);
        list.appendChild(item);
    });
}


// --- Condition Picker (Open button) ---

function getConditionPickerConfigs() {
    // Return configs based on current media type and view mode
    const mediaType = currentConditionMediaType;
    if (conditionPickerViewMode === 'dual') {
        return [
            { id: 'mediaConditionOptions', key: 'mediaCondition', mediaType: mediaType, label: mediaType.toUpperCase() + ' MEDIA CONDITION', useMediaCondition: true },
            { id: 'sleeveConditionOptions', key: mediaType, label: sleeveConditionLabel(mediaType) + ' SLEEVE CONDITION' }
        ];
    } else {
        // Single column mode - only Media Condition; always show the active media format
        return [
            { id: 'mediaConditionOptions', key: 'mediaCondition', mediaType: mediaType, label: mediaType.toUpperCase() + ' MEDIA CONDITION', useMediaCondition: true }
        ];
    }
}

function setDualColumnToggle(visible, checked) {
    const label = document.getElementById('dualColumnModeLabel');
    if (label) label.style.display = visible ? '' : 'none';
    const cb = document.getElementById('dualColumnMode');
    if (cb) cb.checked = !!checked;
}

function conditionOptionKey(opt) {
    return (opt ? opt.title + '|||' + opt.text : '');
}

function openFavoriteContextMenuAt(e, targetId, optionKey, optionMediaType) {
    e.preventDefault();
    e.stopPropagation();
    const menu = document.getElementById('customContextMenu');
    if (!menu) return;
    ['openMediaContextItem', 'openSleeveContextItem', 'openAllMediaContextItem', 'openAllSleeveContextItem',
        'editConditionContextItem', 'clearConditionContextItem'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = 'none';
        });
    const favItem = document.getElementById('favoriteContextItem');
    if (favItem) favItem.style.display = 'block';
    menu.dataset.targetId = targetId;
    menu.dataset.optionKey = optionKey || '';
    menu.dataset.optionMediaType = optionMediaType || '';
    menu.style.display = 'block';
    menu.style.left = e.pageX + 'px';
    menu.style.top = e.pageY + 'px';
}

function getSelectedConditionKeys(selectId) {
    const select = document.getElementById(selectId);
    if (!select) return [];
    return Array.from(select.selectedOptions).map(o => {
        try {
            return conditionOptionKey(JSON.parse(o.value));
        } catch (e) {
            return '';
        }
    });
}

function toggleConditionOption(selectId, opt) {
    const select = document.getElementById(selectId);
    if (!select) return;

    const key = conditionOptionKey(opt);
    const option = Array.from(select.options).find(o => {
        try {
            return conditionOptionKey(JSON.parse(o.value)) === key;
        } catch (e) {
            return false;
        }
    });

    if (option) {
        option.selected = !option.selected;
        renderConditionPicker();
        // Sync to legacy multiselects
        syncConditionMultiselectsToLegacy();
    }
}

function syncMediaOptionsToTextBox() {
    const select = document.getElementById('mediaOptions');
    const box = document.getElementById('mediaDescriptionText');
    if (!select || !box) return;

    const parts = Array.from(select.selectedOptions).map(o => {
        try {
            const d = JSON.parse(o.value);
            return (d.text || d.title || '').trim();
        } catch (e) {
            return o.text.trim();
        }
    }).filter(Boolean);

    box.value = parts.join(' ');
}

function renderConditionPicker() {
    const container = document.getElementById('conditionPickerColumns');
    if (!container) return;

    container.innerHTML = '';

    const query = conditionPickerQuery();

    const configs = getConditionPickerConfigs();
    configs.forEach(config => {
        const select = document.getElementById(config.id);
        
        // Get data based on config type
        let allItems;
        if (config.useMediaCondition) {
            // Filter mediaCondition by media_type
            allItems = (customOptionsData.mediaCondition || []).filter(opt => opt.media_type === config.mediaType);
        } else {
            // Use original condition arrays (lp, cd, cassette)
            allItems = customOptionsData[config.key] || [];
        }
        
        const items = allItems.filter(opt => conditionPickerMatch(opt, query));
        const selectedKeys = getSelectedConditionKeys(config.id);

        const column = document.createElement('div');
        column.style.cssText = 'flex: 1; min-width: 0; display: flex; flex-direction: column;';

        const header = document.createElement('div');
        header.textContent = config.label + (selectedKeys.length ? ` (${selectedKeys.length})` : '');
        header.style.cssText = 'font-size: 11px; font-weight: 700; margin-bottom: 4px; color: var(--text-color, #444); text-align: center; flex-shrink: 0;';
        column.appendChild(header);

        const list = document.createElement('div');
        list.style.cssText = 'flex: 1; min-height: 80px; overflow-y: auto; border: 1px solid var(--border-color, #ccc); border-radius: 4px;';

        if (items.length === 0) {
            const emptyMsg = allItems.length === 0 ? 'No options' : 'No matches';
            list.innerHTML = `<div style="font-size: 11px; color: var(--text-muted, #666); text-align: center; padding: 8px;">${emptyMsg}</div>`;
        }

        items.forEach(opt => {
            const isSelected = selectedKeys.includes(conditionOptionKey(opt));
            const row = document.createElement('div');
            row.style.cssText = 'display: flex; gap: 5px; align-items: flex-start; padding: 4px 6px; cursor: pointer; font-size: 11px; border-bottom: 1px solid var(--border-color, #eee);' +
                (isSelected ? ' background: var(--wysiwyg-blue-light, #e6f0ff); font-weight: bold; color: #000;' : '');
            row.innerHTML =
                `<span style="flex-shrink: 0;">${opt.favorite ? '⭐' : (isSelected ? '☑' : '☐')}</span>` +
                `<div style="min-width: 0;"><strong>${opt.title}</strong><br>` +
                `<span style="color: ${isSelected ? '#444' : 'var(--text-muted, #666)'}; font-weight: normal;">${opt.text || ''}</span></div>`;
            row.onclick = () => toggleConditionOption(config.id, opt);
            // Add context menu for favoriting
            row.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const menu = document.getElementById('customContextMenu');
                if (menu) {
                    // Only show favorite option for modal rows
                    document.getElementById('favoriteContextItem').style.display = 'block';
                    document.getElementById('openMediaContextItem').style.display = 'none';
                    document.getElementById('openSleeveContextItem').style.display = 'none';
                    document.getElementById('openAllMediaContextItem').style.display = 'none';
                    document.getElementById('openAllSleeveContextItem').style.display = 'none';
                    document.getElementById('editConditionContextItem').style.display = 'none';
                    document.getElementById('clearConditionContextItem').style.display = 'none';
                    
                    // Store the option data and config for the favorite toggle
                    menu.dataset.targetId = config.id;
                    menu.dataset.optionKey = conditionOptionKey(opt);
                    menu.dataset.optionMediaType = opt.media_type || '';
                    
                    menu.style.display = 'block';
                    menu.style.left = e.pageX + 'px';
                    menu.style.top = e.pageY + 'px';
                }
            });
            list.appendChild(row);
        });

        column.appendChild(list);
        container.appendChild(column);
    });

    // Single-column default is Media Condition; leave the dual source untouched
    if (conditionPickerViewMode !== 'dual') {
        conditionPickerSingleSource = 'media';
    }

    // Re-show the "Both" toggle for the single-column default view (OPEN button / unchecking the box)
    setDualColumnToggle(true, false);

    // This view owns the search bar until another picker is opened
    conditionPickerRedraw = () => renderConditionPicker();
}


// --- List Picker (small Open buttons beside form labels) ---

const LIST_PICKER_CONFIGS = [
    { selectId: 'packagingFeature', label: 'PACKAGING FEATURE', title: 'Select Packaging Feature' },
    { selectId: 'edition', label: 'EDITION', title: 'Select Edition' },
    { selectId: 'formatTags', label: 'FORMAT TAGS', title: 'Select Format Tags' },
    { selectId: 'weightSpeed', label: 'WEIGHT/SPEED', title: 'Select Weight/Speed' },
    { selectId: 'preFM', label: 'PRE FM', title: 'Select Pre FM' },
    { selectId: 'postFM', label: 'POST FM', title: 'Select Post FM' },
    { selectId: 'sleevePackaging', label: 'SLEEVE PACKAGING', title: 'Select Sleeve Packaging' }
];

let activeListPicker = null;
let listPickerScrollTop = 0;

function renderListPicker() {
    const container = document.getElementById('listPickerColumns');
    if (!container || !activeListPicker) return;
    container.innerHTML = '';
    document.getElementById('listPickerHeader').textContent = activeListPicker.title;

    const select = document.getElementById(activeListPicker.selectId);
    const options = select ? Array.from(select.options).filter(o => o.value) : [];
    const selectedCount = options.filter(o => o.selected).length;

    const column = document.createElement('div');
    column.style.cssText = 'flex: 1; min-width: 0; display: flex; flex-direction: column;';

    const header = document.createElement('div');
    header.textContent = activeListPicker.label + (selectedCount ? ` (${selectedCount})` : '');
    header.style.cssText = 'font-size: 11px; font-weight: 700; margin-bottom: 4px; color: var(--text-color, #444); text-align: center; flex-shrink: 0;';
    column.appendChild(header);

    const list = document.createElement('div');
    list.style.cssText = 'flex: 1; min-height: 80px; overflow-y: auto; border: 1px solid var(--border-color, #ccc); border-radius: 4px;';

    if (options.length === 0) {
        list.innerHTML = '<div style="font-size: 11px; color: var(--text-muted, #666); text-align: center; padding: 8px;">No options</div>';
    }

    options.forEach(opt => {
        const isSelected = opt.selected;
        const row = document.createElement('div');
        row.style.cssText = 'display: flex; gap: 5px; align-items: flex-start; padding: 4px 6px; cursor: pointer; font-size: 11px; border-bottom: 1px solid var(--border-color, #eee);' +
            (isSelected ? ' background: var(--wysiwyg-blue-light, #e6f0ff); font-weight: bold; color: #000;' : '');
        row.innerHTML =
            `<span style="flex-shrink: 0;">${isSelected ? '☑' : '☐'}</span>` +
            `<div style="min-width: 0;"><strong>${opt.text || opt.value}</strong></div>`;
        row.onclick = () => {
            listPickerScrollTop = list.scrollTop;
            opt.selected = !opt.selected;
            renderListPicker();
        };
        list.appendChild(row);
    });

    column.appendChild(list);
    container.appendChild(column);
    list.scrollTop = listPickerScrollTop;
}

function openListPicker(selectId) {
    const config = LIST_PICKER_CONFIGS.find(c => c.selectId === selectId);
    if (!config) return;
    activeListPicker = config;
    listPickerScrollTop = 0;
    window.resetListPickerPlacement?.();
    renderListPicker();
    document.getElementById('listPickerModal').style.display = 'block';
}


// Draggable by header (matches WysiScan ocr-modal behavior); each modal content
// is resizable via CSS and its column lists flex to redraw on resize. Returns a
// function that restores the modal's default placement and size.
function initDraggableModal(contentId, headerId) {
    const content = document.getElementById(contentId);
    const header = document.getElementById(headerId);
    if (!content || !header) return () => { };

    const defaultStyle = content.getAttribute('style') || '';
    let isDragging = false;
    let startX = 0, startY = 0, initialLeft = 0, initialTop = 0;

    header.addEventListener('mousedown', (e) => {
        if (e.target.closest('button, .close-btn')) return;
        isDragging = true;
        startX = e.clientX;
        startY = e.clientY;

        const rect = content.getBoundingClientRect();
        content.style.position = 'fixed';
        content.style.margin = '0';
        content.style.left = rect.left + 'px';
        content.style.top = rect.top + 'px';
        initialLeft = rect.left;
        initialTop = rect.top;

        header.style.cursor = 'grabbing';
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        content.style.left = (initialLeft + (e.clientX - startX)) + 'px';
        content.style.top = (initialTop + (e.clientY - startY)) + 'px';
    });

    document.addEventListener('mouseup', () => {
        if (!isDragging) return;
        isDragging = false;
        header.style.cursor = 'move';
    });

    return () => {
        content.setAttribute('style', defaultStyle);
    };
}

window.resetConditionPickerPlacement = initDraggableModal('conditionPickerContent', 'conditionPickerHeader');
window.resetListPickerPlacement = initDraggableModal('listPickerContent', 'listPickerHeader');
window.resetCustomOptionsModalPlacement = initDraggableModal('customOptionsModalContent', 'customOptionsModalHeader');


window.editCustomOption = function (opt) {
    if (!opt || typeof opt !== 'object') return;

    // Resolve by object identity: the visible list may be filtered by the
    // search box and/or media type, so display indexes are not array indexes.
    const selectedMediaType = document.getElementById('modalMediaTypeSelect')?.value || currentConditionMediaType;
    const currentData = currentModalCategory === 'mediaCondition'
        ? (customOptionsData.mediaCondition || [])
        : (customOptionsData[selectedMediaType] || []);

    editingCustomOptionIndex = currentData.indexOf(opt);
    editingCustomOption = opt;
    document.getElementById('newOptionTitle').value = opt.title;
    document.getElementById('newOptionText').value = opt.text;
    
    // Set the media type dropdown
    const mediaTypeSelect = document.getElementById('newOptionMediaType');
    if (mediaTypeSelect) {
        mediaTypeSelect.value = opt.media_type || selectedMediaType;
    }
    
    document.getElementById('addCustomOptionBtn').innerText = 'Update';

    const cancelBtn = document.getElementById('cancelEditCustomOptionBtn');
    if (cancelBtn) cancelBtn.style.display = 'inline-block';
    const copyBtn = document.getElementById('copyCustomOptionBtn');
    if (copyBtn) copyBtn.style.display = 'inline-block';

    renderCustomOptionsModalList();
};

window.deleteCustomOption = function (event, opt) {
    event.stopPropagation();
    if (!opt || typeof opt !== 'object') return;

    const selectedMediaType = document.getElementById('modalMediaTypeSelect')?.value || currentConditionMediaType;
    const targetArray = currentModalCategory === 'mediaCondition'
        ? (customOptionsData.mediaCondition || [])
        : (customOptionsData[selectedMediaType] || []);

    const actualIndex = targetArray.indexOf(opt);
    if (actualIndex === -1) return;
    targetArray.splice(actualIndex, 1);

    if (editingCustomOption === opt) {
        cancelEditCustomOption();
    }
    saveCustomOptions();
    renderCustomOptionsSelect();
    renderCustomOptionsModalList();
};

window.toggleFavoriteCustomOption = function (event, opt) {
    event.stopPropagation();
    if (!opt || typeof opt !== 'object') return;

    opt.favorite = !opt.favorite;

    saveCustomOptions();
    renderCustomOptionsSelect();
    renderCustomOptionsModalList();
};

function cancelEditCustomOption() {
    editingCustomOptionIndex = -1;
    editingCustomOption = null;
    customOptionCopyDraft = false;
    if (document.getElementById('newOptionTitle')) document.getElementById('newOptionTitle').value = '';
    if (document.getElementById('newOptionText')) document.getElementById('newOptionText').value = '';
    const addBtn = document.getElementById('addCustomOptionBtn');
    if (addBtn) addBtn.innerText = 'Add';

    const cancelBtn = document.getElementById('cancelEditCustomOptionBtn');
    if (cancelBtn) cancelBtn.style.display = 'inline-block';
    const copyBtn = document.getElementById('copyCustomOptionBtn');
    if (copyBtn) copyBtn.style.display = 'none';

    renderCustomOptionsModalList();
}

// Removed mergeConditions function as it is now integrated into updateMenus

document.addEventListener('DOMContentLoaded', () => {
    loadCustomOptions();
    clearCurrentItem();

    // Pick up condition edits made in the editor window without a full reload.
    const refreshCustomOptions = () => { if (!document.hidden) loadCustomOptions(); };
    window.addEventListener('focus', refreshCustomOptions);
    document.addEventListener('visibilitychange', refreshCustomOptions);

    // Media type dropdown for condition multiselects
    document.getElementById('conditionMediaType')?.addEventListener('change', (e) => {
        currentConditionMediaType = e.target.value;
        // Update modal category to match
        currentModalCategory = currentConditionMediaType;
        const modalCatSelect = document.getElementById('modalCategorySelect');
        if (modalCatSelect) modalCatSelect.value = currentModalCategory;
        renderCustomOptionsSelect();
    });

    // Sync new multiselects to legacy on selection change
    ['mediaConditionOptions', 'sleeveConditionOptions'].forEach(id => {
        const select = document.getElementById(id);
        if (select) {
            select.addEventListener('change', () => {
                syncConditionMultiselectsToLegacy();
            });
        }
    });

    document.getElementById('modalCategorySelect')?.addEventListener('change', (e) => {
        currentModalCategory = e.target.value;
        cancelEditCustomOption();
        renderCustomOptionsModalList();
    });

    // Media type filter for modal - track user changes
    document.getElementById('modalMediaTypeSelect')?.addEventListener('change', (e) => {
        e.target.dataset.userChanged = 'true';
        renderCustomOptionsModalList();
    });

    document.getElementById('editCustomOptionsBtn')?.addEventListener('click', (e) => {
        e.preventDefault();
        cancelEditCustomOption();
        // Follow the main form's current type again (Box Set included) instead of
        // whatever was picked in this modal last time.
        const modalTypeSel = document.getElementById('modalMediaTypeSelect');
        if (modalTypeSel) delete modalTypeSel.dataset.userChanged;
        window.resetCustomOptionsModalPlacement?.();
        document.getElementById('customOptionsModal').style.display = 'block';
        resetCustomOptionsSearchAndFocus();
    });

    document.getElementById('closeCustomOptionsModalBtn')?.addEventListener('click', () => {
        document.getElementById('customOptionsModal').style.display = 'none';
    });

    document.getElementById('customOptionsSearch')?.addEventListener('input', (e) => {
        customOptionsSearchTerm = e.target.value.trim();
        renderCustomOptionsModalList();
    });

    document.getElementById('clearCustomOptionsSearchBtn')?.addEventListener('click', (e) => {
        e.preventDefault();
        customOptionsSearchTerm = '';
        const input = document.getElementById('customOptionsSearch');
        if (input) { input.value = ''; input.focus(); }
        renderCustomOptionsModalList();
    });

    document.getElementById('cancelEditCustomOptionBtn')?.addEventListener('click', () => {
        if (editingCustomOption || customOptionCopyDraft) {
            cancelEditCustomOption();
            return;
        }
        document.getElementById('customOptionsModal').style.display = 'none';
    });

    document.getElementById('copyCustomOptionBtn')?.addEventListener('click', () => {
        if (!editingCustomOption) return;

        document.getElementById('newOptionTitle').value = `${editingCustomOption.title} (copy)`;
        document.getElementById('newOptionText').value = editingCustomOption.text;
        document.getElementById('newOptionMediaType').value =
            editingCustomOption.media_type || document.getElementById('modalMediaTypeSelect')?.value || currentConditionMediaType;
        editingCustomOption = null;
        editingCustomOptionIndex = -1;
        customOptionCopyDraft = true;
        document.getElementById('addCustomOptionBtn').innerText = 'Update';
        document.getElementById('copyCustomOptionBtn').style.display = 'none';
        renderCustomOptionsModalList();
    });

    document.getElementById('addCustomOptionBtn')?.addEventListener('click', () => {
        const titleInput = document.getElementById('newOptionTitle');
        const textInput = document.getElementById('newOptionText');

        const title = titleInput.value.trim();
        const text = textInput.value.trim();

        if (!title) {
            alert('Please enter a title');
            return;
        }

        let newOption = { title, text };
        // For both categories, add media_type from the dropdown
        const mediaTypeSelect = document.getElementById('newOptionMediaType');
        const selectedMediaType = mediaTypeSelect ? mediaTypeSelect.value : currentConditionMediaType;
        newOption.media_type = selectedMediaType;

        let targetArray;
        if (currentModalCategory === 'mediaCondition') {
            targetArray = customOptionsData.mediaCondition;
        } else if (currentModalCategory === 'sleeveCondition') {
            targetArray = customOptionsData[editingCustomOption?.media_type || selectedMediaType];
        }

        if (editingCustomOption) {
            const actualIndex = targetArray.indexOf(editingCustomOption);
            if (actualIndex !== -1) {
                targetArray[actualIndex] = newOption;
            } else {
                targetArray.push(newOption);
            }
        } else {
            targetArray.push(newOption);
        }

        saveCustomOptions();
        cancelEditCustomOption();
        renderCustomOptionsSelect();
        renderCustomOptionsModalList();
    });

    document.getElementById('clearCustomOptionsBtn')?.addEventListener('click', (e) => {
        e.preventDefault();
        // Clear new multiselects
        ['mediaConditionOptions', 'sleeveConditionOptions'].forEach(id => {
            const select = document.getElementById(id);
            if (select) {
                Array.from(select.options).forEach(opt => opt.selected = false);
            }
        });
        // Clear legacy multiselects
        ['lpOptions', 'cdOptions', 'customOptions'].forEach(id => {
            const select = document.getElementById(id);
            if (select) {
                Array.from(select.options).forEach(opt => opt.selected = false);
            }
        });
    });

    document.getElementById('openCustomOptionsBtn')?.addEventListener('click', (e) => {
        e.preventDefault();
        const search = document.getElementById('conditionPickerSearch');
        if (search) search.value = '';
        window.resetConditionPickerPlacement?.();
        
        // Reset to single column default
        conditionPickerViewMode = 'single';
        const dualCheckbox = document.getElementById('dualColumnMode');
        if (dualCheckbox) dualCheckbox.checked = false;
        
        const mediaType = currentConditionMediaType;
        
        // Open single column - default to Media Condition
        currentModalCategory = 'mediaCondition';
        const modalCatSelect = document.getElementById('modalCategorySelect');
        if (modalCatSelect) modalCatSelect.value = 'mediaCondition';
        renderConditionPicker();
        const header = document.getElementById('conditionPickerHeader');
        if (header) header.textContent = currentConditionMediaType.toUpperCase() + ' MEDIA CONDITION';
        setAllTypesControlsVisible(false);
        document.getElementById('conditionPickerModal').style.display = 'block';
    });

    document.getElementById('conditionPickerSearch')?.addEventListener('input', () => {
        // Always filter whatever list is currently open; never switch views
        if (conditionPickerRedraw) {
            conditionPickerRedraw();
        } else {
            renderConditionPicker();
        }
    });

    document.getElementById('clearConditionSearchBtn')?.addEventListener('click', (e) => {
        e.preventDefault();
        const search = document.getElementById('conditionPickerSearch');
        if (search) search.value = '';
        if (conditionPickerRedraw) {
            conditionPickerRedraw();
        } else {
            renderConditionPicker();
        }
        search?.focus();
    });

    document.getElementById('allTypesView')?.addEventListener('change', (e) => {
        if (e.target.value === 'sleeve') {
            openSleeveConditionThreeColumnModal(true);
        } else {
            openMediaConditionThreeColumnModal(true);
        }
    });

    document.getElementById('unfavoriteAllBtn')?.addEventListener('click', (e) => {
        e.preventDefault();
        unfavoriteAllCurrentType();
    });

    // Sleeve Packaging drives which sleeve condition list is shown: "Box Set"
    // swaps in the Box Sleeve conditions, anything else restores LP/CD/Cassette.
    document.getElementById('sleevePackaging')?.addEventListener('change', () => {
        renderConditionMultiselects();
    });

    // Handle dual column mode toggle in modal
    document.getElementById('dualColumnMode')?.addEventListener('change', () => {
        const dualColumn = document.getElementById('dualColumnMode').checked;
        const mediaType = currentConditionMediaType;
        if (dualColumn) {
            conditionPickerViewMode = 'dual';
            openDualColumnConditionPicker(mediaType, true);
        } else {
            conditionPickerViewMode = 'single';
            // Return to whichever single column the modal was opened from
            if (conditionPickerSingleSource === 'sleeve') {
                currentModalCategory = 'sleeveCondition';
                const sleeveCatSelect = document.getElementById('modalCategorySelect');
                if (sleeveCatSelect) sleeveCatSelect.value = 'sleeveCondition';
                openConditionPickerForSleeve(mediaType, true);
            } else {
                currentModalCategory = 'mediaCondition';
                const modalCatSelect = document.getElementById('modalCategorySelect');
                if (modalCatSelect) modalCatSelect.value = 'mediaCondition';
                // Preserve scroll/search when collapsing back to the single column
                openConditionPickerForMedia(mediaType, true);
            }
        }
    });

    document.getElementById('closeConditionPickerBtn')?.addEventListener('click', () => {
        document.getElementById('conditionPickerModal').style.display = 'none';
        window.currentThreeColumnMode = null;
    });

    document.getElementById('doneConditionPickerBtn')?.addEventListener('click', () => {
        document.getElementById('conditionPickerModal').style.display = 'none';
    });

    document.getElementById('clearConditionPickerBtn')?.addEventListener('click', (e) => {
        e.preventDefault();
        const dualCb = document.getElementById('dualColumnMode');
        const dualState = dualCb ? dualCb.checked : false;
        // Clear new multiselects
        ['mediaConditionOptions', 'sleeveConditionOptions'].forEach(id => {
            const select = document.getElementById(id);
            if (select) {
                Array.from(select.options).forEach(opt => opt.selected = false);
            }
        });
        // Clear legacy multiselects
        ['lpOptions', 'cdOptions', 'customOptions'].forEach(id => {
            const select = document.getElementById(id);
            if (select) {
                Array.from(select.options).forEach(opt => opt.selected = false);
            }
        });
        // Keep the current view (and its scroll position) instead of rebuilding to the top
        if (conditionPickerRedraw) conditionPickerRedraw();
        else renderConditionPicker();
        // Clearing must not touch the "Both" checkbox state
        if (dualCb) dualCb.checked = dualState;
    });

    // Auto-focus the search box whenever the condition picker opens
    const conditionPickerEl = document.getElementById('conditionPickerModal');
    if (conditionPickerEl) {
        new MutationObserver(() => {
            if (conditionPickerEl.style.display !== 'block') return;
            const search = document.getElementById('conditionPickerSearch');
            if (search && document.activeElement !== search) search.focus();
        }).observe(conditionPickerEl, { attributes: true, attributeFilter: ['style'] });
    }

    document.querySelectorAll('.condition-open-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const mediaTypeSelect = document.getElementById('conditionMediaType');
            const mediaType = mediaTypeSelect ? mediaTypeSelect.value : currentConditionMediaType;
            currentConditionMediaType = mediaType;
            if (e.ctrlKey || e.metaKey) {
                openConditionsBothCurrentType();
            } else if (btn.dataset.condition === 'media') {
                openConditionPickerForMedia(mediaType);
            } else {
                // A box set shows its own sleeve condition list.
                openConditionPickerForSleeve(effectiveSleeveType());
            }
        });
    });

    document.querySelectorAll('.list-picker-open-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            openListPicker(btn.dataset.picker);
        });
    });

    document.getElementById('closeListPickerBtn')?.addEventListener('click', () => {
        document.getElementById('listPickerModal').style.display = 'none';
        renderConditionMultiselects();      // packaging may have just changed
    });

    document.getElementById('doneListPickerBtn')?.addEventListener('click', () => {
        document.getElementById('listPickerModal').style.display = 'none';
        renderConditionMultiselects();      // packaging may have just changed
    });

    document.getElementById('clearListPickerBtn')?.addEventListener('click', (e) => {
        e.preventDefault();
        if (activeListPicker) {
            const select = document.getElementById(activeListPicker.selectId);
            if (select) {
                Array.from(select.options).forEach(opt => opt.selected = false);
            }
        }
        renderListPicker();
        renderConditionMultiselects();      // clearing Box Set restores the media-type list
    });

    // Context Menu for Favoriting
    ['lpOptions', 'cdOptions', 'customOptions', 'mediaConditionOptions', 'sleeveConditionOptions'].forEach(id => {
        const select = document.getElementById(id);
        if (!select) return;

        select.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            const menu = document.getElementById('customContextMenu');
            if (menu) {
                // Show/hide menu items based on target
                const isMediaCondition = id === 'mediaConditionOptions';
                const isSleeveCondition = id === 'sleeveConditionOptions';
                const isConditionMultiselect = isMediaCondition || isSleeveCondition;
                
                document.getElementById('openMediaContextItem').style.display = isMediaCondition ? 'block' : 'none';
                document.getElementById('openSleeveContextItem').style.display = isSleeveCondition ? 'block' : 'none';
                document.getElementById('openAllMediaContextItem').style.display = isMediaCondition ? 'block' : 'none';
                document.getElementById('openAllSleeveContextItem').style.display = isSleeveCondition ? 'block' : 'none';
                document.getElementById('editConditionContextItem').style.display = isConditionMultiselect ? 'block' : 'none';
                document.getElementById('clearConditionContextItem').style.display = isConditionMultiselect ? 'block' : 'none';
                // Show favorite item for condition multiselects and legacy options
                document.getElementById('favoriteContextItem').style.display = (isConditionMultiselect || id === 'lpOptions' || id === 'cdOptions' || id === 'customOptions') ? 'block' : 'none';
                
                menu.style.display = 'block';
                menu.style.left = e.pageX + 'px';
                menu.style.top = e.pageY + 'px';
                menu.dataset.targetId = id;
                delete menu.dataset.optionKey;
                delete menu.dataset.optionMediaType;
            }
        });
    });

    document.addEventListener('click', () => {
        const menu = document.getElementById('customContextMenu');
        if (menu) menu.style.display = 'none';
    });

    const favItem = document.getElementById('favoriteContextItem');
    if (favItem) {
        favItem.onmouseover = () => favItem.style.background = 'rgba(128, 128, 128, 0.2)';
        favItem.onmouseout = () => favItem.style.background = 'transparent';
        favItem.onclick = () => {
            const menu = document.getElementById('customContextMenu');
            const targetId = menu.dataset.targetId;
            const optionKey = menu.dataset.optionKey;
            const optionMediaType = menu.dataset.optionMediaType;
            
            // Handle modal rows (have optionKey but no select element)
            if (optionKey) {
                // Find the item in the appropriate data array
                let targetArray;
                if (targetId === 'mediaConditionOptions') {
                    targetArray = customOptionsData.mediaCondition;
                    // Filter by media_type if available
                    if (optionMediaType) {
                        targetArray = targetArray.filter(opt => opt.media_type === optionMediaType);
                    }
                } else if (targetId === 'sleeveConditionOptions') {
                    targetArray = optionMediaType && customOptionsData[optionMediaType]
                        ? customOptionsData[optionMediaType]
                        : (customOptionsData[currentConditionMediaType] || []);
                } else if (['lp', 'cd', 'cassette'].includes(targetId)) {
                    targetArray = customOptionsData[targetId] || [];
                } else {
                    // Fallback: search all arrays
                    targetArray = [...customOptionsData.lp, ...customOptionsData.cd, ...customOptionsData.cassette,
                                   ...(customOptionsData.boxSleeve || []), ...customOptionsData.mediaCondition];
                }
                
                const [title, text] = optionKey.split('|||');
                const item = targetArray.find(i => i.title === title && i.text === text);
                if (item) {
                    item.favorite = !item.favorite;
                    saveCustomOptions();
                    renderCustomOptionsSelect();
                    // Re-render the active picker so the new fav state shows
                    if (document.getElementById('conditionPickerModal').style.display === 'block' && conditionPickerRedraw) {
                        conditionPickerRedraw();
                    }
                }
                delete menu.dataset.optionKey;
                delete menu.dataset.optionMediaType;
                menu.style.display = 'none';
                return;
            }
            
            // Original logic for select elements
            const select = document.getElementById(targetId);
            if (!select) return;

            let key;
            if (targetId === 'lpOptions') key = 'lp';
            else if (targetId === 'cdOptions') key = 'cd';
            else if (targetId === 'mediaConditionOptions') key = 'mediaCondition';
            else if (targetId === 'sleeveConditionOptions') key = effectiveSleeveType();
            else key = 'cassette';

            const selectedOptions = Array.from(select.selectedOptions);

            if (selectedOptions.length === 0) return;

            selectedOptions.forEach(opt => {
                try {
                    const data = JSON.parse(opt.value);
                    // Use the row's own type when it has one, so favouriting works
                    // for whichever sleeve list is showing (including Box Set).
                    const type = opt.dataset.mediaType || key;
                    const item = (customOptionsData[type] || []).find(i => i.title === data.title && i.text === data.text &&
                        (!data.media_type || i.media_type === data.media_type));
                    if (item) {
                        item.favorite = !item.favorite;
                    }
                } catch (e) { }
            });

            saveCustomOptions();
            renderCustomOptionsSelect();
        };
    }

    // Open Media (Current Type) context menu
    const openMediaContextItem = document.getElementById('openMediaContextItem');
    if (openMediaContextItem) {
        openMediaContextItem.onmouseover = () => openMediaContextItem.style.background = 'rgba(128, 128, 128, 0.2)';
        openMediaContextItem.onmouseout = () => openMediaContextItem.style.background = 'transparent';
        openMediaContextItem.onclick = () => {
            const menu = document.getElementById('customContextMenu');
            const targetId = menu.dataset.targetId;
            if (targetId === 'mediaConditionOptions') {
                openConditionPickerForMedia(currentConditionMediaType);
            }
            menu.style.display = 'none';
        };
    }

    // Open Sleeve (Current Type) context menu
    const openSleeveContextItem = document.getElementById('openSleeveContextItem');
    if (openSleeveContextItem) {
        openSleeveContextItem.onmouseover = () => openSleeveContextItem.style.background = 'rgba(128, 128, 128, 0.2)';
        openSleeveContextItem.onmouseout = () => openSleeveContextItem.style.background = 'transparent';
        openSleeveContextItem.onclick = () => {
            const menu = document.getElementById('customContextMenu');
            const targetId = menu.dataset.targetId;
            if (targetId === 'sleeveConditionOptions') {
                openConditionPickerForSleeve(effectiveSleeveType());
            }
            menu.style.display = 'none';
        };
    }

    // Open Media (All Types) context menu
    const openAllMediaContextItem = document.getElementById('openAllMediaContextItem');
    if (openAllMediaContextItem) {
        openAllMediaContextItem.onmouseover = () => openAllMediaContextItem.style.background = 'rgba(128, 128, 128, 0.2)';
        openAllMediaContextItem.onmouseout = () => openAllMediaContextItem.style.background = 'transparent';
        openAllMediaContextItem.onclick = () => {
            const menu = document.getElementById('customContextMenu');
            const targetId = menu.dataset.targetId;
            if (targetId === 'mediaConditionOptions') {
                openMediaConditionThreeColumnModal();
            }
            menu.style.display = 'none';
        };
    }

    // Open Sleeve (All Types) context menu
    const openAllSleeveContextItem = document.getElementById('openAllSleeveContextItem');
    if (openAllSleeveContextItem) {
        openAllSleeveContextItem.onmouseover = () => openAllSleeveContextItem.style.background = 'rgba(128, 128, 128, 0.2)';
        openAllSleeveContextItem.onmouseout = () => openAllSleeveContextItem.style.background = 'transparent';
        openAllSleeveContextItem.onclick = () => {
            const menu = document.getElementById('customContextMenu');
            const targetId = menu.dataset.targetId;
            if (targetId === 'sleeveConditionOptions') {
                openSleeveConditionThreeColumnModal();
            }
            menu.style.display = 'none';
        };
    }

    // Edit List context menu
    const editContextItem = document.getElementById('editConditionContextItem');
    if (editContextItem) {
        editContextItem.onmouseover = () => editContextItem.style.background = 'rgba(128, 128, 128, 0.2)';
        editContextItem.onmouseout = () => editContextItem.style.background = 'transparent';
        editContextItem.onclick = () => {
            const menu = document.getElementById('customContextMenu');
            const targetId = menu.dataset.targetId;
            if (targetId === 'mediaConditionOptions') {
                currentModalCategory = 'mediaCondition';
                window.resetCustomOptionsModalPlacement?.();
                document.getElementById('customOptionsModal').style.display = 'block';
                const modalCatSelect = document.getElementById('modalCategorySelect');
                if (modalCatSelect) modalCatSelect.value = 'mediaCondition';
                const modalMediaTypeSelect = document.getElementById('modalMediaTypeSelect');
                if (modalMediaTypeSelect) modalMediaTypeSelect.value = currentConditionMediaType;
            } else if (targetId === 'sleeveConditionOptions') {
                currentModalCategory = 'sleeveCondition';
                window.resetCustomOptionsModalPlacement?.();
                document.getElementById('customOptionsModal').style.display = 'block';
                const modalCatSelect = document.getElementById('modalCategorySelect');
                if (modalCatSelect) modalCatSelect.value = 'sleeveCondition';
                const modalMediaTypeSelect = document.getElementById('modalMediaTypeSelect');
                if (modalMediaTypeSelect) {
                    // Box Set opens the Box Sleeve list; otherwise the current type.
                    modalMediaTypeSelect.value = effectiveSleeveType();
                    modalMediaTypeSelect.dataset.userChanged = 'true';
                }
            }
            resetCustomOptionsSearchAndFocus();
            menu.style.display = 'none';
        };
    }

    // Clear Selection context menu
    const clearContextItem = document.getElementById('clearConditionContextItem');
    if (clearContextItem) {
        clearContextItem.onmouseover = () => clearContextItem.style.background = 'rgba(128, 128, 128, 0.2)';
        clearContextItem.onmouseout = () => clearContextItem.style.background = 'transparent';
        clearContextItem.onclick = () => {
            const menu = document.getElementById('customContextMenu');
            const targetId = menu.dataset.targetId;
            const select = document.getElementById(targetId);
            if (select) {
                Array.from(select.options).forEach(opt => opt.selected = false);
                if (targetId === 'sleeveConditionOptions') {
                    syncConditionMultiselectsToLegacy();
                }
            }
            menu.style.display = 'none';
        };
    }
});

// Three-column Media Condition Modal
function openMediaConditionThreeColumnModal(preserveSearch) {
    const modal = document.getElementById('conditionPickerModal');
    const container = document.getElementById('conditionPickerColumns');
    const header = document.getElementById('conditionPickerHeader');
    const searchInput = document.getElementById('conditionPickerSearch');

    if (!modal || !container) return;

    const scrollPositions = preserveSearch ? captureConditionPickerScroll(container) : {};
    container.innerHTML = '';
    if (!preserveSearch && searchInput) searchInput.value = '';

    const pickerQuery = conditionPickerQuery();
    setDualColumnToggle(false, false);
    
    // Get selected options from inline multiselect and group by media_type
    const inlineSelect = document.getElementById('mediaConditionOptions');
    const selectedByMediaType = { lp: [], cd: [], cassette: [] };
    if (inlineSelect) {
        Array.from(inlineSelect.selectedOptions).forEach(o => {
            try {
                const d = JSON.parse(o.value);
                const key = d.title + '|||' + d.text;
                const mediaType = d.media_type;
                if (selectedByMediaType[mediaType]) {
                    selectedByMediaType[mediaType].push(key);
                }
            } catch (e) {}
        });
    }
    
    const mediaTypes = [
        { key: 'lp', label: 'LP MEDIA CONDITION' },
        { key: 'cd', label: 'CD MEDIA CONDITION' },
        { key: 'cassette', label: 'CASSETTE MEDIA CONDITION' }
    ];
    
    mediaTypes.forEach(config => {
        const allItems = (customOptionsData.mediaCondition || []).filter(opt => opt.media_type === config.key);
        const items = allItems.filter(opt => conditionPickerMatch(opt, pickerQuery));
        const selectedKeys = selectedByMediaType[config.key] || [];

        const column = document.createElement('div');
        column.style.cssText = 'flex: 1; min-width: 0; display: flex; flex-direction: column;';

        const headerEl = document.createElement('div');
        headerEl.textContent = config.label + (selectedKeys.length ? ` (${selectedKeys.length})` : '');
            headerEl.style.cssText = 'font-size: 11px; font-weight: 700; margin-bottom: 4px; text-align: center; flex-shrink: 0;' +
                ' background: var(--wysiwyg-blue, #0000ff); color: #fff; border-radius: 4px; padding: 3px 0;';
            column.appendChild(headerEl);

        const list = document.createElement('div');
        list.dataset.conditionPickerList = config.key;
        list.style.cssText = 'flex: 1; min-height: 80px; overflow-y: auto; border: 1px solid var(--border-color, #ccc); border-radius: 4px;';

        if (items.length === 0) {
            list.innerHTML = `<div style="font-size: 11px; color: var(--text-muted, #666); text-align: center; padding: 8px;">${allItems.length === 0 ? 'No options' : 'No matches'}</div>`;
        }

        items.forEach(opt => {
            const isSelected = selectedKeys.includes(conditionOptionKey(opt));
            const row = document.createElement('div');
            row.style.cssText = 'display: flex; gap: 5px; align-items: flex-start; padding: 4px 6px; cursor: pointer; font-size: 11px; border-bottom: 1px solid var(--border-color, #eee);' +
                (isSelected ? ' background: var(--wysiwyg-blue-light, #e6f0ff); font-weight: bold; color: #000;' : '');
            row.innerHTML =
                `<span style="flex-shrink: 0;">${opt.favorite ? '⭐' : (isSelected ? '☑' : '☐')}</span>` +
                `<div style="min-width: 0;"><strong>${opt.title}</strong><br>` +
                `<span style="color: ${isSelected ? '#444' : 'var(--text-muted, #666)'}; font-weight: normal;">${opt.text || ''}</span></div>`;
            row.onclick = () => {
                toggleMediaConditionOption(opt);
                openMediaConditionThreeColumnModal(true);
            };
            // Add context menu for favoriting
            row.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const menu = document.getElementById('customContextMenu');
                if (menu) {
                    document.getElementById('favoriteContextItem').style.display = 'block';
                    document.getElementById('openMediaContextItem').style.display = 'none';
                    document.getElementById('openSleeveContextItem').style.display = 'none';
                    document.getElementById('openAllMediaContextItem').style.display = 'none';
                    document.getElementById('openAllSleeveContextItem').style.display = 'none';
                    document.getElementById('editConditionContextItem').style.display = 'none';
                    document.getElementById('clearConditionContextItem').style.display = 'none';
                    menu.dataset.targetId = 'mediaConditionOptions';
                    menu.dataset.optionKey = conditionOptionKey(opt);
                    menu.dataset.optionMediaType = opt.media_type || '';
                    menu.style.display = 'block';
                    menu.style.left = e.pageX + 'px';
                    menu.style.top = e.pageY + 'px';
                }
            });
            list.appendChild(row);
        });
        
        column.appendChild(list);
        container.appendChild(column);
        list.scrollTop = scrollPositions[config.key] || 0;
    });

    header.textContent = 'Select Media Condition (All Types)';
    modal.style.display = 'block';
    window.currentThreeColumnMode = 'mediaCondition';
    setAllTypesControlsVisible(true);
    // This view owns the search bar until another picker is opened
    conditionPickerRedraw = () => openMediaConditionThreeColumnModal(true);
}

function openSleeveConditionThreeColumnModal(preserveSearch) {
    const modal = document.getElementById('conditionPickerModal');
    const container = document.getElementById('conditionPickerColumns');
    const header = document.getElementById('conditionPickerHeader');
    const searchInput = document.getElementById('conditionPickerSearch');

    if (!modal || !container) return;

    const scrollPositions = preserveSearch ? captureConditionPickerScroll(container) : {};
    container.innerHTML = '';
    if (!preserveSearch && searchInput) searchInput.value = '';

    const pickerQuery = conditionPickerQuery();
    setDualColumnToggle(false, false);

    // Get selected options from hidden legacy multiselects (one per media type)
    const legacySelects = {
        lp: document.getElementById('lpOptions'),
        cd: document.getElementById('cdOptions'),
        cassette: document.getElementById('customOptions'),
        boxSleeve: document.getElementById('boxSleeveOptions')
    };
    const selectedByMediaType = { lp: [], cd: [], cassette: [], boxSleeve: [] };
    Object.entries(legacySelects).forEach(([mediaType, select]) => {
        if (select) {
            Array.from(select.selectedOptions).forEach(o => {
                try {
                    const d = JSON.parse(o.value);
                    selectedByMediaType[mediaType].push(d.title + '|||' + d.text);
                } catch (e) {}
            });
        }
    });
    
    const mediaTypes = [
        { key: 'lp', label: 'LP SLEEVE CONDITION' },
        { key: 'cd', label: 'CD SLEEVE CONDITION' },
        { key: 'cassette', label: 'CASSETTE SLEEVE CONDITION' },
        { key: 'boxSleeve', label: 'BOXSET SLEEVE CONDITION' }
    ];
    
    mediaTypes.forEach(config => {
        const allItems = customOptionsData[config.key] || [];
        const items = allItems.filter(opt => conditionPickerMatch(opt, pickerQuery));
        const selectedKeys = selectedByMediaType[config.key] || [];

        const column = document.createElement('div');
        column.style.cssText = 'flex: 1; min-width: 0; display: flex; flex-direction: column;';

        const headerEl = document.createElement('div');
        headerEl.textContent = config.label + (selectedKeys.length ? ` (${selectedKeys.length})` : '');
        headerEl.style.cssText = 'font-size: 11px; font-weight: 700; margin-bottom: 4px; text-align: center; flex-shrink: 0;' +
            ' background: var(--wysiwyg-blue, #0000ff); color: #fff; border-radius: 4px; padding: 3px 0;';
        column.appendChild(headerEl);

        const list = document.createElement('div');
        list.dataset.conditionPickerList = config.key;
        list.style.cssText = 'flex: 1; min-height: 80px; overflow-y: auto; border: 1px solid var(--border-color, #ccc); border-radius: 4px;';

        if (items.length === 0) {
            list.innerHTML = `<div style="font-size: 11px; color: var(--text-muted, #666); text-align: center; padding: 8px;">${allItems.length === 0 ? 'No options' : 'No matches'}</div>`;
        }

        items.forEach(opt => {
            const isSelected = selectedKeys.includes(conditionOptionKey(opt));
            const row = document.createElement('div');
            row.style.cssText = 'display: flex; gap: 5px; align-items: flex-start; padding: 4px 6px; cursor: pointer; font-size: 11px; border-bottom: 1px solid var(--border-color, #eee);' +
                (isSelected ? ' background: var(--wysiwyg-blue-light, #e6f0ff); font-weight: bold; color: #000;' : '');
            row.innerHTML =
                `<span style="flex-shrink: 0;">${opt.favorite ? '⭐' : (isSelected ? '☑' : '☐')}</span>` +
                `<div style="min-width: 0;"><strong>${opt.title}</strong><br>` +
                `<span style="color: ${isSelected ? '#444' : 'var(--text-muted, #666)'}; font-weight: normal;">${opt.text || ''}</span></div>`;
            row.onclick = () => {
                toggleSleeveConditionOption(config.key, opt);
                openSleeveConditionThreeColumnModal(true);
            };
            // Add context menu for favoriting
            row.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const menu = document.getElementById('customContextMenu');
                if (menu) {
                    document.getElementById('favoriteContextItem').style.display = 'block';
                    document.getElementById('openMediaContextItem').style.display = 'none';
                    document.getElementById('openSleeveContextItem').style.display = 'none';
                    document.getElementById('openAllMediaContextItem').style.display = 'none';
                    document.getElementById('openAllSleeveContextItem').style.display = 'none';
                    document.getElementById('editConditionContextItem').style.display = 'none';
                    document.getElementById('clearConditionContextItem').style.display = 'none';
                    menu.dataset.targetId = 'sleeveConditionOptions';
                    menu.dataset.optionKey = conditionOptionKey(opt);
                    menu.dataset.optionMediaType = config.key;
                    menu.style.display = 'block';
                    menu.style.left = e.pageX + 'px';
                    menu.style.top = e.pageY + 'px';
                }
            });
            list.appendChild(row);
        });
        
        column.appendChild(list);
        container.appendChild(column);
        list.scrollTop = scrollPositions[config.key] || 0;
    });

    header.textContent = 'Select Sleeve Condition (All Types)';
    modal.style.display = 'block';
    window.currentThreeColumnMode = 'sleeveCondition';
    setAllTypesControlsVisible(true);
    // This view owns the search bar until another picker is opened
    conditionPickerRedraw = () => openSleeveConditionThreeColumnModal(true);
}

function captureConditionPickerScroll(container) {
    return Object.fromEntries(
        Array.from(container.querySelectorAll('[data-condition-picker-list]'))
            .map(list => [list.dataset.conditionPickerList, list.scrollTop])
    );
}

function toggleMediaConditionOption(opt) {
    const select = document.getElementById('mediaConditionOptions');
    if (!select) return;
    
    const key = conditionOptionKey(opt);
    const option = Array.from(select.options).find(o => {
        try {
            const d = JSON.parse(o.value);
            if (conditionOptionKey(d) !== key) return false;
            return !opt.media_type || d.media_type === opt.media_type;
        } catch (e) {
            return false;
        }
    });

    if (option) {
        option.selected = !option.selected;
    }
}

function toggleSleeveConditionOption(mediaType, opt) {
    const select = document.getElementById('sleeveConditionOptions');
    if (!select) return;
    
    const key = conditionOptionKey(opt);
    const option = Array.from(select.options).find(o => {
        try {
            const d = JSON.parse(o.value);
            if (conditionOptionKey(d) !== key) return false;
            return !o.dataset.mediaType || o.dataset.mediaType === mediaType;
        } catch (e) {
            return false;
        }
    });
    
    if (option) {
        option.selected = !option.selected;
        syncConditionMultiselectsToLegacy();
    }
}

// Handle Done button for three-column mode
const doneConditionPickerBtn = document.getElementById('doneConditionPickerBtn');
if (doneConditionPickerBtn) {
    const originalClick = doneConditionPickerBtn.onclick;
    doneConditionPickerBtn.onclick = (e) => {
        if (window.currentThreeColumnMode) {
            document.getElementById('conditionPickerModal').style.display = 'none';
            const mode = window.currentThreeColumnMode;
            window.currentThreeColumnMode = null;
            if (mode === 'sleeveCondition') {
                syncConditionMultiselectsToLegacy();
            }
            renderConditionMultiselects();
        } else if (originalClick) {
            originalClick(e);
        }
    };
}

// Handle Clear button for three-column mode
const clearConditionPickerBtn = document.getElementById('clearConditionPickerBtn');
if (clearConditionPickerBtn) {
    const originalClick = clearConditionPickerBtn.onclick;
    clearConditionPickerBtn.onclick = (e) => {
        const dualCb = document.getElementById('dualColumnMode');
        const dualState = dualCb ? dualCb.checked : false;
        if (window.currentThreeColumnMode) {
            const mode = window.currentThreeColumnMode;
            if (mode === 'mediaCondition') {
                const select = document.getElementById('mediaConditionOptions');
                if (select) {
                    Array.from(select.options).forEach(opt => opt.selected = false);
                }
            } else if (mode === 'sleeveCondition') {
                const select = document.getElementById('sleeveConditionOptions');
                if (select) {
                    Array.from(select.options).forEach(opt => opt.selected = false);
                    syncConditionMultiselectsToLegacy();
                }
            } else if (mode === 'dualColumn') {
                const mediaSelect = document.getElementById('mediaConditionOptions');
                const sleeveSelect = document.getElementById('sleeveConditionOptions');
                if (mediaSelect) Array.from(mediaSelect.options).forEach(opt => opt.selected = false);
                if (sleeveSelect) {
                    Array.from(sleeveSelect.options).forEach(opt => opt.selected = false);
                    syncConditionMultiselectsToLegacy();
                }
            }
            if (mode === 'mediaCondition') {
                openMediaConditionThreeColumnModal(true);
            } else if (mode === 'sleeveCondition') {
                openSleeveConditionThreeColumnModal(true);
            } else if (mode === 'dualColumn') {
                openDualColumnConditionPicker(currentConditionMediaType, true);
            }
        } else if (originalClick) {
            originalClick(e);
        }
        if (dualCb) dualCb.checked = dualState;
    };
}

// Open single-column condition picker for Media Condition (current media type) - same as OPEN button
function openConditionPickerForMedia(mediaType, preserveSearch) {
    const modal = document.getElementById('conditionPickerModal');
    const container = document.getElementById('conditionPickerColumns');
    const header = document.getElementById('conditionPickerHeader');
    const searchInput = document.getElementById('conditionPickerSearch');

    if (!modal || !container) return;

    const scrollPositions = preserveSearch ? captureConditionPickerScroll(container) : {};
    container.innerHTML = '';
    if (!preserveSearch && searchInput) searchInput.value = '';
    setDualColumnToggle(true, false);
    conditionPickerSingleSource = 'media';

    // Get media condition data for the specific media type
    const query = conditionPickerQuery();
    const allItems = (customOptionsData.mediaCondition || []).filter(opt => opt.media_type === mediaType);
    const items = allItems.filter(opt => conditionPickerMatch(opt, query));
    const select = document.getElementById('mediaConditionOptions');
    const selectedKeys = select ? Array.from(select.selectedOptions).map(o => {
        try {
            const d = JSON.parse(o.value);
            return d.title + '|||' + d.text;
        } catch (e) { return ''; }
    }) : [];

    const column = document.createElement('div');
    column.style.cssText = 'flex: 1; min-width: 0; display: flex; flex-direction: column;';

    const headerEl = document.createElement('div');
    headerEl.textContent = mediaType.toUpperCase() + ' MEDIA CONDITION' + (selectedKeys.length ? ` (${selectedKeys.length})` : '');
    headerEl.style.cssText = 'font-size: 11px; font-weight: 700; margin-bottom: 4px; color: var(--text-color, #444); text-align: center; flex-shrink: 0;';
    column.appendChild(headerEl);

    const list = document.createElement('div');
    list.dataset.conditionPickerList = 'current';
    list.style.cssText = 'flex: 1; min-height: 80px; overflow-y: auto; border: 1px solid var(--border-color, #ccc); border-radius: 4px;';

    if (items.length === 0) {
        list.innerHTML = `<div style="font-size: 11px; color: var(--text-muted, #666); text-align: center; padding: 8px;">${allItems.length === 0 ? 'No options' : 'No matches'}</div>`;
    }

    items.forEach(opt => {
        const isSelected = selectedKeys.includes(conditionOptionKey(opt));
        const row = document.createElement('div');
        row.style.cssText = 'display: flex; gap: 5px; align-items: flex-start; padding: 4px 6px; cursor: pointer; font-size: 11px; border-bottom: 1px solid var(--border-color, #eee);' +
            (isSelected ? ' background: var(--wysiwyg-blue-light, #e6f0ff); font-weight: bold; color: #000;' : '');
        row.innerHTML =
            `<span style="flex-shrink: 0;">${opt.favorite ? '⭐' : (isSelected ? '☑' : '☐')}</span>` +
            `<div style="min-width: 0;"><strong>${opt.title}</strong><br>` +
            `<span style="color: ${isSelected ? '#444' : 'var(--text-muted, #666)'}; font-weight: normal;">${opt.text || ''}</span></div>`;
        row.onclick = () => {
            toggleMediaConditionOption(opt);
            // Check if dual column mode was active
            if (window.currentThreeColumnMode === 'dualColumn') {
                openDualColumnConditionPicker(mediaType, true);
            } else {
                openConditionPickerForMedia(mediaType, true);
            }
        };
        row.addEventListener('contextmenu', (e) => {
            openFavoriteContextMenuAt(e, 'mediaConditionOptions', conditionOptionKey(opt), opt.media_type || mediaType);
        });
        list.appendChild(row);
    });

    column.appendChild(list);
    container.appendChild(column);
    list.scrollTop = scrollPositions.current || 0;

    header.textContent = mediaType.toUpperCase() + ' MEDIA CONDITION';
    modal.style.display = 'block';
    window.currentThreeColumnMode = null;
    setAllTypesControlsVisible(false);
    // This view owns the search bar until another picker is opened
    conditionPickerRedraw = () => openConditionPickerForMedia(mediaType, true);
}

// Open single-column condition picker for Sleeve Condition (current media type) - same as OPEN button
function openConditionPickerForSleeve(mediaType, preserveSearch) {
    const modal = document.getElementById('conditionPickerModal');
    const container = document.getElementById('conditionPickerColumns');
    const header = document.getElementById('conditionPickerHeader');
    const searchInput = document.getElementById('conditionPickerSearch');

    if (!modal || !container) return;

    const scrollPositions = preserveSearch ? captureConditionPickerScroll(container) : {};
    container.innerHTML = '';
    if (!preserveSearch && searchInput) searchInput.value = '';
    setDualColumnToggle(true, false);
    conditionPickerSingleSource = 'sleeve';

    // Get sleeve condition data for the specific media type
    const query = conditionPickerQuery();
    const allItems = customOptionsData[mediaType] || [];
    const items = allItems.filter(opt => conditionPickerMatch(opt, query));
    const select = document.getElementById('sleeveConditionOptions');
    const selectedKeys = select ? Array.from(select.selectedOptions).map(o => {
        try {
            const d = JSON.parse(o.value);
            return d.title + '|||' + d.text;
        } catch (e) { return ''; }
    }) : [];

    const column = document.createElement('div');
    column.style.cssText = 'flex: 1; min-width: 0; display: flex; flex-direction: column;';

    const headerEl = document.createElement('div');
    headerEl.textContent = sleeveConditionLabel(mediaType) + ' SLEEVE CONDITION' + (selectedKeys.length ? ` (${selectedKeys.length})` : '');
    headerEl.style.cssText = 'font-size: 11px; font-weight: 700; margin-bottom: 4px; color: var(--text-color, #444); text-align: center; flex-shrink: 0;';
    column.appendChild(headerEl);

    const list = document.createElement('div');
    list.dataset.conditionPickerList = 'current';
    list.style.cssText = 'flex: 1; min-height: 80px; overflow-y: auto; border: 1px solid var(--border-color, #ccc); border-radius: 4px;';

    if (items.length === 0) {
        list.innerHTML = `<div style="font-size: 11px; color: var(--text-muted, #666); text-align: center; padding: 8px;">${allItems.length === 0 ? 'No options' : 'No matches'}</div>`;
    }

    items.forEach(opt => {
        const isSelected = selectedKeys.includes(conditionOptionKey(opt));
        const row = document.createElement('div');
        row.style.cssText = 'display: flex; gap: 5px; align-items: flex-start; padding: 4px 6px; cursor: pointer; font-size: 11px; border-bottom: 1px solid var(--border-color, #eee);' +
            (isSelected ? ' background: var(--wysiwyg-blue-light, #e6f0ff); font-weight: bold; color: #000;' : '');
        row.innerHTML =
            `<span style="flex-shrink: 0;">${opt.favorite ? '⭐' : (isSelected ? '☑' : '☐')}</span>` +
            `<div style="min-width: 0;"><strong>${opt.title}</strong><br>` +
            `<span style="color: ${isSelected ? '#444' : 'var(--text-muted, #666)'}; font-weight: normal;">${opt.text || ''}</span></div>`;
        row.onclick = () => {
            toggleSleeveConditionOption(mediaType, opt);
            // Check if dual column mode was active
            if (window.currentThreeColumnMode === 'dualColumn') {
                openDualColumnConditionPicker(mediaType, true);
            } else {
                openConditionPickerForSleeve(mediaType, true);
            }
        };
        row.addEventListener('contextmenu', (e) => {
            openFavoriteContextMenuAt(e, 'sleeveConditionOptions', conditionOptionKey(opt), mediaType);
        });
        list.appendChild(row);
    });

    column.appendChild(list);
    container.appendChild(column);
    list.scrollTop = scrollPositions.current || 0;

    header.textContent = sleeveConditionLabel(mediaType) + ' SLEEVE CONDITION';
    modal.style.display = 'block';
    window.currentThreeColumnMode = null;
    setAllTypesControlsVisible(false);
    // This view owns the search bar until another picker is opened
    conditionPickerRedraw = () => openConditionPickerForSleeve(mediaType, true);
}

// Open dual-column condition picker for both Media and Sleeve conditions (current media type)
function openConditionsBothCurrentType() {
    const mediaTypeSelect = document.getElementById('conditionMediaType');
    const mediaType = mediaTypeSelect ? mediaTypeSelect.value : currentConditionMediaType;
    currentConditionMediaType = mediaType;
    conditionPickerViewMode = 'dual';
    const search = document.getElementById('conditionPickerSearch');
    if (search) search.value = '';
    currentModalCategory = 'mediaCondition';
    const modalCatSelect = document.getElementById('modalCategorySelect');
    if (modalCatSelect) modalCatSelect.value = 'mediaCondition';
    openDualColumnConditionPicker(mediaType);
}

function setAllTypesControlsVisible(visible) {
    const el = document.getElementById('allTypesControls');
    if (el) el.style.display = visible ? 'flex' : 'none';
    if (visible) {
        const viewSel = document.getElementById('allTypesView');
        if (viewSel) viewSel.value = (window.currentThreeColumnMode === 'sleeveCondition') ? 'sleeve' : 'media';
    }
}

function setConditionMediaTypeEverywhere(type) {
    currentConditionMediaType = type;
    const mainSelect = document.getElementById('conditionMediaType');
    if (mainSelect) mainSelect.value = type;
    renderConditionMultiselects();
}

function unfavoriteAllCurrentType() {
    const isSleeve = window.currentThreeColumnMode === 'sleeveCondition';
    // All three columns are active in the All Types views, so this clears every type.
    const list = isSleeve
        ? ['lp', 'cd', 'cassette', 'boxSleeve'].flatMap(k => customOptionsData[k] || [])
        : (customOptionsData.mediaCondition || []);
    let changed = false;
    list.forEach(item => {
        if (item.favorite) {
            item.favorite = false;
            changed = true;
        }
    });
    if (changed) {
        saveCustomOptions();
        renderCustomOptionsSelect();
    }
    if (conditionPickerRedraw) conditionPickerRedraw();
    else renderConditionPicker();
}

function openDualColumnConditionPicker(mediaType, preserveSearch) {
    const modal = document.getElementById('conditionPickerModal');
    const container = document.getElementById('conditionPickerColumns');
    const header = document.getElementById('conditionPickerHeader');
    const searchInput = document.getElementById('conditionPickerSearch');

    if (!modal || !container) return;

    const scrollPositions = preserveSearch ? captureConditionPickerScroll(container) : {};
    container.innerHTML = '';
    if (!preserveSearch && searchInput) searchInput.value = '';

    setDualColumnToggle(true, true);
    const query = conditionPickerQuery();

    // The media column follows the Media Type dropdown; the sleeve column follows
    // that same type unless Box Set is selected, which has its own sleeve list.
    const mediaTypeSelect = document.getElementById('conditionMediaType');
    if (mediaTypeSelect && mediaTypeSelect.value) mediaType = mediaTypeSelect.value;
    const sleeveType = effectiveSleeveType();

    // Media Condition column
    const mediaItems = (customOptionsData.mediaCondition || []).filter(opt => opt.media_type === mediaType);
    const mediaFiltered = mediaItems.filter(opt => conditionPickerMatch(opt, query));
    const mediaSelect = document.getElementById('mediaConditionOptions');
    const mediaSelectedKeys = mediaSelect ? Array.from(mediaSelect.selectedOptions).map(o => {
        try {
            const d = JSON.parse(o.value);
            return d.title + '|||' + d.text;
        } catch (e) { return ''; }
    }) : [];

    // Sleeve Condition column
    const sleeveItems = customOptionsData[sleeveType] || [];
    const sleeveFiltered = sleeveItems.filter(opt => conditionPickerMatch(opt, query));
    const sleeveSelect = document.getElementById('sleeveConditionOptions');
    const sleeveSelectedKeys = sleeveSelect ? Array.from(sleeveSelect.selectedOptions).map(o => {
        try {
            const d = JSON.parse(o.value);
            return d.title + '|||' + d.text;
        } catch (e) { return ''; }
    }) : [];
    
    // Media Condition Column
    const mediaColumn = document.createElement('div');
    mediaColumn.style.cssText = 'flex: 1; min-width: 0; display: flex; flex-direction: column;';
    
    const mediaHeaderEl = document.createElement('div');
    mediaHeaderEl.textContent = mediaType.toUpperCase() + ' MEDIA CONDITION' + (mediaSelectedKeys.length ? ` (${mediaSelectedKeys.length})` : '');
    mediaHeaderEl.style.cssText = 'font-size: 11px; font-weight: 700; margin-bottom: 4px; color: var(--text-color, #444); text-align: center; flex-shrink: 0;';
    mediaColumn.appendChild(mediaHeaderEl);
    
    const mediaList = document.createElement('div');
    mediaList.dataset.conditionPickerList = 'media';
    mediaList.style.cssText = 'flex: 1; min-height: 80px; overflow-y: auto; border: 1px solid var(--border-color, #ccc); border-radius: 4px;';
    
    if (mediaFiltered.length === 0) {
        mediaList.innerHTML = `<div style="font-size: 11px; color: var(--text-muted, #666); text-align: center; padding: 8px;">${mediaItems.length === 0 ? 'No options' : 'No matches'}</div>`;
    }

    mediaFiltered.forEach(opt => {
        const isSelected = mediaSelectedKeys.includes(conditionOptionKey(opt));
        const row = document.createElement('div');
        row.style.cssText = 'display: flex; gap: 5px; align-items: flex-start; padding: 4px 6px; cursor: pointer; font-size: 11px; border-bottom: 1px solid var(--border-color, #eee);' +
            (isSelected ? ' background: var(--wysiwyg-blue-light, #e6f0ff); font-weight: bold; color: #000;' : '');
        row.innerHTML =
            `<span style="flex-shrink: 0;">${opt.favorite ? '⭐' : (isSelected ? '☑' : '☐')}</span>` +
            `<div style="min-width: 0;"><strong>${opt.title}</strong><br>` +
            `<span style="color: ${isSelected ? '#444' : 'var(--text-muted, #666)'}; font-weight: normal;">${opt.text || ''}</span></div>`;
        row.onclick = () => {
            toggleMediaConditionOption(opt);
            openDualColumnConditionPicker(mediaType, true);
        };
        // Add context menu for favoriting
        row.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const menu = document.getElementById('customContextMenu');
            if (menu) {
                document.getElementById('favoriteContextItem').style.display = 'block';
                document.getElementById('openMediaContextItem').style.display = 'none';
                document.getElementById('openSleeveContextItem').style.display = 'none';
                document.getElementById('openAllMediaContextItem').style.display = 'none';
                document.getElementById('openAllSleeveContextItem').style.display = 'none';
                document.getElementById('editConditionContextItem').style.display = 'none';
                document.getElementById('clearConditionContextItem').style.display = 'none';
                menu.dataset.targetId = 'mediaConditionOptions';
                menu.dataset.optionKey = conditionOptionKey(opt);
                menu.dataset.optionMediaType = opt.media_type || mediaType;
                menu.style.display = 'block';
                menu.style.left = e.pageX + 'px';
                menu.style.top = e.pageY + 'px';
            }
        });
        mediaList.appendChild(row);
    });
    
    mediaColumn.appendChild(mediaList);
    container.appendChild(mediaColumn);
    mediaList.scrollTop = scrollPositions.media || 0;
    
    // Sleeve Condition Column
    const sleeveColumn = document.createElement('div');
    sleeveColumn.style.cssText = 'flex: 1; min-width: 0; display: flex; flex-direction: column;';
    
    const sleeveHeaderEl = document.createElement('div');
    sleeveHeaderEl.textContent = sleeveConditionLabel(sleeveType) + ' SLEEVE CONDITION' + (sleeveSelectedKeys.length ? ` (${sleeveSelectedKeys.length})` : '');
    sleeveHeaderEl.style.cssText = 'font-size: 11px; font-weight: 700; margin-bottom: 4px; color: var(--text-color, #444); text-align: center; flex-shrink: 0;';
    sleeveColumn.appendChild(sleeveHeaderEl);
    
    const sleeveList = document.createElement('div');
    sleeveList.dataset.conditionPickerList = 'sleeve';
    sleeveList.style.cssText = 'flex: 1; min-height: 80px; overflow-y: auto; border: 1px solid var(--border-color, #ccc); border-radius: 4px;';
    
    if (sleeveFiltered.length === 0) {
        sleeveList.innerHTML = `<div style="font-size: 11px; color: var(--text-muted, #666); text-align: center; padding: 8px;">${sleeveItems.length === 0 ? 'No options' : 'No matches'}</div>`;
    }

    sleeveFiltered.forEach(opt => {
        const isSelected = sleeveSelectedKeys.includes(conditionOptionKey(opt));
        const row = document.createElement('div');
        row.style.cssText = 'display: flex; gap: 5px; align-items: flex-start; padding: 4px 6px; cursor: pointer; font-size: 11px; border-bottom: 1px solid var(--border-color, #eee);' +
            (isSelected ? ' background: var(--wysiwyg-blue-light, #e6f0ff); font-weight: bold; color: #000;' : '');
        row.innerHTML =
            `<span style="flex-shrink: 0;">${opt.favorite ? '⭐' : (isSelected ? '☑' : '☐')}</span>` +
            `<div style="min-width: 0;"><strong>${opt.title}</strong><br>` +
            `<span style="color: ${isSelected ? '#444' : 'var(--text-muted, #666)'}; font-weight: normal;">${opt.text || ''}</span></div>`;
        row.onclick = () => {
            toggleSleeveConditionOption(sleeveType, opt);
            openDualColumnConditionPicker(mediaType, true);
        };
        row.addEventListener('contextmenu', (e) => {
            openFavoriteContextMenuAt(e, 'sleeveConditionOptions', conditionOptionKey(opt), sleeveType);
        });
        sleeveList.appendChild(row);
    });

    sleeveColumn.appendChild(sleeveList);
    container.appendChild(sleeveColumn);
    sleeveList.scrollTop = scrollPositions.sleeve || 0;

    header.textContent = mediaType.toUpperCase() + ' CONDITIONS';
    modal.style.display = 'block';
    window.currentThreeColumnMode = 'dualColumn';
    setAllTypesControlsVisible(false);
    // This view owns the search bar until another picker is opened
    conditionPickerRedraw = () => openDualColumnConditionPicker(mediaType, true);
}
