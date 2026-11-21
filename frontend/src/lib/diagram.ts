
import type { Result, Rule } from "../types";

// ============================================================
// ЕДИНЫЙ ДВИЖОК СХЕМЫ
// Используется для SVG на сайте и XML Draw.io.
// ============================================================

export type DiagramSide = "open" | "closed";

export type DiagramPoint = {
  x: number;
  y: number;
};

export type DiagramRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type DiagramDevice = {
  id: string;
  deviceId: string;
  name: string;
  subtitle: string;
  side: DiagramSide;
  rect: DiagramRect;
};

export type DiagramNode = {
  id: string;
  name: string;
  subtitle: string;
  side: DiagramSide;
  shape: "rounded" | "hexagon";
  rect: DiagramRect;
};

export type DiagramConnection = {
  id: string;
  ruleId: number;
  sourceId: string;
  targetId: string;
  points: DiagramPoint[];
  color: string;
  mode: "one-way" | "two-way";
  label: string;
  labelRect: DiagramRect;
};

export type DiagramUsb = {
  ruleId: number;
  rect: DiagramRect;
  label: string;
  labelRect: DiagramRect;
  color: string;
};

export type DiagramLegendItem = {
  id: string;
  ruleId: number;
  color: string;
  text: string;
  bullet: DiagramRect;
  textRect: DiagramRect;
};

export type DiagramModel = {
  width: number;
  height: number;
  background: string;

  title: string;
  subtitle: string;

  openSegment: DiagramRect;
  closedSegment: DiagramRect;

  openNetworkName: string;
  closedNetworkName: string;

  devices: DiagramDevice[];

  firewall: {
    rect: DiagramRect;
    side: string;
    lines: {
      x1: number;
      y1: number;
      x2: number;
      y2: number;
    }[];
    flame: DiagramRect;
  };

  synonyx: {
    labelRect: DiagramRect;
    box: DiagramRect;
    nodeA: DiagramNode;
    core: DiagramNode;
    nodeB: DiagramNode;
  };

  usb: DiagramUsb[];

  connections: DiagramConnection[];

  rulesCount: number;

  footerTitle: {
    text: string;
    x: number;
    y: number;
  };

  legend: DiagramLegendItem[];

  footerNote: {
    text: string;
    rect: DiagramRect;
  };
};

// ============================================================
// ЦВЕТА И ОФОРМЛЕНИЕ ИЗ ШАБЛОНА И ОБРАЗЦОВ
// ============================================================

export const DIAGRAM_THEME = {
  background: "#303E48",

  segment: {
    open: "#E06733",
    closed: "#35C4AF",
  },

  device: {
    fill: "#4A5D6A",
    text: "#FFFFFF",
    subtitle: "#35C4AF",
  },

  firewall: {
    fill: "#354552",
    stroke: "#FFAB4D",
    flame: "#E06733",
    flameInner: "#FFAB4D",
  },

  synonyx: {
    border: "#E06733",
    background: "#FFFFFF",
    nodeFill: "#F2F4F6",
    nodeBorder: "#B9C5CD",
    nodeText: "#3A4D59",
    secondaryText: "#64748B",
  },

  text: {
    primary: "#FFFFFF",
    secondary: "#B9C5CD",
  },

  label: {
    background: "#354552",
    text: "#FFFFFF",
  },

  ruleColors: [
    "#E06733",
    "#35C4AF",
    "#FFAB4D",
  ],
} as const;

// ============================================================
// ОБЩИЕ РАЗМЕРЫ
// Основа — образцы 05_pattern_F02 и 05_pattern_F07.
// ============================================================

const LAYOUT = {
  width: 1450,
  height: 634,

  segmentY: 90,
  segmentHeight: 370,

  openX: 30,
  openWidth: 320,

  closedX: 584,
  closedWidth: 836,

  deviceOpenX: 70,
  deviceClosedX: 1150,
  deviceWidth: 240,
  deviceHeight: 56,

  deviceCenterY: 305,

  firewallX: 560,
  firewallWidth: 48,

  synonyxX: 644,
  synonyxWidth: 240,
  synonyxHeight: 120,

  nodeWidth: 64,
  nodeHeight: 80,

  usbX: 633,
  usbY: 369,
  usbWidth: 110,
  usbHeight: 34,

  footerY: 476,
  footerRowY: 510,
  footerRowStep: 26,
};

