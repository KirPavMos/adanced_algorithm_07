# adanced_algorithm_07
Как запустить сервис
Установите необходимые зависимости:

pip install fastapi sqlalchemy redis fastapi-redis-cache pydantic python-multipart uvicorn[standard] python-dotenv
Создайте файл .env с настройками:

DATABASE_URL=sqlite:///./sql_app.db
REDIS_URL=redis://localhost:6379
SMTP_SERVER=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=user@example.com
SMTP_PASSWORD=password
Запустите сервер:

uvicorn main:app --reload

Описание реализации
Кэширование API методов:

Используется fastapi-redis-cache для кэширования всех GET и POST методов

Кэш автоматически инвалидируется при изменении данных

Время жизни кэша задается для каждого метода отдельно

Фоновые задачи:

Реализован endpoint /statistics/ который принимает email и запускает фоновую задачу

Фоновая задача собирает статистику по всем продавцам:

Количество товаров у продавца

Общее количество продаж

Количество отгрузок за текущий месяц

Отчет отправляется на указанный email

Модели данных:

Продавцы (Sellers)

Товары (Products)

Продажи (Sales)

Отправка email:

Реализована функция отправки email через SMTP

В реальном приложении нужно настроить SMTP сервер

Примеры запросов
Создать продавца:

curl -X POST "http://localhost:8000/sellers/" -H "Content-Type: application/json" -d '{"name":"John Doe","email":"john@example.com"}'
Получить список продавцов:

curl "http://localhost:8000/sellers/"
Запросить отчет по статистике:

curl -X POST "http://localhost:8000/statistics/" -H "Content-Type: application/json" -d '{"email":"your@email.com"}'
Этот сервис реализует все требуемые функции: кэширование API методов, фоновые задачи для генерации отчетов и отправки их по email, а также полный CRUD интерфейс для работы с данными.
