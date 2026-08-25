let data = {};
let mediaFormats = {};
let walmartWindow = null; // Track the Walmart window globally
let walmartFilteredDesc = ""; // Track the filtered description for Walmart

// --- INITIALIZATION & EVENT LISTENERS ---
document.addEventListener('DOMContentLoaded', () => {
    // Force hard reload once on start to ensure latest version (same as Refresh button)
    if (!sessionStorage.getItem('force_refreshed')) {
        sessionStorage.setItem('force_refreshed', 'true');
        location.reload(true);
        return;
    }
    clearWalmartCache();
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

    // Initialize Dock Walmart Preference
    const walmartDockPref = localStorage.getItem('wysiwyg_dock_walmart');
    if (walmartDockPref === 'true' && document.getElementById('dockWalmartSheet')) {
        document.getElementById('dockWalmartSheet').checked = true;
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
    addClickListener('runWalmartSheetBtn', runWalmartSheet);
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
    document.getElementById('discogsUrlInput')?.addEventListener('click', async function () {
        if (document.getElementById('autoPasteToggle').checked) {
            try {
                const text = await navigator.clipboard.readText();
                if (text) this.value = text;
            } catch (err) {
                console.error('Autopaste failed:', err);
            }
        }
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
    addClickListener('copyScratchpadBtn', (e) => copyScratchpad(e.currentTarget));
    addClickListener('selectAllScratchpadBtn', () => document.getElementById('manualInputBox').select());
    addClickListener('pasteToScratchpadBtn', pasteToManualInput);

    // --- Footer ---
    addClickListener('openRequestModalBtn', openRequestModal);

    // --- Service Status Polling ---
    // Check status every 5 seconds to reduce system load
    setInterval(updateServiceStatus, 5000);
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

async function runWalmartSheet() {
    try {
        await clearWalmartCache(); // Clear cache before populating it
        const dock = document.getElementById('dockWalmartSheet')?.checked ?? true;

        // Try to get text from Scratchpad first, then fall back to the hidden scraper result
        const scratchpadEl = document.getElementById('manualInputBox');
        const hiddenScrapeEl = document.getElementById('scraperResultText');
        const rawText = (scratchpadEl && scratchpadEl.value) ? scratchpadEl.value : (hiddenScrapeEl ? hiddenScrapeEl.textContent : '');

        // Prepare the full context and send it to the server cache
        const context = {
            sku: document.getElementById('outputSku')?.value || '',
            builderDescription: document.getElementById('mediaDescriptionText')?.value || '',
            generatedDescription: walmartFilteredDesc || document.getElementById('outputDesc')?.value || '',
            label: document.getElementById('recordLabel')?.value || '',
            raw_text: rawText,
            discogsUrl: document.getElementById('discogsUrlInput')?.value || ''
        };
        await fetch('/api/walmart/cache-context', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(context)
        });

        const url = '/walmart-sheet';

        if (dock) {
            walmartWindow = window.open(url, '_blank');
        } else {
            const windowFeatures = "width=1000,height=800,resizable=yes,scrollbars=yes,status=yes";
            walmartWindow = window.open(url, 'WalmartSheetWindow', windowFeatures);
        }

        if (walmartWindow) {
            walmartWindow.focus();
            // Trigger an immediate UI update
            updateServiceStatus();
        } else {
            customAlert('Popup window was blocked by the browser. Please allow popups for this site.');
        }
    } catch (e) {
        customAlert('Failed to open Walmart Sheet: ' + e);
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
        // Reuse the existing window if it's still open.
        if (_addsDiscogsWindow && !_addsDiscogsWindow.closed) {
            _addsDiscogsWindow.focus();
            return;
        }
        const url = '/adds/discogs';
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
    try {
        // 1. Check Walmart Window (Client-side check)
        const walBtn = document.getElementById('runWalmartSheetBtn');
        if (walBtn) {
            if (walmartWindow && !walmartWindow.closed) {
                walBtn.disabled = true;
                walBtn.style.opacity = "0.5";
                walBtn.title = "Walmart Sheet is already open";
            } else {
                walBtn.disabled = false;
                walBtn.style.opacity = "1";
                walBtn.title = "Open Walmart Spreadsheet Exporter";
            }
        }

        // 2. Check Backend Services (Server-side check)
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
    try {
        // Ask the main server to launch the WysiScan server
        const resp = await fetch('/run-wysiscan', { method: 'POST' });
        const res = await resp.json();

        if (res.status === 'success') {
            // If launch is successful (or it was already running), open the UI in a popup window.
            // dockScanner checkbox was removed from the header; default to docked (new tab).
            const dock = document.getElementById('dockScanner')?.checked ?? true;
            let wysiScanWindow;

            if (dock) {
                wysiScanWindow = window.open('http://127.0.0.1:8010/', '_blank');
            } else {
                const windowFeatures = "width=1200,height=900,resizable=yes,scrollbars=yes,status=yes";
                wysiScanWindow = window.open('http://127.0.0.1:8010/', 'WysiScanWindow', windowFeatures);
            }

            if (wysiScanWindow) {
                wysiScanWindow.focus();
            } else {
                customAlert('Popup window was blocked by the browser. Please allow popups for this site.');
            }
        } else {
            customAlert('Could not start WysiScan: ' + res.message);
        }
    } catch (e) {
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

    saveBtn.style.marginLeft = '8px';
    saveBtn.style.padding = '0 5px';
    saveBtn.style.fontSize = '1em';
    saveBtn.style.lineHeight = '1';
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

        if (v.update_available) {
            titleHtml += ` <span onclick="event.stopPropagation(); runInstaller()" style="cursor:pointer; background: #ffc107; color: #000; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; margin-left: 10px; border: 1px solid #000; vertical-align: middle;" title="Click to run installer">* UPDATE AVAILABLE *</span>`;
            document.getElementById('updateBanner').style.display = 'block';
        } else {
            document.getElementById('updateBanner').style.display = 'none';
        }
        if (titleEl) titleEl.innerHTML = titleHtml;
    } catch (e) { console.error("Version load failed", e); }
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

async function updateMenus() {
    customConfirm("Pull latest menus and merge conditions from server?", async () => {
        try {
            // 1. Update general menus (data.json, version.json, etc.)
            const resp = await fetch('/update-menus', { method: 'POST' });
            const res = await resp.json();

            // 2. Merge conditions (Conditions.json)
            const respCond = await fetch('/api/merge-conditions', { method: 'POST' });
            const resCond = await respCond.json();

            let msg = res.message;
            if (resCond.status === 'success') {
                msg += "\n\n" + resCond.message;
            } else {
                msg += "\n\nCondition Merge Failed: " + resCond.message;
            }

            customAlert(msg);
            if (res.status === 'success' || resCond.status === 'success') {
                location.reload();
            }
        } catch (e) { customAlert("Error: " + e); }
    });
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
const MAX_COUNTERS = 7; // 4 defaults + up to 3 more
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

function deleteCounter(idx) {
    if (counterConfig.length <= 1) return;
    counterConfig.splice(idx, 1);
    saveCounterConfig();
    renderCounterButtons();
    openCounterEditor();
}

function moveCounter(idx, dir) {
    const target = idx + dir;
    if (target < 0 || target >= counterConfig.length) return;
    const tmp = counterConfig[idx];
    counterConfig[idx] = counterConfig[target];
    counterConfig[target] = tmp;
    saveCounterConfig();
    renderCounterButtons();
    openCounterEditor();
}

function openCounterEditor() {
    loadCounterConfig();
    let body = '<div style="display:flex; flex-direction:column; gap:8px;">';
    counterConfig.forEach((c, i) => {
        const upDisabled = i === 0 ? 'disabled' : '';
        const downDisabled = i === counterConfig.length - 1 ? 'disabled' : '';
        body += `<div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
            <button type="button" class="ctr-move" data-idx="${i}" data-dir="-1" ${upDisabled} style="border:none; background:#6c757d; color:#fff; border-radius:4px; cursor:pointer; padding:4px 7px; font-size:11px;" onclick="moveCounter(${i}, -1)" ${upDisabled}>▲</button>
            <button type="button" class="ctr-move" data-idx="${i}" data-dir="1" ${downDisabled} style="border:none; background:#6c757d; color:#fff; border-radius:4px; cursor:pointer; padding:4px 7px; font-size:11px;" onclick="moveCounter(${i}, 1)" ${downDisabled}>▼</button>
            <input type="color" value="${c.color}" data-idx="${i}" class="ctr-color" style="width:32px; height:28px; border:none; background:none; cursor:pointer;">
            <input type="text" value="${c.label}" data-idx="${i}" class="ctr-label" placeholder="Label" style="width:50px; padding:4px; font-size:12px;">
            ${counterConfig.length > 1 ? `<button type="button" class="ctr-del" data-idx="${i}" style="border:none; background:#dc3545; color:#fff; background:#dc3545; border-radius:4px; cursor:pointer; padding:4px 8px; font-size:11px;" onclick="deleteCounter(${i})">Delete</button>` : ''}
        </div>`;
    });
    body += '</div>';
    const canAdd = counterConfig.length < MAX_COUNTERS;
    showModal('Edit Counters', body, [
        ...(canAdd ? [{ text: '+ Add Counter', primary: false, onClick: () => {
            counterConfig.push({ id: 'cnt_' + Date.now(), label: 'NEW', serverKey: 'New ' + (counterConfig.length + 1), color: '#6c757d', text: '' });
            saveCounterConfig(); renderCounterButtons(); openCounterEditor();
        } }] : []),
        { text: 'Cancel', primary: false, onClick: closeModal },
        { text: 'Save', primary: true, onClick: () => {
            document.querySelectorAll('.ctr-label').forEach(inp => {
                const i = parseInt(inp.dataset.idx, 10);
                if (counterConfig[i]) counterConfig[i].label = inp.value;
            });
            document.querySelectorAll('.ctr-color').forEach(inp => {
                const i = parseInt(inp.dataset.idx, 10);
                if (counterConfig[i]) counterConfig[i].color = inp.value;
            });
            saveCounterConfig();
            renderCounterButtons();
            loadCounters();
            closeModal();
        } }
    ]);
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
    { id: 'walmart', label: 'Walmart Sheet', run: () => runWalmartSheet() },
    { id: 'amazonAdds', label: 'Amazon Adds', run: () => openAddsAmazon() },
    { id: 'discogsAdds', label: 'Discogs Adds', run: () => openAddsDiscogs() },
    { id: 'calc', label: 'Cost Calculator', run: () => openCalcModal() },
    { id: 'refresh', label: 'Refresh', run: () => location.reload(true) },
    { id: 'reports', label: 'Reports', run: () => openReportsModal() },
    { id: 'shutdown', label: 'Shut Down', run: () => shutdownApp() }
];
const HOTKEY_DEFAULTS = {
    menu: 'Ctrl+Shift+M',
    wysiscan: 'Ctrl+Shift+W',
    walmart: 'Ctrl+Shift+B',
    amazonAdds: 'Ctrl+Shift+A',
    discogsAdds: 'Ctrl+Shift+D',
    calc: 'Ctrl+Shift+C',
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
            if (e.key === 'Escape') { cancelCapture(); return; }
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
        };
        actionsEl.appendChild(b);
    });

    overlay.style.display = 'flex';
}

window.customAlert = function (msg) {
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
function submitPassword() {
    const input = document.getElementById('adminPasswordInput').value;
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

async function fullReset() {
    const inputs = document.querySelectorAll('input[type="text"]:not(#boxNumber):not(#lister), input[type="url"], textarea:not(#outputDesc)');
    inputs.forEach(input => input.value = "");
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

    await clearWalmartCache();

    loadProfile(); // Revert to profile settings first (box, lister, skuFlag)
    loadVariableConditions(); // Restore saved variables after reset
    updateDynamicColors(); // Update dynamic colors using the restored values
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

async function clearWalmartCache() {
    walmartFilteredDesc = "";
    localStorage.removeItem('wysiwyg_walmart_context');
    try {
        await fetch('/api/walmart/cache-context', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}) // Send empty object to clear the server-side cache
        });
    } catch (e) {
        console.error("Failed to clear Walmart context cache:", e);
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

    // AUTO-SYNC: Immediately push fresh scrape data to the Walmart context cache
    const context = {
        sku: document.getElementById('outputSku')?.value || '',
        builderDescription: document.getElementById('mediaDescriptionText')?.value || '',
        generatedDescription: document.getElementById('outputDesc')?.value || '',
        label: document.getElementById('recordLabel')?.value || '',
        raw_text: input,
        discogsUrl: document.getElementById('discogsUrlInput')?.value || ''
    };
    fetch('/api/walmart/cache-context', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(context)
    }).catch(err => console.error("Auto-sync to Walmart failed:", err));
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
            ...Array.from(document.getElementById('customOptions')?.selectedOptions || []).map(o => o.value)
        ]
    };

    // 2. Process Logic
    const processedCountry = processCountry(inputs.country);
    const fmtData = processFormatData(inputs);

    // 3. Assemble Description
    const desc = assembleDescription(inputs, processedCountry, fmtData);

    // 3b. Assemble Walmart Description (Filtered)
    walmartFilteredDesc = assembleWalmartDescription(inputs, processedCountry, fmtData);

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
    let { formatLineRaw, mediaDesc, colorVal, preFM, weightSpeed, mediaFormat, postFM, sleevePkg, pkgFeature, edition, formatTags, customOptionsSelected, sleeveDesc, sleeveCond } = inputs;

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
    if (sleeveCond.trim() !== "" && !sleevePkg) {
        if (mediaFormat === "Vinyl") sleeveTypeLabel = "Sleeve";
        else if (mediaFormat.includes("CD") || mediaFormat.includes("DVD") || mediaFormat.includes("Blu-ray")) {
            if (sleeveDesc && sleeveDesc.toLowerCase().includes("insert")) {
                sleeveTypeLabel = "Artwork";
            } else {
                sleeveTypeLabel = "Artwork / Insert";
            }
        }
        else if (mediaFormat === "Cassette") sleeveTypeLabel = "JCard";
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

    // Edition Logic
    // (Handled in getVal)

    // Custom Options Logic
    // Build the flaw string: first item uses " & ", subsequent items use " / "
    let conditionPhrase = ""; // will be placed contextually in the assembled string
    if (customOptionsSelected && customOptionsSelected.length > 0) {
        let flaws = [];
        customOptionsSelected.forEach(optJson => {
            try {
                const opt = JSON.parse(optJson);
                if (opt.title === "Final Sale") {
                    finalFormatString += " " + opt.text;
                } else {
                    if (opt.text) flaws.push(opt.text);
                    else flaws.push(opt.title);
                }
            } catch (e) { }
        });

        if (flaws.length > 0) {
            // Group flaws to combine duplicates (e.g. "water damage to Booklet/Inlay")
            flaws = groupFlaws(flaws);

            // Join: first separator = " & ", all subsequent = " / "
            const combinedFlaws = flaws.length === 1
                ? flaws[0]
                : flaws[0] + " & " + flaws.slice(1).join(" / ");

            const hasSleeveCondition = sleeveCond && sleeveCond.trim() !== "";
            const hasSleeveDesc = sleeveDesc && sleeveDesc.trim() !== "";

            if (hasSleeveCondition && hasSleeveDesc) {
                // Case A: sleeveDesc text is treated as the FIRST condition.
                // Menu item 1 -> " & ", menu items 2+ -> " / "
                if (flaws.length === 1) {
                    sleeveDesc += ' & ' + flaws[0];
                } else {
                    sleeveDesc += ' & ' + flaws[0] + ' / ' + flaws.slice(1).join(' / ');
                }
            } else if (hasSleeveCondition && !hasSleeveDesc) {
                // Case B: sleeve cond set + sleeve desc BLANK -> goes AFTER sleevePkg
                // Store in conditionPhrase; assembleDescription will place it after sleevePkg.
                conditionPhrase = combinedFlaws;
            } else if (sleevePkg && !hasSleeveCondition && !sleeveDesc) {
                // If there is a sleeve pack but no sleeve condition, attach
                // the condition options directly to the sleeve pack.
                sleevePkg += " with " + combinedFlaws;
            } else if (sleeveDesc) {
                sleeveDesc += " & " + combinedFlaws;
            } else if (postFM) {
                finalFormatString += " with " + combinedFlaws;
            } else if (mediaDesc) {
                mediaDesc += " & " + combinedFlaws;
            } else {
                finalFormatString += " with " + combinedFlaws;
            }
        }
    }

    if (sleevePkg && sleevePkg.toLowerCase().includes('gatefold') && sleeveDesc) {
        sleevePkg = sleevePkg.replace(/gatefold/ig, 'Gatefold Sleeve');
    }

    return {
        finalFormatString,
        sleeveTypeLabel,
        sleevePkg,
        mediaDesc,
        sleeveDesc,
        pkgFeature,
        edition,
        conditionPhrase   // NEW: condition text to inject after sleevePkg when sleeveDesc is blank
    };
}

function assembleDescription(inputs, country, fmtData) {
    let parts;

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
            fmtData.mediaDesc,
            inputs.sleeveCond,
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
            fmtData.mediaDesc,
            inputs.sleeveCond,
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


function groupFlaws(flaws) {
    if (!flaws || flaws.length <= 1) return flaws;

    const separators = [' to ', ' through ', ' on '];

    // Helper to split a flaw into [prefix, separator, suffix]
    function splitFlaw(f) {
        for (const sep of separators) {
            if (f.includes(sep)) {
                const parts = f.split(sep);
                return [parts[0], sep, parts.slice(1).join(sep)];
            }
        }
        if (f.toLowerCase().startsWith('corner ')) {
            return ['Corner', ' ', f.substring(7)];
        }
        return [f, null, null];
    }

    let result = [...flaws];

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
            if (p1 === p2 && s1 === s2) {
                matches.push(j);
            }
        }

        if (matches.length > 1) {
            const suffixes = matches.map(idx => splitFlaw(result[idx])[2]);
            const uniqueSuffixes = [...new Set(suffixes)];
            prefixGrouped.push(p1 + s1 + uniqueSuffixes.join('/'));
            matches.forEach(idx => handled.add(idx));
        } else {
            prefixGrouped.push(result[i]);
            handled.add(i);
        }
    }

    // 2. Suffix Grouping
    // Group by suffix
    result = prefixGrouped;
    let suffixGrouped = [];
    handled = new Set();
    for (let i = 0; i < result.length; i++) {
        if (handled.has(i)) continue;
        const [p1, s1, x1] = splitFlaw(result[i]);
        if (!x1) {
            suffixGrouped.push(result[i]);
            continue;
        }

        let matches = [i];
        for (let j = i + 1; j < result.length; j++) {
            if (handled.has(j)) continue;
            const [p2, s2, x2] = splitFlaw(result[j]);
            if (x1 === x2) {
                matches.push(j);
            }
        }

        if (matches.length > 1) {
            // Group by separator within this suffix group
            let sepMap = new Map(); // separator -> [prefixes]
            matches.forEach(idx => {
                const [p, s, x] = splitFlaw(result[idx]);
                if (!sepMap.has(s)) sepMap.set(s, []);
                sepMap.get(s).push(p);
            });

            let combinedParts = [];
            for (let [sep, prefixes] of sepMap.entries()) {
                const uniquePrefixes = [...new Set(prefixes)];
                if (sep === ' ') { // Special case for "Corner"
                    combinedParts.push(uniquePrefixes.join('/'));
                } else {
                    combinedParts.push(uniquePrefixes.join('/') + sep.trimEnd());
                }
            }
            // Join parts with / and append the suffix
            // If it was "Corner", sep was ' ' and suffix was the flaw part
            const firstSep = splitFlaw(result[matches[0]])[1];
            if (firstSep === ' ') {
                suffixGrouped.push('Corner ' + combinedParts.join('/'));
            } else {
                suffixGrouped.push(combinedParts.join('/') + ' ' + x1);
            }
            matches.forEach(idx => handled.add(idx));
        } else {
            suffixGrouped.push(result[i]);
            handled.add(i);
        }
    }

    return suffixGrouped;
}

function assembleWalmartDescription(inputs, country, fmtData) {
    const parts = [
        inputs.mediaCond,
        fmtData.pkgFeature,
        inputs.isOOP ? "Out-of-Print" : "",
        fmtData.edition,
        inputs.year,
        country, // Keep country
        fmtData.finalFormatString,
        fmtData.mediaDesc, // Include media description
        inputs.sleeveCond, // Include sleeve condition
        fmtData.sleevePkg,
        // fmtData.sleeveTypeLabel, // Excluded for Walmart
        // fmtData.sleeveDesc // Excluded for Walmart
    ];

    let desc = parts.filter(p => p && p.toString().trim() !== "").join(' ');

    if (inputs.trackTime) desc += " with " + inputs.trackTime + " Tracks";

    if (inputs.label) desc += " - " + inputs.label;

    return desc;
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

    // Update Walmart Context immediately so the sheet can pull it
    try {
        // Rebuild the entire context from the current state of the main app
        // to ensure all data is fresh when the Walmart sheet pulls it.
        const scratchpadEl = document.getElementById('manualInputBox');
        const hiddenScrapeEl = document.getElementById('scraperResultText');
        const rawText = (scratchpadEl && scratchpadEl.value) ? scratchpadEl.value : (hiddenScrapeEl ? hiddenScrapeEl.textContent : '');

        const context = {
            sku: finalSku,
            builderDescription: document.getElementById('mediaDescriptionText')?.value || '',
            generatedDescription: lockDesc ? finalDesc : (walmartFilteredDesc || finalDesc), // Use the fresh filtered description unless locked
            label: document.getElementById('recordLabel')?.value || '',
            raw_text: rawText,
            discogsUrl: document.getElementById('discogsUrlInput')?.value || ''
        };
        localStorage.setItem('wysiwyg_walmart_context', JSON.stringify(context));

        // Push context to server cache immediately so the Walmart tool can "re-pull" it
        fetch('/api/walmart/cache-context', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(context)
        }).catch(err => console.error("Failed to push Walmart context to server:", err));

    } catch (e) { console.error("Failed to auto-update walmart context", e); }

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

function shutdownApp() {
    document.getElementById('shutdownModal').style.display = 'block';
}

function closeShutdownModal() {
    document.getElementById('shutdownModal').style.display = 'none';
}

function confirmShutdown() {
    fetch('/shutdown', { method: 'POST' }).then(() => {
        // Try to close the tab. This only works for tabs opened by script
        // (e.g. the Walmart/UberPaste popups). For a user-opened tab the browser
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

function pasteToManualInput() {
    navigator.clipboard.readText().then(text => {
        document.getElementById('manualInputBox').value = text;
    }).catch(err => {
        console.error('Failed to read clipboard contents: ', err);
        customAlert("Could not paste from clipboard. Please paste manually.");
    });
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

function copyScratchpad(btn) {
    const el = document.getElementById('manualInputBox');
    el.select();
    navigator.clipboard.writeText(el.value).then(() => {
        const originalText = btn.innerText;
        const originalColor = btn.style.backgroundColor;
        btn.innerText = "Copied!";
        btn.style.backgroundColor = "#28a745";
        setTimeout(() => {
            btn.innerText = originalText;
            btn.style.backgroundColor = originalColor;
        }, 1500);
    }).catch(err => customAlert("Copy failed: " + err));
}

function resetScraperTab() {
    customConfirm("Clear all scraper fields?", () => {
        document.querySelector('input[name="url"]').value = "";
        document.getElementById('scraperOutput').innerHTML = "";
        document.getElementById('manualInputBox').value = "";
        document.getElementById('htmlOutputBox').value = "";
        document.getElementById('htmlPreview').innerHTML = "";
    });
}

function updateCounterUIDeprecated() {}

// --- Custom Options Logic ---

let customOptionsData = { cassette: [], cd: [], lp: [] };
let editingCustomOptionIndex = -1;
let currentModalCategory = 'cassette';

function sortCustomOptionsData() {
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
        const response = await fetch('/api/conditions');
        if (response.ok) {
            customOptionsData = await response.json();
            // Ensure all keys exist
            if (!customOptionsData.cassette) customOptionsData.cassette = [];
            if (!customOptionsData.cd) customOptionsData.cd = [];
            if (!customOptionsData.lp) customOptionsData.lp = [];
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
        { id: 'lpOptions', key: 'lp' }
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

        customOptionsData[config.key].forEach((opt) => {
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
}

function renderCustomOptionsModalList() {
    const list = document.getElementById('customOptionsList');
    if (!list) return;

    list.innerHTML = '';
    const currentData = customOptionsData[currentModalCategory];

    if (!currentData || currentData.length === 0) {
        list.innerHTML = '<div style="font-size: 11px; color: #666; text-align: center;">No options found for this category. Add one below.</div>';
        return;
    }

    currentData.forEach((opt, index) => {
        const item = document.createElement('div');
        item.style.cssText = 'display:flex; justify-content:space-between; align-items:center; padding:4px 5px; border-bottom:1px solid var(--border-color); gap:3px;';

        if (editingCustomOptionIndex === index) {
            item.style.backgroundColor = 'var(--wysiwyg-blue-light, #e6f0ff)';
        }

        const textCol = document.createElement('div');
        textCol.style.cssText = 'font-size:11px; flex-grow:1; cursor:pointer; min-width:0;';
        textCol.title = 'Click to Edit';
        textCol.onclick = () => editCustomOption(index);
        textCol.innerHTML = `<strong>${opt.title}</strong><br><span style="color:#666;">${opt.text}</span>`;

        const starBtn = document.createElement('button');
        starBtn.innerHTML = opt.favorite ? '⭐' : '☆';
        starBtn.title = opt.favorite ? 'Remove from Favorites' : 'Add to Favorites';
        starBtn.className = 'nav-btn';
        starBtn.style.cssText = 'padding:2px 5px; height:20px; font-size:10px; flex-shrink:0; cursor:pointer;';
        starBtn.onclick = (e) => toggleFavoriteCustomOption(e, index);

        const delBtn = document.createElement('button');
        delBtn.innerHTML = '❌';
        delBtn.title = 'Delete Option';
        delBtn.className = 'nav-btn';
        delBtn.style.cssText = 'padding:2px 5px; color:var(--danger-color); height:20px; font-size:10px; flex-shrink:0;';
        delBtn.onclick = (e) => deleteCustomOption(e, index);

        item.appendChild(textCol);
        item.appendChild(starBtn);
        item.appendChild(delBtn);
        list.appendChild(item);
    });
}


window.editCustomOption = function (index) {
    editingCustomOptionIndex = index;
    const opt = customOptionsData[currentModalCategory][index];
    document.getElementById('newOptionTitle').value = opt.title;
    document.getElementById('newOptionText').value = opt.text;
    document.getElementById('addCustomOptionBtn').innerText = 'Update';

    const cancelBtn = document.getElementById('cancelEditCustomOptionBtn');
    if (cancelBtn) cancelBtn.style.display = 'inline-block';

    renderCustomOptionsModalList();
};

window.deleteCustomOption = function (event, index) {
    event.stopPropagation();
    customOptionsData[currentModalCategory].splice(index, 1);
    if (editingCustomOptionIndex === index) {
        cancelEditCustomOption();
    } else if (editingCustomOptionIndex > index) {
        editingCustomOptionIndex--;
    }
    saveCustomOptions();
    renderCustomOptionsSelect();
    renderCustomOptionsModalList();
};

window.toggleFavoriteCustomOption = function (event, index) {
    event.stopPropagation();
    const item = customOptionsData[currentModalCategory][index];
    if (item) {
        item.favorite = !item.favorite;
        if (editingCustomOptionIndex === index) {
            // Keep editing index in sync if it moves after sorting
            const tempItem = item;
            saveCustomOptions(); // sorts list
            editingCustomOptionIndex = customOptionsData[currentModalCategory].findIndex(i => i.title === tempItem.title && i.text === tempItem.text);
        } else {
            saveCustomOptions();
        }
        renderCustomOptionsSelect();
        renderCustomOptionsModalList();
    }
};

function cancelEditCustomOption() {
    editingCustomOptionIndex = -1;
    if (document.getElementById('newOptionTitle')) document.getElementById('newOptionTitle').value = '';
    if (document.getElementById('newOptionText')) document.getElementById('newOptionText').value = '';
    const addBtn = document.getElementById('addCustomOptionBtn');
    if (addBtn) addBtn.innerText = 'Add';

    const cancelBtn = document.getElementById('cancelEditCustomOptionBtn');
    if (cancelBtn) cancelBtn.style.display = 'none';

    renderCustomOptionsModalList();
}

// Removed mergeConditions function as it is now integrated into updateMenus

document.addEventListener('DOMContentLoaded', () => {
    loadCustomOptions();

    document.getElementById('modalCategorySelect')?.addEventListener('change', (e) => {
        currentModalCategory = e.target.value;
        cancelEditCustomOption();
    });

    document.getElementById('editCustomOptionsBtn')?.addEventListener('click', (e) => {
        e.preventDefault();
        cancelEditCustomOption();
        document.getElementById('customOptionsModal').style.display = 'block';
    });

    document.getElementById('closeCustomOptionsModalBtn')?.addEventListener('click', () => {
        document.getElementById('customOptionsModal').style.display = 'none';
    });

    document.getElementById('cancelEditCustomOptionBtn')?.addEventListener('click', () => {
        cancelEditCustomOption();
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

        if (editingCustomOptionIndex !== -1) {
            customOptionsData[currentModalCategory][editingCustomOptionIndex] = { title, text };
        } else {
            customOptionsData[currentModalCategory].push({ title, text });
        }

        saveCustomOptions();
        cancelEditCustomOption();
        renderCustomOptionsSelect();
    });

    document.getElementById('clearCustomOptionsBtn')?.addEventListener('click', (e) => {
        e.preventDefault();
        ['lpOptions', 'cdOptions', 'customOptions'].forEach(id => {
            const select = document.getElementById(id);
            if (select) {
                Array.from(select.options).forEach(opt => opt.selected = false);
            }
        });
    });

    // Context Menu for Favoriting
    ['lpOptions', 'cdOptions', 'customOptions'].forEach(id => {
        const select = document.getElementById(id);
        if (!select) return;

        select.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            const menu = document.getElementById('customContextMenu');
            if (menu) {
                menu.style.display = 'block';
                menu.style.left = e.pageX + 'px';
                menu.style.top = e.pageY + 'px';
                menu.dataset.targetId = id;
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
            const select = document.getElementById(targetId);
            if (!select) return;

            const key = targetId === 'lpOptions' ? 'lp' : (targetId === 'cdOptions' ? 'cd' : 'cassette');
            const selectedOptions = Array.from(select.selectedOptions);

            if (selectedOptions.length === 0) return;

            selectedOptions.forEach(opt => {
                try {
                    const data = JSON.parse(opt.value);
                    const item = customOptionsData[key].find(i => i.title === data.title && i.text === data.text);
                    if (item) {
                        item.favorite = !item.favorite;
                    }
                } catch (e) { }
            });

            saveCustomOptions();
            renderCustomOptionsSelect();
        };
    }
});
