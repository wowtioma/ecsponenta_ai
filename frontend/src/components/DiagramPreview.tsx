
import { useState } from "react";
import type { PointerEvent, WheelEvent } from "react";
import type { Result, Rule } from "../types";

const RULE_COLORS = [
  "#38BDF8",
  "#FBBF24",
  "#C084FC",
  "#4ADE80",
  "#FB7185",
  "#F97316",
];

const SVG_WIDTH = 1120;

const LAYOUT = {
  openX: 15,
  openWidth: 255,
  firewallX: 300,
  firewallWidth: 90,
  synonyxX: 440,
  synonyxWidth: 300,
  closedX: 790,
  closedWidth: 315,
  deviceStartY: 80,
  deviceStep: 70,
  deviceHeight: 58,
};

function getRuleColor(index: number) {
  return RULE_COLORS[index % RULE_COLORS.length];
}

function getDeviceName(result: Result, deviceId?: string | null) {
  if (!deviceId) return "Устройство не указано";

  return (
    result.devices.find((device) => device.id === deviceId)?.name ??
    "Устройство не найдено"
  );
}

function getProtocol(rule: Rule) {
  if (rule.transport === "usb") return "USB-носитель";

  if (typeof rule.protocol === "string") {
    return rule.protocol;
  }

  if (rule.protocol && typeof rule.protocol === "object") {
    const open = rule.protocol.open ?? "не указан";
    const closed = rule.protocol.closed ?? "не указан";

    return `Открытая: ${open} · Закрытая: ${closed}`;
  }

  return rule.type === "file"
    ? "Способ передачи не указан"
    : "Не указан";
}

function getShortProtocol(rule: Rule) {
  if (rule.transport === "usb") return "USB";

  if (typeof rule.protocol === "string") {
    return rule.protocol;
  }

  if (rule.protocol && typeof rule.protocol === "object") {
    return (
      rule.protocol.open ??
      rule.protocol.closed ??
      "Протокол"
    );
  }

  return "Протокол";
}

function splitDeviceName(name: string) {
  const words = name.split(" ");
  const lines: string[] = [];
  let current = "";

  words.forEach((word) => {
    const next = current ? `${current} ${word}` : word;

    if (next.length > 25 && current) {
      lines.push(current);
      current = word;
    } else {
      current = next;
    }
  });

  if (current) lines.push(current);

  return lines.slice(0, 2);
}

