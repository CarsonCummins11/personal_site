const md = document.getElementById('md');
const preview = document.getElementById('preview');

document.getElementById('date').value = new Date().toISOString().slice(0, 10);

document.getElementById('slug').addEventListener('input', e => {
  document.getElementById('slug-preview').textContent = e.target.value || '…';
});

md.addEventListener('input', updatePreview);

// Image management
const imageFiles = new Map();
const imageObjectURLs = new Map();

document.getElementById('add-images-btn').addEventListener('click', () => {
  document.getElementById('image-input').click();
});

document.getElementById('image-input').addEventListener('change', e => {
  for (const file of e.target.files) {
    if (imageObjectURLs.has(file.name)) URL.revokeObjectURL(imageObjectURLs.get(file.name));
    imageFiles.set(file.name, file);
    imageObjectURLs.set(file.name, URL.createObjectURL(file));
  }
  renderImageList();
  updatePreview();
  e.target.value = '';
});

function escHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderImageList() {
  const list = document.getElementById('image-list');
  list.innerHTML = '';
  for (const [name] of imageFiles) {
    const url = imageObjectURLs.get(name);
    const div = document.createElement('div');
    div.className = 'image-item';
    div.innerHTML =
      '<img src="' + url + '" class="image-thumb" alt="">' +
      '<span class="image-name">' + escHtml(name) + '</span>' +
      '<div class="image-actions">' +
        '<button type="button" class="img-btn insert" data-name="' + escHtml(name) + '">Insert</button>' +
        '<button type="button" class="img-btn remove" data-name="' + escHtml(name) + '">×</button>' +
      '</div>';
    list.appendChild(div);
  }
  list.querySelectorAll('.img-btn.insert').forEach(btn => {
    btn.addEventListener('click', () => insertImage(btn.dataset.name));
  });
  list.querySelectorAll('.img-btn.remove').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.dataset.name;
      URL.revokeObjectURL(imageObjectURLs.get(name));
      imageObjectURLs.delete(name);
      imageFiles.delete(name);
      renderImageList();
      updatePreview();
    });
  });
}

function updatePreview() {
  const tmp = document.createElement('div');
  tmp.innerHTML = marked.parse(md.value);
  tmp.querySelectorAll('img').forEach(img => {
    const src = img.getAttribute('src');
    if (imageObjectURLs.has(src)) img.src = imageObjectURLs.get(src);
    else if (existingImages.has(src)) img.src = existingImages.get(src);
  });
  preview.innerHTML = tmp.innerHTML;
}

function insertImage(name) {
  const ta = document.getElementById('md');
  const start = ta.selectionStart;
  const end = ta.selectionEnd;
  const alt = name.replace(/\.[^.]+$/, '');
  const snippet = '![' + alt + '](' + name + ')';
  ta.value = ta.value.slice(0, start) + snippet + ta.value.slice(end);
  ta.dispatchEvent(new Event('input'));
  ta.focus();
  ta.selectionStart = ta.selectionEnd = start + snippet.length;
}

// Edit-mode management — existingImages maps filename → raw GitHub URL
const existingImages = new Map();

function renderExistingImages() {
  const section = document.getElementById('existing-img-section');
  const list = document.getElementById('existing-img-list');
  list.innerHTML = '';
  if (existingImages.size === 0) { section.style.display = 'none'; return; }
  section.style.display = '';
  for (const [name, url] of existingImages) {
    const div = document.createElement('div');
    div.className = 'image-item';
    div.innerHTML =
      '<img src="' + escHtml(url) + '" class="image-thumb" alt="">' +
      '<span class="image-name">' + escHtml(name) + '</span>' +
      '<div class="image-actions">' +
        '<button type="button" class="img-btn insert" data-name="' + escHtml(name) + '">Insert</button>' +
      '</div>';
    list.appendChild(div);
  }
  list.querySelectorAll('.img-btn.insert').forEach(btn => {
    btn.addEventListener('click', () => insertImage(btn.dataset.name));
  });
}

