"""
minicpm_gui.py — Native PySide6 window for MiniCPM-V image extraction via ollama.

Usage:
    .venv311\Scripts\python.exe minicpm_gui.py

Requires: PySide6, httpx (both in .venv311).

Run from a PySide6 window so Python (not the browser) calls ollama on
localhost:11434 — no file:// CORS issues. Uses a worker thread so the UI
stays responsive during the ollama call.
"""

import json
import os
import sys

from PySide6.QtCore import Qt, QObject, Signal, QThread, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel

try:
    import httpx
except ImportError:
    httpx = None


OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "minicpm-v4.6:1b"


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

class OllamaWorker(QThread):
    """Background thread that calls ollama and emits the result."""
    finished = Signal(bool, str, str)  # ok, text, error_msg

    def __init__(self, base64_list, prompt, parent=None):
        super().__init__(parent)
        self.base64_list = base64_list
        self.prompt = prompt

    def run(self):
        try:
            ok, text, err = _call_ollama(self.base64_list, self.prompt)
        except Exception as exc:
            ok, text, err = False, "", str(exc)
        self.finished.emit(ok, text, err)


def _call_ollama(base64_list, prompt):
    """Call ollama /api/chat with stream:false (single JSON response)."""
    content = []
    if prompt:
        content.append({"type": "text", "text": prompt})

    for b64 in base64_list:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
        })

    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "stream": False
    }

    if httpx is None:
        import urllib.request
        import urllib.error
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            OLLAMA_URL, data=data,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.URLError as exc:
            return False, "", f"Could not reach ollama: {exc.reason}"

        obj = json.loads(raw)
        msg = obj.get("message", {})
        return True, msg.get("content", ""), ""

    with httpx.Client(timeout=600.0) as client:
        resp = client.post(OLLAMA_URL, json=body)

    if resp.status_code != 200:
        snippet = resp.text[:300] if resp.text else ""
        return False, "", f"ollama returned {resp.status_code}: {snippet}"

    obj = resp.json()
    msg = obj.get("message", {})
    return True, msg.get("content", ""), ""


# ---------------------------------------------------------------------------
# QWebChannel bridge — exposes runExtraction() to the HTML page.
# JS calls runExtraction(); a worker thread runs and the bridge emits
# extractionFinished, which JS connects to via QWebChannel.
# ---------------------------------------------------------------------------

class OllamaBridge(QObject):
    extractionFinished = Signal(bool, str, str)  # ok, text, error_msg

    def runExtraction(self, base64_list, prompt):
        worker = OllamaWorker(base64_list, prompt)
        worker.finished.connect(self._onFinished, Qt.QueuedConnection)
        worker.finished.connect(worker.deleteLater, Qt.QueuedConnection)
        worker.start()

    def _onFinished(self, ok, text, err):
        self.extractionFinished.emit(ok, text, err)


