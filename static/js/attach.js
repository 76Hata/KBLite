// attach.js — ファイル添付（チャット用）・クリップボードペースト

function triggerAttach() {
  document.getElementById('attachInput').click();
}

async function _addFile(file) {
  if (_attachments.length >= _ATTACH_MAX_FILES) {
    showToast('添付は最大' + _ATTACH_MAX_FILES + 'ファイルまでです');
    return;
  }
  const isImage = _IMAGE_TYPES.has(file.type);
  const isPdf = file.name.toLowerCase().endsWith('.pdf') || file.type === 'application/pdf';
  const maxSize = (isImage || isPdf) ? _ATTACH_MAX_SIZE_IMAGE : _ATTACH_MAX_SIZE_TEXT;
  const label  = '10MB';
  if (file.size > maxSize) {
    showToast(file.name + ' は' + label + '超のためスキップ');
    return;
  }
  try {
    if (isImage) {
      const content = await readFileAsDataURL(file);
      _attachments.push({ name: file.name, content, type: 'image' });
    } else if (isPdf) {
      const content = await readFileAsDataURL(file);
      _attachments.push({ name: file.name, content, type: 'pdf' });
    } else {
      const content = await readFileAsText(file);
      _attachments.push({ name: file.name, content, type: 'text' });
    }
  } catch (e) {
    showToast(file.name + ' の読み込みに失敗しました');
  }
}

function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file, 'UTF-8');
  });
}

function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function renderAttachChips() {
  const area = document.getElementById('attachArea');
  if (_attachments.length === 0) {
    area.classList.remove('visible');
    area.innerHTML = '';
    return;
  }
  area.classList.add('visible');
  let html = '';
  _attachments.forEach((att, i) => {
    if (att.type === 'image') {
      html += '<span class="attach-chip">' +
        '<img src="' + att.content + '" style="width:40px;height:40px;object-fit:cover;border-radius:3px;flex-shrink:0;" title="' + esc(att.name) + '">' +
        '<span class="attach-chip-name" title="' + esc(att.name) + '">' + esc(att.name) + '</span>' +
        '<button class="attach-chip-remove" onclick="removeAttach(' + i + ')" title="削除">&times;</button>' +
        '</span>';
    } else if (att.type === 'pdf') {
      html += '<span class="attach-chip">' +
        '<span style="font-size:18px;margin-right:4px">&#128196;</span>' +
        '<span class="attach-chip-name" title="' + esc(att.name) + '">' + esc(att.name) + '</span>' +
        '<button class="attach-chip-remove" onclick="removeAttach(' + i + ')" title="削除">&times;</button>' +
        '</span>';
    } else {
      html += '<span class="attach-chip">' +
        '<span class="attach-chip-name" title="' + esc(att.name) + '">' + esc(att.name) + '</span>' +
        '<button class="attach-chip-remove" onclick="removeAttach(' + i + ')" title="削除">&times;</button>' +
        '</span>';
    }
  });
  area.innerHTML = html;
}

function removeAttach(index) {
  _attachments.splice(index, 1);
  renderAttachChips();
}

function clearAttachments() {
  _attachments = [];
  renderAttachChips();
}

// ── attachInput イベントリスナー ──────────────────────
document.getElementById('attachInput').addEventListener('change', async function() {
  const files = this.files;
  if (!files || files.length === 0) return;
  for (const file of files) await _addFile(file);
  renderAttachChips();
  this.value = '';
});

// クリップボードからのペースト（スクリーンショット対応）
document.getElementById('messageInput').addEventListener('paste', async function(e) {
  const items = e.clipboardData && e.clipboardData.items;
  if (!items) return;
  let hasImage = false;
  for (const item of items) {
    if (_IMAGE_TYPES.has(item.type)) {
      hasImage = true;
      const file = item.getAsFile();
      if (!file) continue;
      const name = 'screenshot_' + Date.now() + '.png';
      const namedFile = new File([file], name, { type: file.type });
      await _addFile(namedFile);
    }
  }
  if (hasImage) renderAttachChips();
});