function createPath(points: [number, number][]) {
  return points
    .map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x} ${y}`)
    .join(" ");
}

function DeviceNode({
  x,
  y,
  width,
  name,
  color,
}: {
  x: number;
  y: number;
  width: number;
  name: string;
  color: "orange" | "teal";
}) {
  const lines = splitDeviceName(name);
  const accent = color === "orange" ? "#FDBA74" : "#5EEAD4";

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={58}
        rx={8}
        fill="#334155"
        stroke={accent}
        strokeWidth={1}
      />

      <rect
        x={x}
        y={y}
        width={5}
        height={58}
        rx={2}
        fill={accent}
      />

      <text
        x={x + width / 2}
        y={lines.length > 1 ? y + 25 : y + 34}
        fill="#F8FAFC"
        fontSize={13}
        fontWeight={500}
        textAnchor="middle"
      >
        {lines.map((line, index) => (
          <tspan
            key={index}
            x={x + width / 2}
            dy={index === 0 ? 0 : 17}
          >
            {line}
          </tspan>
        ))}
      </text>
    </g>
  );
}

function NetworkSection({
  x,
  y,
  width,
  height,
  title,
  subtitle,
  devices,
  color,
}: {
  x: number;
  y: number;
  width: number;
  height: number;
  title: string;
  subtitle: string;
  devices: Result["devices"];
  color: "orange" | "teal";
}) {
  const accent = color === "orange" ? "#F97316" : "#2DD4BF";

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx={13}
        fill="#1E293B"
        stroke={accent}
        strokeWidth={2}
        strokeDasharray="7 5"
      />

      <text
        x={x + 16}
        y={y + 27}
        fill={accent}
        fontSize={12}
        fontWeight={700}
        letterSpacing={1}
      >
        {title}
      </text>

      <text
        x={x + 16}
        y={y + 49}
        fill="#F8FAFC"
        fontSize={14}
        fontWeight={600}
      >
        {subtitle}
      </text>

      {devices.length > 0 ? (
        devices.map((device, index) => (
          <DeviceNode
            key={device.id}
            x={x + 12}
            y={y + 65 + index * 70}
            width={width - 24}
            name={device.name}
            color={color}
          />
        ))
      ) : (
        <text
          x={x + width / 2}
          y={y + 105}
          fill="#94A3B8"
          fontSize={12}
          textAnchor="middle"
        >
          Устройства пока не указаны
        </text>
      )}
    </g>
  );
}

function FirewallNode({
  x,
  y,
  firewallSide,
}: {
  x: number;
  y: number;
  firewallSide: string;
}) {
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={90}
        height={112}
        rx={10}
        fill="#334155"
        stroke="#FB923C"
        strokeWidth={2}
      />

      <text
        x={x + 45}
        y={y + 43}
        fill="#FDBA74"
        fontSize={29}
        textAnchor="middle"
      >
        ▥
      </text>

      <text
        x={x + 45}
        y={y + 68}
        fill="#FFFFFF"
        fontSize={15}
        fontWeight={700}
        textAnchor="middle"
      >
        МЭ
      </text>

      <text
        x={x + 45}
        y={y + 132}
        fill="#CBD5E1"
        fontSize={11}
        textAnchor="middle"
      >
        Межсетевой
      </text>

      <text
        x={x + 45}
        y={y + 146}
        fill="#CBD5E1"
        fontSize={11}
        textAnchor="middle"
      >
        экран
      </text>

      {firewallSide === "both" && (
        <text
          x={x + 45}
          y={y + 163}
          fill="#FDBA74"
          fontSize={9}
          textAnchor="middle"
        >
          Защита с двух сторон
        </text>
      )}
    </g>
  );
}

function SynonyxSection({
  x,
  y,
  nodeHeight,
}: {
  x: number;
  y: number;
  nodeHeight: number;
}) {
  const nodeY = y + 48;

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={300}
        height={nodeHeight + 48}
        rx={13}
        fill="#F1F5F9"
        stroke="#F97316"
        strokeWidth={3}
      />

      <text
        x={x + 150}
        y={y + 29}
        fill="#0F172A"
        fontSize={16}
        fontWeight={700}
        textAnchor="middle"
      >
        СКИО «Синоникс»
      </text>

      <rect
        x={x + 12}
        y={nodeY}
        width={84}
        height={nodeHeight}
        rx={7}
        fill="#CBD5E1"
      />

      <rect
        x={x + 108}
        y={nodeY}
        width={84}
        height={nodeHeight}
        rx={7}
        fill="#94A3B8"
      />

      <rect
        x={x + 204}
        y={nodeY}
        width={84}
        height={nodeHeight}
        rx={7}
        fill="#CBD5E1"
      />

      <text
        x={x + 54}
        y={nodeY + 26}
        fill="#0F172A"
        fontSize={13}
        fontWeight={700}
        textAnchor="middle"
      >
        Узел А
      </text>

      <text
        x={x + 54}
        y={nodeY + 45}
        fill="#475569"
        fontSize={10}
        textAnchor="middle"
      >
        Открытая сеть
      </text>

      <text
        x={x + 150}
        y={nodeY + 26}
        fill="#0F172A"
        fontSize={13}
        fontWeight={700}
        textAnchor="middle"
      >
        Ядро
      </text>

      <text
        x={x + 150}
        y={nodeY + 45}
        fill="#475569"
        fontSize={10}
        textAnchor="middle"
      >
        Изоляция
      </text>

      <text
        x={x + 246}
        y={nodeY + 26}
        fill="#0F172A"
        fontSize={13}
        fontWeight={700}
        textAnchor="middle"
      >
        Узел В
      </text>

      <text
        x={x + 246}
        y={nodeY + 45}
        fill="#475569"
        fontSize={10}
        textAnchor="middle"
      >
        Закрытая сеть
      </text>

      <text
        x={x + 150}
        y={nodeY + nodeHeight - 9}
        fill="#64748B"
        fontSize={10}
        textAnchor="middle"
      >
        ПАК версии 1.9
      </text>
    </g>
  );
}

// USB подключается отдельно и только к Узлу А.
function UsbConnection({
  rules,
  synonyxX,
  synonyxY,
}: {
  rules: { rule: Rule; color: string }[];
  synonyxX: number;
  synonyxY: number;
}) {
  if (rules.length === 0) return null;

  const centerX = synonyxX + 54;
  const usbY = synonyxY - 43;
  const nodeAY = synonyxY + 48;

  return (
    <g>
      {rules.map(({ rule, color }, index) => {
        const offset = (index - (rules.length - 1) / 2) * 6;
        const startX = centerX + offset;

        const points: [number, number][] = [
          [startX, usbY + 25],
          [startX, usbY + 34],
          [startX, nodeAY - 12],
          [centerX, nodeAY],
        ];

        return (
          <g key={rule.id}>
            <path
              d={createPath(points)}
              fill="none"
              stroke={color}
              strokeWidth={2.5}
              strokeLinecap="round"
              strokeLinejoin="round"
              markerEnd={`url(#arrow-${rule.id})`}
            />

            <rect
              x={synonyxX + 105}
              y={usbY - 2 + index * 17}
              width={155}
              height={15}
              rx={4}
              fill="#0F172A"
              stroke={color}
              strokeWidth={0.8}
            />

            <text
              x={synonyxX + 182}
              y={usbY + 9 + index * 17}
              fill={color}
              fontSize={9}
              fontWeight={700}
              textAnchor="middle"
            >
              {`№${rule.id} · USB`}
            </text>
          </g>
        );
      })}

      <g>
        <rect
          x={centerX - 27}
          y={usbY}
          width={54}
          height={25}
          rx={5}
          fill="#475569"
          stroke="#CBD5E1"
          strokeWidth={1.5}
        />

        <rect
          x={centerX - 27}
          y={usbY + 5}
          width={12}
          height={15}
          rx={2}
          fill="#94A3B8"
        />

        <rect
          x={centerX - 15}
          y={usbY + 8}
          width={8}
          height={9}
          rx={1}
          fill="#CBD5E1"
        />

        <text
          x={centerX + 7}
          y={usbY + 16}
          fill="#FFFFFF"
          fontSize={10}
          fontWeight={700}
          textAnchor="middle"
        >
          USB
        </text>

        <text
          x={centerX}
          y={usbY - 5}
          fill="#E2E8F0"
          fontSize={10}
          fontWeight={600}
          textAnchor="middle"
        >
          USB-носитель
        </text>
      </g>
    </g>
  );
}

