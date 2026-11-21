
import type { Result } from "../types";

import {
  buildDiagramModel,
  DIAGRAM_THEME,
} from "./diagram";

import type {
  DiagramConnection,
  DiagramModel,
  DiagramRect,
} from "./diagram";

// ============================================================
// XML ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// ============================================================

function escapeXml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatNumber(value: number): string {
  return Number.isInteger(value)
    ? String(value)
    : String(Number(value.toFixed(3)));
}

function geometry(rect: DiagramRect): string {
  return `
    <mxGeometry
      x="${formatNumber(rect.x)}"
      y="${formatNumber(rect.y)}"
      width="${formatNumber(rect.width)}"
      height="${formatNumber(rect.height)}"
      as="geometry"/>
  `;
}

// ============================================================
// СОЗДАНИЕ РЕДАКТИРУЕМЫХ БЛОКОВ
// ============================================================

function createVertex(
  id: string,
  value: string,
  rect: DiagramRect,
  style: string,
): string {
  return `
    <mxCell
      id="${escapeXml(id)}"
      value="${escapeXml(value)}"
      style="${escapeXml(style)}"
      vertex="1"
      parent="1">
      ${geometry(rect)}
    </mxCell>
  `;
}

function createText(
  id: string,
  value: string,
  rect: DiagramRect,
  color: string,
  fontSize: number,
  options: {
    bold?: boolean;
    align?: "left" | "center" | "right";
    fontStyle?: string;
  } = {},
): string {
  const style =
    "text;" +
    "html=1;" +
    "whiteSpace=wrap;" +
    "overflow=hidden;" +
    `align=${options.align ?? "left"};` +
    "verticalAlign=middle;" +
    `fontColor=${color};` +
    `fontSize=${fontSize};` +
    `fontFamily=${options.fontStyle ?? "Open Sans"};` +
    `fontStyle=${options.bold ? 1 : 0};`;

  return createVertex(id, escapeHtml(value), rect, style);
}

// ============================================================
// СЕТЕВЫЕ СЕГМЕНТЫ
// ============================================================

function createNetwork(
  id: string,
  title: string,
  subtitle: string,
  rect: DiagramRect,
  color: string,
): string {
  const value =
    `<b>${escapeHtml(title)}</b>` +
    `<br>` +
    `<span style="font-weight:normal;font-size:11px">` +
    `${escapeHtml(subtitle)}` +
    `</span>`;

  const style =
    "rounded=1;" +
    "arcSize=5;" +
    "dashed=1;" +
    "dashPattern=8 6;" +
    "fillColor=none;" +
    `strokeColor=${color};` +
    "strokeWidth=2;" +
    "html=1;" +
    "whiteSpace=wrap;" +
    "align=left;" +
    "verticalAlign=top;" +
    "spacingLeft=14;" +
    "spacingTop=6;" +
    `fontColor=${color};` +
    "fontSize=12;" +
    "fontFamily=Open Sans;";

  return createVertex(id, value, rect, style);
}

// ============================================================
// КАРТОЧКИ УСТРОЙСТВ
// ============================================================

function createDevice(
  id: string,
  name: string,
  rect: DiagramRect,
): string {
  const value = `<b>${escapeHtml(name)}</b>`;

  const style =
    "rounded=1;" +
    "arcSize=14;" +
    `fillColor=${DIAGRAM_THEME.device.fill};` +
    "strokeColor=none;" +
    "html=1;" +
    "whiteSpace=wrap;" +
    "align=left;" +
    "verticalAlign=middle;" +
    "spacingLeft=14;" +
    "spacingRight=8;" +
    `fontColor=${DIAGRAM_THEME.device.text};` +
    "fontSize=13;" +
    "fontFamily=Open Sans;";

  return createVertex(id, value, rect, style);
}

// ============================================================
// МЕЖСЕТЕВОЙ ЭКРАН
// ============================================================

function createFirewallBody(
  rect: DiagramRect,
): string {
  return createVertex(
    "firewall",
    "",
    rect,
    "rounded=1;" +
      "arcSize=5;" +
      `fillColor=${DIAGRAM_THEME.firewall.fill};` +
      `strokeColor=${DIAGRAM_THEME.firewall.stroke};` +
      "strokeWidth=2;" +
      "html=1;",
  );
}

