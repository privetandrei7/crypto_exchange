# Проверка сборки

Проверено перед упаковкой:
- Python syntax: OK
- JavaScript syntax: OK
- fresh SQLite database: OK
- legacy `old_status/new_status` history schema migration: OK
- ORM history INSERT after migration: OK
- `/`: 200
- `/api/rates`: 200
- `/order/{id}`: 200
- `/admin/orders/{id}`: 200 after admin login
- status change: OK
- website order creation: OK
- RUB pair: OK
- clickable admin order IDs: present

Архив предназначен для demo/test использования.