// ============================================================
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// ============================================================

function safeId(value: unknown): string {
  return String(value ?? "")
    .replace(/[^a-zA-Z0-9_-]/g, "_");
}

export function getRuleColor(index: number): string {
  return DIAGRAM_THEME.ruleColors[
    index % DIAGRAM_THEME.ruleColors.length
  ];
}

export function getDeviceName(
  result: Result,
  deviceId?: string | null,
): string {
  if (!deviceId) {
    return "Устройство не указано";
  }

  return (
    result.devices.find(
      (device) => device.id === deviceId,
    )?.name ?? "Устройство не найдено"
  );
}

export function getProtocolLabel(rule: Rule): string {
  if (rule.transport === "usb") {
    return "USB-носитель";
  }

  const protocol = rule.protocol;

  if (typeof protocol === "string") {
    return protocol;
  }

  if (protocol && typeof protocol === "object") {
    const values = [
      protocol.open,
      protocol.closed,
    ].filter(
      (value): value is string =>
        typeof value === "string" && value.length > 0,
    );

    return [...new Set(values)].join(" / ") || "Не указан";
  }

  return rule.type === "file"
    ? "Передача файлов"
    : "Не указан";
}

export function getShortProtocol(rule: Rule): string {
  return getProtocolLabel(rule);
}

export function getRuleLabel(rule: Rule): string {
  if (rule.transport === "usb") {
    return `${rule.id} · файлы с флешки`;
  }

  const protocol = getProtocolLabel(rule);
  const port = rule.port != null
    ? ` ${rule.port}`
    : "";

  return `${rule.id} · ${protocol}${port}`;
}

function normalizeSide(value?: string | null): DiagramSide | undefined {
  if (!value) return undefined;

  const normalized = value.toLowerCase();

  if (
    normalized.includes("open") ||
    normalized.includes("открыт")
  ) {
    return "open";
  }

  if (
    normalized.includes("closed") ||
    normalized.includes("закрыт")
  ) {
    return "closed";
  }

  return undefined;
}

function getOppositeSide(side: DiagramSide): DiagramSide {
  return side === "open" ? "closed" : "open";
}

function getScenarioTitle(result: Result): string {
  const networkNames = result.networks
    .map((network) => network.name)
    .join(" ")
    .toLowerCase();

  if (
    networkNames.includes("водоканал") ||
    networkNames.includes("насос")
  ) {
    return "НАСОСНАЯ СТАНЦИЯ: ОБМЕН С ОБЩЕЙ СЕТЬЮ";
  }

  if (
    networkNames.includes("офис") ||
    networkNames.includes("цех")
  ) {
    return "ЦЕХ И ОФИС: ТЕЛЕМЕТРИЯ, ВРЕМЯ, ОБНОВЛЕНИЯ";
  }

  return "СХЕМА ВЗАИМОДЕЙСТВИЯ СЕТЕЙ";
}

function getScenarioSubtitle(result: Result): string {
  const networkNames = result.networks
    .map((network) => network.name)
    .join(" ")
    .toLowerCase();

  let scenario = "Конфигурация сети";

  if (
    networkNames.includes("водоканал") ||
    networkNames.includes("насос")
  ) {
    scenario = "Сценарий F02";
  } else if (
    networkNames.includes("офис") ||
    networkNames.includes("цех")
  ) {
    scenario = "Сценарий F07";
  }

  let subtitle =
    `${scenario} · правил Синоникса: ${result.rules.length}`;

  if (result.file_users_count != null) {
    subtitle +=
      ` · пользователей передачи файлов: ${result.file_users_count}`;
  }

  return subtitle;
}

// Распределяем устройства по вертикали.
// Для двух и трёх устройств координаты совпадают с образцами F02/F07.
function getDevicePositions(count: number): number[] {
  if (count <= 0) return [];

  const gap =
    count === 1
      ? 0
      : count === 2
        ? 130
        : count === 3
          ? 87
          : Math.max(
              60,
              Math.min(87, 260 / (count - 1)),
            );

  const firstCenter =
    LAYOUT.deviceCenterY -
    ((count - 1) * gap) / 2;

  return Array.from(
    { length: count },
    (_, index) =>
      firstCenter +
      index * gap -
      LAYOUT.deviceHeight / 2,
  );
}

