const API_URL = 'https://api-extract.vanwtoanf.io.vn';

const VN_CENTER = [16.4, 107.6];
const VN_ZOOM   = 6;
const AUTOSAVE_DELAY = 8000; // ms after last keystroke

const ERROR_LABELS = {
  address_not_found: 'Không tìm thấy địa chỉ trong nội dung đơn hàng.',
  geocode_failed:    'Không xác định được tọa độ — địa chỉ thiếu tỉnh/thành phố hoặc không tồn tại.',
  input_too_long:    'Nội dung quá dài — tối đa 5.000 ký tự.',
};

const FIELDS = ['f-name', 'f-phone', 'f-note', 'f-street', 'f-ward', 'f-province'];

let leafletMap    = null;
let leafletMarker = null;
let rawVisible    = false;

let apiValues       = {};   // what API returned (never changes per session)
let lastApiResponse = null;
let hasParsed       = false;

let feedbackTimer   = null;
let feedbackSaved   = false; // true after first auto-save; reset when new parse happens

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initMap();

  document.getElementById('parse-btn').addEventListener('click', handleParse);
  document.getElementById('clear-btn').addEventListener('click', handleClear);
  document.getElementById('toggle-raw').addEventListener('click', toggleRaw);

  document.getElementById('input-text').addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') handleParse();
  });

  FIELDS.forEach(id => {
    document.getElementById(id)?.addEventListener('input', onFieldEdit);
  });
});

function initMap() {
  leafletMap = L.map('map', { zoomControl: true }).setView(VN_CENTER, VN_ZOOM);
  L.tileLayer('https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://openstreetmap.org" target="_blank">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(leafletMap);
}

// ── Parse ─────────────────────────────────────────────────────────────────────

async function handleParse() {
  const text = document.getElementById('input-text').value.trim();
  if (!text) return;

  setLoading(true);
  hideError();

  try {
    const res  = await fetch(`${API_URL}/parse-text`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ text }),
    });
    const data = await res.json();

    if (!res.ok) {
      showError(ERROR_LABELS[data.detail] || `Lỗi từ server: ${data.detail ?? res.status}`);
      clearFields();
      resetMap();
      return;
    }

    fillResults(data);

  } catch {
    showError('Không thể kết nối đến server. Kiểm tra lại kết nối mạng.');
  } finally {
    setLoading(false);
  }
}

function handleClear() {
  clearTimeout(feedbackTimer);
  document.getElementById('input-text').value = '';
  hideError();
  clearFields();
  resetMap();
  document.getElementById('result-tag').classList.add('hidden');
  document.getElementById('raw-address-box').classList.add('hidden');
  rawVisible = false;
  document.getElementById('toggle-arrow').textContent = '▼';
  document.getElementById('toggle-label').textContent  = 'Xem địa chỉ gốc (chưa chuẩn hóa)';
  hasParsed = false;
  lastApiResponse = null;
  apiValues = {};
}

// ── Fill ──────────────────────────────────────────────────────────────────────

function fillResults(data) {
  clearTimeout(feedbackTimer);
  lastApiResponse = data;
  hasParsed       = true;
  feedbackSaved   = false;

  const info       = data.address_info ?? {};
  const streetLine = [info.address_number, info.street].filter(Boolean).join(' ');

  apiValues = {
    'f-name':     data.recipient_name ?? '',
    'f-phone':    data.phone_number   ?? '',
    'f-note':     data.note           ?? '',
    'f-street':   streetLine,
    'f-ward':     info.municipality   ?? '',
    'f-province': info.sub_region     ?? '',
  };

  Object.entries(apiValues).forEach(([id, val]) => setField(id, val || null));

  document.getElementById('raw-address-text').textContent = data.address_raw ?? '—';
  rawVisible = false;
  document.getElementById('raw-address-box').classList.add('hidden');
  document.getElementById('toggle-arrow').textContent = '▼';
  document.getElementById('toggle-label').textContent  = 'Xem địa chỉ gốc (chưa chuẩn hóa)';
  document.getElementById('result-tag').classList.remove('hidden');
  document.getElementById('feedback-saved').classList.add('hidden');

  if (data.lat != null && data.lng != null) {
    zoomToLocation(data.lat, data.lng, data);
  } else {
    resetMap();
  }
}

