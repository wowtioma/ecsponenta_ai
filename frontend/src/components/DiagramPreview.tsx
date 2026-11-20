
import type { Result, Rule } from "../types";

function getNetworkName(result: Result, id: string) {
  return result.networks.find((network) => network.id === id)?.name ?? id;
}

function getProtocol(rule: Rule) {
  if (typeof rule.protocol === "string") {
    return rule.protocol;
  }

  if (rule.protocol && typeof rule.protocol === "object") {
    const open = rule.protocol.open ?? "не указан";
    const closed = rule.protocol.closed ?? "не указан";

    return `Открытая: ${open} · Закрытая: ${closed}`;
  }

  return rule.type === "file" ? "Способ передачи не указан" : "Не указан";
}

function NetworkCard({
  title,
  subtitle,
  devices,
  color,
}: {
  title: string;
  subtitle: string;
  devices: Result["devices"];
  color: "orange" | "teal";
}) {
  const border =
    color === "orange"
      ? "border-orange-500/70"
      : "border-teal-400/70";

  const accent =
    color === "orange" ? "text-orange-300" : "text-teal-300";

  return (
    <div className={`min-w-0 rounded-xl border-2 border-dashed ${border} bg-slate-800/60 p-3`}>
      <div className={`text-xs font-semibold tracking-wider ${accent}`}>
        {title}
      </div>

      <div className="mt-1 text-sm font-medium text-white">
        {subtitle}
      </div>

      <div className="mt-4 space-y-2">
        {devices.length > 0 ? (
          devices.map((device) => (
            <div
              key={device.id}
              className="rounded-lg bg-slate-700 px-3 py-2"
            >
              <div className="text-sm font-medium text-white">
                {device.name}
              </div>
            </div>
          ))
        ) : (
          <div className="rounded-lg border border-slate-600 border-dashed px-3 py-4 text-center text-xs text-slate-500">
            Устройства пока не указаны
          </div>
        )}
      </div>
    </div>
  );
}

function SynonyxCard() {
  return (
    <div className="rounded-xl border-2 border-orange-500 bg-slate-100 p-3 text-slate-900 shadow-lg">
      <div className="mb-3 text-center text-sm font-bold">
        СКИО «Синоникс»
      </div>

      <div className="grid grid-cols-3 gap-1">
        <div className="rounded-md bg-slate-300 p-2 text-center">
          <div className="text-xs font-bold">Узел А</div>
          <div className="mt-1 text-[10px] text-slate-600">Открытая сеть</div>
        </div>

        <div className="rounded-md bg-slate-300 p-2 text-center">
          <div className="text-xs font-bold">Ядро</div>
          <div className="mt-1 text-[10px] text-slate-600">Изоляция</div>
        </div>

        <div className="rounded-md bg-slate-300 p-2 text-center">
          <div className="text-xs font-bold">Узел В</div>
          <div className="mt-1 text-[10px] text-slate-600">Закрытая сеть</div>
        </div>
      </div>

      <div className="mt-2 text-center text-[10px] text-slate-600">
        ПАК версии 1.9
      </div>
    </div>
  );
}

function RuleFlow({ rule, result }: { rule: Rule; result: Result }) {
  const from = getNetworkName(result, rule.from);
  const to = getNetworkName(result, rule.to);
  const isTwoWay = rule.mode === "two-way";

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/70 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-semibold text-slate-300">
          Правило №{rule.id} · {rule.type === "data" ? "Данные" : "Файлы"}
        </div>

        <span className="rounded-full bg-slate-700 px-2 py-1 text-[10px] text-slate-300">
          {isTwoWay ? "Двунаправленное" : "Однонаправленное"}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-slate-200">{from}</span>

        <span className="font-semibold text-teal-300">
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

export default function DiagramPreview({ result }: { result: Result }) {
  const openNetwork = result.networks.find((network) => network.trust === "open");
  const closedNetwork = result.networks.find((network) => network.trust === "closed");

  const openDevices = result.devices.filter(
    (device) => device.network_id === openNetwork?.id
  );

  const closedDevices = result.devices.filter(
    (device) => device.network_id === closedNetwork?.id
  );

  const firewallSide = result.firewall?.side ?? "open";

  return (
    <div className="min-w-[680px] space-y-4 rounded-xl bg-[#303E48] p-4">
      <div className="grid grid-cols-[1fr_auto_1.2fr] items-stretch gap-3">
        <NetworkCard
          title="ОТКРЫТАЯ СЕТЬ"
          subtitle={openNetwork?.name ?? "Открытая сеть"}
          devices={openDevices}
          color="orange"
        />

        <div className="flex min-w-[76px] flex-col items-center justify-center gap-2">
          <div className="flex h-20 w-14 flex-col items-center justify-center rounded-md border border-orange-400 bg-slate-700">
            <div className="text-xl text-orange-300">▥</div>
            <div className="mt-1 text-xs font-bold text-white">МЭ</div>
          </div>

          <div className="text-center text-[10px] text-slate-400">
            Межсетевой экран
          </div>

          {firewallSide === "both" && (
            <div className="text-center text-[10px] text-orange-300">
              Защита с двух сторон
            </div>
          )}
        </div>

        <div className="min-w-0 rounded-xl border-2 border-teal-400 bg-slate-800/60 p-3">
          <div className="text-xs font-semibold tracking-wider text-teal-300">
            ЗАКРЫТЫЙ СЕГМЕНТ
          </div>

          <div className="mt-1 text-sm font-medium text-white">
            {closedNetwork?.name ?? "Закрытая сеть"}
          </div>

          <div className="mt-3">
            <SynonyxCard />
          </div>

          <div className="mt-3 space-y-2">
            {closedDevices.length > 0 ? (
              closedDevices.map((device) => (
                <div
                  key={device.id}
                  className="rounded-lg bg-slate-700 px-3 py-2"
                >
                  <div className="text-sm font-medium text-white">
                    {device.name}
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-lg border border-slate-600 border-dashed px-3 py-4 text-center text-xs text-slate-500">
                Устройства пока не указаны
              </div>
            )}
          </div>
        </div>
      </div>

      {result.rules.length > 0 && (
        <div>
          <div className="mb-2 text-sm font-semibold text-white">
            Потоки передачи через Синоникс
          </div>

          <div className="grid gap-2">
            {result.rules.map((rule) => (
              <RuleFlow key={rule.id} rule={rule} result={result} />
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
          Синоникс размещается в закрытом сегменте сразу за МЭ.
        </p>
      </div>
    </div>
  );
}
