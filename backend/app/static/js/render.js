/**
 * М.Видео AI — Модуль рендеринга и презентации данных (Views & Components)
 * Формирует визуальное представление результатов работы моделей и очередей.
 */

const RenderService = {
  /**
   * Отрисовка результатов извлечения одиночной карточки.
   * @param {Object} data - CardOut
   */
  renderSingleResults(data) {
    document.getElementById('empty-state').classList.add('hidden');
    document.getElementById('results-card').classList.remove('hidden');

    // 1. Категория товара
    const catBadge = document.getElementById('category-name');
    if (catBadge) {
      catBadge.innerText = data.category || 'Электроника';
    }

    // 2. Общая уверенность карточки
    const conf = Math.round((data.overall_confidence || 0) * 100);
    const confValEl = document.getElementById('confidence-value');
    if (confValEl) confValEl.innerText = `${conf}%`;

    const barEl = document.getElementById('confidence-bar');
    if (barEl) {
      barEl.style.width = `${conf}%`;
      barEl.className = 'h-2.5 rounded-full transition-all duration-500 ' +
        (conf >= 87 ? 'bg-green-500' : (conf >= 60 ? 'bg-yellow-500' : 'bg-red-500'));
    }

    // 3. Статус валидации и публикация
    const statusBadge = document.getElementById('status-badge');
    if (statusBadge) {
      if (data.needs_review) {
        statusBadge.className = 'inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-yellow-100 text-yellow-800 border border-yellow-200';
        statusBadge.innerHTML = `<i class="fa-solid fa-triangle-exclamation mr-1.5"></i> Требует проверки (HITL)`;
      } else if (data.status === 'degraded_success') {
        statusBadge.className = 'inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-blue-100 text-blue-800 border border-blue-200';
        statusBadge.innerHTML = `<i class="fa-solid fa-bolt mr-1.5"></i> Одобрено (Fast Mode)`;
      } else {
        statusBadge.className = 'inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-green-100 text-green-800 border border-green-200';
        statusBadge.innerHTML = `<i class="fa-solid fa-circle-check mr-1.5"></i> Опубликовано в каталог`;
      }
    }

    // 4. Пояснение причин модерации
    const statusDescEl = document.getElementById('status-description');
    if (statusDescEl) {
      if (data.status_description) {
        statusDescEl.innerText = data.status_description;
        statusDescEl.classList.remove('hidden');
      } else {
        statusDescEl.classList.add('hidden');
      }
    }

    // 5. Пропущенные обязательные атрибуты
    const missingTags = document.getElementById('missing-tags');
    if (missingTags) {
      if (data.missing && data.missing.length > 0) {
        missingTags.innerHTML = data.missing
          .map(m => `<span class="bg-gray-100 px-2 py-0.5 rounded text-gray-700 mr-1 font-mono text-xs">${m}</span>`)
          .join('');
      } else {
        missingTags.innerHTML = `<span class="text-green-600 font-bold text-xs"><i class="fa-solid fa-check mr-1"></i>Все обязательные поля закрыты (100%)</span>`;
      }
    }

    // 6. Таблица извлеченных характеристик
    const table = document.getElementById('attributes-table');
    table.innerHTML = '';
    const preds = data.predictions || [];
    const countEl = document.getElementById('attr-count');
    if (countEl) countEl.innerText = preds.length;

    preds.forEach(p => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-gray-50 transition border-b border-gray-100';

      const pConf = Math.round((p.confidence || 0) * 100);
      const pBadgeColor = pConf >= 87
        ? 'bg-green-100 text-green-800'
        : (pConf >= 60 ? 'bg-yellow-100 text-yellow-800' : 'bg-red-100 text-red-800');

      let consensusTag = '';
      if (p.consensus) {
        consensusTag = `<span class="inline-flex items-center text-xs font-bold text-indigo-700 bg-indigo-50 px-2.5 py-0.5 rounded-full border border-indigo-200" title="${p.confidence_reason || ''}"><i class="fa-solid fa-handshake mr-1"></i> Консенсус</span>`;
      } else if (p.status === 'valid' || p.status === 'high_confidence') {
        consensusTag = `<span class="text-xs text-green-600 font-medium" title="${p.confidence_reason || ''}"><i class="fa-solid fa-check mr-1"></i> Верифицировано</span>`;
      } else {
        consensusTag = `<span class="text-xs text-amber-600 font-medium" title="${p.confidence_reason || ''}"><i class="fa-solid fa-triangle-exclamation mr-1"></i> Требует внимания</span>`;
      }

      tr.innerHTML = `
        <td class="px-6 py-4 font-bold text-gray-900">${p.attribute}</td>
        <td class="px-6 py-4 text-gray-800 font-medium">${p.value}</td>
        <td class="px-6 py-4 text-center">
          <span class="inline-block px-2.5 py-0.5 rounded-full text-xs font-bold ${pBadgeColor}">${pConf}%</span>
        </td>
        <td class="px-6 py-4 text-gray-500 font-mono text-xs">
          <span class="bg-gray-100 px-2 py-0.5 rounded font-bold">${p.source}</span>
        </td>
        <td class="px-6 py-4">${consensusTag}</td>
      `;
      table.appendChild(tr);
    });

    // 7. JSON-представление
    const jsonViewer = document.getElementById('json-viewer');
    if (jsonViewer) {
      jsonViewer.innerText = JSON.stringify(data, null, 2);
    }
  },

  /**
   * Отрисовка сводных и табличных результатов пакетной обработки.
   * @param {Object} data - BatchOut
   */
  renderBatchResults(data) {
    const container = document.getElementById('batch-results-container');
    container.classList.remove('hidden');

    document.getElementById('batch-total-count').innerText = data.total || 0;
    
    // Агрегированные метрики пакета
    const approvedEl = document.getElementById('batch-approved-count');
    if (approvedEl) approvedEl.innerText = data.approved_count || 0;

    const reviewEl = document.getElementById('batch-review-count');
    if (reviewEl) reviewEl.innerText = data.needs_review_count || 0;

    const failedEl = document.getElementById('batch-failed-count');
    if (failedEl) failedEl.innerText = data.failed_count || 0;

    const tbody = document.getElementById('batch-table-body');
    tbody.innerHTML = '';

    (data.cards || []).forEach(c => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-gray-50 transition border-b border-gray-100';

      const conf = Math.round((c.overall_confidence || 0) * 100);
      const statusClass = c.status === 'approved'
        ? 'bg-green-100 text-green-800 border-green-200'
        : (c.status === 'failed' ? 'bg-red-100 text-red-800 border-red-200' : 'bg-yellow-100 text-yellow-800 border-yellow-200');

      tr.innerHTML = `
        <td class="px-4 py-3 font-mono text-xs font-bold">${c.external_id || '-'}</td>
        <td class="px-4 py-3 font-medium text-gray-900">${c.category || '-'}</td>
        <td class="px-4 py-3 text-center font-bold">${conf}%</td>
        <td class="px-4 py-3 text-center">
          <span class="px-2.5 py-0.5 rounded-full text-xs font-bold border ${statusClass}">${c.status}</span>
        </td>
        <td class="px-4 py-3 font-mono text-xs">${(c.predictions || []).length} полей</td>
        <td class="px-4 py-3 text-xs text-gray-500">${(c.missing || []).join(', ') || '—'}</td>
      `;
      tbody.appendChild(tr);
    });
  },

  /**
   * Отрисовка очереди карточек модерации Human-in-the-Loop.
   * @param {Array} items
   * @param {Function} onAction - callback(extId, attr, action)
   */
  renderReviewQueue(items, onAction) {
    const cont = document.getElementById('review-queue-content');

    if (!items || items.length === 0) {
      cont.innerHTML = `
        <div class="text-center py-12 text-gray-500">
          <i class="fa-solid fa-circle-check text-green-500 text-5xl mb-3"></i>
          <p class="font-bold text-gray-800 text-base">Очередь модерации пуста!</p>
          <p class="text-xs text-gray-400 mt-1">Все карточки успешно проверены и согласованы автоматическим консенсусом.</p>
        </div>
      `;
      return;
    }

    cont.innerHTML = '';
    items.forEach(item => {
      const cardEl = document.createElement('div');
      cardEl.className = 'border border-gray-200 rounded-xl p-4 hover:border-gray-300 transition space-y-3 bg-white shadow-xs';

      const conf = Math.round((item.overall_confidence || 0) * 100);
      const reasons = (item.review_reasons || []).join('; ') || 'Требуется подтверждение оператора';

      cardEl.innerHTML = `
        <div class="flex items-center justify-between">
          <div>
            <span class="font-bold text-gray-900">${item.title || item.external_id || 'Товар'}</span>
            <span class="ml-2 text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded font-mono">${item.category || ''}</span>
          </div>
          <span class="text-xs font-bold px-2.5 py-0.5 rounded-full bg-yellow-100 text-yellow-800">${conf}%</span>
        </div>
        <p class="text-xs text-red-600 font-medium"><i class="fa-solid fa-circle-exclamation mr-1"></i> Причина: ${reasons}</p>
        <div class="flex items-center justify-end space-x-2 pt-2 border-t border-gray-100">
          <button data-action="approve" data-id="${item.external_id}" class="btn-review-approve px-3 py-1 bg-green-50 text-green-700 hover:bg-green-100 rounded-lg text-xs font-bold transition">
            <i class="fa-solid fa-check mr-1"></i> Одобрить
          </button>
          <button data-action="reject" data-id="${item.external_id}" class="btn-review-reject px-3 py-1 bg-red-50 text-red-700 hover:bg-red-100 rounded-lg text-xs font-bold transition">
            <i class="fa-solid fa-xmark mr-1"></i> Отклонить
          </button>
        </div>
      `;

      // Навешивание обработчиков кнопок
      cardEl.querySelector('.btn-review-approve').addEventListener('click', () => onAction(item.external_id, 'brand', 'approve'));
      cardEl.querySelector('.btn-review-reject').addEventListener('click', () => onAction(item.external_id, 'brand', 'reject'));

      cont.appendChild(cardEl);
    });
  }
};

window.RenderService = RenderService;
