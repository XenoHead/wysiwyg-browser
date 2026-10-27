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
    document.getElementById('footerYear').textContent = new Date().getFullYear();

    // Setup Event Listeners
    setupEventListeners();

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
});

function setupEventListeners() {
    function addClickListener(id, callback) {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('click', callback);
        } else {
            console.warn(`Element with ID '${id}' not found for click listener.`);
        }
    }

    // --- Create and Insert Walmart Button ---
    const uberPasteBtn = document.getElementById('runUberPasteBtn');
    if (uberPasteBtn && uberPasteBtn.parentElement) {
        const parent = uberPasteBtn.parentElement;

        // Create a wrapper for vertical stacking
        const wrapper = document.createElement('div');
        wrapper.style.display = 'flex';
        wrapper.style.flexDirection = 'column';
        wrapper.style.alignItems = 'center';
        wrapper.style.marginRight = '10px';

        // Create Walmart Button
        const walmartBtn = document.createElement('button');
        walmartBtn.id = 'runWalmartSheetBtn';
        walmartBtn.className = 'nav-btn nav-item-group';
        walmartBtn.title = 'Open Walmart Spreadsheet Exporter';

        const walmartIcon = document.createElement('img');
        walmartIcon.src = '/WalmartSheet/walmart.png';
        walmartIcon.className = 'nav-icon';
        walmartBtn.appendChild(walmartIcon);
        walmartBtn.appendChild(document.createTextNode(' Walmart'));

        // Create Dock Checkbox and Label
        const dockLabel = document.createElement('label');

        dockLabel.title = "Docking opens the tool in a new browser tab instead of a floating popup window.";
        dockLabel.style.cursor = 'pointer';
        dockLabel.style.fontSize = '10px';
        dockLabel.style.color = 'var(--text-color)';
        dockLabel.style.marginTop = '2px';

        const dockCheckbox = document.createElement('input');
        dockCheckbox.type = 'checkbox';
        dockCheckbox.id = 'dockWalmartSheet';
        dockCheckbox.style.marginRight = '3px';

        dockLabel.appendChild(dockCheckbox);
        dockLabel.appendChild(document.createTextNode('Dock'));

        wrapper.appendChild(walmartBtn);
        wrapper.appendChild(dockLabel);

        // Insert before UberPaste button
        parent.insertBefore(wrapper, uberPasteBtn);

        // Add event listeners
        walmartBtn.addEventListener('click', runWalmartSheet);
        dockCheckbox.addEventListener('change', (e) => {
            localStorage.setItem('wysiwyg_dock_walmart', e.target.checked);
        });
    }


    // --- Top Nav ---
    addClickListener('runUberPasteBtn', runUberPaste);
    addClickListener('runWysiScanBtn', runWysiScan);
    addClickListener('themeBtn', toggleTheme);
    addClickListener('refreshBtn', () => location.reload(true));
    addClickListener('updateMenusBtn', updateMenus);
    addClickListener('editorBtn', openEditor);
    addClickListener('shutdownBtn', shutdownApp);
    document.getElementById('dockScanner')?.addEventListener('change', (e) => {
        localStorage.setItem('wysiwyg_dock_scanner', e.target.checked);
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

    // --- Calculator Live Auto-Populate & Enter Key ---
    ['calcCompPrice', 'calcCompShip'].forEach(id => {
        document.getElementById(id)?.addEventListener('input', () => {
            const cp = parseFloat(document.getElementById('calcCompPrice').value) || 0;
            const cs = parseFloat(document.getElementById('calcCompShip').value) || 0;
            const ct = cp + cs;
            if (ct > 0) {
                document.getElementById('calcCompTotal').value = ct.toFixed(2);
                document.getElementById('calcOurPrice').value = (ct - 9).toFixed(2);
            } else {
                document.getElementById('calcCompTotal').value = '';
                document.getElementById('calcOurPrice').value = '';
            }
        });
    });
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
    document.getElementById('discogsUrlInput')?.addEventListener('click', async function() {
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

    document.getElementById('conditionOfMedia')?.addEventListener('change', function() {
        if (!this.value) document.getElementById('mediaDescriptionText').value = "";
        updateDynamicColors();
    });
    document.querySelectorAll('input[name="media_modifier"]').forEach(radio => {
        radio.addEventListener('change', updateDynamicColors);
    });
    document.getElementById('sleeveCondition')?.addEventListener('change', function() {
        if (!this.value) document.getElementById('sleeveDesc').value = "";
        updateDynamicColors();
    });
    updateDynamicColors();

    // --- Output Area ---
    addClickListener('copySkuBtn', (e) => copyField('outputSku', e.currentTarget));
    addClickListener('copyDescBtn', (e) => copyField('outputDesc', e.currentTarget));
    addClickListener('btnListed', (e) => incrementCounter('L', e.currentTarget));
    addClickListener('btnAmazon', (e) => incrementCounter('AA', e.currentTarget));
    addClickListener('btnDiscogs', (e) => incrementCounter('DA', e.currentTarget));
    addClickListener('btnDupes', (e) => incrementCounter('D', e.currentTarget));
    addClickListener('openListingsFolderBtn', openListingsFolder);

    // --- Details Tab ---
    addClickListener('copyLivePreviewBtn', copyLivePreview);
    addClickListener('copyHtmlBtn', copyGeneratedHtml);
    addClickListener('copyScratchpadBtn', (e) => copyScratchpad(e.currentTarget));
    addClickListener('selectAllScratchpadBtn', () => document.getElementById('manualInputBox').select());
    addClickListener('pasteToScratchpadBtn', pasteToManualInput);

    // --- Footer ---
    if (document.getElementById('openRequestModalBtn')) {
        addClickListener('openRequestModalBtn', openRequestModal);
    }

    // --- Service Status Polling ---
    // Check status every 5 seconds to reduce system load
    setInterval(updateServiceStatus, 5000);
}


// --- ASYNC & API FUNCTIONS ---

async function runUberPaste() {
    try {
        const resp = await fetch('/run-uberpaste', { method: 'POST' });
        const res = await resp.json();
        if (res.status !== 'success') {
            customAlert('Could not start UberPaste: ' + res.message);
        }
    } catch (e) {
        customAlert('Failed to connect to server to run UberPaste: ' + e);
    }
}

async function runWalmartSheet() {
    try {
        await clearWalmartCache(); // Clear cache before populating it
        const dock = document.getElementById('dockWalmartSheet').checked;

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

async function updateServiceStatus() {
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
    try {
        const resp = await fetch('/api/service-status');
        const status = await resp.json();
        
        const wysiBtn = document.getElementById('runWysiScanBtn');
        if (wysiBtn) {
            // Do not disable, just indicate status. 
            // Clicking again will simply open the window if server is running.
            if (status.wysiscan) {
                wysiBtn.classList.add('active-tool'); // You can add CSS for this later if you want
                wysiBtn.title = "Scanner is running (Click to open)";
                wysiBtn.style.border = "2px solid #28a745";
            } else {
                wysiBtn.classList.remove('active-tool');
                wysiBtn.title = "Open WysiScan";
                wysiBtn.style.border = "";
            }
        }
        
        const uberBtn = document.getElementById('runUberPasteBtn');
        if (uberBtn) {
            if (status.uberpaste) {
                uberBtn.style.border = "2px solid #28a745";
                uberBtn.title = "UberPaste is running";
            } else {
                uberBtn.style.border = "";
                uberBtn.title = "Launch UberPaste";
            }
        }
    } catch (e) {
        // Silent fail if server is unreachable
    }
}

async function runWysiScan() {
    try {
        // Ask the main server to launch the WysiScan server
        const resp = await fetch('/run-wysiscan', { method: 'POST' });
        const res = await resp.json();

        if (res.status === 'success') {
            // If launch is successful (or it was already running), open the UI in a popup window.
            const dock = document.getElementById('dockScanner').checked;
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
    // Let's try placing the button somewhere else to ensure it's not a layout issue.
    const anchorElement = document.getElementById('trackTimeInfo');
    if (!anchorElement || document.getElementById('saveVariableConditionsBtn')) return;

    // 1. Create the button by default, but in a disabled state.
    const saveBtn = document.createElement('button');
    saveBtn.id = 'saveVariableConditionsBtn';
    saveBtn.title = 'Save Variable Conditions (Requires Admin File)';
    saveBtn.innerHTML = '💾'; // Save icon
    saveBtn.disabled = true; // Start as disabled
    
    // Styling for disabled state
    saveBtn.style.marginLeft = '8px';
    saveBtn.style.padding = '0 5px';
    saveBtn.style.fontSize = '1em';
    saveBtn.style.lineHeight = '1';
    saveBtn.style.cursor = 'not-allowed';
    saveBtn.style.border = '1px solid #ccc';
    saveBtn.style.borderRadius = '3px';
    saveBtn.style.opacity = '0.5';

    anchorElement.insertAdjacentElement('afterend', saveBtn);

    saveBtn.addEventListener('click', (e) => {
        e.preventDefault();
        if (!saveBtn.disabled) {
            saveVariableConditions();
        }
    });

    // 2. Try to fetch the admin file to enable it.
    try {
        const response = await fetch('/allpass.json?t=' + new Date().getTime());
        if (response.ok) {
            // Enable the button on success
            saveBtn.disabled = false;
            saveBtn.style.cursor = 'pointer';
            saveBtn.style.opacity = '1';
            saveBtn.title = 'Save Variable Conditions';
            saveBtn.style.backgroundColor = '#28a745';
            saveBtn.style.borderColor = '#28a745';
            saveBtn.style.color = 'white';
        } else {
            console.warn(`Could not load '/allpass.json' (status: ${response.status}). The 'Save Conditions' button remains disabled.`);
        }
    } catch (e) {
        console.warn("Network error while checking for admin file. The 'Save Conditions' button remains disabled.", e);
    }
}

async function loadAppVersion() {
    try {
        const resp = await fetch('/api/version');
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
        const titleEl = document.getElementById('appTitle');

        let titleHtml = `${appName} - v${vStr}`;
        if (isDev) {
             titleHtml = `<span style="color: #ff9800;">🛠️ ${titleHtml}</span>`;
        }

        if (v.update_available) {
            titleHtml += ` <span onclick="event.stopPropagation(); runInstaller()" style="cursor:pointer; background: #ffc107; color: #000; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; margin-left: 10px; border: 1px solid #000; vertical-align: middle;" title="Click to run installer">* UPDATE AVAILABLE *</span>`;
            document.getElementById('updateBanner').style.display = 'block';
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
    customConfirm("Overwrite local menus with server version?", async () => {
        try {
            const resp = await fetch('/update-menus', { method: 'POST' });
            const res = await resp.json();
            customAlert(res.message);
            if (res.status === 'success') location.reload();
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

async function loadCounters() {
    try {
        const resp = await fetch('/api/get-counters');
        const counts = await resp.json();
        updateCounterUI(counts);
    } catch (e) { console.error(e); }
}

async function incrementCounter(type, btn) {
    const originalHTML = btn.innerHTML;
    btn.innerText = "⏳";
    try {
        const resp = await fetch('/api/increment-counter', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: type })
        });
        const res = await resp.json();
        if (res.status === 'success') {
            btn.innerText = "✅";
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

async function openListingsFolder() {
    try {
        await fetch('/open-listings-folder', { method: 'POST' });
    } catch (e) {
        console.error(e);
    }
}

// --- CUSTOM MODAL SYSTEM ---
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
    
    // Clear all fields every time the modal opens
    ['calcCompPrice', 'calcCompShip', 'calcCompTotal', 'calcOurPrice', 'calcOurTotal'].forEach(id => {
        document.getElementById(id).value = '';
    });
    
    if (!costCalcData) {
        try {
            const resp = await fetch('/api/cost_calc.json');
            if (resp.ok) {
                const data = await resp.json();
                costCalcData = data.Cost_calulation || [];
                const sel = document.getElementById('calcCondition');
                sel.innerHTML = '';
                costCalcData.forEach(item => {
                    const opt = document.createElement('option');
                    opt.value = item; opt.textContent = item;
                    sel.appendChild(opt);
                });
            }
        } catch (e) { console.error("Failed to load cost_calc.json", e); }
    }
}
function closeCalcModal() { document.getElementById('calcModal').style.display = 'none'; }
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

function loadVariableConditions() {
    const savedMediaCondition = localStorage.getItem('wysiwyg_variable_media_condition');
    const savedIsOOP = localStorage.getItem('wysiwyg_variable_is_oop');

    if (savedMediaCondition) {
        const select = document.getElementById('conditionOfMedia');
        const modifiers = ['+', '-'];
        let baseValue = savedMediaCondition;
        let modifierValue = "";

        if (modifiers.includes(savedMediaCondition.slice(-1))) {
            baseValue = savedMediaCondition.slice(0, -1);
            modifierValue = savedMediaCondition.slice(-1);
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

    if (savedIsOOP !== null) {
        document.getElementById('oopToggle').checked = (savedIsOOP === 'true');
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

async function fullReset() {
    const inputs = document.querySelectorAll('input[type="text"]:not(#boxNumber):not(#lister), input[type="url"], textarea:not(#outputDesc)');
    inputs.forEach(input => input.value = "");
    const selects = document.querySelectorAll('select');
    selects.forEach(sel => {
        Array.from(sel.options).forEach(opt => {
            opt.selected = (opt.value === "");
        });
    });
    document.querySelectorAll('input[type="radio"][value=""]').forEach(rad => rad.checked = true);
    document.getElementById('oopToggle').checked = false;
    ['checkA', 'checkB', 'checkC'].forEach(id => document.getElementById(id).checked = false);
    document.getElementById('outputSku').value = "";
    document.getElementById('outputDesc').value = "";

    // Clear Details Tab Elements
    document.getElementById('htmlPreview').innerHTML = "";
    document.getElementById('scraperOutput').innerHTML = "";
    document.getElementById('scraperError').innerHTML = "";

    await clearWalmartCache();

    updateDynamicColors();
    loadVariableConditions(); // Restore saved variables after reset
}

function saveProfile() {
    const box = document.getElementById('boxNumber').value;
    const init = document.getElementById('lister').value;
    localStorage.setItem('wysiwyg_profile_box', box);
    localStorage.setItem('wysiwyg_profile_init', init);
    customAlert("Profile Saved!");
}

function loadProfile() {
    const box = localStorage.getItem('wysiwyg_profile_box');
    const init = localStorage.getItem('wysiwyg_profile_init');
    if (box) document.getElementById('boxNumber').value = box;
    if (init) document.getElementById('lister').value = init;
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
    document.querySelectorAll('select').forEach(sel => {
        if (sel.multiple) Array.from(sel.options).forEach(opt => opt.selected = false);
        else sel.selectedIndex = 0;
    });

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
    ['checkA', 'checkB', 'checkC'].forEach(id => document.getElementById(id).checked = false);

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
            document.getElementById('formatLine').innerText = expandedFStr;
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
}

function generateListingData() {
    // 1. Gather Inputs
    const inputs = {
        mediaCond: getVal('conditionOfMedia') || "",
        sleeveCond: getVal('sleeveCondition') || "",
        country: getVal('country').trim(),
        formatLineRaw: document.getElementById('formatLine').innerText || "",
        mediaDesc: document.getElementById('mediaDescriptionText').value.trim() || "",
        colorVal: document.getElementById('mediaColor').value.trim(),
        preFM: getVal('preFM'),
        weightSpeed: getVal('weightSpeed'),
        mediaFormat: getVal('mediaFormat') || "",
        postFM: getVal('postFM') || "",
        sleevePkg: getVal('sleevePackaging'),
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
        checkA: document.getElementById('checkA').checked,
        checkB: document.getElementById('checkB').checked,
        checkC: document.getElementById('checkC').checked
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
    let { formatLineRaw, mediaDesc, colorVal, preFM, weightSpeed, mediaFormat, postFM, sleevePkg, pkgFeature, edition, formatTags, checkA, checkB, checkC, sleeveDesc, sleeveCond } = inputs;

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

    // Checkbox Logic
    if (checkC) {
        finalFormatString += " ( final sale - can’t verify matrix/pressing/label variant due to seal )";
    }

    if (checkA || checkB) {
        let flaws = [];
        if (checkB) flaws.push("Jewel Case cracking");
        if (checkA) flaws.push("cellophane tearing");
        const combinedFlaws = flaws.join(" & ");

        if (sleeveDesc) sleeveDesc += " & " + combinedFlaws;
        else if (sleevePkg) sleevePkg += " with " + combinedFlaws;
        else if (postFM) finalFormatString += " with " + combinedFlaws;
        else if (mediaDesc) mediaDesc += " & " + combinedFlaws;
        else finalFormatString += " with " + combinedFlaws;
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
        edition
    };
}

function assembleDescription(inputs, country, fmtData) {
    const parts = [
        inputs.mediaCond,
        fmtData.pkgFeature,
        inputs.isOOP ? "Out-of-Print" : "",
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

    let desc = parts.filter(p => p && p.toString().trim() !== "").join(' ');
    desc = desc.replace(/,/g, '');

    if (inputs.trackTime) desc += " with " + inputs.trackTime + " Tracks";

    if (inputs.label) desc += " - " + inputs.label;

    desc = desc.replace(/,/g, '');
    return desc;
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
    desc = desc.replace(/,/g, '');

    if (inputs.trackTime) desc += " with " + inputs.trackTime + " Tracks";

    if (inputs.label) desc += " - " + inputs.label;

    desc = desc.replace(/,/g, '');
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
            { code: "BLUERAY", count: cBD, regex: rBD },
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
    if (combined.includes("blu-ray")) return "BLUERAY";
    if (combined.includes("dvd")) return "DVD";
    if (combined.includes("vhs")) return "VHS";

    // 3. SINGLES
    const singleSignals = ["7\"", "12\"", "10\"", "single", "maxi-single"];
    const hasSignal = singleSignals.some(s => combined.includes(s));
    const isAlbum = combined.includes("lp") || combined.includes("album");

    if (hasSignal && !isAlbum) {
        if (combined.includes("cd")) return "CDS";
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

    if (!isOOP && !suppressSuffix) {
        document.getElementById('outputSku').value = sku + "-O";
        copyText = `${sku}-O\n${desc}`;
    } else {
        document.getElementById('outputSku').value = sku;
        copyText = `${sku}\n${desc}`;
    }
    document.getElementById('outputDesc').value = desc;

    // Update Walmart Context immediately so the sheet can pull it
    try {
        // Rebuild the entire context from the current state of the main app
        // to ensure all data is fresh when the Walmart sheet pulls it.
        const scratchpadEl = document.getElementById('manualInputBox');
        const hiddenScrapeEl = document.getElementById('scraperResultText');
        const rawText = (scratchpadEl && scratchpadEl.value) ? scratchpadEl.value : (hiddenScrapeEl ? hiddenScrapeEl.textContent : '');

        const context = {
            sku: document.getElementById('outputSku')?.value || '',
            builderDescription: document.getElementById('mediaDescriptionText')?.value || '',
            generatedDescription: walmartFilteredDesc || desc, // Use the fresh filtered description
            label: document.getElementById('recordLabel')?.value || '',
            raw_text: rawText 
        };
        localStorage.setItem('wysiwyg_walmart_context', JSON.stringify(context));
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
        document.body.innerHTML = "<div style='display:flex;justify-content:center;align-items:center;height:100vh;flex-direction:column;font-family:Arial;'><h1>🔌 System Offline</h1><p>You can close this tab.</p></div>";
        window.close();
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

function updateCounterUI(counts) {
    const btnL = document.getElementById('btnListed');
    const btnAA = document.getElementById('btnAmazon');
    const btnDA = document.getElementById('btnDiscogs');
    const btnD = document.getElementById('btnDupes');

    if (btnL) btnL.innerHTML = `L<br>${counts['Listed'] || 0}`;
    if (btnAA) btnAA.innerHTML = `AA<br>${counts['Amazon Adds'] || 0}`;
    if (btnDA) btnDA.innerHTML = `DA<br>${counts['Discogs Adds'] || 0}`;
    if (btnD) btnD.innerHTML = `D<br>${counts['Duplicates'] || 0}`;
}

/**
 * Clears all input fields in the Walmart UI to ensure a clean slate.
 * No confirmation prompt is used to allow for rapid switching between items.
 */
function clearAllFields() {
    const fieldIds = [
        'productName', 'siteDescription', 'sellingPrice', 
        'manufacturerPartNumber', 'musicMediaFormat', 
        'originalReleaseDate', 'performer', 'recordLabel', 
        'title', 'musicGenre', 'condition', 'numberOfDiscs'
    ];
    fieldIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    
    // Clear any results tables or status messages if they exist
    const resultsDiv = document.getElementById('walmartResults');
    if (resultsDiv) resultsDiv.innerHTML = '';
}

/**
 * Takes the context imported from the Builder and processes it for the Walmart form.
 */
async function handleImportedContext(context) {
    if (!context || Object.keys(context).length === 0) return;

    try {
        // Call the backend API to process the raw Discogs text into Walmart-specific fields
        const resp = await fetch('/api/walmart/process-item', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(context)
        });

        if (!resp.ok) throw new Error("Failed to process item metadata.");

        const result = await resp.json();

        // Map the result keys to the corresponding UI element IDs
        const mapping = {
            'productName': result.productName,
            'siteDescription': result.siteDescription,
            'sellingPrice': result.sellingPrice,
            'manufacturerPartNumber': result.manufacturerPartNumber,
            'musicMediaFormat': result.mediaFormat,
            'originalReleaseDate': result.originalReleaseDate,
            'performer': result.performer,
            'recordLabel': result.recordLabel,
            'title': result.title,
            'musicGenre': result.musicGenre || 'Pop',
            'condition': result.condition || 'Used',
            'numberOfDiscs': result.numberOfDiscs || '1'
        };

        for (const [id, value] of Object.entries(mapping)) {
            const el = document.getElementById(id);
            if (el) el.value = value || '';
        }

    } catch (e) {
        console.error("Error handling imported context:", e);
        customAlert("Failed to process Builder data: " + e.message);
    }
}

/**
 * Independent Scrape function for the Walmart tab.
 * Allows users to scrape metadata directly from a Discogs URL without using the Builder.
 */
async function runWalmartScrape() {
    const urlInput = document.getElementById('walmartScrapeUrl');
    const url = urlInput ? urlInput.value.trim() : "";
    if (!url) {
        customAlert("Please paste a Discogs Release or Marketplace URL.");
        return;
    }

    const scrapeBtn = document.getElementById('walmartScrapeBtn');
    const originalText = scrapeBtn.innerText;
    scrapeBtn.innerText = "⏳ Scraping...";
    scrapeBtn.disabled = true;

    try {
        // We use the JSON scraper endpoint for cleaner data handling
        const resp = await fetch('/api/scrape-json', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });

        if (!resp.ok) throw new Error("Scrape failed. Ensure the URL is valid.");

        const json = await resp.json();
        if (json.status !== 'success') throw new Error(json.message);

        // We don't want to affect the Builder, so we create a local context
        // and pass it directly to handleImportedContext.
        const release = json.data.release;
        const artist = release.artists.map(a => a.name.replace(/\s*\(\d+\)$/, '')).join(', ');
        
        // Format the raw_text as walmart.py expects it for parsing
        const raw_text = `${artist} - ${release.title}\n` +
                         `Label: ${release.labels[0]?.name} ${release.labels[0]?.catno}\n` +
                         `Format: ${release.formats[0]?.name} ${release.formats[0]?.descriptions?.join(' ')}\n` +
                         `Released: ${release.released_year || ''}\n` +
                         `Country: ${release.country || ''}`;

        const context = {
            raw_text: raw_text,
            label: `${release.labels[0]?.name} ${release.labels[0]?.catno}`,
            generatedDescription: "", // Empty so it generates a fresh one
            discogsUrl: url
        };

        clearAllFields();
        await handleImportedContext(context);
        scrapeBtn.innerText = "✅ Done!";

    } catch (e) {
        console.error("Walmart Scrape Error:", e);
        customAlert(e.message);
    } finally {
        setTimeout(() => {
            scrapeBtn.innerText = originalText;
            scrapeBtn.disabled = false;
        }, 2000);
    }
}

/**
 * Function to be called by the "Load From Builder" button in the Walmart UI.
 * It clears the server cache and re-pulls the freshest data.
 */
async function loadFromBuilder() {
    try {
        // 1. Wipe the UI and explicitly clear Product Name to prevent "stickiness"
        clearAllFields();
        const pNameEl = document.getElementById('productName');
        if (pNameEl) pNameEl.value = '';

        // 2. Re-pull context with cache-busting timestamp
        const resp = await fetch(`/api/walmart/cache-context?cachebuster=${Date.now()}`);
        if (resp.status === 404) {
            throw new Error("No data found in Builder. Please click 'Generate' on the Builder tab first.");
        }
        
        const context = await resp.json();
        
        // 3. Pass the data to the processing logic
        await handleImportedContext(context);

    } catch (e) {
        customAlert("Load From Builder failed: " + e.message);
    }
}