import type { ChatResponse, Result } from "./types";

const f02: Result = {
  networks: [
    { id: "open", name: "Общая сеть водоканала", trust: "open" },
    { id: "closed", name: "Сеть насосной станции", trust: "closed" },
  ],
  firewall: { side: "open" },
  rules: [
    {
      id: 1, type: "data", from: "open", to: "closed", mode: "two-way",
      protocol: "Modbus TCP", port: 502,
      description: "Опрос контроллера насосов программой диспетчера",
      justification: "Modbus TCP всегда двунаправленный: запрос и ответ образуют одно правило.",
    },
    {
      id: 2, type: "data", from: "closed", to: "open", mode: "one-way",
      protocol: "UDP", port: 514,
      description: "Журналы событий на сервер мониторинга",
      justification: "Один получатель, порт и протокол, обратной передачи нет.",
    },
    {
      id: 3, type: "data", from: "open", to: "closed", mode: "one-way",
      protocol: "UDP", port: 123,
      description: "Синхронизация времени: от сервера времени общей сети на сервер времени станции",
      justification: "NTP по условиям кейса это одно однонаправленное правило в защищаемую сеть.",
    },
  ],
  rules_count: 3,
  synonyx: { location: "closed", node_a_faces: "open", node_b_faces: "closed" },
  file_users_count: 0,
  schema_version: "1.1",
  status: "completed",
  unknowns: [],
  assumptions: [],
  devices: [
    { id: "controller", network_id: "closed", name: "Контроллер насосов" },
    { id: "dispatcher", network_id: "open", name: "Программа диспетчера" },
    { id: "logs", network_id: "open", name: "Сервер мониторинга" },
    { id: "operator", network_id: "closed", name: "Компьютер оператора" },
    { id: "ntp-office", network_id: "open", name: "Сервер времени" },
    { id: "ntp-station", network_id: "closed", name: "Сервер времени станции" },
  ],
  sources: [{ file: "02_methodology.md", section: "Размещение и подсчёт правил" }],
  requests_for_vendor: [],
  usage: null,
};

const n01: Result = {
  networks: [
    { id: "open", name: "Офисная сеть", trust: "open" },
    { id: "closed", name: "Сеть цеха", trust: "closed" },
  ],
  firewall: { side: "open" },
  rules: [
    {
      id: 1, type: "file", from: "open", to: "closed", mode: "two-way",
      protocol: null, port: null,
      description: "Файловый обмен между офисом и цехом",
      justification: "Нижняя оценка: один файловый обмен. Методы и проверки неизвестны.",
    },
  ],
  rules_count: 1,
  synonyx: { location: "closed", node_a_faces: "open", node_b_faces: "closed" },
  file_users_count: null,
  file_users_range: { min: 1, max: null },
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
  usage: null,
};

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function mockAnswer(text: string, current: Result | null): Promise<ChatResponse> {
  await delay(900);
  const t = text.toLowerCase();

  if (t.includes("насос")) {
    return {
      text: "Размещение: открытая сеть → межсетевой экран → «Синоникс» внутри сети станции. Правил три: Modbus двунаправленный, журналы и NTP однонаправленные.",
      result: f02,
      sources: f02.sources,
    };
  }

  if (t.includes("файл") && !current) {
    return {
      text: "Файловый обмен в обе стороны пока описан не полностью. Оценка предварительная: минимум 1 правило.",
      result: n01,
      questions: [
        {
          id: "methods",
          text: "Как файлы отправляются и принимаются на каждой стороне?",
          options: ["Вручную по SFTP", "Автоматически (PULL/PUSH)", "С USB-носителя"],
        },
        {
          id: "checks",
          text: "Какие проверки файлов нужны?",
          options: ["Маска имени и размер", "Внешний антивирус по ICAP", "Проверки не нужны"],
        },
      ],
    };
  }

    if (current) {
    return { text: "Спасибо, учёл ответ. Конфигурация сохранена." };
  }

  return {
    text: "Опишите, какие две сети нужно связать и что между ними передавать.",
    questions: [
      {
        id: "closed",
        text: "Какая из сетей закрытая (защищаемая)?",
        options: ["Сеть цеха", "Офисная сеть"],
      },
    ],
  };
}