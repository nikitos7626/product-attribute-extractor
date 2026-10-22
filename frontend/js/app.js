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

    ['single', 'review'].forEach(t => {
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
      if (data.needs_review) {
        await updateQueueBadge();
        const countEl = document.getElementById('review-queue-badge');
        if (countEl && countEl.classList.contains('hidden')) {
          countEl.innerText = '1';
          countEl.classList.remove('hidden');
        }
      }
    } catch (err) {
      alert(`Ошибка при обработке: ${err.message}`);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles mr-2"></i><span>Извлечь характеристики</span>`;
    }
  });



  // ----------------- Действия в карте модерации одиночной карточки -----------------
  document.getElementById('single-approve-btn')?.addEventListener('click', async () => {
    if (!lastSingleResponse) return;
    const btn = document.getElementById('single-approve-btn');
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1.5"></i> Сохранение...`;

    try {
      const newAttrs = {};
      document.querySelectorAll('.single-attr-input').forEach(inp => {
        const attr = inp.getAttribute('data-single-attr');
        const val = inp.value.trim();
        if (val) newAttrs[attr] = val;
      });

      const extId = lastSingleResponse.external_id || 'card-single';
      await api.submitReviewOverride({
        external_id: extId,
        action: 'approve',
        reviewed_by: 'web-moderator',
        attributes: newAttrs,
      });

      // Обновляем статус карточки
      const statusBadge = document.getElementById('status-badge');
      if (statusBadge) {
        statusBadge.className = 'inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-green-100 text-green-800 border border-green-200';
        statusBadge.innerHTML = `<i class="fa-solid fa-circle-check mr-1.5"></i> Одобрено оператором (Каталог обновлен)`;
      }

      const successEl = document.getElementById('single-review-success');
      if (successEl) {
        successEl.classList.remove('hidden');
      }

      lastSingleResponse.needs_review = false;
      lastSingleResponse.status = 'approved_by_operator';

      // Обновляем бейдж очереди
      await updateQueueBadge();
    } catch (err) {
      alert(`Ошибка сохранения: ${err.message}`);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<i class="fa-solid fa-check mr-2"></i> Сохранить и одобрить (Опубликовать)`;
    }
  });

  document.getElementById('single-reject-btn')?.addEventListener('click', async () => {
    if (!lastSingleResponse) return;
    if (!confirm('Вы уверены, что хотите отклонить эту карточку?')) return;

    try {
      const extId = lastSingleResponse.external_id || 'card-single';
      await api.submitReviewOverride({
        external_id: extId,
        action: 'reject',
        reviewed_by: 'web-moderator',
      });

      const statusBadge = document.getElementById('status-badge');
      if (statusBadge) {
        statusBadge.className = 'inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-red-100 text-red-800 border border-red-200';
        statusBadge.innerHTML = `<i class="fa-solid fa-xmark mr-1.5"></i> Отклонено модератором`;
      }

      lastSingleResponse.needs_review = false;
      lastSingleResponse.status = 'rejected';
      await updateQueueBadge();
    } catch (err) {
      alert(`Ошибка при отклонении: ${err.message}`);
    }
  });

  document.getElementById('single-open-queue-btn')?.addEventListener('click', () => {
    const queueTabBtn = document.getElementById('tab-queue');
    if (queueTabBtn) {
      queueTabBtn.click();
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
      const data = await api.getReviewQueue(5);
      let items = [...(data.items || [])];

      // Клиентская синхронизация: гарантируем, что сомнительная одиночная карточка видна в очереди
      if (lastSingleResponse && lastSingleResponse.needs_review) {
        const extId = lastSingleResponse.external_id || 'card-single';
        const alreadyInQueue = items.some(it => String(it.external_id) === String(extId));
        if (!alreadyInQueue) {
          const flatAttrs = {};
          (lastSingleResponse.predictions || []).forEach(p => {
            if (p.attribute) flatAttrs[p.attribute] = p.value;
          });
          const rawTextEl = document.getElementById('raw_text');
          const title = (rawTextEl ? rawTextEl.value.trim() : '') || extId;
          const localItem = {
            external_id: extId,
            title: title,
            category: lastSingleResponse.category || 'Электроника',
            overall_confidence: lastSingleResponse.overall_confidence || 0.5,
            needs_review: true,
            status: 'needs_review',
            status_description: lastSingleResponse.status_description || '',
            review_reasons: lastSingleResponse.review_reasons || [],
            missing_required: lastSingleResponse.missing || [],
            extracted_attributes: flatAttrs,
            detailed_predictions: lastSingleResponse.predictions || [],
          };
          items.unshift(localItem);
        }
      }

      render.renderReviewQueue(items, handleReviewAction);
      const totalCount = Math.max(data.total_in_queue || 0, items.length);
      const countEl = document.getElementById('review-queue-badge');
      if (countEl) {
        if (totalCount > 0) {
          countEl.innerText = totalCount;
          countEl.classList.remove('hidden');
        } else {
          countEl.innerText = '0';
          countEl.classList.add('hidden');
        }
      }
    } catch (err) {
      if (cont) {
        cont.innerHTML = `<p class="text-sm text-red-500 text-center py-8">Ошибка: ${err.message}</p>`;
      }
    }
  }

  async function handleReviewAction(extId, attr, action, newAttrs) {
    try {
      const payload = {
        external_id: extId,
        action: action,
        reviewed_by: 'web-moderator',
      };
      if (newAttrs) {
        payload.attributes = newAttrs;
      }
      if (attr && attr !== 'all') {
        payload.attribute = attr;
      }

      const res = await api.submitReviewOverride(payload);

      // Анимация успешного удаления карточки из очереди
      const cardEl = document.getElementById(`queue-card-${extId}`);
      if (cardEl) {
        cardEl.style.transition = 'all 0.35s ease';
        cardEl.style.opacity = '0';
        cardEl.style.transform = 'translateX(25px)';
        setTimeout(() => {
          cardEl.remove();
          const cont = document.getElementById('review-queue-content');
          if (cont && cont.children.length === 0) {
            loadReviewQueue();
          }
        }, 350);
      } else {
        loadReviewQueue();
      }

      // Автоматическое удаление повторяющихся дубликатов из очереди
      if (res && res.auto_resolved_duplicates && res.auto_resolved_duplicates.length > 0) {
        res.auto_resolved_duplicates.forEach(dupId => {
          const dupEl = document.getElementById(`queue-card-${dupId}`);
          if (dupEl) {
            dupEl.style.transition = 'all 0.35s ease';
            dupEl.style.opacity = '0';
            dupEl.style.transform = 'translateX(25px)';
            setTimeout(() => dupEl.remove(), 350);
          }
        });
        alert(`Карточка одобрена и добавлена в базу знаний (Catalog KB)!
Автоматически закрыто повторяющихся карточек: ${res.auto_resolved_duplicates.length}`);
      }

      // Обновляем бейдж счетчика из сервера
      await updateQueueBadge();
    } catch (err) {
      alert(`Ошибка сохранения решения: ${err.message}`);
    }
  }

  document.getElementById('refresh-review-btn')?.addEventListener('click', loadReviewQueue);

  document.getElementById('clear-review-btn')?.addEventListener('click', async () => {
    if (!confirm('Вы уверены, что хотите очистить очередь модерации? Все неразрешенные карточки будут помечены как проверенные.')) {
      return;
    }
    const cont = document.getElementById('review-queue-content');
    if (cont) {
      cont.innerHTML = `<p class="text-sm text-gray-400 text-center py-8"><i class="fa-solid fa-spinner fa-spin mr-2"></i> Очистка очереди...</p>`;
    }
    try {
      const res = await api.clearReviewQueue();
      alert(`Очередь модерации успешно очищена! Обработано карточек: ${res.cleared_count || 0}`);
      await loadReviewQueue();
    } catch (err) {
      alert(`Ошибка при очистке очереди: ${err.message}`);
      await loadReviewQueue();
    }
  });

  // ----------------- Синхронизация бейджа очереди -----------------
  async function updateQueueBadge() {
    try {
      const data = await api.getReviewQueue(1);
      const countEl = document.getElementById('review-queue-badge');
      if (countEl) {
        if (data.total_in_queue > 0) {
          countEl.innerText = data.total_in_queue;
          countEl.classList.remove('hidden');
        } else {
          countEl.innerText = '0';
          countEl.classList.add('hidden');
        }
      }
    } catch (_) {}
  }

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
  updateQueueBadge();
});
