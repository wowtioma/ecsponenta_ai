
import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { WheelEvent } from "react";

import type { Result, Rule } from "../types";

import {
  buildDrawioXml,
  downloadDrawioXml,
} from "../lib/exportDrawio";

import {
  buildDiagramModel,
  DIAGRAM_THEME,
  getDeviceName,
  getProtocolLabel,
  getRuleColor,
} from "../lib/diagram";

import type {
  DiagramDevice,
  DiagramModel,
  DiagramNode,
  DiagramPoint,
  DiagramRect,
} from "../lib/diagram";

// ============================================================
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// ============================================================

function createPath(points: DiagramPoint[]): string {
  return points
    .map(
      (point, index) =>
        `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`
    )
    .join(" ");
}

function getArrowId(ruleId: number): string {
  return `diagram-arrow-${ruleId}`;
}

function splitText(
  value: string,
  maxLength = 28
): string[] {
  const words = value.split(/\s+/);
  const lines: string[] = [];
  let current = "";

  for (const word of words) {
    const next = current
      ? `${current} ${word}`
      : word;

    if (next.length > maxLength && current) {
      lines.push(current);
      current = word;
    } else {
      current = next;
    }
  }

  if (current) {
    lines.push(current);
  }

  return lines;
}

// ============================================================
// СЕТЕВОЙ СЕГМЕНТ
// ============================================================

function NetworkSection({
  rect,
  title,
  subtitle,
  color,
}: {
  rect: DiagramRect;
  title: string;
  subtitle: string;
  color: string;
}) {
  return (
    <g>
      <rect
        x={rect.x}
        y={rect.y}
        width={rect.width}
        height={rect.height}
        rx={5}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeDasharray="8 6"
      />

      <text
        x={rect.x + 14}
        y={rect.y + 22}
        fill={color}
        fontSize={12}
        fontWeight={700}
        letterSpacing={0.5}
        fontFamily="Open Sans, Arial, sans-serif"
      >
        {title}
      </text>

      <text
        x={rect.x + 14}
        y={rect.y + 43}
        fill={DIAGRAM_THEME.text.primary}
        fontSize={11}
        fontFamily="Open Sans, Arial, sans-serif"
      >
        {subtitle}
      </text>
    </g>
  );
}

// ============================================================
// КАРТОЧКА УСТРОЙСТВА
// ============================================================

function DeviceNode({
  device,
}: {
  device: DiagramDevice;
}) {
  const { rect } = device;
  const lines = splitText(device.name, 30);

  return (
    <g>
      <rect
        x={rect.x}
        y={rect.y}
        width={rect.width}
        height={rect.height}
        rx={14}
        fill={DIAGRAM_THEME.device.fill}
        stroke="none"
      />

      <text
        x={rect.x + 14}
        y={
          lines.length > 1
            ? rect.y + 23
            : device.subtitle
              ? rect.y + 24
              : rect.y + 33
        }
        fill={DIAGRAM_THEME.device.text}
        fontSize={13}
        fontWeight={700}
        fontFamily="Open Sans, Arial, sans-serif"
      >
        {lines.slice(0, 2).map((line, index) => (
          <tspan
            key={`${device.id}-${index}`}
            x={rect.x + 14}
            dy={index === 0 ? 0 : 16}
          >
            {line}
          </tspan>
        ))}
      </text>

      {device.subtitle && (
        <text
          x={rect.x + 14}
          y={rect.y + rect.height - 9}
          fill={DIAGRAM_THEME.device.subtitle}
          fontSize={11}
          fontFamily="Open Sans, Arial, sans-serif"
        >
          {device.subtitle}
        </text>
      )}
    </g>
  );
}

// ============================================================
// МЕЖСЕТЕВОЙ ЭКРАН
// ============================================================