function RuleConnection({
  rule,
  result,
  openDevices,
  closedDevices,
  index,
  color,
  synonyxY,
  svgHeight,
}: {
  rule: Rule;
  result: Result;
  openDevices: Result["devices"];
  closedDevices: Result["devices"];
  index: number;
  color: string;
  synonyxY: number;
  svgHeight: number;
}) {
  if (rule.transport === "usb") return null;

  const fromDevice = result.devices.find(
    (device) => device.id === rule.from_device_id
  );

  const toDevice = result.devices.find(
    (device) => device.id === rule.to_device_id
  );

  if (!fromDevice || !toDevice) return null;

  const openNetworkId = openDevices[0]?.network_id;
  const closedNetworkId = closedDevices[0]?.network_id;

  const fromIsOpen = fromDevice.network_id === openNetworkId;
  const fromIsClosed = fromDevice.network_id === closedNetworkId;
  const toIsOpen = toDevice.network_id === openNetworkId;
  const toIsClosed = toDevice.network_id === closedNetworkId;

  const isOpenToClosed = fromIsOpen && toIsClosed;
  const isClosedToOpen = fromIsClosed && toIsOpen;

  if (!isOpenToClosed && !isClosedToOpen) return null;

  const openDevice = isOpenToClosed ? fromDevice : toDevice;
  const closedDevice = isOpenToClosed ? toDevice : fromDevice;

  const openIndex = openDevices.findIndex(
    (device) => device.id === openDevice.id
  );

  const closedIndex = closedDevices.findIndex(
    (device) => device.id === closedDevice.id
  );

  if (openIndex < 0 || closedIndex < 0) return null;

  // Центры карточек устройств.
  // NetworkSection начинается с y=15, а карточки — с y=80.
  const openY =
    LAYOUT.deviceStartY +
    openIndex * LAYOUT.deviceStep +
    LAYOUT.deviceHeight / 2;

  const closedY =
    LAYOUT.deviceStartY +
    closedIndex * LAYOUT.deviceStep +
    LAYOUT.deviceHeight / 2;

  // Положение внутренних портов Синоникса.
  const nodeY = synonyxY + 48;
  const portY = nodeY + 58 + index * 10;

  // Границы внутренних компонентов.
  const nodeALeft = LAYOUT.synonyxX + 12;
  const nodeARight = LAYOUT.synonyxX + 96;

  const coreLeft = LAYOUT.synonyxX + 108;
  const coreRight = LAYOUT.synonyxX + 192;

  const nodeBLeft = LAYOUT.synonyxX + 204;
  const nodeBRight = LAYOUT.synonyxX + 288;

  // Каналы обхода межсетевого экрана.
  const firewallCenter = svgHeight / 2;
  const firewallTop = firewallCenter - 75;
  const firewallBottom = firewallCenter + 37;

  const laneNumber = Math.floor(index / 2);

  const firewallLaneY =
    index % 2 === 0
      ? firewallTop - 12 - laneNumber * 10
      : firewallBottom + 12 + laneNumber * 10;

  const openLaneX = 276 + (index % 10) * 2;
  const closedLaneX = 770 + (index % 10) * 2;

  // Базовый маршрут: открытая сеть → Синоникс → закрытая сеть.
  const openToClosedPoints: [number, number][] = [
    // Конкретное устройство открытой сети.
    [LAYOUT.openX + LAYOUT.openWidth - 12, openY],
    [openLaneX, openY],

    // Обход межсетевого экрана.
    [openLaneX, firewallLaneY],
    [410, firewallLaneY],
    [410, portY],

    // Вход в Узел А.
    [nodeALeft, portY],
    [nodeARight, portY],

    // Прохождение через Ядро.
    [coreLeft, portY],
    [coreRight, portY],

    // Прохождение через Узел В.
    [nodeBLeft, portY],
    [nodeBRight, portY],

    // Выход к конкретному устройству закрытой сети.
    [closedLaneX, portY],
    [closedLaneX, closedY],
    [LAYOUT.closedX + 12, closedY],
  ];

  // Для обратного направления разворачиваем весь маршрут.
  const points = isOpenToClosed
    ? openToClosedPoints
    : [...openToClosedPoints].reverse();

  const path = createPath(points);

  const isTwoWay = rule.mode === "two-way";
  const protocol = getShortProtocol(rule);
  const label = `№${rule.id} · ${protocol} · ${rule.port ?? "—"}`;

  // Подписи располагаются в отдельной области над Синониксом.
  const labelY = 30 + index * 14;

  return (
    <g>
      <path
        d={path}
        fill="none"
        stroke={color}
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={0.95}
        markerEnd={`url(#arrow-${rule.id})`}
        markerStart={
          isTwoWay ? `url(#arrow-${rule.id})` : undefined
        }
      />

      <text
        x={590}
        y={labelY}
        fill={color}
        fontSize={10}
        fontWeight={700}
        textAnchor="middle"
      >
        {label}
      </text>
    </g>
  );
}

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
      className="rounded-lg border border-slate-700 border-l-4 bg-slate-800/70 p-3"
      style={{ borderLeftColor: color }}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-semibold text-slate-300">
          <span style={{ color }}>● </span>
          Правило №{rule.id} · {rule.type === "data" ? "Данные" : "Файлы"}
          {isUsb ? " · USB" : ""}
        </div>

        <span className="rounded-full bg-slate-700 px-2 py-1 text-[10px] text-slate-300">
          {isTwoWay ? "Двунаправленное" : "Однонаправленное"}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-slate-200">{from}</span>

        <span className="font-semibold" style={{ color }}>
          {isTwoWay ? "↔" : "→"}
        </span>

        <span className="text-slate-200">{to}</span>
      </div>

      <div className="mt-2 text-xs text-slate-400">
        {rule.description}
      </div>

      <div className="mt-1 text-xs text-slate-400">
        {getProtocol(rule)}
        {rule.port != null ? ` · порт ${rule.port}` : ""}
      </div>
    </div>
  );
}