function setNewMode() {
  document.getElementById('edit-mode').value = '';
  document.getElementById('submit-btn').textContent = 'Publish';
  document.getElementById('slug').readOnly = false;
  existingImages.clear();
  renderExistingImages();
}

// Populate post dropdown on page load
(async () => {
  try {
    const resp = await fetch(window.location.pathname + '?action=list');
    if (!resp.ok) return;
    const posts = await resp.json();
    const sel = document.getElementById('post-select');
    posts.slice().reverse().forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.folder;
      opt.textContent = p.title;
      sel.appendChild(opt);
    });
  } catch (e) {}
})();

document.getElementById('post-select').addEventListener('change', e => {
  const slug = e.target.value;
  document.getElementById('load-btn').disabled = !slug;
  if (!slug) {
    document.getElementById('post-form').reset();
    document.getElementById('date').value = new Date().toISOString().slice(0, 10);
    preview.innerHTML = '';
    document.getElementById('slug-preview').textContent = '…';
    imageObjectURLs.forEach(url => URL.revokeObjectURL(url));
    imageObjectURLs.clear();
    imageFiles.clear();
    renderImageList();
    setNewMode();
  }
});

document.getElementById('load-btn').addEventListener('click', async () => {
  const slug = document.getElementById('post-select').value;
  if (!slug) return;
  const btn = document.getElementById('load-btn');
  btn.textContent = 'Loading…';
  btn.disabled = true;
  try {
    const resp = await fetch(window.location.pathname + '?action=load&slug=' + encodeURIComponent(slug));
    if (!resp.ok) { alert('Failed to load: ' + await resp.text()); return; }
    const data = await resp.json();
    document.getElementById('title').value = data.title || '';
    document.getElementById('slug').value = slug;
    document.getElementById('slug-preview').textContent = slug;
    if (data.date) {
      const parts = data.date.split('/');
      document.getElementById('date').value = parts[2] + '-' + parts[0].padStart(2, '0') + '-' + parts[1].padStart(2, '0');
    }
    md.value = data.markdown || '';
    existingImages.clear();
    (data.images || []).forEach(img => existingImages.set(img.name, img.url));
    renderExistingImages();
    updatePreview();
    document.getElementById('edit-mode').value = 'true';
    document.getElementById('submit-btn').textContent = 'Update';
    document.getElementById('slug').readOnly = true;
  } catch (err) {
    alert('Error loading post: ' + err.message);
  } finally {
    btn.textContent = 'Load';
    btn.disabled = false;
  }
});

document.getElementById('post-form').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = document.getElementById('submit-btn');
  const status = document.getElementById('status');
  const isEdit = document.getElementById('edit-mode').value === 'true';
  btn.disabled = true;
  status.className = 'status';
  status.textContent = isEdit ? 'Updating…' : 'Publishing…';

  const form = new FormData(e.target);
  const raw = form.get('date');
  const [y, m, day] = raw.split('-');
  form.set('date', m + '/' + day + '/' + y);

  for (const [name, file] of imageFiles) {
    form.append('images', file, name);
  }

  try {
    const resp = await fetch(window.location.pathname, {
      method: 'POST',
      body: form,
    });
    const text = await resp.text();
    if (resp.ok) {
      status.className = 'status ok';
      status.textContent = text;
      e.target.reset();
      document.getElementById('date').value = new Date().toISOString().slice(0, 10);
      preview.innerHTML = '';
      document.getElementById('slug-preview').textContent = '…';
      imageObjectURLs.forEach(url => URL.revokeObjectURL(url));
      imageObjectURLs.clear();
      imageFiles.clear();
      renderImageList();
      document.getElementById('load-btn').disabled = true;
      setNewMode();
    } else {
      status.className = 'status error';
      status.textContent = 'Error: ' + text;
    }
  } catch (err) {
    status.className = 'status error';
    status.textContent = 'Network error: ' + err.message;
  } finally {
    btn.disabled = false;
  }
});
