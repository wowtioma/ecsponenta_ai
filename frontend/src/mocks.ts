
import type { ChatResponse, Result, Usage } from "./types";

// Демонстрационные расходы для mock-режима.
// Фактические значения приходят из usage результата бэкенда.
function mockUsage(
  callId: string,
  inputTokens: number,
  outputTokens: number,
  inputCostUsd: number,
  outputCostUsd: number,
): Usage {
  return {
    status: "measured",
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    input_cost_usd: inputCostUsd,
    output_cost_usd: outputCostUsd,
    evaluation_cost_usd: inputCostUsd + outputCostUsd,
    actual_cost_usd: null,
    calls: [
      {
        call_id: callId,
        model_id: "openai/gpt-oss-20b",
        purpose: "answer",
        input_tokens: inputTokens,
        output_tokens: outputTokens,
        cost_total_usd: inputCostUsd + outputCostUsd,
      },
    ],
  };
}

const f02: Result = {
  networks: [
    { id: "open", name: "Общая сеть водоканала", trust: "open" },
    { id: "closed", name: "Сеть насосной станции", trust: "closed" },
  ],

  firewall: { side: "open" },

  rules: [
    {
      id: 1,
      type: "data",
      from: "open",
      to: "closed",
      from_device_id: "dispatcher",
      to_device_id: "controller",
      transport: "network",
      mode: "two-way",
      protocol: "Modbus TCP",
      port: 502,
      description: "Опрос контроллера насосов программой диспетчера",
      justification:
        "Modbus TCP всегда двунаправленный: запрос и ответ образуют одно правило.",
    },
    {
      id: 2,
      type: "data",
      from: "closed",
      to: "open",
      from_device_id: "operator",
      to_device_id: "logs",
      transport: "network",
      mode: "one-way",
      protocol: "UDP",
      port: 514,
      description: "Журналы событий на сервер мониторинга",
      justification:
        "Один получатель, порт и протокол, обратной передачи нет.",
    },
    {
      id: 3,
      type: "data",
      from: "open",
      to: "closed",
      from_device_id: "ntp-office",
      to_device_id: "ntp-station",
      transport: "network",
      mode: "one-way",
      protocol: "UDP",
      port: 123,
      description:
        "Синхронизация времени: от сервера времени общей сети на сервер времени станции",
      justification:
        "NTP по условиям кейса это одно однонаправленное правило в защищаемую сеть.",
    },
  ],

  rules_count: 3,

  synonyx: {
    location: "closed",
    node_a_faces: "open",
    node_b_faces: "closed",
  },

  file_users_count: 0,

  schema_version: "1.1",
  status: "completed",
  unknowns: [],
  assumptions: [],

  devices: [
    {
      id: "controller",
      network_id: "closed",
      name: "Контроллер насосов",
    },
    {
      id: "dispatcher",
      network_id: "open",
      name: "Программа диспетчера",
    },
    {
      id: "logs",
      network_id: "open",
      name: "Сервер мониторинга",
    },
    {
      id: "operator",
      network_id: "closed",
      name: "Компьютер оператора",
    },
    {
      id: "ntp-office",
      network_id: "open",
      name: "Сервер времени",
    },
    {
      id: "ntp-station",
      network_id: "closed",
      name: "Сервер времени станции",
    },
  ],

  sources: [
    {
      file: "02_methodology.md",
      section: "Размещение и подсчёт правил",
    },
  ],

  requests_for_vendor: [],
  usage: mockUsage(
    "mock-f02",
    12480,
    2140,
    0.00125,
    0.00107,
  ),
};

const n01: Result = {
  networks: [
    { id: "open", name: "Офисная сеть", trust: "open" },
    { id: "closed", name: "Сеть цеха", trust: "closed" },
  ],

  firewall: { side: "open" },

  rules: [
    {
      id: 1,
      type: "file",
      from: "open",
      to: "closed",
      mode: "two-way",
      protocol: null,
      port: null,
      description: "Файловый обмен между офисом и цехом",
      justification:
        "Файлы передаются между двумя сетями с использованием SFTP.",
    },
  ],

  rules_count: 1,

  synonyx: {
    location: "closed",
    node_a_faces: "open",
    node_b_faces: "closed",
  },

  file_users_count: null,

  file_users_range: {
    min: 1,
    max: null,
  },

  status: "preliminary",

  unknowns: [
    "Способ отправки и получения файлов",
    "Требования к проверкам файлов",
    "Количество пользователей файловой передачи",
    "Нужно ли разделять видимость полученных файлов",
  ],

  assumptions: [],
  devices: [],
  sources: [],
  requests_for_vendor: [],
  usage: mockUsage(
    "mock-n01",
    9820,
    1580,
    0.00098,
    0.00079,
  ),
};