function FirewallNode({
  model,
}: {
  model: DiagramModel["firewall"];
}) {
  const { rect, flame, lines } = model;

  const flameCenterX = flame.x + flame.width / 2;
  const flameCenterY = flame.y + flame.height / 2;

  return (
    <g>
      {/* Корпус межсетевого экрана */}
      <rect
        x={rect.x}
        y={rect.y}
        width={rect.width}
        height={rect.height}
        rx={6}
        fill={DIAGRAM_THEME.firewall.fill}
        stroke={DIAGRAM_THEME.firewall.stroke}
        strokeWidth={2}
      />

      {/* Кирпичная структура */}
      {lines.map((line, index) => (
        <line
          key={`firewall-line-${index}`}
          x1={line.x1}
          y1={line.y1}
          x2={line.x2}
          y2={line.y2}
          stroke={DIAGRAM_THEME.firewall.stroke}
          strokeWidth={1.5}
        />
      ))}

      {/* Значок пламени */}
      <path
        transform={`translate(${flameCenterX}, ${flameCenterY})`}
        d="
          M 0,-20
          C 7,-10 13,-4 13,5
          C 13,13 7,19 0,19
          C -7,19 -13,13 -13,5
          C -13,0 -10,-4 -7,-8
          C -6,-4 -4,-2 -2,-2
          C -4,-8 -3,-14 0,-20 Z
        "
        fill={DIAGRAM_THEME.firewall.flame}
      />

      <path
        transform={`translate(${flameCenterX}, ${flameCenterY + 5})`}
        d="
          M 0,-9
          C 4,-4 6,-1 6,3
          C 6,8 3,11 0,11
          C -3,11 -6,8 -6,3
          C -6,0 -3,-4 0,-9 Z
        "
        fill={DIAGRAM_THEME.firewall.flameInner}
      />

      <text
        x={rect.x + rect.width / 2}
        y={rect.y + 81}
        fill={DIAGRAM_THEME.firewall.stroke}
        fontSize={13}
        fontWeight={700}
        textAnchor="middle"
        fontFamily="Open Sans, Arial, sans-serif"
      >
        МЭ
      </text>

      {model.side === "both" && (
        <text
          x={rect.x + rect.width / 2}
          y={rect.y + rect.height - 10}
          fill={DIAGRAM_THEME.text.primary}
          fontSize={8}
          textAnchor="middle"
        >
          Двусторонняя защита
        </text>
      )}
    </g>
  );
}

// ============================================================
// УЗЕЛ СИНОНИКСА
// ============================================================

function SynonyxNode({
  node,
}: {
  node: DiagramNode;
}) {
  const { rect } = node;

  const centerX = rect.x + rect.width / 2;

  const hexagonPoints = [
    `${rect.x + rect.width * 0.25},${rect.y}`,
    `${rect.x + rect.width * 0.75},${rect.y}`,
    `${rect.x + rect.width},${rect.y + rect.height / 2}`,
    `${rect.x + rect.width * 0.75},${rect.y + rect.height}`,
    `${rect.x + rect.width * 0.25},${rect.y + rect.height}`,
    `${rect.x},${rect.y + rect.height / 2}`,
  ].join(" ");

  return (
    <g>
      {node.shape === "hexagon" ? (
        <polygon
          points={hexagonPoints}
          fill={DIAGRAM_THEME.synonyx.nodeFill}
          stroke={DIAGRAM_THEME.synonyx.nodeBorder}
          strokeWidth={1}
        />
      ) : (
        <rect
          x={rect.x}
          y={rect.y}
          width={rect.width}
          height={rect.height}
          rx={12}
          fill={DIAGRAM_THEME.synonyx.nodeFill}
          stroke={DIAGRAM_THEME.synonyx.nodeBorder}
          strokeWidth={1}
        />
      )}

      <text
        x={centerX}
        y={rect.y + 35}
        fill={DIAGRAM_THEME.synonyx.nodeText}
        fontSize={10}
        fontWeight={700}
        textAnchor="middle"
        fontFamily="Open Sans, Arial, sans-serif"
      >
        {node.name}
      </text>
    </g>
  );
}

// ============================================================
// СКИО «СИНОНИКС»
// ============================================================

function SynonyxSection({
  model,
}: {
  model: DiagramModel["synonyx"];
}) {
  const { box, labelRect, nodeA, core, nodeB } = model;

  return (
    <g>
      <text
        x={labelRect.x + labelRect.width / 2}
        y={labelRect.y + 17}
        fill={DIAGRAM_THEME.segment.open}
        fontSize={13}
        fontWeight={700}
        textAnchor="middle"
        letterSpacing={0.5}
        fontFamily="Open Sans, Arial, sans-serif"
      >
        СИНОНИКС
      </text>

      <rect
        x={box.x}
        y={box.y}
        width={box.width}
        height={box.height}
        rx={10}
        fill={DIAGRAM_THEME.synonyx.background}
        stroke={DIAGRAM_THEME.synonyx.border}
        strokeWidth={2}
      />

      <SynonyxNode node={nodeA} />
      <SynonyxNode node={core} />
      <SynonyxNode node={nodeB} />

      <text
        x={box.x + box.width / 2}
        y={box.y + box.height - 5}
        fill={DIAGRAM_THEME.synonyx.secondaryText}
        fontSize={9}
        textAnchor="middle"
        fontFamily="Open Sans, Arial, sans-serif"
      >
        ПАК версии 1.9
      </text>
    </g>
  );
}

