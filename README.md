# Jino data parser for Home Assistant

Кастомная интеграция Home Assistant для мониторинга аккаунта **[Jino](https://jino.ru/)**: баланса, даты окончания услуг и доменов.  
Дополнительно поддерживается мониторинг аккаунтов **Nightscout Easy** из той же интеграции.  
Интеграция работает через `config_flow`, использует `DataUpdateCoordinator` и создаёт сенсоры в Home Assistant. :contentReference[oaicite:0]{index=0} :contentReference[oaicite:1]{index=1} :contentReference[oaicite:2]{index=2}

## Возможности

Интеграция получает из Jino:

- текущий баланс
- доступные средства и бонусные средства
- дату окончания действия баланса
- информацию по доменам
- дату продления домена
- статус автопродления
- стоимость продления
- признак истечения или скорого окончания услуги

Также поддерживается получение информации по аккаунтам **Nightscout Easy**:

- название аккаунта
- дата окончания доступа
- количество дней до окончания
- текстовое уведомление по сроку оплаты/доступа

Сенсоры создаются на платформе `sensor`. Интеграция определена как `cloud_polling` и использует библиотеки `requests` и `beautifulsoup4`. :contentReference[oaicite:3]{index=3} :contentReference[oaicite:4]{index=4}

## Что создаётся в Home Assistant

После настройки создаются:

### 1. Сенсор баланса Jino
Один общий сенсор баланса:

- `Balance`

Атрибуты включают:

- `real_funds`
- `bonus_funds`
- `payments_count`
- `expiration_days`
- `due_date`
- `expiration_label`
- `min_payment`
- `min_person_payment`
- `min_org_payment`
- `max_payment`
- `autoinvoice_enabled`
- `days_left`
- `message`
- `execution_seconds`

### 2. Сенсоры доменов Jino
Для каждого домена создаётся отдельный сенсор.

Состояние сенсора — дата окончания домена.  
Атрибуты включают:

- `due_date`
- `autorenewal_enabled`
- `is_expired`
- `expiring`
- `renewal_cost`
- `renewal_available`
- `can_be_renewed_from_balance`
- `days_left`
- `message`

### 3. Сенсоры Nightscout Easy
Для каждого добавленного аккаунта Nightscout создаётся отдельный сенсор.

Состояние сенсора — дата окончания доступа.  
Атрибуты включают:

- `due_date`
- `days_left`
- `message`
- `name`

Список атрибутов и логика создания сенсоров реализованы в `const.py` и `sensor.py`. :contentReference[oaicite:5]{index=5} :contentReference[oaicite:6]{index=6}

## Установка

### Вариант 1. Ручная установка

1. Скопируйте папку интеграции в:
   `config/custom_components/jino/`

2. Убедитесь, что в папке находятся файлы:
   - `__init__.py`
   - `api.py`
   - `config_flow.py`
   - `const.py`
   - `coordinator.py`
   - `entity_descriptions.py`
   - `manifest.json`
   - `sensor.py`
   - `strings.json`

3. Перезапустите Home Assistant.

### Вариант 2. Через HACS
Если репозиторий оформлен под HACS, добавьте его как кастомный репозиторий и установите интеграцию, затем перезапустите Home Assistant.

## Настройка

Интеграция настраивается через интерфейс Home Assistant:

**Settings → Devices & Services → Add Integration → Jino**

На первом шаге нужно указать:

- логин Jino
- пароль Jino
- интервал обновления в минутах

После этого можно добавить один или несколько аккаунтов **Nightscout**.  
Если Nightscout не нужен, поля можно оставить пустыми и завершить настройку. :contentReference[oaicite:7]{index=7} :contentReference[oaicite:8]{index=8}

## Параметры

### Основные
- **Jino login**
- **Jino password**
- **Scan interval minutes**

### Дополнительно
- список аккаунтов **Nightscout Easy**

Интервал обновления хранится в `options` и может быть изменён после добавления интеграции через параметры. По умолчанию используется интервал **60 минут**. :contentReference[oaicite:9]{index=9} :contentReference[oaicite:10]{index=10} :contentReference[oaicite:11]{index=11}

## Принцип работы

Интеграция:

1. Авторизуется в Jino
2. Получает баланс через GraphQL
3. Получает список доменов
4. Для каждого домена получает дополнительную информацию по продлению
5. При необходимости авторизуется в Nightscout Easy и получает срок действия доступа
6. Передаёт все данные в Home Assistant через `DataUpdateCoordinator` :contentReference[oaicite:12]{index=12} :contentReference[oaicite:13]{index=13}

## Сообщения и расчёт сроков

Для баланса, доменов и Nightscout формируется понятное текстовое сообщение, например:

- `Сегодня срок оплаты ...`
- `Через N дней нужно оплатить ...`
- `Просрочена оплата ...`
- `Все в порядке! ...`

Также рассчитывается `days_left`.  
Эта логика реализована в `api.py`. :contentReference[oaicite:14]{index=14}

## Структура интеграции

- `__init__.py` — загрузка интеграции и регистрация платформ :contentReference[oaicite:15]{index=15}
- `api.py` — работа с Jino и Nightscout Easy, авторизация, парсинг, GraphQL-запросы :contentReference[oaicite:16]{index=16}
- `config_flow.py` — настройка через UI Home Assistant, проверка логина/пароля, options flow :contentReference[oaicite:17]{index=17}
- `const.py` — константы интеграции и атрибуты сенсоров :contentReference[oaicite:18]{index=18}
- `coordinator.py` — обновление данных по расписанию через `DataUpdateCoordinator` :contentReference[oaicite:19]{index=19}
- `entity_descriptions.py` — описание сущностей :contentReference[oaicite:20]{index=20}
- `sensor.py` — сенсоры Jino и Nightscout :contentReference[oaicite:21]{index=21}
- `manifest.json` — метаданные интеграции и зависимости :contentReference[oaicite:22]{index=22}
- `strings.json` — локализация шагов настройки и ошибок :contentReference[oaicite:23]{index=23}

## Возможные проблемы

### Неверный логин или пароль
Если данные Jino введены неверно, интеграция вернёт ошибку авторизации.

### Не удалось подключиться
Может возникать при временной недоступности Jino или проблемах сети.

### Данные Nightscout не появились
Проверьте логин и пароль Nightscout Easy, а также доступность страницы авторизации.

Тексты ошибок для UI описаны в `strings.json`. :contentReference[oaicite:24]{index=24}

## Требования

Интеграция использует зависимости:

- `requests>=2.31.0`
- `beautifulsoup4>=4.12.0`

Версия в `manifest.json`: `1.0.1`. :contentReference[oaicite:25]{index=25}

## Roadmap

Потенциально можно добавить:

- кнопки принудительного обновления
- бинарные сенсоры для статусов "истекает скоро" / "просрочено"
- отдельные устройства для доменов
- диагностику соединения
- поддержку HACS release workflow

## Обратная связь

- Documentation: `https://github.com/alexanderznamensky/Jino`
- Issues: `https://github.com/alexanderznamensky/Jino/issues` :contentReference[oaicite:26]{index=26}
