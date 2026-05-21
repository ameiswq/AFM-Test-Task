## Проект выполнен по ветке B - Backend / Data Engineering.

app/                  FastAPI-приложение
initdb/               SQL-скрипты для создания таблицы и загрузки данных в PostgreSQL
notebook/edu.ipynb    EDA, очистка данных и выводы
sql/                  SQL-запросы из базовой части задания
tests.py              pytest-тесты API
requirements.txt      Python-зависимости
docker-compose.yml    PostgreSQL + API
Dockerfile            образ API

Перед запуском положите файлы в папку `data/`: data/transactions.csv

Для запуска API через Docker также нужен очищенный файл: data/transactions_clean.csv (Он генерируется в ноутбуке `notebook/edu.ipynb` после очистки данных)

## Запуск через Docker
docker compose up --build
По умолчанию API будет доступен на: http://127.0.0.1:8001
PostgreSQL будет доступен с хоста на порту 5433, внутри Docker API подключается к базе по адресу 5432.

## Проверка API

Карточка контрагента:
GET http://127.0.0.1:8001/counterparty/421128527724

Поиск по описанию:
GET http://127.0.0.1:8001/search?q=бумаг&page=1&page_size=3

Поиск с фильтрами:
GET http://127.0.0.1:8001/search?q=бумаг&date_from=2026-04-30&date_to=2026-04-30&amount_min=90000&amount_max=100000&page=1&page_size=5

Аномалии контрагента:
GET http://127.0.0.1:8001/counterparty/421128527724/anomalies

Граничные случаи:
GET http://127.0.0.1:8001/counterparty/999999999999
GET http://127.0.0.1:8001/counterparty/999999999999/anomalies
GET http://127.0.0.1:8001/search?q=&page=1&page_size=5

Для несуществующего контрагента ожидается `404 Not Found`.

## Локальный запуск без Docker

Если PostgreSQL уже установлен локально и база заполнена:
pip install -r requirements.txt
uvicorn app.main:app --reload