// ============================================================
// ЛИНИИ ПЕРЕДАЧИ
// ============================================================

function ConnectionPath({
  model,
}: {
  model: DiagramModel;
}) {
  return (
    <g>
      {model.connections.map((connection) => (
        <path
          key={connection.id}
          d={createPath(connection.points)}
          fill="none"
          stroke={connection.color}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          markerEnd={`url(#${getArrowId(connection.ruleId)})`}
          markerStart={
            connection.mode === "two-way"
              ? `url(#${getArrowId(connection.ruleId)})`
              : undefined
          }
        />
      ))}
    </g>
  );
}

// ============================================================
// ПОДПИСИ СОЕДИНЕНИЙ
// ============================================================

function ConnectionLabels({
  model,
}: {
  model: DiagramModel;
}) {
  return (
    <g>
      {model.connections.map((connection) => {
        if (!connection.label) return null;

        const rect = connection.labelRect;

        return (
          <g key={`label-${connection.id}`}>
            <rect
              x={rect.x}
              y={rect.y}
              width={rect.width}
              height={rect.height}
              rx={9}
              fill={DIAGRAM_THEME.label.background}
              stroke="none"
            />

            <text
              x={rect.x + rect.width / 2}
              y={rect.y + 12}
              fill={DIAGRAM_THEME.label.text}
              fontSize={10}
              fontWeight={700}
              textAnchor="middle"
              fontFamily="Open Sans, Arial, sans-serif"
            >
              {connection.label}
            </text>
          </g>
        );
      })}
    </g>
  );
}

// ============================================================
// USB-НОСИТЕЛЬ
// ============================================================

function UsbNodes({
  model,
}: {
  model: DiagramModel;
}) {
  return (
    <g>
      {model.usb.map((item) => {
        const { rect, labelRect, color } = item;

        return (
          <g key={`usb-${item.ruleId}`}>
            <rect
              x={rect.x}
              y={rect.y}
              width={rect.width}
              height={rect.height}
              rx={17}
              fill={DIAGRAM_THEME.device.fill}
              stroke="#B9C5CD"
              strokeWidth={1}
            />

            <text
              x={rect.x + rect.width / 2}
              y={rect.y + 22}
              fill={DIAGRAM_THEME.device.text}
              fontSize={11}
              fontWeight={700}
              textAnchor="middle"
              fontFamily="Open Sans, Arial, sans-serif"
            >
              USB-носитель
            </text>

            <rect
              x={labelRect.x}
              y={labelRect.y}
              width={labelRect.width}
              height={labelRect.height}
              rx={9}
              fill={DIAGRAM_THEME.label.background}
            />

            <text
              x={labelRect.x + labelRect.width / 2}
              y={labelRect.y + 12}
              fill={color}
              fontSize={10}
              fontWeight={700}
              textAnchor="middle"
              fontFamily="Open Sans, Arial, sans-serif"
            >
              {item.label}
            </text>
          </g>
        );
      })}
    </g>
  );
}

// ============================================================
// ЛЕГЕНДА
// ============================================================

function DiagramLegend({
  model,
}: {
  model: DiagramModel;
}) {
  return (
    <g>
      <text
        x={model.footerTitle.x}
        y={model.footerTitle.y + 20}
        fill={DIAGRAM_THEME.text.primary}
        fontSize={13}
        fontWeight={700}
        fontFamily="Open Sans, Arial, sans-serif"
      >
        {model.footerTitle.text}
      </text>

      {model.legend.map((item) => (
        <g key={item.id}>
          <rect
            x={item.bullet.x}
            y={item.bullet.y}
            width={item.bullet.width}
            height={item.bullet.height}
            rx={3}
            fill={item.color}
          />

          <text
            x={item.textRect.x}
            y={item.textRect.y + 19}
            fill={DIAGRAM_THEME.text.primary}
            fontSize={11}
            fontFamily="Open Sans, Arial, sans-serif"
          >
            {item.text}
          </text>
        </g>
      ))}

      <text
        x={model.footerNote.rect.x}
        y={model.footerNote.rect.y + 19}
        fill={DIAGRAM_THEME.text.secondary}
        fontSize={11}
        fontFamily="Open Sans, Arial, sans-serif"
      >
        {model.footerNote.text}
      </text>
    </g>
  );
}