function createFirewallLine(
  id: string,
  line: {
    x1: number;
    y1: number;
    x2: number;
    y2: number;
  },
): string {
  const style =
    "edgeStyle=none;" +
    "rounded=0;" +
    "html=1;" +
    `strokeColor=${DIAGRAM_THEME.firewall.stroke};` +
    "strokeWidth=1.5;" +
    "startArrow=none;" +
    "endArrow=none;";

  return `
    <mxCell
      id="${escapeXml(id)}"
      value=""
      style="${escapeXml(style)}"
      edge="1"
      parent="1">
      <mxGeometry as="geometry">
        <mxPoint
          x="${formatNumber(line.x1)}"
          y="${formatNumber(line.y1)}"
          as="sourcePoint"/>
        <mxPoint
          x="${formatNumber(line.x2)}"
          y="${formatNumber(line.y2)}"
          as="targetPoint"/>
      </mxGeometry>
    </mxCell>
  `;
}

function createFirewallFlame(
  rect: DiagramRect,
): string {
  // Отдельная SVG-иконка внутри XML Draw.io.
  // Сам блок МЭ и его надпись остаются редактируемыми.
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg"
         width="48" height="48" viewBox="0 0 48 48">
      <path
        d="M24 2 C31 13 39 18 37 29
           C36 40 29 46 21 45
           C11 44 7 36 10 26
           C12 19 18 14 17 7
           C22 12 25 16 24 22
           C29 17 29 9 24 2 Z"
        fill="#E06733"/>
      <path
        d="M24 24 C30 30 30 38 24 41
           C19 43 15 38 17 33
           C19 29 22 27 24 24 Z"
        fill="#FFAB4D"/>
    </svg>
  `;

  const image = encodeURIComponent(svg);

  return createVertex(
    "firewall-flame",
    "",
    rect,
    "shape=image;" +
      "imageAspect=0;" +
      "aspect=fixed;" +
      "html=1;" +
      `image=data:image/svg+xml,${image};`,
  );
}

function createFirewallLabel(
  model: DiagramModel,
): string {
  const rect = model.firewall.rect;

  return createText(
    "firewall-label",
    "МЭ",
    {
      x: rect.x,
      y: rect.y + 69,
      width: rect.width,
      height: 24,
    },
    DIAGRAM_THEME.firewall.stroke,
    13,
    {
      bold: true,
      align: "center",
    },
  );
}

// ============================================================
// СКИО «СИНОНИКС»
// ============================================================

function createSynonyxBox(
  rect: DiagramRect,
): string {
  return createVertex(
    "synonyx-area",
    "",
    rect,
    "rounded=1;" +
      "arcSize=10;" +
      `fillColor=${DIAGRAM_THEME.synonyx.background};` +
      `strokeColor=${DIAGRAM_THEME.synonyx.border};` +
      "strokeWidth=2;" +
      "html=1;",
  );
}

function createSynonyxNode(
  id: string,
  name: string,
  rect: DiagramRect,
  shape: "rounded" | "hexagon",
): string {
  const shapeStyle =
    shape === "hexagon"
      ? "shape=hexagon;" +
        "perimeter=hexagonPerimeter2;" +
        "fixedSize=1;" +
        "size=14;"
      : "rounded=1;arcSize=12;";

  const style =
    shapeStyle +
    `fillColor=${DIAGRAM_THEME.synonyx.nodeFill};` +
    `strokeColor=${DIAGRAM_THEME.synonyx.nodeBorder};` +
    "html=1;" +
    `fontColor=${DIAGRAM_THEME.synonyx.nodeText};` +
    "fontSize=10;" +
    "fontStyle=1;" +
    "fontFamily=Open Sans;" +
    "align=center;" +
    "verticalAlign=middle;";

  return createVertex(
    id,
    escapeHtml(name),
    rect,
    style,
  );
}

function createSynonyx(
  model: DiagramModel,
): string[] {
  const { synonyx } = model;

  const cells: string[] = [];

  cells.push(
    createText(
      "synonyx-label",
      "СИНОНИКС",
      synonyx.labelRect,
      DIAGRAM_THEME.segment.open,
      13,
      {
        bold: true,
        align: "center",
      },
    ),
  );

  cells.push(
    createSynonyxBox(synonyx.box),
  );

  cells.push(
    createSynonyxNode(
      synonyx.nodeA.id,
      synonyx.nodeA.name,
      synonyx.nodeA.rect,
      synonyx.nodeA.shape,
    ),
  );

  cells.push(
    createSynonyxNode(
      synonyx.core.id,
      synonyx.core.name,
      synonyx.core.rect,
      synonyx.core.shape,
    ),
  );

  cells.push(
    createSynonyxNode(
      synonyx.nodeB.id,
      synonyx.nodeB.name,
      synonyx.nodeB.rect,
      synonyx.nodeB.shape,
    ),
  );

  cells.push(
    createText(
      "synonyx-version",
      "ПАК версии 1.9",
      {
        x: synonyx.box.x,
        y: synonyx.box.y + synonyx.box.height - 21,
        width: synonyx.box.width,
        height: 16,
      },
      DIAGRAM_THEME.synonyx.secondaryText,
      9,
      {
        align: "center",
      },
    ),
  );

  return cells;
}

// ============================================================
// USB-НОСИТЕЛИ
// ============================================================

function createUsb(
  model: DiagramModel,
): string[] {
  const cells: string[] = [];

  model.usb.forEach((item) => {
    const rect = item.rect;

    cells.push(
      createVertex(
        `usb-${item.ruleId}`,
        escapeHtml("USB-носитель"),
        rect,
        "rounded=1;" +
          "arcSize=30;" +
          `fillColor=${DIAGRAM_THEME.device.fill};` +
          "strokeColor=#B9C5CD;" +
          "strokeWidth=1;" +
          "html=1;" +
          "whiteSpace=wrap;" +
          "align=center;" +
          "verticalAlign=middle;" +
          `fontColor=${DIAGRAM_THEME.device.text};` +
          "fontSize=11;" +
          "fontStyle=1;" +
          "fontFamily=Open Sans;",
      ),
    );

    cells.push(
      createVertex(
        `usb-label-${item.ruleId}`,
        escapeHtml(item.label),
        item.labelRect,
        "rounded=1;" +
          "arcSize=50;" +
          `fillColor=${DIAGRAM_THEME.label.background};` +
          "strokeColor=none;" +
          "html=1;" +
          "align=center;" +
          "verticalAlign=middle;" +
          `fontColor=${item.color};` +
          "fontSize=10;" +
          "fontStyle=1;" +
          "fontFamily=Open Sans;",
      ),
    );
  });

  return cells;
}

// ============================================================
// СОЕДИНЕНИЯ
// ============================================================

function getAnchor(
  rect: DiagramRect,
  point: { x: number; y: number },
): { x: number; y: number } {
  return {
    x: Math.max(
      0,
      Math.min(1, (point.x - rect.x) / rect.width),
    ),
    y: Math.max(
      0,
      Math.min(1, (point.y - rect.y) / rect.height),
    ),
  };
}

function createConnection(
  connection: DiagramConnection,
  rects: Map<string, DiagramRect>,
): string {
  const sourceRect = rects.get(connection.sourceId);
  const targetRect = rects.get(connection.targetId);

  const points = connection.points;

  if (!sourceRect || !targetRect || points.length < 2) {
    return "";
  }

  const sourceAnchor = getAnchor(
    sourceRect,
    points[0],
  );

  const targetAnchor = getAnchor(
    targetRect,
    points[points.length - 1],
  );

  const arrows =
    connection.mode === "two-way"
      ? "startArrow=block;" +
        "startFill=1;" +
        "endArrow=block;" +
        "endFill=1;"
      : "startArrow=none;" +
        "endArrow=block;" +
        "endFill=1;";

  const style =
    "edgeStyle=none;" +
    "rounded=0;" +
    "html=1;" +
    `strokeColor=${connection.color};` +
    "strokeWidth=2;" +
    "exitPerimeter=1;" +
    "entryPerimeter=1;" +
    `exitX=${formatNumber(sourceAnchor.x)};` +
    `exitY=${formatNumber(sourceAnchor.y)};` +
    `entryX=${formatNumber(targetAnchor.x)};` +
    `entryY=${formatNumber(targetAnchor.y)};` +
    arrows;

  // Первый и последний точки задаются через порты объектов.
  // Остальные сохраняются как промежуточные точки маршрута.
  const intermediatePoints = points.slice(1, -1);

  const pointsXml =
    intermediatePoints.length > 0
      ? `
        <Array as="points">
          ${intermediatePoints
            .map(
              (point) => `
                <mxPoint
                  x="${formatNumber(point.x)}"
                  y="${formatNumber(point.y)}"/>
              `,
            )
            .join("\n")}
        </Array>
      `
      : "";

  return `
    <mxCell
      id="${escapeXml(connection.id)}"
      value=""
      style="${escapeXml(style)}"
      edge="1"
      parent="1"
      source="${escapeXml(connection.sourceId)}"
      target="${escapeXml(connection.targetId)}">
      <mxGeometry relative="1" as="geometry">
        ${pointsXml}
      </mxGeometry>
    </mxCell>
  `;
}

function createConnections(
  model: DiagramModel,
): string[] {
  const rects = new Map<string, DiagramRect>();

  // Устройства
  model.devices.forEach((device) => {
    rects.set(device.id, device.rect);
  });

  // Узлы Синоникса
  rects.set(
    model.synonyx.nodeA.id,
    model.synonyx.nodeA.rect,
  );

  rects.set(
    model.synonyx.core.id,
    model.synonyx.core.rect,
  );

  rects.set(
    model.synonyx.nodeB.id,
    model.synonyx.nodeB.rect,
  );

  // USB-носители
  model.usb.forEach((item) => {
    rects.set(
      `usb-${item.ruleId}`,
      item.rect,
    );
  });

  return model.connections.map(
    (connection) =>
      createConnection(connection, rects),
  );
}

// ============================================================
// ПОДПИСИ СОЕДИНЕНИЙ
// ============================================================

function createConnectionLabels(
  model: DiagramModel,
): string[] {
  return model.connections
    .filter((connection) => connection.label.length > 0)
    .map((connection) => {
      const rect = connection.labelRect;

      return createVertex(
        `connection-label-${connection.id}`,
        escapeHtml(connection.label),
        rect,
        "rounded=1;" +
          "arcSize=50;" +
          `fillColor=${DIAGRAM_THEME.label.background};` +
          "strokeColor=none;" +
          "html=1;" +
          "align=center;" +
          "verticalAlign=middle;" +
          `fontColor=${DIAGRAM_THEME.label.text};` +
          "fontSize=10;" +
          "fontStyle=1;" +
          "fontFamily=Open Sans;",
      );
    });
}

// ============================================================
// ЛЕГЕНДА И ПРИМЕЧАНИЯ
// ============================================================

function createLegend(
  model: DiagramModel,
): string[] {
  const cells: string[] = [];

  cells.push(
    createText(
      "diagram-footer-title",
      model.footerTitle.text,
      {
        x: model.footerTitle.x,
        y: model.footerTitle.y,
        width: model.width - 80,
        height: 30,
      },
      DIAGRAM_THEME.text.primary,
      13,
      {
        bold: true,
      },
    ),
  );

  model.legend.forEach((item) => {
    cells.push(
      createVertex(
        item.id + "-bullet",
        "",
        item.bullet,
        "rounded=1;" +
          "arcSize=30;" +
          `fillColor=${item.color};` +
          "strokeColor=none;",
      ),
    );

    cells.push(
      createText(
        item.id + "-text",
        item.text,
        item.textRect,
        DIAGRAM_THEME.text.primary,
        11,
      ),
    );
  });

  cells.push(
    createText(
      "diagram-footer-note",
      model.footerNote.text,
      model.footerNote.rect,
      DIAGRAM_THEME.text.secondary,
      11,
    ),
  );

  return cells;
}

// ============================================================
// ПОЛНАЯ ГЕНЕРАЦИЯ XML
// ============================================================

function createDiagramXml(result: Result): string {
  // ВАЖНО:
  // Используем ту же модель, что и DiagramPreview.tsx.
  const model = buildDiagramModel(result);

  const cells: string[] = [];

  // Корневые элементы mxGraph
  cells.push(`
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
  `);

  // ----------------------------------------------------------
  // Фон
  // ----------------------------------------------------------

  cells.push(
    createVertex(
      "diagram-background",
      "",
      {
        x: 0,
        y: 0,
        width: model.width,
        height: model.height,
      },
      `rounded=0;fillColor=${model.background};` +
        "strokeColor=none;",
    ),
  );

  // ----------------------------------------------------------
  // Заголовки
  // ----------------------------------------------------------

  cells.push(
    createText(
      "diagram-title",
      model.title,
      {
        x: 40,
        y: 16,
        width: model.width - 80,
        height: 30,
      },
      DIAGRAM_THEME.text.primary,
      20,
      {
        bold: true,
      },
    ),
  );

  cells.push(
    createText(
      "diagram-subtitle",
      model.subtitle,
      {
        x: 40,
        y: 46,
        width: model.width - 80,
        height: 20,
      },
      DIAGRAM_THEME.text.secondary,
      12,
    ),
  );

  // ----------------------------------------------------------
  // Сетевые сегменты
  // ----------------------------------------------------------

  cells.push(
    createNetwork(
      "network-open",
      "ОТКРЫТАЯ СЕТЬ",
      model.openNetworkName,
      model.openSegment,
      DIAGRAM_THEME.segment.open,
    ),
  );

  cells.push(
    createNetwork(
      "network-closed",
      "ЗАКРЫТЫЙ СЕГМЕНТ",
      model.closedNetworkName,
      model.closedSegment,
      DIAGRAM_THEME.segment.closed,
    ),
  );

  // ----------------------------------------------------------
  // Линии соединений
  // ----------------------------------------------------------

  cells.push(
    ...createConnections(model),
  );

  // ----------------------------------------------------------
  // Межсетевой экран
  // ----------------------------------------------------------

  cells.push(
    createFirewallBody(model.firewall.rect),
  );

  model.firewall.lines.forEach((line, index) => {
    cells.push(
      createFirewallLine(
        `firewall-line-${index}`,
        line,
      ),
    );
  });

  cells.push(
    createFirewallFlame(model.firewall.flame),
  );

  cells.push(
    createFirewallLabel(model),
  );

  // ----------------------------------------------------------
  // Устройства
  // ----------------------------------------------------------

  model.devices.forEach((device) => {
    cells.push(
      createDevice(
        device.id,
        device.name,
        device.rect,
      ),
    );
  });

  // ----------------------------------------------------------
  // Синоникс
  // ----------------------------------------------------------

  cells.push(
    ...createSynonyx(model),
  );

  // ----------------------------------------------------------
  // USB
  // ----------------------------------------------------------

  cells.push(
    ...createUsb(model),
  );

  // ----------------------------------------------------------
  // Подписи линий
  // ----------------------------------------------------------

  cells.push(
    ...createConnectionLabels(model),
  );

  // ----------------------------------------------------------
  // Нижняя легенда и пояснения
  // ----------------------------------------------------------

  cells.push(
    ...createLegend(model),
  );

  // ----------------------------------------------------------
  // Сборка несжатого XML Draw.io
  // ----------------------------------------------------------

  return `<?xml version="1.0" encoding="UTF-8"?>
<mxfile
  host="app.diagrams.net"
  modified="${new Date().toISOString()}"
  agent="Synonyx"
  version="24.7.17"
  type="device">
  <diagram id="synonyx-diagram" name="Схема сети">
    <mxGraphModel
      dx="${model.width}"
      dy="${model.height}"
      grid="1"
      gridSize="10"
      guides="1"
      tooltips="1"
      connect="1"
      arrows="1"
      fold="1"
      page="1"
      pageScale="1"
      pageWidth="${model.width}"
      pageHeight="${model.height}"
      math="0"
      shadow="0"
      background="${model.background}">
      <root>
        ${cells.join("\n")}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>`;
}

// ============================================================
// ПУБЛИЧНАЯ ФУНКЦИЯ ЭКСПОРТА
// ============================================================

export function exportDrawio(result: Result): void {
  const xml = createDiagramXml(result);

  const blob = new Blob(
    [xml],
    {
      type: "application/xml;charset=utf-8",
    },
  );

  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");

  link.href = url;
  link.download = "synonyx-network.drawio";

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  window.setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 1000);
}
