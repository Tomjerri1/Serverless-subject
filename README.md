# Лабораторна робота 4: S3 -> Lambda -> DynamoDB (варіант 4)

Файл JSON у `incoming/` бакета S3 запускає Lambda, яка записує дані в DynamoDB.
Варіант 4: оновлення наявних записів, виграє найновіший `updatedAt`.
Відхилені оновлення рахуються атомарним `ADD` в елементі `STAT#rejected`.
Невдалі події потрапляють у чергу SQS `lab4-dlq`.

## Структура репозиторію
- `src/lambda_function.py` - код функції
- `tests/` - модульні тести
- `scripts/gen_test_files.py` - генерація тестових файлів у `testdata/`
- `scripts/upload_parallel.sh` - одночасне завантаження файлів
- `scripts/cleanup.sh` - видалення всіх ресурсів (імена передаються аргументами)
- `policy/lab4-processor-policy.json` - політика IAM за найменшими привілеями

## Формат вхідного файлу
```json
[{"id": "1", "name": "Alice", "updatedAt": 100}]
```
Кожен запис зберігається як елемент `PK = REC#<id>`. Запис оновлюється, лише якщо елемента
ще немає або збережений `updatedAt` менший за новий:
`attribute_not_exists(PK) OR updatedAt < :u`.

## Створені ресурси (eu-north-1)
- S3: бакет `lab4-maksymchuk-2026`, сповіщення `incoming-json` (префікс `incoming/`, суфікс `.json`)
- DynamoDB: таблиця `lab4-items` (PK, Provisioned 5/5, TTL за `ttl`)
- Lambda: `lab4-processor` (Python 3.13, arm64, 512 МБ, 30 с, `TABLE_NAME=lab4-items`),
  повторів 2, при збої - SQS `lab4-dlq`
- SQS: `lab4-dlq`
- IAM: роль `lab4-processor-role-8z6k2mtd`, політика `lab4-processor-policy`
- CloudWatch: алярми `lab4-processor-errors`, `lab4-dlq-messages`; група логів `/aws/lambda/lab4-processor`

## Ключ ідемпотентності
`bucket/key#eTag` (версіонування вимкнено).
- bucket + key визначають об'єкт.
- eTag змінюється разом із вмістом: перезаписаний файл є новою подією.
- Самого імені недостатньо, час події не підходить (при повторі він може відрізнятися).

Запис `IDEMP#<ключ>` створюється умовно (`attribute_not_exists(PK)`), має `ttl` 3 доби.
Файл спочатку читається й розбирається, потім позначається як оброблений: битий файл
не позначається, подія йде на повтор і в чергу збоїв.

Відомий компроміс: ключ записується до обробки записів, тому збій посередині обробки
призведе до пропуску повтору як дубліката. Це потрібно, бо лічильник відхилених
оновлень не можна безпечно повторювати.

## Результати експериментів
- Подвійна обробка однієї події: повтор пропущено (`duplicate, skipped`), лічильник не змінився.
- П'ять одночасних завантажень з атомарним `ADD`: `rejected` = 5 (очікувалось 5).
- Те саме без атомарності (read-modify-write): `rejected` = 4, втрачено 1 оновлення.
- Невдала обробка (`FORCE_FAIL=true`): 3 виклики (початковий і 2 повтори), далі повідомлення
  в `lab4-dlq` з `condition: RetriesExhausted`; обидва алярми спрацювали.

## Вартість 1 млн файлів
Припущення: 1 запис у файлі, 200 мс, 512 МБ, arm64.
- Lambda: запити 0,20 $ + обчислення ~1,33 $ (100 000 ГБ-с)
- DynamoDB: 2 млн записів, ~1,25 $ (on-demand)
- S3: PUT 5,00 $ + GET 0,40 $
- Разом ~8,2 $. З безкоштовним рівнем Lambda і provisioned-таблицею лишається S3, ~5,4 $.
  5 WCU дають 5 записів за секунду, тому 2 млн записів займуть ~4,6 доби.

## Запуск
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest -v
python scripts/gen_test_files.py
./scripts/upload_parallel.sh lab4-maksymchuk-2026 1 5
./scripts/cleanup.sh lab4-maksymchuk-2026 lab4-items lab4-processor lab4-dlq \
    lab4-processor-policy lab4-processor-role-8z6k2mtd \
    lab4-processor-errors lab4-dlq-messages
```