
import type { Result, Rule } from "../types";
import {
  checksLabel,
  methodsLabel,
  modeLabel,
  netName,
  typeLabel,
} from "../lib/format";

const unknownCls = "app-table__unknown";

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
          <div className="app-table__note">Порт: {rule.port}</div>
        ) : (
          <div className={unknownCls}>Порт: Не определён</div>
        )}
      </div>
    );
  }

  if (rule.type === "file") {
    return <span className="app-table__note">Не применимо</span>;
  }

  return <span className={unknownCls}>Не указан</span>;
}

// Методы файлового обмена
function MethodsCell({ rule }: { rule: Rule }) {
  if (rule.type !== "file") {
    return <span className="app-table__note">—</span>;
  }

  const methods = methodsLabel(rule);

  return methods ? (
    <span className="app-table__pre">{methods}</span>
  ) : (
    <span className={unknownCls}>Не определены</span>
  );
}

// Проверки файлов
function ChecksCell({ rule }: { rule: Rule }) {
  if (rule.type !== "file") {
    return <span className="app-table__note">—</span>;
  }

  const checks = checksLabel(rule);

  return checks ? (
    <span className="app-table__pre">{checks}</span>
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
      <p className="app-hint">Правила ещё не определены.</p>
    );
  }

  return (
    <div>
      <div className="app-table__wrap">
        <table className="app-table">
          <thead>
            <tr>
              {headers.map((header) => (
                <th key={header}>{header}</th>
              ))}
            </tr>
          </thead>

          <tbody>
            {result.rules.map((rule) => (
              <tr key={rule.id}>
                <td className="app-table__id">{rule.id}</td>

                <td className="app-table__strong">
                  {netName(result, rule.from)}
                </td>

                <td className="app-table__strong">
                  {netName(result, rule.to)}
                </td>

                <td>
                  <div className="app-table__strong">
                    {typeLabel(rule.type)}
                  </div>

                  <div className="app-table__note">
                    {rule.description || (
                      <span className={unknownCls}>
                        Описание не указано
                      </span>
                    )}
                  </div>
                </td>

                <td>{modeLabel(rule.mode)}</td>

                <td>
                  <ProtocolCell rule={rule} />
                </td>

                <td>
                  <MethodsCell rule={rule} />
                </td>

                <td>
                  <ChecksCell rule={rule} />
                </td>

                <td>
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

      <p className="app-table__hint">
        Для двунаправленных правил источник обозначает сторону-инициатора,
        а получатель — вторую сторону обмена.
      </p>

      {result.rules.length !== result.rules_count && (
        <p className="app-table__warning">
          Внимание: количество правил ({result.rules_count}) не совпадает
          с числом записей в таблице ({result.rules.length}).
        </p>
      )}
    </div>
  );
}