function makeLabelRect(
  side: DiagramSide,
  y: number,
  label: string,
): DiagramRect {
  const width = Math.max(
    66,
    Math.min(160, label.length * 6.5 + 14),
  );

  return {
    x: side === "open" ? 332 : 999,
    y: y - 9,
    width,
    height: 18,
  };
}


function makeConnection(
  id: string,
  rule: Rule,
  sourceId: string,
  targetId: string,
  points: DiagramPoint[],
  side: DiagramSide,
  labelY: number,
  color: string,
): DiagramConnection {
  const label = getRuleLabel(rule);

  return {
    id,
    ruleId: rule.id,
    sourceId,
    targetId,
    points,
    color,
    mode: rule.mode,
    label,
    labelRect: makeLabelRect(side, labelY, label),
  };
}

function getNodeForSide(
  side: DiagramSide,
  nodeA: DiagramNode,
  nodeB: DiagramNode,
): DiagramNode {
  return nodeA.side === side ? nodeA : nodeB;
}

// ============================================================
// ОСНОВНАЯ ФУНКЦИЯ ПОСТРОЕНИЯ СХЕМЫ
// ============================================================

export function buildDiagramModel(
  result: Result,
): DiagramModel {
  const openNetwork = result.networks.find(
    (network) => network.trust === "open",
  );

  const closedNetwork = result.networks.find(
    (network) => network.trust === "closed",
  );

  const openNetworkName =
    openNetwork?.name ?? "Открытая сеть";

  const closedNetworkName =
    closedNetwork?.name ?? "Закрытый сегмент";

  const openDevicesSource = result.devices.filter(
    (device) => device.network_id === openNetwork?.id,
  );

  const closedDevicesSource = result.devices.filter(
    (device) => device.network_id === closedNetwork?.id,
  );

  // ----------------------------------------------------------
  // 1. Устройства и их координаты
  // ----------------------------------------------------------

  const openPositions = getDevicePositions(
    openDevicesSource.length,
  );

  const closedPositions = getDevicePositions(
    closedDevicesSource.length,
  );

  const devices: DiagramDevice[] = [
    ...openDevicesSource.map((device, index) => ({
      id: `device-open-${index}-${safeId(device.id)}`,
      deviceId: device.id,
      name: device.name,
      subtitle: "",
      side: "open" as const,
      rect: {
        x: LAYOUT.deviceOpenX,
        y: openPositions[index],
        width: LAYOUT.deviceWidth,
        height: LAYOUT.deviceHeight,
      },
    })),

    ...closedDevicesSource.map((device, index) => ({
      id: `device-closed-${index}-${safeId(device.id)}`,
      deviceId: device.id,
      name: device.name,
      subtitle: "",
      side: "closed" as const,
      rect: {
        x: LAYOUT.deviceClosedX,
        y: closedPositions[index],
        width: LAYOUT.deviceWidth,
        height: LAYOUT.deviceHeight,
      },
    })),
  ];

  const deviceById = new Map(
    devices.map((device) => [
      device.deviceId,
      device,
    ]),
  );

  const maxDeviceBottom = Math.max(
    LAYOUT.segmentY + LAYOUT.segmentHeight,
    ...devices.map(
      (device) => device.rect.y + device.rect.height + 40,
    ),
  );

  const segmentHeight = maxDeviceBottom - LAYOUT.segmentY;

  const openSegment: DiagramRect = {
    x: LAYOUT.openX,
    y: LAYOUT.segmentY,
    width: LAYOUT.openWidth,
    height: segmentHeight,
  };

  const closedSegment: DiagramRect = {
    x: LAYOUT.closedX,
    y: LAYOUT.segmentY,
    width: LAYOUT.closedWidth,
    height: segmentHeight,
  };

  // ----------------------------------------------------------
  // 2. Межсетевой экран
  // ----------------------------------------------------------

  const firewallRect: DiagramRect = {
    x: LAYOUT.firewallX,
    y: LAYOUT.segmentY + 75,
    width: LAYOUT.firewallWidth,
    height: Math.max(280, segmentHeight - 90),
  };

  const firewallLines: DiagramModel["firewall"]["lines"] = [];

  // Горизонтальные и вертикальные линии кирпичной стены.
  for (
    let y = firewallRect.y + 58;
    y < firewallRect.y + firewallRect.height - 5;
    y += 18
  ) {
    firewallLines.push({
      x1: firewallRect.x + 2,
      y1: y,
      x2: firewallRect.x + firewallRect.width - 2,
      y2: y,
    });

    const row = Math.round(
      (y - firewallRect.y) / 18,
    );

    const verticalX =
      row % 2 === 0
        ? firewallRect.x + 12
        : firewallRect.x + 36;

    firewallLines.push({
      x1: verticalX,
      y1: y,
      x2: verticalX,
      y2: y + 18,
    });
  }

  const firewall = {
    rect: firewallRect,
    side: result.firewall?.side ?? "open",
    lines: firewallLines,
    flame: {
      x: firewallRect.x + 7,
      y: firewallRect.y + 9,
      width: firewallRect.width - 14,
      height: 44,
    },
  };

  // ----------------------------------------------------------
  // 3. СКИО «Синоникс»
  // ----------------------------------------------------------

  // Вертикальное положение соответствует образцам:
  // F02: 3 устройства в открытой и 3 в закрытой сети.
  // F07: 2 устройства в открытой и 3 в закрытой сети.
  const synonyxY =
    openDevicesSource.length < closedDevicesSource.length
      ? 209
      : 245;

  const nodeAFace =
    normalizeSide(result.synonyx?.node_a_faces) ?? "open";

  const nodeBFace =
    normalizeSide(result.synonyx?.node_b_faces) ??
    getOppositeSide(nodeAFace);

  const nodeA: DiagramNode = {
    id: "synonyx-node-a",
    name: "УЗЕЛ А",
    subtitle:
      nodeAFace === "open"
        ? openNetworkName
        : closedNetworkName,
    side: nodeAFace,
    shape: "rounded",
    rect: {
      x: LAYOUT.synonyxX + 12,
      y: synonyxY + 20,
      width: LAYOUT.nodeWidth,
      height: LAYOUT.nodeHeight,
    },
  };

  const core: DiagramNode = {
    id: "synonyx-core",
    name: "ЯДРО",
    subtitle: "Изоляция",
    side: "open",
    shape: "hexagon",
    rect: {
      x: LAYOUT.synonyxX + 88,
      y: synonyxY + 20,
      width: LAYOUT.nodeWidth,
      height: LAYOUT.nodeHeight,
    },
  };

  const nodeB: DiagramNode = {
    id: "synonyx-node-b",
    name: "УЗЕЛ В",
    subtitle:
      nodeBFace === "closed"
        ? closedNetworkName
        : openNetworkName,
    side: nodeBFace,
    shape: "rounded",
    rect: {
      x: LAYOUT.synonyxX + 164,
      y: synonyxY + 20,
      width: LAYOUT.nodeWidth,
      height: LAYOUT.nodeHeight,
    },
  };

  const synonyx = {
    labelRect: {
      x: LAYOUT.synonyxX,
      y: synonyxY - 30,
      width: LAYOUT.synonyxWidth,
      height: 24,
    },
    box: {
      x: LAYOUT.synonyxX,
      y: synonyxY,
      width: LAYOUT.synonyxWidth,
      height: LAYOUT.synonyxHeight,
    },
    nodeA,
    core,
    nodeB,
  };

  // ----------------------------------------------------------
  // 4. USB и сетевые соединения
  // ----------------------------------------------------------

  const connections: DiagramConnection[] = [];
  const usb: DiagramUsb[] = [];

  result.rules.forEach((rule, index) => {
    const color = getRuleColor(index);
    const ruleKey = `rule-${safeId(rule.id)}`;

    // USB подключается только к Узлу А.
    if (rule.transport === "usb") {
      const usbRect: DiagramRect = {
        x: LAYOUT.usbX,
        y: LAYOUT.usbY + usb.length * 42,
        width: LAYOUT.usbWidth,
        height: LAYOUT.usbHeight,
      };

      const label = getRuleLabel(rule);

      const labelRect: DiagramRect = {
        x: 751,
        y: usbRect.y + 8,
        width: Math.max(
          100,
          Math.min(180, label.length * 6.5 + 14),
        ),
        height: 18,
      };

      usb.push({
        ruleId: rule.id,
        rect: usbRect,
        label,
        labelRect,
        color,
      });

      const node = nodeA;
      const sourceX = usbRect.x + usbRect.width / 2;
      const sourceY = usbRect.y;
      const targetX = node.rect.x + node.rect.width / 2;
      const targetY = node.rect.y + node.rect.height;

      connections.push({
        id: `${ruleKey}-usb`,
        ruleId: rule.id,
        sourceId: `usb-${rule.id}`,
        targetId: node.id,
        points: [
          { x: sourceX, y: sourceY },
          { x: sourceX, y: targetY + 10 },
          { x: targetX, y: targetY },
        ],
        color,
        mode: "one-way",
        label: "",
        labelRect: {
          x: 0,
          y: 0,
          width: 0,
          height: 0,
        },
      });

      return;
    }

    const source = rule.from_device_id
      ? deviceById.get(rule.from_device_id)
      : undefined;

    const target = rule.to_device_id
      ? deviceById.get(rule.to_device_id)
      : undefined;

    // Без конкретных устройств маршрут нельзя построить достоверно.
    // Само правило при этом остаётся в легенде и JSON.
    if (!source || !target) {
      return;
    }

    const sourceSide = source.side;
    const targetSide = target.side;

    const sourceCenterY =
      source.rect.y + source.rect.height / 2;

    const targetCenterY =
      target.rect.y + target.rect.height / 2;

    // --------------------------------------------------------
    // Если оба устройства находятся в одной сети
    // --------------------------------------------------------

    if (sourceSide === targetSide) {
      const laneX =
        sourceSide === "open" ? 340 : 1410;

      const sourceX =
        sourceSide === "open"
          ? source.rect.x + source.rect.width
          : source.rect.x;

      const targetX =
        targetSide === "open"
          ? target.rect.x + target.rect.width
          : target.rect.x;

      const side = sourceSide;

      connections.push(
        makeConnection(
          `${ruleKey}-direct`,
          rule,
          source.id,
          target.id,
          [
            { x: sourceX, y: sourceCenterY },
            { x: laneX, y: sourceCenterY },
            { x: laneX, y: targetCenterY },
            { x: targetX, y: targetCenterY },
          ],
          side,
          sourceCenterY,
          color,
        ),
      );

      return;
    }

    // --------------------------------------------------------
    // Для разных сетей выбираем соответствующие узлы.
    // Открытая сеть соединяется с узлом, обращённым к ней.
    // Закрытая сеть соединяется с узлом, обращённым к ней.
    // --------------------------------------------------------

    const sourceNode = getNodeForSide(
      sourceSide,
      nodeA,
      nodeB,
    );

    const targetNode = getNodeForSide(
      targetSide,
      nodeA,
      nodeB,
    );

    const sourceNodeCenterY =
      sourceNode.rect.y + sourceNode.rect.height / 2;

    const targetNodeCenterY =
      targetNode.rect.y + targetNode.rect.height / 2;

    // --------------------------------------------------------
    // Первый участок: устройство-источник → узел Синоникса
    // --------------------------------------------------------

    let firstPoints: DiagramPoint[];
    let sourceAnchorX: number;
    let nodeAnchorX: number;
    let firstLaneX: number;

    if (sourceSide === "open") {
      sourceAnchorX =
        source.rect.x + source.rect.width;

      nodeAnchorX = sourceNode.rect.x;
      firstLaneX = 540;

      firstPoints = [
        {
          x: sourceAnchorX,
          y: sourceCenterY,
        },
        {
          x: firstLaneX,
          y: sourceCenterY,
        },
        {
          x: firstLaneX,
          y: sourceNodeCenterY,
        },
        {
          x: nodeAnchorX,
          y: sourceNodeCenterY,
        },
      ];
    } else {
      sourceAnchorX = source.rect.x;

      nodeAnchorX =
        sourceNode.rect.x + sourceNode.rect.width;

      firstLaneX = 918;

      firstPoints = [
        {
          x: sourceAnchorX,
          y: sourceCenterY,
        },
        {
          x: firstLaneX,
          y: sourceCenterY,
        },
        {
          x: firstLaneX,
          y: sourceNodeCenterY,
        },
        {
          x: nodeAnchorX,
          y: sourceNodeCenterY,
        },
      ];
    }

    connections.push(
      makeConnection(
        `${ruleKey}-source`,
        rule,
        source.id,
        sourceNode.id,
        firstPoints,
        sourceSide,
        sourceCenterY,
        color,
      ),
    );

    // --------------------------------------------------------
    // Второй участок: узел Синоникса → устройство-получатель
    // --------------------------------------------------------

    let secondPoints: DiagramPoint[];
    let targetAnchorX: number;
    let nodeTargetX: number;
    let secondLaneX: number;

    if (targetSide === "open") {
      nodeTargetX = targetNode.rect.x;
      targetAnchorX =
        target.rect.x + target.rect.width;

      secondLaneX = 540;

      secondPoints = [
        {
          x: nodeTargetX,
          y: targetNodeCenterY,
        },
        {
          x: secondLaneX,
          y: targetNodeCenterY,
        },
        {
          x: secondLaneX,
          y: targetCenterY,
        },
        {
          x: targetAnchorX,
          y: targetCenterY,
        },
      ];
    } else {
      nodeTargetX =
        targetNode.rect.x + targetNode.rect.width;

      targetAnchorX = target.rect.x;
      secondLaneX = 900;

      secondPoints = [
        {
          x: nodeTargetX,
          y: targetNodeCenterY,
        },
        {
          x: secondLaneX,
          y: targetNodeCenterY,
        },
        {
          x: secondLaneX,
          y: targetCenterY,
        },
        {
          x: targetAnchorX,
          y: targetCenterY,
        },
      ];
    }

    connections.push(
      makeConnection(
        `${ruleKey}-target`,
        rule,
        targetNode.id,
        target.id,
        secondPoints,
        targetSide,
        targetCenterY,
        color,
      ),
    );
  });

  // ----------------------------------------------------------
  // 5. Легенда и нижняя подпись
  // ----------------------------------------------------------

  const footerY = Math.max(
    LAYOUT.footerY,
    LAYOUT.segmentY + segmentHeight + 16,
  );

  const legend: DiagramLegendItem[] = result.rules.map(
    (rule, index) => {
      const y =
        footerY +
        34 +
        index * LAYOUT.footerRowStep;

      return {
        id: `legend-${safeId(rule.id)}`,
        ruleId: rule.id,
        color: getRuleColor(index),
        text: `${rule.id}. ${rule.description}`,
        bullet: {
          x: 40,
          y: y + 9,
          width: 12,
          height: 12,
        },
        textRect: {
          x: 62,
          y,
          width: 1350,
          height: 30,
        },
      };
    },
  );

  const footerNoteY =
    footerY +
    34 +
    result.rules.length * LAYOUT.footerRowStep;

  const footerNote =
    "МЭ расположен на границе закрытого сегмента. " +
    "Синоникс размещён внутри закрытого сегмента сразу за МЭ. " +
    "Узел А обращён к открытой сети, Узел В — к закрытому сегменту. " +
    "USB подключается к Узлу А в обход МЭ.";

  const height = Math.max(
    LAYOUT.height,
    footerNoteY + 46,
  );

  // ----------------------------------------------------------
  // 6. Итоговая модель
  // ----------------------------------------------------------

  return {
    width: LAYOUT.width,
    height,
    background: DIAGRAM_THEME.background,

    title: getScenarioTitle(result),
    subtitle: getScenarioSubtitle(result),

    openSegment,
    closedSegment,

    openNetworkName,
    closedNetworkName,

    devices,

    firewall,

    synonyx,

    usb,

    connections,

    rulesCount: result.rules.length,

    footerTitle: {
      text: `Правил Синоникса: ${result.rules.length}`,
      x: 40,
      y: footerY,
    },

    legend,

    footerNote: {
      text: footerNote,
      rect: {
        x: 62,
        y: footerNoteY,
        width: 1350,
        height: 30,
      },
    },
  };
}
