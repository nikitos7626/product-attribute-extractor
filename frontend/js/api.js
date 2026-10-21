/**
 * М.Видео AI — Модуль взаимодействия с Backend API
 * Инкапсулирует сетевые вызовы к REST-эндпоинтам сервиса.
 */

class ApiService {
  constructor(baseUrl = '') {
    if (!baseUrl && typeof window !== 'undefined' && window.location.protocol === 'file:') {
      this.baseUrl = 'http://localhost:8000';
    } else {
      this.baseUrl = baseUrl;
    }
  }

  /**
   * Извлечение характеристик для одиночной карточки товара.
   * @param {Object} cardData - { title, description, raw_text, category, seller_attributes }
   * @returns {Promise<Object>} CardOut результат извлечения
   */
  async extractSingle(cardData) {
    const response = await fetch(`${this.baseUrl}/api/extract`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify(cardData),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Ошибка сервера (${response.status}): ${errorText}`);
    }

    return await response.json();
  }

  /**
   * Пакетная обработка файла CSV/JSON со списком карточек.
   * @param {File} file
   * @returns {Promise<Object>} BatchOut
   */
  async extractBatch(file) {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${this.baseUrl}/api/extract/batch`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Ошибка пакетной обработки (${response.status}): ${errorText}`);
    }

    return await response.json();
  }

  /**
   * Экспорт стандартизированных предсказаний в CSV или JSON.
   * @param {File} file
   * @param {'json'|'csv'} format
   * @returns {Promise<Blob>}
   */
  async exportBatch(file, format = 'json') {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${this.baseUrl}/api/extract/export?output_format=${format}`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Ошибка экспорта (${response.status}): ${response.statusText}`);
    }

    return await response.blob();
  }

  /**
   * Загрузка очереди карточек для ручной проверки Human-in-the-Loop.
   * @param {number} limit
   * @returns {Promise<Object>} ReviewQueueResponse
   */
  async getReviewQueue(limit = 25) {
    const response = await fetch(`${this.baseUrl}/api/extract/review-queue?limit=${limit}`);
    if (!response.ok) {
      throw new Error(`Не удалось загрузить очередь модерации (${response.status})`);
    }
    return await response.json();
  }

  /**
   * Очистка всей очереди ручной модерации.
   * @returns {Promise<Object>}
   */
  async clearReviewQueue() {
    const response = await fetch(`${this.baseUrl}/api/extract/review-queue/clear`, {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error(`Не удалось очистить очередь (${response.status})`);
    }
    return await response.json();
  }

  /**
   * Отправка решения оператора модерации.
   * @param {Object} overrideData - { external_id, attribute, override_value, action, reviewed_by }
   * @returns {Promise<Object>}
   */
  async submitReviewOverride(overrideData) {
    const response = await fetch(`${this.baseUrl}/api/extract/review-override`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(overrideData),
    });

    if (!response.ok) {
      throw new Error(`Не удалось сохранить решение (${response.status})`);
    }

    return await response.json();
  }

  /**
   * Проверка состояния здоровья сервиса (Health Check).
   * @returns {Promise<Object>}
   */
  async checkHealth() {
    try {
      const response = await fetch(`${this.baseUrl}/health`);
      if (response.ok) {
        return await response.json();
      }
      return { ok: false };
    } catch {
      return { ok: false };
    }
  }

  /**
   * Получение таксономии каталога и поддерживаемых категорий.
   * @returns {Promise<Object>}
   */
  async getTaxonomy() {
    const response = await fetch(`${this.baseUrl}/api/extract/taxonomy`);
    if (!response.ok) {
      throw new Error(`Не удалось загрузить таксономию (${response.status})`);
    }
    return await response.json();
  }

  /**
   * Получение эталонного отчета качества per-attribute.
   * @returns {Promise<Object>}
   */
  async getMetrics() {
    const response = await fetch(`${this.baseUrl}/api/extract/metrics`);
    if (!response.ok) {
      throw new Error(`Не удалось загрузить отчет метрик (${response.status})`);
    }
    return await response.json();
  }
}

window.apiService = new ApiService();
