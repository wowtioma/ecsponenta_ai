# Участник B — LLM + факты + учёт стоимости

Твоя часть: модели, извлечение слотов из текста, фактические ответы по базе
знаний, журнал вызовов, расчёт стоимости и сбор потребностей для разработчика.

## Провайдер и модель (актуально)

- **Провайдер:** Groq (бесплатный план, без карты), OpenAI-совместимый API.
- **Модель:** `openai/gpt-oss-20b` — есть в каталоге OpenRouter ($0,03/$0,14).
- По ТЗ §7 (стр. 157) стоимость считается **по каталоговому тарифу OpenRouter**,
  а не по цене Groq. Всё уже настроено в `llm/config.py`.

## Что в пакете `llm/`

| Файл | Что делает |
|---|---|
| `config.py` | профили провайдеров (openrouter/groq/yandex/gigachat), тарифы, пути к базе |
| `client.py` | `LLMClient.chat()` — вызов модели, чтение usage, стоимость, запись в журнал |
| `journal.py` | `Journal` + `CallRecord` — учёт по `call_id`, стоимость сессии, JSONL/CSV |
| `storage.py` | сохранение журнала сессии на диск в `sessions/` (ТЗ §8) |
| `report.py` | блоки `usage` и `timing` по схеме `result.example.json` (ТЗ §8–§10) |
| `rag.py` | ключевой поиск по `.md` базе + цитата «файл + раздел». Без эмбеддингов |
| `extract.py` | `extract()` извлечение слотов (LLM) + `quick_extract()` regex-фолбэк |
| `answer.py` | `answer_fact()`, `explain_placement()`, `explain_rules()` |
| `vendor.py` | `requests_for_vendor` — детекция неподдерживаемого (бонус §12.7) |
| `prompts.py` | промпты + `STARTER_MESSAGE` (методика §1.1) |

## Структура проекта

```
basti/
├── llm/                  # ← участок B (этот пакет)
├── tests/                # юнит-тесты (без сети)
├── scripts/              # демо и проверки (участок B)
│   ├── demo_b.py         #   starter / fact / extract / models
│   ├── check_groq.py     #   проверка ключа Groq + модель
│   ├── check_openrouter.py
│   ├── check_yandex.py
│   ├── check_providers.py
│   └── benchmark_test.py #   прогон на 04_benchmarks.json (нужен ключ)
├── requirements.txt
├── .env.example          # шаблон (без ключа) — коммитим
├── .env                  # реальный ключ — НЕ коммитим
├── README_B.md
└── Кейс АйТи Бастион — Синоникс/   # материалы организаторов — НЕ коммитим
```

## Запуск и проверка

```powershell
# ключ Groq: console.groq.com/keys -> gsk_... -> в .env

.\venv\Scripts\python.exe scripts\demo_b.py starter
.\venv\Scripts\python.exe scripts\demo_b.py fact "Сколько правил можно настроить на одном Синониксе?"
.\venv\Scripts\python.exe scripts\demo_b.py extract "Насосная станция — закрытая сеть. Диспетчер опрашивает контроллер по Modbus TCP 502."
.\venv\Scripts\python.exe scripts\check_groq.py
.\venv\Scripts\python.exe scripts\benchmark_test.py
```

Тесты без сети:
```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Для сокомандников (важно при клонировании)

`rag.py` по умолчанию читает базу из папки кейса, которой в git нет. Поэтому:
1. Положите папку `Кейс АйТи Бастион — Синоникс` в корень проекта, **или**
2. Задайте в `.env` путь: `SYNONYX_BASE_DIR=...`

Каждый делает **свой** ключ Groq (30 секунд, бесплатно) и кладёт в свой `.env`.

## Границы части B (что НЕ твоё)

- **Расчёт правил и размещение** — A (`core/rules.py`). Ты отдаёшь слоты из
  `extract()`, он возвращает `rules`/`synonyx` по схеме `result.example.json`.
- **Отрисовка схемы и `.drawio`** — C.

## Контракт с A (формат извлечения)

`extract()` возвращает dict:
```json
{
  "networks": [{"id": "closed", "name": "Сеть цеха", "trust": "closed"}],
  "flows": [
    {"type": "data", "from": "closed", "to": "open", "mode": "one-way",
     "protocol": "UDP", "port": 514, "description": "журналы",
     "checks": [], "method_open": null, "method_closed": null}
  ],
  "unknowns": ["способ передачи файлов"],
  "assumptions": []
}
```
`unknowns` — чего не хватает; A превратит их в уточняющие вопросы (методика §4).
При сбое LLM в результат добавляются `_fallback: true` и `_warning` — не игнорируй их.
