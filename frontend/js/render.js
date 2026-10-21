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
    const llmBadge = document.getElementById('llm-usage-badge');
    const hasLlm = (data.predictions || []).some(p => p.source === 'llm_fallback' || p.source === 'llm_strict' || p.source === 'llm_new_product' || p.tier === 'Tier 3');
    if (llmBadge) {
      if (hasLlm) {
        llmBadge.className = 'inline-flex items-center text-[11px] font-bold text-purple-700 bg-purple-50 px-2.5 py-1 rounded-full border border-purple-200';
        llmBadge.innerHTML = `<i class="fa-solid fa-brain mr-1.5 text-purple-600"></i> Использован LLM Fallback (Tier 3)`;
      } else {
        llmBadge.className = 'inline-flex items-center text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200';
        llmBadge.innerHTML = `<i class="fa-solid fa-bolt mr-1.5 text-emerald-600"></i> LLM не вызывалась (0 токенов, 0 ₽)`;
      }
    }

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

      // Понятное название источника
      let sourceName = p.source || '';
      if (sourceName === 'flashtext') sourceName = 'Словарь';
      else if (sourceName === 'regex') sourceName = 'Правило';
      else if (sourceName === 'gliner') sourceName = 'NER-парсер';
      else if (sourceName === 'catalog_kb') sourceName = 'База каталога';
      else if (sourceName.startsWith('llm')) sourceName = 'LLM Fallback';
      const tierPrefix = p.tier ? `${p.tier}: ` : '';

      const scoreTooltip = p.confidence_reason || (pConf >= 87 ? 'Высокая уверенность' : 'Требует проверки');
      const consensusBadge = p.consensus
        ? ' <span class="text-indigo-600 ml-1 font-bold" title="Подтверждено Tier 1 + Tier 2 (0 токенов)">✓✓</span>'
        : '';

      tr.innerHTML = `
        <td class="px-6 py-4 font-bold text-gray-900">${p.attribute}</td>
        <td class="px-6 py-4 text-gray-800 font-medium">${p.value}</td>
        <td class="px-6 py-4 text-center">
          <span class="inline-block px-2.5 py-0.5 rounded-full text-xs font-bold ${pBadgeColor}" title="${scoreTooltip}">${pConf}%</span>
        </td>
        <td class="px-6 py-4 text-gray-600 text-xs font-medium">
          <span class="inline-block px-2 py-0.5 rounded font-semibold ${p.source === 'catalog_kb' ? 'bg-purple-100 text-purple-800 border border-purple-200' : 'bg-gray-100 text-gray-700'}" title="${scoreTooltip}">${tierPrefix}${sourceName}</span>${consensusBadge}
        </td>
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
   * Отрисовка очереди карточек модерации Human-in-the-Loop с интерактивным просмотром и редактированием.
   * @param {Array} items
   * @param {Function} onAction - callback(extId, attr, action, newAttrs)
   */
  renderReviewQueue(items, onAction) {
    const cont = document.getElementById('review-queue-content');
    if (!cont) return;

    if (!items || items.length === 0) {
      cont.innerHTML = `
        <div class="text-center py-12 text-gray-500">
          <i class="fa-solid fa-circle-check text-green-500 text-5xl mb-3"></i>
          <p class="font-bold text-gray-800 text-base">Очередь модерации пуста!</p>
          <p class="text-xs text-gray-400 mt-1">Все карточки успешно проверены или подтверждены оператором.</p>
        </div>
      `;
      return;
    }

    cont.innerHTML = '';
    items.forEach((item, idx) => {
      const cardEl = document.createElement('div');
      cardEl.className = 'border border-gray-200 rounded-xl p-4 hover:border-gray-300 transition space-y-3 bg-white shadow-xs';
      cardEl.id = `queue-card-${item.external_id || idx}`;

      const conf = Math.round((item.overall_confidence || 0) * 100);
      const confBadgeClass = conf >= 87 ? 'bg-green-100 text-green-800' : (conf >= 50 ? 'bg-yellow-100 text-yellow-800' : 'bg-red-100 text-red-800');
      
      const reasonsList = [...(item.review_reasons || [])];
      if (item.missing_required && item.missing_required.length > 0) {
        reasonsList.push(`Не заполнены обязательные поля: ${item.missing_required.join(', ')}`);
      }
      const reasons = reasonsList.join('; ') || 'Требуется подтверждение оператора (низкая уверенность или сработал LLM-фоллбэк)';

      const extAttrs = item.extracted_attributes || {};
      const missingAttrs = item.missing_required || [];

      // Собираем общий словарь атрибутов
      const allAttrsMap = {};
      Object.keys(extAttrs).forEach(k => {
        allAttrsMap[k] = { value: extAttrs[k], isMissing: false };
      });
      missingAttrs.forEach(k => {
        if (!allAttrsMap[k]) {
          allAttrsMap[k] = { value: '', isMissing: true };
        }
      });

      // Метаданные из детальных предсказаний (tier, source, confidence)
      const predMeta = {};
      (item.detailed_predictions || []).forEach(p => {
        if (p.attribute) predMeta[p.attribute] = p;
      });

      let attrInputsHtml = '';
      Object.keys(allAttrsMap).forEach(attrName => {
        const attrInfo = allAttrsMap[attrName];
        const meta = predMeta[attrName] || {};
        const tierBadge = meta.tier ? `<span class="text-[10px] bg-purple-50 text-purple-700 px-1.5 py-0.5 rounded font-mono">${meta.tier}</span>` : '';
        const confBadge = meta.confidence ? `<span class="text-[10px] text-gray-400 font-mono">${Math.round(meta.confidence * 100)}%</span>` : '';
        const missingBadge = attrInfo.isMissing ? `<span class="text-[10px] bg-red-100 text-red-700 px-1.5 py-0.5 rounded font-bold">Обязательно</span>` : '';

        attrInputsHtml += `
          <div class="bg-gray-50 border border-gray-200 rounded-lg p-2.5 space-y-1.5 hover:border-gray-300 transition">
            <div class="flex items-center justify-between text-xs">
              <span class="font-bold text-gray-700 font-mono">${attrName}</span>
              <div class="flex items-center space-x-1">
                ${missingBadge}
                ${tierBadge}
                ${confBadge}
              </div>
            </div>
            <div class="flex items-center space-x-1">
              <input type="text" data-card-id="${item.external_id}" data-attr="${attrName}" value="${attrInfo.value || ''}" 
                placeholder="${attrInfo.isMissing ? 'Заполните значение...' : 'Значение'}"
                class="queue-attr-input w-full text-xs font-semibold text-gray-900 bg-white border ${attrInfo.isMissing ? 'border-red-300 focus:border-red-500' : 'border-gray-300 focus:border-blue-500'} rounded-md px-2.5 py-1.5 focus:outline-none transition" />
            </div>
          </div>
        `;
      });

      cardEl.innerHTML = `
        <!-- Заголовок карточки и статус -->
        <div class="flex items-center justify-between cursor-pointer select-none" data-action="toggle" data-id="${item.external_id}">
          <div class="flex items-center space-x-2.5">
            <i class="fa-solid fa-chevron-right text-gray-400 text-xs transition-transform transform chevron-icon" data-id="${item.external_id}"></i>
            <div>
              <span class="font-bold text-gray-900 text-sm hover:text-blue-600 transition">${item.title || item.external_id || 'Товар'}</span>
              <span class="ml-2 text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded font-mono font-medium">${item.category || 'Общая'}</span>
            </div>
          </div>
          <div class="flex items-center space-x-2">
            <span class="text-xs font-bold px-2.5 py-0.5 rounded-full ${confBadgeClass}">${conf}%</span>
            <button type="button" data-action="toggle" data-id="${item.external_id}" class="text-xs text-blue-600 hover:text-blue-800 font-semibold px-2.5 py-1 bg-blue-50 hover:bg-blue-100 rounded-lg transition flex items-center">
              <i class="fa-solid fa-pen-to-square mr-1.5"></i> <span class="btn-toggle-label" data-id="${item.external_id}">Просмотреть и изменить</span>
            </button>
          </div>
        </div>

        <!-- Причина отправки на ручную проверку -->
        <div class="flex items-center justify-between text-xs text-red-700 font-medium bg-red-50 px-3 py-1.5 rounded-lg border border-red-100">
          <span><i class="fa-solid fa-circle-exclamation mr-1.5 text-red-500"></i> ${reasons}</span>
          <span class="text-gray-400 text-[11px] font-mono">ID: ${item.external_id || 'N/A'}</span>
        </div>

        <!-- Разворачиваемая форма деталей и редактирования (по умолчанию скрыта) -->
        <div id="details-${item.external_id}" class="details-panel hidden pt-3 border-t border-gray-100 space-y-3.5">
          <!-- Исходный текст карточки -->
          <div class="bg-gray-50 border border-gray-200 rounded-lg p-3 text-xs">
            <div class="flex items-center justify-between text-gray-500 font-bold mb-1">
              <span><i class="fa-solid fa-file-lines mr-1.5 text-gray-400"></i> Исходное описание товара из каталога:</span>
              <span class="text-[11px] text-gray-400 font-normal">для сверки оператором</span>
            </div>
            <p class="text-gray-800 font-medium select-all leading-relaxed">${item.raw_text || item.description || item.title || 'Описание отсутствует'}</p>
          </div>

          <!-- Сетка характеристик -->
          <div>
            <div class="flex items-center justify-between mb-2">
              <span class="text-xs font-bold text-gray-700"><i class="fa-solid fa-sliders mr-1.5 text-blue-500"></i> Характеристики товара (можно отредактировать любое значение):</span>
              <button type="button" class="btn-add-attr text-[11px] text-blue-600 hover:text-blue-800 font-semibold px-2 py-0.5 rounded border border-blue-200 hover:bg-blue-50 transition" data-id="${item.external_id}">
                <i class="fa-solid fa-plus mr-1"></i> Добавить поле
              </button>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 attr-grid" id="attr-grid-${item.external_id}">
              ${attrInputsHtml}
            </div>
          </div>

          <!-- Нижняя панель действий -->
          <div class="flex items-center justify-between pt-3 border-t border-gray-100">
            <button type="button" data-action="toggle" data-id="${item.external_id}" class="text-xs text-gray-500 hover:text-gray-700 px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 transition">
              <i class="fa-solid fa-chevron-up mr-1"></i> Свернуть
            </button>
            <div class="flex items-center space-x-2">
              <button type="button" data-action="reject" data-id="${item.external_id}" class="btn-review-reject px-3.5 py-1.5 bg-red-50 text-red-700 hover:bg-red-100 rounded-lg text-xs font-bold transition flex items-center">
                <i class="fa-solid fa-xmark mr-1.5"></i> Отклонить
              </button>
              <button type="button" data-action="approve" data-id="${item.external_id}" class="btn-review-approve px-4 py-1.5 bg-green-600 text-white hover:bg-green-700 rounded-lg text-xs font-bold shadow-xs transition flex items-center">
                <i class="fa-solid fa-check mr-1.5"></i> Сохранить и одобрить
              </button>
            </div>
          </div>
        </div>
      `;

      // Обработчик разворачивания/сворачивания
      const toggleDetails = () => {
        const detailsEl = cardEl.querySelector(`#details-${item.external_id}`);
        const chevron = cardEl.querySelector(`.chevron-icon[data-id="${item.external_id}"]`);
        const labelEl = cardEl.querySelector(`.btn-toggle-label[data-id="${item.external_id}"]`);
        if (detailsEl) {
          const isHidden = detailsEl.classList.toggle('hidden');
          if (chevron) chevron.style.transform = isHidden ? 'rotate(0deg)' : 'rotate(90deg)';
          if (labelEl) labelEl.innerText = isHidden ? 'Просмотреть и изменить' : 'Скрыть редактор';
        }
      };

      cardEl.querySelectorAll('[data-action="toggle"]').forEach(el => {
        el.addEventListener('click', (e) => {
          e.stopPropagation();
          toggleDetails();
        });
      });

      // Обработчик кнопки добавления нового атрибута
      const addAttrBtn = cardEl.querySelector('.btn-add-attr');
      if (addAttrBtn) {
        addAttrBtn.addEventListener('click', () => {
          const attrName = prompt('Введите имя характеристики (например, volume, screen_diagonal, power):');
          if (!attrName || !attrName.trim()) return;
          const cleanName = attrName.trim().toLowerCase();
          const grid = cardEl.querySelector(`#attr-grid-${item.external_id}`);
          if (grid) {
            const newDiv = document.createElement('div');
            newDiv.className = 'bg-blue-50 border border-blue-200 rounded-lg p-2.5 space-y-1.5';
            newDiv.innerHTML = `
              <div class="flex items-center justify-between text-xs">
                <span class="font-bold text-blue-900 font-mono">${cleanName}</span>
                <span class="text-[10px] bg-blue-200 text-blue-800 px-1.5 py-0.5 rounded font-bold">Новое</span>
              </div>
              <input type="text" data-card-id="${item.external_id}" data-attr="${cleanName}" value="" placeholder="Значение..."
                class="queue-attr-input w-full text-xs font-semibold text-gray-900 bg-white border border-blue-300 focus:border-blue-500 rounded-md px-2.5 py-1.5 focus:outline-none transition" />
            `;
            grid.appendChild(newDiv);
          }
        });
      }

      // Функция сбора отредактированных атрибутов
      const collectAttributes = () => {
        const currentAttrs = {};
        cardEl.querySelectorAll(`.queue-attr-input[data-card-id="${item.external_id}"]`).forEach(inp => {
          const a = inp.getAttribute('data-attr');
          const v = inp.value.trim();
          if (a && v) {
            currentAttrs[a] = v;
          }
        });
        return currentAttrs;
      };

      // Обработчик "Сохранить и одобрить"
      cardEl.querySelector('.btn-review-approve')?.addEventListener('click', () => {
        const editedAttrs = collectAttributes();
        onAction(item.external_id, 'all', 'approve', editedAttrs);
      });

      // Обработчик "Отклонить"
      cardEl.querySelector('.btn-review-reject')?.addEventListener('click', () => {
        if (confirm(`Отклонить карточку "${item.title || item.external_id}"?`)) {
          onAction(item.external_id, 'all', 'reject', null);
        }
      });

      cont.appendChild(cardEl);
    });
  }
};

window.RenderService = RenderService;