// ============================================================
// КАРТОЧКА ПРАВИЛА ПОД СХЕМОЙ
// ============================================================

function RuleFlow({
  rule,
  result,
  color,
}: {
  rule: Rule;
  result: Result;
  color: string;
}) {
  const isUsb = rule.transport === "usb";

  const from = isUsb
    ? rule.from
    : getDeviceName(result, rule.from_device_id);

  const to = isUsb
    ? rule.to
    : getDeviceName(result, rule.to_device_id);

  const isTwoWay = rule.mode === "two-way";

  return (
    <div
      className="diagram-rule"
      style={{
        borderLeftColor: color,
      }}
    >
      <div className="diagram-rule__head">
        <div className="diagram-rule__title">
          <span style={{ color }}>● </span>
          Правило №{rule.id}
          {" · "}
          {rule.type === "data" ? "Данные" : "Файлы"}
          {isUsb ? " · USB" : ""}
        </div>

        <span className="diagram-rule__mode">
          {isTwoWay
            ? "Двунаправленное"
            : "Однонаправленное"}
        </span>
      </div>

      <div className="diagram-rule__flow">
        <span>{from}</span>

        <span
          className="diagram-rule__arrow"
          style={{ color }}
        >
          {isTwoWay ? "↔" : "→"}
        </span>

        <span>{to}</span>
      </div>

      <div className="diagram-rule__desc">
        {rule.description}
      </div>

      <div className="diagram-rule__meta">
        {getProtocolLabel(rule)}
        {rule.port != null
          ? ` · порт ${rule.port}`
          : ""}
      </div>
    </div>
  );
}

// ============================================================
// ОСНОВНОЙ КОМПОНЕНТ
// ============================================================

