
(function () {
    const API_BASE =   ;
    const imgInput = document.getElementById(          );
    const thumbList = document.getElementById(           );
    const statusEl = document.getElementById(        );
    const results = document.getElementById(         );
    const buildBtn = document.getElementById(          );
    let lastText =   ;

                                         
    try {
        const t = localStorage.getItem(               );
        if (t ===       ) document.body.classList.add(      );
    } catch (e) {}

    function setStatus(msg, kind) {
        statusEl.textContent = msg ||   ;
        statusEl.className =          + (kind ?     + kind :   );
    }

                                  
    let selectedFiles = [];
    imgInput.addEventListener(        , () => {
        for (const f of imgInput.files) {
            if (selectedFiles.length >= 8) {
                setStatus(                              ,      );
                break;
            }
            selectedFiles.push(f);
        }
        renderThumbs();
        imgInput.value =   ;
    });

    function renderThumbs() {
        thumbList.innerHTML =   ;
        selectedFiles.forEach((f, i) => {
            const div = document.createElement(     );
            div.className =        ;
            const url = URL.createObjectURL(f);
            const img = document.createElement(     );
            img.src = url;
            const rm = document.createElement(        );
            rm.className =     ;
            rm.textContent =    ;
            rm.onclick = () => { URL.revokeObjectURL(url); selectedFiles.splice(i, 1); renderThumbs(); };
            div.appendChild(img); div.appendChild(rm);
            thumbList.appendChild(div);
        });
        document.getElementById(          ).textContent = selectedFiles.length;
    }

    async function copyText(text) {
        try { await navigator.clipboard.writeText(text); }
        catch (e) {             }
    }
    function flashCopied(btn) {
        const old = btn.textContent;
        btn.textContent =    ;
        setTimeout(() => { btn.textContent = old; }, 900);
    }

                                                                         
    function renderTables(tables) {
        results.innerHTML =   ;
        const sectionOrder = Object.keys(tables);
        for (const title of sectionOrder) {
            const rows = tables[title] || [];
            const h = document.createElement(     );
            h.className =                ;
            h.textContent = title;
            results.appendChild(h);
            for (const row of rows) {
                                                                 
                if (row && typeof row ===          && !Array.isArray(row)) {
                    const track = row.Track ||   ;
                    let title = (row.Title ||   ).replace(          ,     );
                    const time = row.Time ||   ;
                    const r = document.createElement(     );
                    r.className =            ;
                    const lbl = document.createElement(     );
                    lbl.className =              ;
                    lbl.textContent = (title && title.startsWith(    )) ?           : (track ?          + track :   );
                    const val = document.createElement(          );
                    val.className =            ;
                    val.value = title + (time ?       + time +     :   );
                    val.rows = 1;
                    r.appendChild(lbl); r.appendChild(val);
                    if (String(title).trim()) {
                        const btn = document.createElement(        );
                        btn.className =           ;
                        btn.textContent =       ;
                        btn.onclick = async () => { await copyText(val.value); flashCopied(btn); };
                        r.appendChild(btn);
                    }
                    results.appendChild(r);
                    continue;
                }
                if (!Array.isArray(row) || row.length < 2) continue;
                const label = row[0];
                const value = row[1];
                if (value ===     && label ===    ) {
                                          
                    const sep = document.createElement(     );
                    sep.style.height =      ;
                    results.appendChild(sep);
                    continue;
                }
                                                                                  
                if ((label ===        && value ===        ) || (label ===        && value ===         )) {
                    const hd = document.createElement(     );
                    hd.style.cssText =                                                                                                                     ;
                    hd.textContent = label +       + value;
                    results.appendChild(hd);
                    continue;
                }
                const r = document.createElement(     );
                r.className =            ;
                const lbl = document.createElement(     );
                lbl.className =              ;
                lbl.textContent = label;
                const val = document.createElement(          );
                val.className =            ;
                val.value = value == null ?    : String(value);
                val.rows = Math.max(1, Math.min(8, Math.ceil(val.value.length / 60)));
                r.appendChild(lbl); r.appendChild(val);
                if (value !==     && String(value).trim() !==   ) {
                    const btn = document.createElement(        );
                    btn.className =           ;
                    btn.textContent =       ;
                    btn.onclick = async () => { await copyText(val.value); flashCopied(btn); };
                    r.appendChild(btn);
                }
                results.appendChild(r);
            }

        lastText = results.innerText;
    }

    window.copyAll = function () {
        let out =   ;
        results.querySelectorAll(                ).forEach(sec => {
            out +=     + sec.textContent +    ;
            let n = sec.nextElementSibling;
            while (n && !n.classList.contains(               )) {
                if (n.classList.contains(           )) {
                    const l = n.querySelector(              )?.textContent ||   ;
                    const v = n.querySelector(            )?.value ||   ;
                    if (v.trim()) out += l +      + v +    ;
                }
                n = n.nextElementSibling;
            }
        });
        copyText(out.trim());
        setStatus(                                 ,     );
    };

    window.runDiscogsAdd = async function () {
        if (!selectedFiles.length) {
            setStatus(                                       ,      );
            return;
        }
        buildBtn.disabled = true;
        setStatus(                                         );
        results.innerHTML =   ;
        const url = API_BASE +                    ;
        console.log(                     , url,          , selectedFiles.length);
        try {
            const fd = new FormData();
            selectedFiles.forEach(f => fd.append(        , f, f.name));
            const resp = await fetch(url, { method:       , body: fd });
            console.log(                       , resp.status, resp.statusText);
            const data = await resp.json();
            console.log(                     , data);
            if (data.status ===          ) {
                const tables = data.tables || {};
                if (data.phase ===           ) {
                                                                           
                    results.innerHTML =   ;
                    const h = document.createElement(     );
                    h.className =                ;
                    h.textContent =                                   ;
                    results.appendChild(h);
                    const ta = document.createElement(          );
                    ta.className =            ;
                    ta.style.height =        ;
                    ta.value = (data.extracted && (data.extracted.raw_text || JSON.stringify(data.extracted, null, 2))) ||   ;
                    results.appendChild(ta);
                    setStatus(                                                                     ,     );
                } else {
                    renderTables(tables);
                    const n = Object.keys(tables).length;
                    const totalRows = Object.values(tables).reduce((a, r) => a + (Array.isArray(r) ? r.length : 0), 0);
                    if (n === 0 || totalRows === 0) {
                        setStatus(                                                                             ,      );
                    } else {
                        setStatus(         + n +             + totalRows +          ,     );
                    }
                }
            } else {
                setStatus(          + (data.message ||                ),      );
                if (data.raw) console.error(             , data.raw);
            }
        } catch (e) {
            setStatus(                  + e,      );
            console.error(                           , e);
        } finally {
            buildBtn.disabled = false;
        }
    };

    window.toggleDaPin = function () {
        const w = document.getElementById(        );
        const btn = document.getElementById(          );
        const on = w.classList.toggle(        );
        btn.textContent = on ?                       :                       ;
    };
})();
}