function setField(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  el.value = value ?? '';
  el.classList.toggle('filled',   !!value);
  el.classList.toggle('missing',  !value);
  el.classList.remove('modified');
}

function clearFields() {
  FIELDS.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.value = '';
    el.classList.remove('filled', 'missing', 'modified');
  });
  document.getElementById('feedback-saved').classList.add('hidden');
  apiValues = {};
}

// ── Auto-save feedback ────────────────────────────────────────────────────────

function onFieldEdit() {
  if (!hasParsed) return;

  // Highlight modified vs original
  FIELDS.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const changed = el.value.trim() !== (apiValues[id] ?? '').trim();
    el.classList.toggle('modified', changed);
    el.classList.toggle('filled',   !changed && !!el.value);
  });

  // Debounce auto-save — reset on each new keystroke
  clearTimeout(feedbackTimer);
  feedbackTimer = setTimeout(autoSaveFeedback, AUTOSAVE_DELAY);
}

async function autoSaveFeedback() {
  if (!hasParsed) return;

  const corrections = {};
  FIELDS.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const corrected = el.value.trim();
    const original  = (apiValues[id] ?? '').trim();
    if (corrected !== original) {
      corrections[id] = { original, corrected };
    }
  });

  if (Object.keys(corrections).length === 0) return;

  try {
    await fetch(`${API_URL}/feedback`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        input_text:   document.getElementById('input-text').value,
        api_response: lastApiResponse,
        corrections,
      }),
    });
    feedbackSaved = true;
    flashSaved();
  } catch {
    // silently ignore — don't disrupt user
  }
}

function flashSaved() {
  const el = document.getElementById('feedback-saved');
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 2500);
}

// ── Map ───────────────────────────────────────────────────────────────────────

function zoomToLocation(lat, lng, data) {
  if (leafletMarker) leafletMarker.remove();

  const info  = data.address_info ?? {};
  const name  = data.recipient_name ?? 'Người nhận';
  const phone = data.phone_number ? `<br><small>📞 ${data.phone_number}</small>` : '';
  const addr  = [
    [info.address_number, info.street].filter(Boolean).join(' '),
    info.municipality,
    info.sub_region,
  ].filter(Boolean).join(', ');

  leafletMarker = L.marker([lat, lng])
    .addTo(leafletMap)
    .bindPopup(`<b>${name}</b>${phone}${addr ? `<br><small>📍 ${addr}</small>` : ''}`, { maxWidth: 240 })
    .openPopup();

  leafletMap.setView([lat, lng], 15);

  const coordsText = document.getElementById('coords-text');
  coordsText.textContent = `📍 ${lat.toFixed(6)}° N,  ${lng.toFixed(6)}° E`;
  coordsText.classList.remove('coords-empty');

  const link = document.getElementById('maps-link');
  link.href = `https://www.google.com/maps?q=${lat},${lng}`;
  link.classList.remove('hidden');
}

function resetMap() {
  if (leafletMarker) { leafletMarker.remove(); leafletMarker = null; }
  leafletMap.setView(VN_CENTER, VN_ZOOM);

  const coordsText = document.getElementById('coords-text');
  coordsText.textContent = 'Chưa có tọa độ';
  coordsText.classList.add('coords-empty');
  document.getElementById('maps-link').classList.add('hidden');
}

// ── Raw address toggle ────────────────────────────────────────────────────────

function toggleRaw() {
  rawVisible = !rawVisible;
  document.getElementById('raw-address-box').classList.toggle('hidden', !rawVisible);
  document.getElementById('toggle-arrow').textContent = rawVisible ? '▲' : '▼';
  document.getElementById('toggle-label').textContent = rawVisible
    ? 'Ẩn địa chỉ gốc'
    : 'Xem địa chỉ gốc (chưa chuẩn hóa)';
}

// ── UI helpers ────────────────────────────────────────────────────────────────

function setLoading(on) {
  const btn = document.getElementById('parse-btn');
  btn.disabled = on;
  document.getElementById('btn-label').textContent = on ? 'Đang xử lý...' : 'Phân tích đơn';
  document.getElementById('btn-icon').style.opacity = on ? '0.4' : '1';
  btn.classList.toggle('loading', on);
}

function showError(msg) {
  document.getElementById('error-text').textContent = msg;
  document.getElementById('error-banner').classList.remove('hidden');
}

function hideError() {
  document.getElementById('error-banner').classList.add('hidden');
}
