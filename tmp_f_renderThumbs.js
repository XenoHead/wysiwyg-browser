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