export default function DiagramPreview({
  result,
}: {
  result: Result;
}) {
  // Общая модель схемы.
  // Координаты и цвета берутся из diagram.ts.
  const model = useMemo(
    () => buildDiagramModel(result),
    [result],
  );

  const viewportRef = useRef<HTMLDivElement>(null);

  const [viewportWidth, setViewportWidth] = useState(0);
  const [zoom, setZoom] = useState<number | null>(null);

  // Определяем ширину области просмотра.
  useEffect(() => {
    const element = viewportRef.current;

    if (!element) return;

    const updateWidth = () => {
      setViewportWidth(element.clientWidth);
    };

    updateWidth();

    const observer = new ResizeObserver(updateWidth);
    observer.observe(element);

    return () => observer.disconnect();
  }, []);

  // Масштаб, при котором схема полностью помещается по ширине.
  const fitScale = Math.max(
    0.35,
    Math.min(
      1,
      viewportWidth > 0
        ? viewportWidth / model.width
        : 1,
    ),
  );

  const scale = zoom ?? fitScale;

  const zoomIn = () => {
    setZoom((current) =>
      Math.min(
        2.5,
        (current ?? fitScale) + 0.15,
      ),
    );
  };

  const zoomOut = () => {
    setZoom((current) =>
      Math.max(
        0.35,
        (current ?? fitScale) - 0.15,
      ),
    );
  };

  const fitDiagram = () => {
    setZoom(fitScale);
  };

  const handleWheel = (
    event: WheelEvent<HTMLDivElement>,
  ) => {
    if (!event.ctrlKey) return;

    event.preventDefault();

    setZoom((current) =>
      Math.max(
        0.35,
        Math.min(
          2.5,
          (current ?? fitScale) +
            (event.deltaY < 0 ? 0.1 : -0.1),
        ),
      ),
    );
  };

  // Уникальные маркеры для правил.
  const arrowRules = Array.from(
    new Map(
      model.connections.map((connection) => [
        connection.ruleId,
        {
          ruleId: connection.ruleId,
          color: connection.color,
        },
      ]),
    ).values(),
  );

  return (
    <div className="diagram-card">
      {/* Заголовок и управление масштабом */}
      <div className="diagram-toolbar">
        <div className="diagram-card__title">
          Схема взаимодействия сетей
        </div>

        <div className="diagram-controls">
          <button
            type="button"
            onClick={() =>
              downloadDrawioXml(buildDrawioXml(result))
            }
            className="diagram-btn"
          >
            Скачать .drawio
          </button>

          <button
            type="button"
            onClick={zoomOut}
            className="diagram-btn"
            aria-label="Уменьшить схему"
          >
            −
          </button>

          <span className="diagram-zoom">
            {Math.round(scale * 100)}%
          </span>

          <button
            type="button"
            onClick={zoomIn}
            className="diagram-btn"
            aria-label="Увеличить схему"
          >
            +
          </button>

          <button
            type="button"
            onClick={fitDiagram}
            className="diagram-btn"
          >
            Показать целиком
          </button>
        </div>
      </div>

      {/* Область отображения SVG */}
      <div
        ref={viewportRef}
        onWheel={handleWheel}
        className="diagram-frame"
      >
        <svg
          viewBox={`0 0 ${model.width} ${model.height}`}
          width={model.width * scale}
          height={model.height * scale}
          role="img"
          aria-label="Схема взаимодействия открытой и закрытой сетей через межсетевой экран и Синоникс"
          className="block max-w-none"
        >
          {/* Фон */}
          <rect
            x={0}
            y={0}
            width={model.width}
            height={model.height}
            fill={model.background}
          />

          <defs>
            {arrowRules.map((item) => (
              <marker
                key={item.ruleId}
                id={getArrowId(item.ruleId)}
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path
                  d="M 0 0 L 10 5 L 0 10 z"
                  fill={item.color}
                />
              </marker>
            ))}
          </defs>

          {/* Заголовок схемы */}
          <text
            x={40}
            y={36}
            fill={DIAGRAM_THEME.text.primary}
            fontSize={20}
            fontWeight={700}
            fontFamily="Open Sans, Arial, sans-serif"
          >
            {model.title}
          </text>

          <text
            x={40}
            y={59}
            fill={DIAGRAM_THEME.text.secondary}
            fontSize={12}
            fontFamily="Open Sans, Arial, sans-serif"
          >
            {model.subtitle}
          </text>

          {/* Сетевые сегменты */}
          <NetworkSection
            rect={model.openSegment}
            title="ОТКРЫТАЯ СЕТЬ"
            subtitle={model.openNetworkName}
            color={DIAGRAM_THEME.segment.open}
          />

          <NetworkSection
            rect={model.closedSegment}
            title="ЗАКРЫТЫЙ СЕГМЕНТ"
            subtitle={model.closedNetworkName}
            color={DIAGRAM_THEME.segment.closed}
          />

          {/* Линии передачи рисуются под блоками устройств */}
          <ConnectionPath model={model} />

          {/* Межсетевой экран */}
          <FirewallNode model={model.firewall} />

          {/* Устройства */}
          {model.devices.map((device) => (
            <DeviceNode
              key={device.id}
              device={device}
            />
          ))}

          {/* Синоникс */}
          <SynonyxSection model={model.synonyx} />

          {/* USB-носители */}
          <UsbNodes model={model} />

          {/* Подписи линий располагаются поверх схемы */}
          <ConnectionLabels model={model} />

          {/* Нижняя информация и легенда */}
          <DiagramLegend model={model} />
        </svg>
      </div>

      <div className="diagram-note">
        Управление схемой: кнопки масштабирования или Ctrl + прокрутка
        колеса мыши. Кнопка «Показать целиком» подбирает масштаб
        для отображения всей схемы.
      </div>

      {/* Список правил */}
      {result.rules.length > 0 && (
        <div>
          <div className="diagram-card__title diagram-card__title--block">
            Потоки передачи через Синоникс
          </div>

          <div className="diagram-rules">
            {result.rules.map((rule, index) => (
              <RuleFlow
                key={rule.id}
                rule={rule}
                result={result}
                color={getRuleColor(index)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Нижнее пояснение */}
      <div className="diagram-footer">
        <div className="diagram-footer__title">
          Правил Синоникса: {result.rules_count}
        </div>

        <p className="diagram-footer__text">
          Межсетевой экран обеспечивает фильтрацию трафика.
          Синоникс размещается в закрытом сегменте за МЭ.
          USB-носитель подключается к Узлу А в обход межсетевого экрана.
        </p>
      </div>
    </div>
  );
}
