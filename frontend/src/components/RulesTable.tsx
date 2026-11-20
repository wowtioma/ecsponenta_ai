import type { Result, Rule } from "../types";
import { checksLabel, modeLabel, netName, typeLabel } from "../lib/format";

const unknownCls = "italic text-amber-400";
const headers = [
  "№",
  "Источник",
  "Получатель",
  "Тип обмена",
  "Режим",
  "Протокол / порт",
  "Проверки",
  "Обоснование",
];

function ProtocolCell({ rule }: { rule: Rule }) {
  if (rule.protocol) {
    return (
      <>
        <span>
  {typeof rule.protocol === "string"
    ? rule.protocol
    : rule.protocol
      ? `Открытая: ${rule.protocol.open ?? "не указано"} / Закрытая: ${rule.protocol.closed ?? "не указано"}`
      : "Не указан"}
</span>
        {rule.port ? (
          <span> {rule.port}</span>
        ) : rule.type === "data" ? (
          <div className={unknownCls}>порт не определён</div>
        ) : null}
      </>
    );
  }
  if (rule.type === "file") return <span className={unknownCls}>методы не определены</span>;
  return <span className={unknownCls}>не указан</span>;
}

function ChecksCell({ rule }: { rule: Rule }) {
  if (rule.type !== "file") return <span className="text-zinc-500">—</span>;
  const c = checksLabel(rule);
  return c ? <span>{c}</span> : <span className={unknownCls}>не указаны</span>;
}

export default function RulesTable({ result }: { result: Result }) {
  if (result.rules.length === 0) {
    return <p className="p-4 text-sm text-zinc-500">Правила ещё не определены.</p>;
  }

  return (
    <div className="p-3">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-left text-xs">
          <thead className="text-zinc-400">
            <tr>
              {headers.map((h) => (
                <th key={h} className="border-b border-zinc-800 px-2 py-2 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rules.map((r) => (
              <tr key={r.id} className="align-top border-b border-zinc-900">
                <td className="px-2 py-2 font-semibold">{r.id}</td>
                <td className="px-2 py-2">{netName(result, r.from)}</td>
                <td className="px-2 py-2">{netName(result, r.to)}</td>
                <td className="px-2 py-2">
                  <div>{typeLabel(r.type)}</div>
                  <div className="text-zinc-400">{r.description}</div>
                </td>
                <td className="px-2 py-2">{modeLabel(r.mode)}</td>
                <td className="px-2 py-2">
                  <ProtocolCell rule={r} />
                </td>
                <td className="px-2 py-2">
                  <ChecksCell rule={r} />
                </td>
                <td className="px-2 py-2 text-zinc-300">
                  {r.justification ?? <span className={unknownCls}>не указано</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-zinc-500">
        Для двунаправленных правил источник это сторона-инициатор.
      </p>
      {result.rules.length !== result.rules_count && (
        <p className="mt-1 text-xs text-red-400">
          Внимание: rules_count ({result.rules_count}) не равен числу правил ({result.rules.length}).
        </p>
      )}
    </div>
  );
}