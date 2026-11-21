
import type { Result, Rule } from "../types";
import {
  checksLabel,
  methodsLabel,
  modeLabel,
  netName,
  typeLabel,
} from "../lib/format";

const unknownCls = "italic text-amber-400";

const headers = [
  "№",
  "Источник",
  "Получатель",
  "Тип обмена",
  "Режим",
  "Протокол / порт",
  "Методы файлов",
  "Проверки файлов",
  "Обоснование",
];

// Отображение протокола и порта
function ProtocolCell({ rule }: { rule: Rule }) {
  if (rule.protocol) {
    const protocol =
      typeof rule.protocol === "string"
        ? rule.protocol
        : `Открытая: ${rule.protocol.open ?? "не указано"} / Закрытая: ${
            rule.protocol.closed ?? "не указано"
          }`;

    return (
      <div>
        <div>{protocol}</div>

        {rule.port != null ? (
          <div className="text-zinc-400">
            Порт: {rule.port}
          </div>
        ) : (
          <div className={unknownCls}>
            Порт: Не определён
          </div>
        )}
      </div>
    );
  }

  if (rule.type === "file") {
    return <span className="text-zinc-500">Не применимо</span>;
  }

  return <span className={unknownCls}>Не указан</span>;
}

// Методы файлового обмена
function MethodsCell({ rule }: { rule: Rule }) {
  if (rule.type !== "file") {
    return <span className="text-zinc-500">—</span>;
  }

  const methods = methodsLabel(rule);

  return methods ? (
    <span className="whitespace-pre-wrap">{methods}</span>
  ) : (
    <span className={unknownCls}>Не определены</span>
  );
}

// Проверки файлов
function ChecksCell({ rule }: { rule: Rule }) {
  if (rule.type !== "file") {
    return <span className="text-zinc-500">—</span>;
  }

  const checks = checksLabel(rule);

  return checks ? (
    <span className="whitespace-pre-wrap">{checks}</span>
  ) : (
    <span className={unknownCls}>Не указаны</span>
  );
}

// Основная таблица правил
export default function RulesTable({
  result,
}: {
  result: Result;
}) {
  if (result.rules.length === 0) {
    return (
      <p className="p-4 text-sm text-zinc-500">
        Правила ещё не определены.
      </p>
    );
  }

  return (
    <div className="p-3">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1100px] border-collapse text-left text-xs">
          <thead className="text-zinc-400">
            <tr>
              {headers.map((header) => (
                <th
                  key={header}
                  className="border-b border-zinc-800 px-3 py-3 font-medium"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {result.rules.map((rule) => (
              <tr
                key={rule.id}
                className="align-top border-b border-zinc-900 hover:bg-zinc-900/40"
              >
                <td className="px-3 py-3 font-semibold text-zinc-200">
                  {rule.id}
                </td>

                <td className="px-3 py-3 text-zinc-200">
                  {netName(result, rule.from)}
                </td>

                <td className="px-3 py-3 text-zinc-200">
                  {netName(result, rule.to)}
                </td>

                <td className="px-3 py-3">
                  <div className="font-medium text-zinc-200">
                    {typeLabel(rule.type)}
                  </div>

                  <div className="mt-1 text-zinc-400">
                    {rule.description || (
                      <span className={unknownCls}>
                        Описание не указано
                      </span>
                    )}
                  </div>
                </td>

                <td className="px-3 py-3 text-zinc-300">
                  {modeLabel(rule.mode)}
                </td>

                <td className="px-3 py-3 text-zinc-300">
                  <ProtocolCell rule={rule} />
                </td>

                <td className="px-3 py-3 text-zinc-300">
                  <MethodsCell rule={rule} />
                </td>

                <td className="px-3 py-3 text-zinc-300">
                  <ChecksCell rule={rule} />
                </td>

                <td className="px-3 py-3 text-zinc-300">
                  {rule.justification ? (
                    rule.justification
                  ) : (
                    <span className={unknownCls}>
                      Не указано
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-zinc-500">
        Для двунаправленных правил источник обозначает сторону-инициатора,
        а получатель — вторую сторону обмена.
      </p>

      {result.rules.length !== result.rules_count && (
        <p className="mt-2 text-xs text-red-400">
          Внимание: количество правил ({result.rules_count}) не совпадает
          с числом записей в таблице ({result.rules.length}).
        </p>
      )}
    </div>
  );
}
