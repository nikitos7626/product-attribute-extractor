/**
 * М.Видео AI — Главный контроллер пользовательского интерфейса (App Controller)
 * Инициализирует обработчики событий, управляет жизненным циклом и маршрутизацией вкладок.
 */

document.addEventListener('DOMContentLoaded', () => {
  let selectedBatchFile = null;
  let lastSingleResponse = null;

  // Инициализация сервисов
  const api = window.apiService;
  const render = window.RenderService;
  const presets = window.PRESETS || {};

  // ----------------- Переключение вкладок -----------------
  function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    const targetTab = document.getElementById(`tab-${tabId}`);
    if (targetTab) targetTab.classList.remove('hidden');

    ['single', 'batch', 'review'].forEach(t => {
      const btn = document.getElementById(`tab-btn-${t}`);
      if (!btn) return;
      if (t === tabId) {
        btn.className = 'px-4 py-2 rounded-lg bg-white shadow-sm text-gray-900 transition flex items-center space-x-2';
      } else {
        btn.className = 'px-4 py-2 rounded-lg text-gray-600 hover:text-gray-900 transition flex items-center space-x-2';
      }
    });

    if (tabId === 'review') {
      loadReviewQueue();
    }
  }

  // Навешиваем слушатели на кнопки переключения вкладок
  document.getElementById('tab-btn-single')?.addEventListener('click', () => switchTab('single'));
  document.getElementById('tab-btn-batch')?.addEventListener('click', () => switchTab('batch'));
  document.getElementById('tab-btn-review')?.addEventListener('click', () => switchTab('review'));

  // ----------------- Быстрые пресеты -----------------
  document.querySelectorAll('[data-preset]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const key = e.currentTarget.getAttribute('data-preset');
      const text = presets[key];
      const inputEl = document.getElementById('raw_text');
      if (inputEl && text) {
        inputEl.value = text;
        inputEl.focus();
      }
    });
  });

  // ----------------- Одиночное извлечение -----------------
  const singleForm = document.getElementById('single-form');
  singleForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('submit-btn');
    const rawTextEl = document.getElementById('raw_text');
    const rawText = rawTextEl ? rawTextEl.value.trim() : '';

    if (!rawText) return;

    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin mr-2"></i><span>Извлечение характеристик...</span>`;

    try {
      const data = await api.extractSingle({ raw_text: rawText });
      lastSingleResponse = data;
      render.renderSingleResults(data);
    } catch (err) {
      alert(`Ошибка при обработке: ${err.message}`);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles mr-2"></i><span>Извлечь характеристики</span>`;
    }
  });

  // Копирование JSON
  document.getElementById('copy-json-btn')?.addEventListener('click', () => {
    if (!lastSingleResponse) return;
    navigator.clipboard.writeText(JSON.stringify(lastSingleResponse, null, 2));
    alert('JSON-ответ успешно скопирован в буфер обмена!');
  });

  // ----------------- Пакетная обработка -----------------
  const fileInput = document.getElementById('batch-file-input');
  const dropZone = document.getElementById('drop-zone');

  function updateSelectedFile(file) {
    if (!file) return;
    selectedBatchFile = file;
    const label = document.getElementById('file-name-label');
    if (label) {
      label.innerText = `Выбран файл: ${file.name} (${Math.round(file.size / 1024)} КБ)`;
    }
    const processBtn = document.getElementById('batch-process-btn');
    if (processBtn) processBtn.disabled = false;

    const expJsonBtn = document.getElementById('batch-export-json-btn');
    if (expJsonBtn) expJsonBtn.disabled = false;

    const expCsvBtn = document.getElementById('batch-export-csv-btn');
    if (expCsvBtn) expCsvBtn.disabled = false;
  }

  fileInput?.addEventListener('change', (e) => {
    updateSelectedFile(e.target.files[0]);
  });

  // Drag & Drop
  if (dropZone) {
    ['dragenter', 'dragover'].forEach(eventName => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
      });
    });

    ['dragleave', 'drop'].forEach(eventName => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
      });
    });

    dropZone.addEventListener('drop', (e) => {
      const files = e.dataTransfer.files;
      if (files && files.length > 0) {
        updateSelectedFile(files[0]);
      }
    });
  }

  // Запуск пакетной обработки
  document.getElementById('batch-process-btn')?.addEventListener('click', async () => {
    if (!selectedBatchFile) return;
    const btn = document.getElementById('batch-process-btn');
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin mr-2"></i><span>Обработка пакета...</span>`;

    try {
      const data = await api.extractBatch(selectedBatchFile);
      render.renderBatchResults(data);
    } catch (err) {
      alert(`Ошибка при пакетной обработке: ${err.message}`);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<i class="fa-solid fa-play mr-2"></i><span>Запустить пакетную обработку</span>`;
    }
  });

  // Экспорт пакета
  async function triggerExport(fmt) {
    if (!selectedBatchFile) return;
    try {
      const blob = await api.exportBatch(selectedBatchFile, fmt);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `predictions.${fmt}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      alert(`Ошибка при экспорте: ${err.message}`);
    }
  }

  document.getElementById('batch-export-json-btn')?.addEventListener('click', () => triggerExport('json'));
  document.getElementById('batch-export-csv-btn')?.addEventListener('click', () => triggerExport('csv'));

  // ----------------- Очередь модерации (HITL) -----------------
  async function loadReviewQueue() {
    const cont = document.getElementById('review-queue-content');
    if (cont) {
      cont.innerHTML = `<p class="text-sm text-gray-400 text-center py-8"><i class="fa-solid fa-spinner fa-spin mr-2"></i> Загрузка очереди...</p>`;
    }

    try {
      const data = await api.getReviewQueue(25);
      render.renderReviewQueue(data.items || [], handleReviewAction);
    } catch (err) {
      if (cont) {
        cont.innerHTML = `<p class="text-sm text-red-500 text-center py-8">Ошибка: ${err.message}</p>`;
      }
    }
  }

  async function handleReviewAction(extId, attr, action) {
    try {
      await api.submitReviewOverride({
        external_id: extId,
        attribute: attr,
        override_value: action === 'approve' ? 'Confirmed by operator' : 'Rejected by operator',
        action: action,
        reviewed_by: 'web-moderator',
      });
      alert(`Решение (${action}) успешно сохранено!`);
      loadReviewQueue();
    } catch (err) {
      alert(`Ошибка сохранения: ${err.message}`);
    }
  }

  document.getElementById('refresh-review-btn')?.addEventListener('click', loadReviewQueue);

  // ----------------- Проверка статуса сервера -----------------
  async function pollServerHealth() {
    const statusEl = document.getElementById('api-status');
    if (!statusEl) return;
    const health = await api.checkHealth();
    if (health.ok) {
      statusEl.className = 'flex items-center text-xs text-green-700 bg-green-50 px-2.5 py-1 rounded-full border border-green-200';
      statusEl.innerHTML = `<span class="w-2 h-2 rounded-full bg-green-500 mr-1.5 status-dot-pulse"></span>Сервер онлайн`;
    } else {
      statusEl.className = 'flex items-center text-xs text-red-700 bg-red-50 px-2.5 py-1 rounded-full border border-red-200';
      statusEl.innerHTML = `<span class="w-2 h-2 rounded-full bg-red-500 mr-1.5"></span>Сервер оффлайн`;
    }
  }

  pollServerHealth();
});
