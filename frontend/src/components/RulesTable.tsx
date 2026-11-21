
import type { Result, Rule } from "../types";
import {
  checksLabel,
  fileProtocolsLabel,
  methodsLabel,
  modeLabel,
  netName,
  typeLabel,
  usbEndpoint,
} from "../lib/format";

const unknownCls = "app-table__unknown";

const headers = [
  "№",
  "Источник",
  "Получатель",
  "Тип обмена",
  "Режим",
  "Протокол",
  "Методы файлов",
  "Проверки файлов",
  "Обоснование",
];

function ProtocolCell({ result, rule }: { result: Result; rule: Rule }) {
  if (rule.type === "file") {
    const protocols = fileProtocolsLabel(result, rule);
    return protocols
      ? <span className="app-table__pre">{protocols}</span>
      : <span className={unknownCls}>Не указаны</span>;
  }

  return (
    <div>
      <div>{typeof rule.protocol === "string" ? rule.protocol : "Протокол не указан"}</div>
      {rule.port != null ? (
        <div className="app-table__note">Порт: {rule.port}</div>
      ) : (
        <div className={unknownCls}>Порт: не определён</div>
      )}
    </div>
  );
}

function FileDetailsCell({ value }: { value: string | null }) {
  return value
    ? <span className="app-table__pre">{value}</span>
    : <span className={unknownCls}>Не указаны</span>;
}

function endpointLabel(result: Result, networkId: string, deviceId?: string | null) {
  const network = netName(result, networkId);
  const device = result.devices.find((item) => item.id === deviceId);
  return device ? (
    <>
      <div className="app-table__strong">{device.name}</div>
      <div className="app-table__note">{network}</div>
    </>
  ) : <span className="app-table__strong">{network}</span>;
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

  const hasDataRules = result.rules.some((rule) => rule.type === "data");
  return (
    <div>
      <div className="app-table__wrap">
        <table className="app-table">
          <thead>
            <tr>
              {headers.map((header) => (
                <th key={header}>{header === "Протокол" && hasDataRules ? "Протокол / порт" : header}</th>
              ))}
            </tr>
          </thead>

          <tbody>
            {result.rules.map((rule) => (
              <tr key={rule.id}>
                <td className="app-table__id">{rule.id}</td>

                <td>{usbEndpoint(rule) === "from" ? "USB-носитель на Узле А" : endpointLabel(result, rule.from, rule.from_device_id)}</td>
                <td>{usbEndpoint(rule) === "to" ? "USB-носитель на Узле А" : endpointLabel(result, rule.to, rule.to_device_id)}</td>

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
                  <ProtocolCell result={result} rule={rule} />
                </td>

                <td>
                  {rule.type === "file"
                    ? <FileDetailsCell value={methodsLabel(result, rule)} />
                    : <span className="app-table__note">—</span>}
                </td>

                <td>
                  {rule.type === "file"
                    ? <FileDetailsCell value={checksLabel(result, rule)} />
                    : <span className="app-table__note">—</span>}
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

      {result.rules.some((rule) => rule.type === "data" && rule.mode === "two-way") && (
        <p className="app-table__hint">
          У двунаправленных правил передачи данных источник обозначает сторону-инициатора.
        </p>
      )}

      {result.rules.length !== result.rules_count && (
        <p className="app-table__warning">
          Внимание: количество правил ({result.rules_count}) не совпадает
          с числом записей в таблице ({result.rules.length}).
        </p>
      )}
    </div>
  );
}
