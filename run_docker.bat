@echo off
chcp 65001 >nul
echo ========================================================
echo   М.Видео AI - Извлечение характеристик товаров
echo   Запуск полного проекта (Frontend + Backend) в Docker
echo ========================================================
echo.
echo Сборка и запуск контейнера одной командой...
docker compose up --build -d
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ОШИБКА] Не удалось запустить Docker Compose.
    echo Убедитесь, что Docker Desktop запущен и доступен.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ========================================================
echo   Сервис успешно запущен и готов к работе!
echo   - Веб-интерфейс (UI):  http://localhost:8000/
echo   - Swagger API (Docs):  http://localhost:8000/docs
echo   - Проверка здоровья:   http://localhost:8000/health
echo ========================================================
echo.
echo Для остановки контейнера выполните: docker compose down
pause