# ---------------------------------------------------------------------------
# HTML UI
# ---------------------------------------------------------------------------

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  :root {
    --bg: #0f0f11; --surface: #1a1a1e; --surface2: #222228;
    --border: #2a2a30; --fg: #e4e4e7; --muted: #888890;
    --accent: #7c6ff7; --danger: #e05a5a; --success: #4caf80; --radius: 8px;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    background: var(--bg); color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 14px; line-height: 1.5; padding: 16px;
  }
  .header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid var(--border);
  }
  .header h1 { font-size: 16px; font-weight: 600; }
  .badge {
    font-size: 10px; color: var(--muted); background: var(--surface2);
    padding: 3px 8px; border-radius: var(--radius); border: 1px solid var(--border);
  }
  .drop-zone {
    position: relative;
    border: 2px dashed var(--border); border-radius: var(--radius);
    padding: 36px 16px; text-align: center; cursor: pointer;
    background: var(--surface);
    user-select: none;
  }
  .drop-zone.dragover { border-color: var(--accent); background: var(--surface2); }
  .drop-zone .icon { font-size: 30px; margin-bottom: 4px; opacity: 0.6; }
  .drop-zone p { color: var(--muted); font-size: 12px; }
  .drop-zone p strong { color: var(--fg); }
  .drop-zone input[type="file"] {
    display: none;
  }
  .btn-browse {
    background: var(--surface2); color: var(--fg);
    border: 1px solid var(--border); border-radius: var(--radius);
    padding: 4px 10px; font-size: 11px; cursor: pointer;
    font-family: inherit; margin-left: 4px;
  }
  .btn-browse:hover { border-color: var(--accent); }
  .grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 8px; margin-top: 10px;
  }
  .card {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius); overflow: hidden; position: relative;
  }
  .card img { width: 100%; display: block; aspect-ratio: 1; object-fit: cover; background: #000; }
  .card .name {
    padding: 4px 6px; font-size: 9px; color: var(--muted);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center;
  }
  .card .rm {
    position: absolute; top: 2px; right: 2px; width: 18px; height: 18px;
    border-radius: 50%; background: rgba(0,0,0,0.7); color: #fff;
    border: none; cursor: pointer; font-size: 11px; line-height: 18px; text-align: center;
  }
  .controls {
    margin-top: 12px; display: flex; gap: 8px; align-items: flex-end; flex-wrap: wrap;
  }
  .prompt-box { flex: 1; min-width: 160px; }
  .prompt-box label { display: block; font-size: 10px; color: var(--muted); margin-bottom: 3px; }
  .prompt-box textarea {
    width: 100%; min-height: 54px; padding: 6px 8px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); color: var(--fg); font-family: inherit;
    font-size: 11px; resize: vertical;
  }
  .prompt-box textarea:focus { outline: none; border-color: var(--accent); }
  button {
    padding: 7px 14px; border: none; border-radius: var(--radius);
    font-size: 11px; font-weight: 500; cursor: pointer;
    font-family: inherit; transition: background 0.2s, opacity 0.2s;
  }
  .btn-primary { background: var(--accent); color: #fff; }
  .btn-primary:hover { background: #6a5ce0; }
  .btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
  .btn-danger { background: var(--danger); color: #fff; }
  .btn-danger:hover { opacity: 0.85; }
  .status {
    margin-top: 10px; padding: 8px 12px; background: var(--surface);
    border: 1px solid var(--border); border-radius: var(--radius);
    font-size: 11px; color: var(--muted); min-height: 30px;
    display: flex; align-items: center; gap: 6px;
  }
  .status.error { color: var(--danger); border-color: var(--danger); }
  .status.success { color: var(--success); border-color: var(--success); }
  .spinner {
    width: 12px; height: 12px; border: 2px solid var(--border);
    border-top-color: var(--accent); border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .result {
    margin-top: 10px; background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 10px;
  }
  .result h3 {
    font-size: 10px; color: var(--muted); margin-bottom: 6px;
    text-transform: uppercase; letter-spacing: 0.5px;
  }
  .result pre {
    background: var(--bg); padding: 8px; border-radius: var(--radius);
    overflow-x: auto; font-size: 10px; line-height: 1.5;
    white-space: pre-wrap; word-break: break-word; max-height: 450px; overflow-y: auto;
  }
  .footer {
    margin-top: 12px; padding-top: 8px; border-top: 1px solid var(--border);
    font-size: 9px; color: var(--muted); text-align: center;
  }
</style>
</head>
<body>
  <div class="header">
    <h1>MiniCPM Vision — Image Extractor</h1>
    <span class="badge">ollama · minicpm-v4.6:1b</span>
  </div>

  <div class="drop-zone" id="dz">
    <div class="icon">📁</div>
    <p><strong>Drop images here</strong> or <button id="browseBtn" class="btn-browse">Browse</button><br>
       <small style="color:var(--muted)">JPG, PNG, WEBP — multiple allowed</small></p>
    <input type="file" id="fi" multiple accept="image/jpeg,image/png,image/webp" style="display:none">
  </div>

  <div class="grid" id="grid"></div>

  <div class="controls">
    <div class="prompt-box">
      <label for="prompt">Prompt</label>
      <textarea id="prompt" rows="3">Read all text visible in these images: artist name, album title, tracklist, catalog number, label, format, country of origin, and any copyright (c) or patent (p) markings. List everything you can read.</textarea>
    </div>
    <button class="btn-primary" id="run">▶ Run</button>
    <button class="btn-danger" id="clear">Clear All</button>
  </div>

  <div class="status" id="status">Ready — add images and click Run</div>

  <div class="result" id="result" style="display:none">
    <h3>Extraction Result</h3>
    <pre id="resultText"></pre>
  </div>

  <div class="footer">
    Calls ollama on <strong>http://localhost:11434</strong> via the host app (no browser CORS).
  </div>

<script>
  const dz     = document.getElementById('dz');
  const fi     = document.getElementById('fi');
  const grid   = document.getElementById('grid');
  const runBtn = document.getElementById('run');
  const clear  = document.getElementById('clear');
  const status = document.getElementById('status');
  const result = document.getElementById('result');
  const resultText = document.getElementById('resultText');
  const promptEl = document.getElementById('prompt');

  let files = [];      // {name, size, b64}

  fi.addEventListener('change', () => addFiles(fi.files));

  dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('dragover'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('dragover'));
  dz.addEventListener('drop', e => {
    e.preventDefault(); dz.classList.remove('dragover');
    addFiles(e.dataTransfer.files);
  });

  const browseBtn = document.getElementById('browseBtn');
  if (browseBtn) browseBtn.addEventListener('click', e => {
    e.stopPropagation();
    fi.click();
  });

  async function addFiles(fileList) {
    for (const f of fileList) {
      if (!f.type.startsWith('image/')) continue;
      const key = f.name + '|' + f.size;
      if (files.some(x => x.name + '|' + x.size === key)) continue;
      const b64 = await readAsBase64(f);
      files.push({ name: f.name, size: f.size, b64 });
    }
    render();
    setStatus(`${files.length} image(s) loaded.`);
  }

  function render() {
    grid.innerHTML = '';
    files.forEach((f, i) => {
      const card = document.createElement('div');
      card.className = 'card';
      const mime = f.name.match(/\.png$/i) ? 'image/png' : 'image/jpeg';
      const img = document.createElement('img');
      img.src = 'data:' + mime + ';base64,' + f.b64;
      const nm = document.createElement('div');
      nm.className = 'name'; nm.textContent = f.name;
      const rm = document.createElement('button');
      rm.className = 'rm'; rm.textContent = '\u00d7';
      rm.onclick = () => { files.splice(i,1); render(); setStatus(''); };
      card.append(img, nm, rm);
      grid.appendChild(card);
    });
    runBtn.disabled = files.length === 0;
  }

  function readAsBase64(file) {
    return new Promise((ok, no) => {
      const r = new FileReader();
      r.onload = () => ok(r.result.split(',')[1]);
      r.onerror = no;
      r.readAsDataURL(file);
    });
  }

  function setStatus(msg, type) {
    status.className = 'status' + (type ? ' ' + type : '');
    status.innerHTML = msg
      ? (type === 'loading' ? '<div class="spinner"></div>' + msg : msg)
      : 'Ready — add images and click Run';
  }

  clear.addEventListener('click', () => {
    files = []; render(); setStatus('Cleared.');
    result.style.display = 'none';
  });

  // Set up the QWebChannel bridge to receive extraction results.
  // Polls until qt.webChannelTransport is available (set by PySide6 when
  // setWebChannel is called before setHtml).
  let bridge = null;
  function setupChannel() {
    if (typeof qt !== 'undefined' && qt.webChannelTransport) {
      new QWebChannel(qt.webChannelTransport, function(channel) {
        bridge = channel.objects.bridge;
        bridge.extractionFinished.connect(function(ok, text, err) {
          runBtn.disabled = false;
          if (!ok) {
            setStatus('Error: ' + err, 'error');
            return;
          }
          setStatus('Done — extracted from ' + files.length + ' image(s).', 'success');
          resultText.textContent = text || '(no text returned)';
          result.style.display = 'block';
        });
      });
    } else {
      setTimeout(setupChannel, 100);
    }
  }
  setupChannel();

  runBtn.addEventListener('click', () => {
    if (files.length === 0 || !bridge) return;
    runBtn.disabled = true;
    setStatus('Sending to ollama…', 'loading');
    result.style.display = 'none';

    const b64s = files.map(f => f.b64);
    const prompt = promptEl.value.trim();
    bridge.runExtraction(b64s, prompt);
  });
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MiniCPM Vision — Image Extractor")
        self.resize(800, 620)

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fyr-logo.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.web = QWebEngineView()
        self.web.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        # Allow local HTML to talk to localhost:11434 (called by Python, not JS,
        # but enabling for completeness)
        self.web.settings().setAttribute(
            QWebEngineSettings.LocalContentCanAccessRemoteUrls, True
        )
        layout.addWidget(self.web, stretch=1)

        # QWebChannel: expose the bridge to the HTML page
        self.channel = QWebChannel(self)
        self.bridge = OllamaBridge()
        self.channel.registerObject("bridge", self.bridge)
        self.web.page().setWebChannel(self.channel)
        # IMPORTANT: setWebChannel BEFORE setHtml so qt.webChannelTransport is
        # ready when the page's script first runs.
        self.web.setHtml(HTML, QUrl.fromLocalFile(
            os.path.dirname(os.path.abspath(__file__)) + "/index.html"
        ))

        self.statusBar().showMessage("Ready — add images and click Run")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