export default function DiagramPreview({
  result,
}: {
  result: Result;
}) {
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);

  const [dragStart, setDragStart] = useState({
    x: 0,
    y: 0,
  });

  const openNetwork = result.networks.find(
    (network) => network.trust === "open"
  );

  const closedNetwork = result.networks.find(
    (network) => network.trust === "closed"
  );

  const openDevices = result.devices.filter(
    (device) => device.network_id === openNetwork?.id
  );

  const closedDevices = result.devices.filter(
    (device) => device.network_id === closedNetwork?.id
  );

  const firewallSide = result.firewall?.side ?? "open";

  const networkRules = result.rules.filter(
    (rule) => rule.transport !== "usb"
  );

  const maxDevices = Math.max(
    openDevices.length,
    closedDevices.length,
    1
  );

  // Высота компонентов увеличивается при добавлении правил.
  const nodeHeight = Math.max(
    85,
    58 + networkRules.length * 10 + 10
  );

  const synonyxHeight = nodeHeight + 48;
  const synonyxY = 130 + networkRules.length * 14;

  const svgHeight = Math.max(
    300,
    105 + maxDevices * 70,
    synonyxY + synonyxHeight + 80,
    260 + result.rules.length * 20
  );

  const usbRules = result.rules
    .map((rule, index) => ({
      rule,
      color: getRuleColor(index),
    }))
    .filter(({ rule }) => rule.transport === "usb");

  const handleZoomIn = () => {
    setScale((current) => Math.min(2.5, current + 0.15));
  };

  const handleZoomOut = () => {
    setScale((current) => Math.max(0.5, current - 0.15));
  };

  const handleFit = () => {
    setScale(1);
    setOffset({ x: 0, y: 0 });
  };

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;

    setDragging(true);

    setDragStart({
      x: event.clientX - offset.x,
      y: event.clientY - offset.y,
    });

    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;

    setOffset({
      x: event.clientX - dragStart.x,
      y: event.clientY - dragStart.y,
    });
  };

  const handlePointerUp = () => {
    setDragging(false);
  };

  const handleWheel = (event: WheelEvent<HTMLDivElement>) => {
    if (!event.ctrlKey) return;

    event.preventDefault();

    setScale((current) =>
      Math.max(
        0.5,
        Math.min(2.5, current + (event.deltaY < 0 ? 0.1 : -0.1))
      )
    );
  };

  return (
    <div className="space-y-4 rounded-xl bg-[#303E48] p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-semibold text-white">
          Схема взаимодействия сетей
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleZoomOut}
            className="rounded-lg border border-slate-600 px-3 py-1.5 text-sm text-white hover:bg-slate-700"
          >
            −
          </button>

          <span className="min-w-12 text-center text-xs text-slate-300">
            {Math.round(scale * 100)}%
          </span>

          <button
            type="button"
            onClick={handleZoomIn}
            className="rounded-lg border border-slate-600 px-3 py-1.5 text-sm text-white hover:bg-slate-700"
          >
            +
          </button>

          <button
            type="button"
            onClick={handleFit}
            className="rounded-lg border border-slate-600 px-3 py-1.5 text-xs text-white hover:bg-slate-700"
          >
            Показать целиком
          </button>
        </div>
      </div>

      <div
        className="overflow-hidden rounded-lg bg-[#26343E]"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onWheel={handleWheel}
        style={{
          cursor: dragging ? "grabbing" : "grab",
          touchAction: "none",
        }}
      >
        <div
          style={{
            width: SVG_WIDTH,
            transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
            transformOrigin: "top left",
          }}
        >
          <svg
            viewBox={`0 0 ${SVG_WIDTH} ${svgHeight}`}
            width={SVG_WIDTH}
            height={svgHeight}
            role="img"
            aria-label="Схема взаимодействия открытой и закрытой сетей через межсетевой экран и Синоникс"
            className="block max-w-none"
          >
            <defs>
              {result.rules.map((rule, index) => {
                const color = getRuleColor(index);

                return (
                  <marker
                    key={rule.id}
                    id={`arrow-${rule.id}`}
                    viewBox="0 0 10 10"
                    refX="8"
                    refY="5"
                    markerWidth="6"
                    markerHeight="6"
                    orient="auto-start-reverse"
                  >
                    <path
                      d="M 0 0 L 10 5 L 0 10 z"
                      fill={color}
                    />
                  </marker>
                );
              })}
            </defs>

            {/* Открытая сеть */}
            <NetworkSection
              x={LAYOUT.openX}
              y={15}
              width={LAYOUT.openWidth}
              height={svgHeight - 30}
              title="ОТКРЫТАЯ СЕТЬ"
              subtitle={openNetwork?.name ?? "Открытая сеть"}
              devices={openDevices}
              color="orange"
            />

            {/* Межсетевой экран */}
            <FirewallNode
              x={LAYOUT.firewallX}
              y={svgHeight / 2 - 75}
              firewallSide={firewallSide}
            />

            {/* Синоникс */}
            <SynonyxSection
              x={LAYOUT.synonyxX}
              y={synonyxY}
              nodeHeight={nodeHeight}
            />

            {/* Закрытая сеть */}
            <NetworkSection
              x={LAYOUT.closedX}
              y={15}
              width={LAYOUT.closedWidth}
              height={svgHeight - 30}
              title="ЗАКРЫТАЯ СЕТЬ"
              subtitle={closedNetwork?.name ?? "Закрытая сеть"}
              devices={closedDevices}
              color="teal"
            />

            {/* Сетевые маршруты поверх компонентов Синоникса */}
            {networkRules.map((rule, index) => {
              const originalIndex = result.rules.findIndex(
                (item) => item.id === rule.id
              );

              return (
                <RuleConnection
                  key={rule.id}
                  rule={rule}
                  result={result}
                  openDevices={openDevices}
                  closedDevices={closedDevices}
                  index={index}
                  color={getRuleColor(originalIndex)}
                  synonyxY={synonyxY}
                  svgHeight={svgHeight}
                />
              );
            })}

            {/* USB подключается отдельно и только к Узлу А */}
            <UsbConnection
              rules={usbRules}
              synonyxX={LAYOUT.synonyxX}
              synonyxY={synonyxY}
            />

            <text
              x={285}
              y={svgHeight / 2 + 5}
              fill="#94A3B8"
              fontSize={18}
              textAnchor="middle"
            >
              →
            </text>

            <text
              x={420}
              y={svgHeight / 2 + 5}
              fill="#94A3B8"
              fontSize={18}
              textAnchor="middle"
            >
              →
            </text>

            <text
              x={760}
              y={svgHeight / 2 + 5}
              fill="#94A3B8"
              fontSize={18}
              textAnchor="middle"
            >
              →
            </text>
          </svg>
        </div>
      </div>

      <div className="text-xs text-slate-400">
        Управление схемой: кнопки масштабирования или Ctrl + прокрутка
        колеса мыши. Для перемещения зажми левую кнопку мыши и перетащи схему.
      </div>

      {result.rules.length > 0 && (
        <div>
          <div className="mb-2 text-sm font-semibold text-white">
            Потоки передачи через Синоникс
          </div>

          <div className="grid gap-2">
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

      <div className="border-t border-slate-600 pt-3 text-xs text-slate-300">
        <div className="font-semibold text-white">
          Правил Синоникса: {result.rules_count}
        </div>

        <p className="mt-1">
          Межсетевой экран обеспечивает базовую фильтрацию трафика.
          Синоникс размещается между межсетевым экраном и закрытой сетью.
        </p>
      </div>
    </div>
  );
}