// Определение выбранных проверок файлов
function getUsbChecks(text: string): string[] | null {
  const t = text.toLowerCase();

  if (
    t.includes("маск") ||
    t.includes("имени") ||
    t.includes("размер")
  ) {
    return [
      "Проверка имени файла",
      "Проверка размера",
    ];
  }

  if (t.includes("icap") || t.includes("антивирус")) {
    return ["Проверка внешним антивирусом по ICAP"];
  }

  if (
    t.includes("проверки не нужны") ||
    t.includes("не нужны") ||
    t.includes("без проверок")
  ) {
    return ["Проверки не требуются"];
  }

  return null;
}

// Создание результата USB-сценария
function createUsbResult(
  checks?: string[],
  previous?: Result
): Result {
  const previousRule = previous?.rules.find(
    (rule) => rule.type === "file"
  );

  const previousChecks = previousRule?.checks_by_node as
    | Record<string, string[]>
    | undefined;

  const selectedChecks =
    checks ?? previousChecks?.node_a;

  const justificationChecks =
    selectedChecks && selectedChecks.length > 0
      ? selectedChecks.join(", ")
      : "требования к проверкам пока не определены";

  return {
    ...n01,

    rules: [
      {
        id: 1,
        type: "file",
        transport: "usb",

        from: "USB-носитель",
        to: "Узел А СКИО «Синоникс»",

        mode: "one-way",
        protocol: null,
        port: null,

        description:
          "Передача файлов с USB-носителя на Узел А для последующей проверки",

        methods_by_node: {
          node_a: "USB-носитель",
        },

        checks_by_node: selectedChecks
          ? {
              node_a: selectedChecks,
            }
          : {},

        justification:
          `USB-носитель подключается непосредственно к Узлу А СКИО «Синоникс». ` +
          `На Узле А выполняются следующие проверки: ${justificationChecks}. ` +
          "Передача в ядро, Узел В и закрытую сеть не осуществляется.",
      },
    ],

    rules_count: 1,
    file_users_count: 1,

    status: "completed",
    unknowns: [],
    assumptions: [],

    devices: [],

    usage: mockUsage(
      "mock-usb",
      7180,
      1220,
      0.00072,
      0.00061,
    ),
  };
}

const delay = (ms: number) =>
  new Promise((resolve) => setTimeout(resolve, ms));

export async function mockAnswer(
  text: string,
  current: Result | null
): Promise<ChatResponse> {
  await delay(900);

  const t = text.toLowerCase();

  const currentFileRule = current?.rules.find(
    (rule) => rule.type === "file"
  );

  const isCurrentUsb =
    currentFileRule?.transport === "usb";

  const selectedChecks = getUsbChecks(t);

  // 1. Обработка выбора проверок для USB
  if (current && isCurrentUsb && selectedChecks !== null) {
    const result = createUsbResult(selectedChecks, current);

    return {
      text:
        "Проверки файлов добавлены. На Узле А выполняются: " +
        selectedChecks.join(", ") +
        ".",
      result,
    };
  }

  // 2. Обработка выбора USB
  if (
    current &&
    currentFileRule &&
    (
      t.includes("usb") ||
      t.includes("с флеш") ||
      t.includes("флешк")
    )
  ) {
    const result = createUsbResult(
      selectedChecks ?? undefined,
      current
    );

    return {
      text:
        "Добавлено однонаправленное правило передачи файлов с USB-носителя на Узел А СКИО «Синоникс»." +
        (selectedChecks
          ? " Также добавлены проверки: " +
            selectedChecks.join(", ") +
            "."
          : " Теперь можно указать необходимые проверки файлов."),
      result,
    };
  }

  // 3. Сценарий обычной передачи файлов
  if (t.includes("файл")) {
    return {
      text:
        "Файловый обмен в обе стороны пока описан не полностью. Оценка предварительная: минимум 1 правило.",

      result: n01,

      questions: [
        {
          id: "methods",
          text:
            "Как файлы отправляются и принимаются на каждой стороне?",
          options: [
            "Вручную по SFTP",
            "Автоматически (PULL/PUSH)",
            "С USB-носителя",
          ],
        },
        {
          id: "checks",
          text: "Какие проверки файлов нужны?",
          options: [
            "Маска имени и размер",
            "Внешний антивирус по ICAP",
            "Проверки не нужны",
          ],
        },
      ],
    };
  }

  // 4. Сценарий насосной станции
  if (t.includes("насос")) {
    return {
      text:
        "Размещение: открытая сеть → межсетевой экран → «Синоникс» внутри сети станции. Правил три: Modbus двунаправленный, журналы и NTP однонаправленные.",
      result: f02,
    };
  }

  // 5. Ответ на другие уточняющие вопросы
  if (current) {
    return {
      text: "Спасибо, учёл ответ. Конфигурация сохранена.",
    };
  }

  // 6. Неизвестный сценарий
  return {
    text:
      "Опишите, какие две сети нужно связать и что между ними передавать.",
    questions: [
      {
        id: "closed",
        text: "Какая из сетей закрытая (защищаемая)?",
        options: ["Сеть цеха", "Офисная сеть"],
      },
    ],
  };
}
