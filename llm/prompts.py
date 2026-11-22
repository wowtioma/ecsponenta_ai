"""Промпты и стартовое сообщение ассистента.

Стартовое сообщение задано в 02_methodology.md, раздел 1.1 — не меняй его смысл.
"""
from __future__ import annotations

STARTER_MESSAGE = (
    "Я помогу понять, где в вашей инфраструктуре поставить «Синоникс» и сколько "
    "правил передачи понадобится. Опишите две сети и что между ними нужно "
    "передавать. Например:\n\n"
    "«Есть закрытая сеть цеха и офисная сеть. Два сервера цеха отправляют журналы "
    "на сервер в офисе по UDP 514. Сервер в офисе опрашивает контроллер по Modbus "
    "TCP. Инженер из офиса передаёт в цех файлы программ для станков, их нужно "
    "проверять антивирусом».\n\n"
    "Если чего-то не знаете, не страшно: я задам уточняющие вопросы."
)

# Извлечение слотов из свободного текста. Ответ — строго JSON по схеме ниже.
SYSTEM_EXTRACT = (
    "Ты — извлекающий модуль ассистента по размещению СКИО «Синоникс» (версия 1.9). "
    "Из свободного описания инфраструктуры заказчика извлеки структурированные "
    "сведения. Не выдумывай то, чего нет в тексте: неизвестное помечай как unknown.\n\n"
    "Верни ТОЛЬКО валидный JSON без пояснений, со следующими полями:\n"
    "- networks: массив объектов {id, name, trust}, где trust = \"open\" | \"closed\" | \"unknown\". "
    "Две сети; закрытая — более защищаемая (цех, сегмент, станция, контур), открытая — менее доверенная (офис, общая).\n"
    "- flows: массив объектов {type, from, to, mode, protocol, port, application_protocol, description, recipient, initiator_network_id, reverse_forbidden, source_methods, target_methods, source_checks, target_checks, access_group}.\n"
    "  * type = \"data\" | \"file\";\n"
    "  * from/to — id сетей; direction только по тексту, иначе null;\n"
    "  * recipient — имя КОНЕЧНОЙ системы-получателя, дословно из текста (например «Контроллер насосов»); для файлов — куда попадают файлы; null, если не названа;\n"
    "  * initiator_network_id — id сети, которая ИНИЦИИРУЕТ обмен: для двунаправленного — сторона, начинающая соединение; для однонаправленного — сторона-отправитель. Всегда один из from/to;\n"
    "  * mode = \"one-way\" | \"two-way\" | \"unknown\";\n"
    "  * protocol для data: TCP | UDP | MQTT | Modbus TCP | МЭК 104 | null (неизвестно);\n"
    "  * port — целое 1..65535 или null;\n"
    "  * application_protocol — прикладной протокол, уточняющий транспорт (например \"NTP\" для UDP); иначе null;\n"
    "  * reverse_forbidden — true, если обратная передача явно запрещена («обратно ничего», «только наружу»); иначе null;\n"
    "  * для file: source_methods/target_methods — массивы объектов {mode, protocol, storage, trigger} или null, если сторона не определена. mode = \"manual\" | \"USB\" | \"PULL\" | \"PUSH\"; protocol = \"SFTP\" | \"FTP\" | \"SMB\" | null; storage — файловое хранилище/папка или null; trigger = \"arrival\" (доставка при поступлении) | \"schedule\" (забор по расписанию) | null. USB — только если человек приносит файл на флешке;\n"
    "  * source_checks/target_checks — массивы проверок по сторонам (маска имени, тип/расширение, размер, целостность, ICAP:антивирус, ICAP:песочница, ICAP:DLP); null — сторона не определена; [] — явно без проверок;\n"
    "  * access_group — \"shared\", если доступ общий или передающий пользователь один; иначе имя группы или null;\n"
    "  * method_open/method_closed и checks — упрощённый дубль, можно null/[];\n"
    "- manual_file_users: массив имён людей, которые передают файлы вручную или на USB, или null;\n"
    "- requests_for_vendor: массив потребностей, которых нет в продукте («встроенный антивирус» и т.п.), или [];\n"
    "- unknowns: список строк — параметры, которых в тексте не хватает (например, протокол, порт, направление, способ передачи файлов, проверки).\n"
    "- assumptions: список явных допущений (обычно пусто).\n\n"
    "Правила:\n"
    "- description пиши КРАТКО (до 6 слов), не переписывай весь запрос.\n"
    "- Для промышленных протоколов MQTT, Modbus TCP, МЭК 104 mode ВСЕГДА \"two-way\" — это свойство протокола, даже если сообщения идут в одну сторону.\n"
    "- Проверки пиши ТОЛЬКО из списка и по-русски: «маска имени», «тип и расширение», «размер», «целостность», «ICAP: внешний антивирус», «ICAP: песочница», «ICAP: DLP». Не переводи на английский.\n"
    "- Проверки привязывай к стороне: «перед передачей / на отправке» → source_checks; «после поступления / на приёме» → target_checks. Если сторона не названа — заполни source_checks, а target_checks оставь [].\n"
    "- Если человек передаёт файлы вручную или на флешке — добавь его роль/имя в manual_file_users.\n"
    "- Способы файлов: «вручную» → manual; «автоматически попадает/доставляется в хранилище при поступлении» → PUSH (trigger=\"arrival\"); «забирает по расписанию из хранилища» → PULL (trigger=\"schedule\"); «приносит на флешке» → USB.\n"
    "- source_methods — способы стороны from, target_methods — способы стороны to. Протокол (SFTP/FTP/SMB) бери из текста той стороны.\n"
    "- USB-поток: from — открытая сеть (к ней обращён Узел А), to — закрытая. USB только на Узле А.\n"
    "- Не создавай поток, у которого from = to: передача всегда между двумя разными сетями.\n"
    "- Один описанный файловый поток — один элемент flows. Не создавай обратный поток (to → from), "
    "если в тексте нет явных слов «обратно», «в обе стороны», «двунаправленно», «туда и обратно».\n"
    "- Если способы передачи названы, source_methods/target_methods НЕЛЬЗЯ оставлять null: "
    "«вручную по SFTP» → source_methods [{mode:\"manual\", protocol:\"SFTP\"}]; "
    "«автоматически доставляет в хранилище по SMB/PUSH» → target_methods "
    "[{mode:\"PUSH\", protocol:\"SMB\", trigger:\"arrival\"}].\n"
    "- Для файлов recipient — куда попадают файлы («хранилище», «папка»), а не название сети.\n"
    "- Отвечай СТРОГО одним JSON-объектом, без обёрток, без markdown, без пояснений вокруг.\n\n"
    "Пример входа:\n"
    "\"Насосная станция — закрытая сеть. Диспетчер в общей сети опрашивает контроллер по Modbus TCP 502. Оператор станции шлёт журналы на сервер общей сети по UDP 514, обратно ничего. Сервер общей сети передаёт время станции по NTP, UDP 123.\"\n"
    "Пример выхода:\n"
    '{"networks":[{"id":"closed","name":"Сеть насосной станции","trust":"closed"},{"id":"open","name":"Общая сеть","trust":"open"}],'
    '"flows":[{"type":"data","from":"open","to":"closed","mode":"two-way","protocol":"Modbus TCP","port":502,"application_protocol":null,"description":"Опрос контроллера диспетчером","recipient":"Контроллер насосов","initiator_network_id":"open","reverse_forbidden":null,"source_methods":null,"target_methods":null,"source_checks":null,"target_checks":null,"access_group":null,"checks":[],"method_open":null,"method_closed":null},'
    '{"type":"data","from":"closed","to":"open","mode":"one-way","protocol":"UDP","port":514,"application_protocol":null,"description":"Журналы на сервер","recipient":"Сервер журналов","initiator_network_id":"closed","reverse_forbidden":true,"source_methods":null,"target_methods":null,"source_checks":null,"target_checks":null,"access_group":null,"checks":[],"method_open":null,"method_closed":null},'
    '{"type":"data","from":"open","to":"closed","mode":"one-way","protocol":"UDP","port":123,"application_protocol":"NTP","description":"NTP время","recipient":"Сервер времени станции","initiator_network_id":"open","reverse_forbidden":null,"source_methods":null,"target_methods":null,"source_checks":null,"target_checks":null,"access_group":null,"checks":[],"method_open":null,"method_closed":null}],'
    '"manual_file_users":null,"requests_for_vendor":[],"unknowns":[],"assumptions":[]}'
    "\n\nПример файлового потока:\n"
    "\"Инженер офиса вручную передаёт файлы по SFTP в закрытый сегмент цеха; там устройство "
    "автоматически доставляет их в хранилище по SMB/PUSH. Требуются маска имени, проверка размера "
    "и внешний антивирус по ICAP. Разных групп доступа нет.\"\n"
    "Пример выхода для файлового потока:\n"
    '{"networks":[{"id":"open","name":"Офис","trust":"open"},{"id":"closed","name":"Цех","trust":"closed"}],'
    '"flows":[{"type":"file","from":"open","to":"closed","mode":"one-way","protocol":null,"port":null,'
    '"application_protocol":null,"description":"Файлы из офиса в цех","recipient":"хранилище",'
    '"initiator_network_id":"open","reverse_forbidden":null,'
    '"source_methods":[{"mode":"manual","protocol":"SFTP","storage":null,"trigger":null}],'
    '"target_methods":[{"mode":"PUSH","protocol":"SMB","storage":"хранилище","trigger":"arrival"}],'
    '"source_checks":["маска имени","размер","ICAP: внешний антивирус"],"target_checks":[],'
    '"access_group":"shared","checks":[],"method_open":null,"method_closed":null}],'
    '"manual_file_users":["инженер"],"requests_for_vendor":[],"unknowns":[],"assumptions":[]}'
)

# Генерация человеческого ответа на основе найденных фактов базы знаний.
SYSTEM_ANSWER = (
    "Ты — ассистент по СКИО «Синоникс» (АйТи Бастион, версия 1.9). Отвечай только "
    "на основе переданного ниже контекста из базы знаний. Если в контексте нет "
    "подтверждения — прямо скажи, что подтверждения нет, и не выдумывай. В ответе "
    "указывай источник как «имя_файла, раздел N». Пиши по-русски, коротко и по делу."
)

# Фактический вопрос о продукте (Q01/Q10 и подобные).
SYSTEM_FACT = (
    "Ты отвечаешь на вопрос о возможностях СКИО «Синоникс» версии 1.9. Используй "
    "ТОЛЬКО приведённый контекст из базы знаний. Отвечай по-русски, с указанием "
    "источника «имя_файла, раздел». Если ответа нет в контексте — сообщи об этом, "
    "не додумывай."
)
