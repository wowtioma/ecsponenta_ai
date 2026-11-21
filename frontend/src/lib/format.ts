
import type { Result, Rule } from "../types";

export function plural(
  n: number,
  forms: [string, string, string]
): string {
  const a = Math.abs(n) % 100;
  const b = a % 10;

  if (a > 10 && a < 20) return forms[2];
  if (b > 1 && b < 5) return forms[1];
  if (b === 1) return forms[0];

  return forms[2];
}

export const netName = (r: Result, id: string) =>
  r.networks.find((n) => n.id === id)?.name ?? id;

export const modeLabel = (m: Rule["mode"]) =>
  m === "two-way" ? "Двунаправленное" : "Однонаправленное";

export const typeLabel = (t: Rule["type"]) =>
  t === "file" ? "Файлы" : "Данные";

export function fileUsersLabel(r: Result): string {
  if (r.file_users_count !== null) {
    return String(r.file_users_count);
  }

  if (r.file_users_range) {
    const { min, max } = r.file_users_range;

    if (max === null) return `не менее ${min}`;

    return min === max ? String(min) : `от ${min} до ${max}`;
  }

  return "не определено";
}

const NODE_NAMES: Record<string, string> = {
  node_a: "Узел А",
  node_b: "Узел В",
  open: "Открытая сеть",
  closed: "Закрытый сегмент",
};

const FILE_MODE_NAMES: Record<string, string> = {
  manual: "Вручную",
  USB: "USB-носитель",
  PULL: "Автоматический забор (PULL)",
  PUSH: "Автоматическая доставка (PUSH)",
};

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function nonemptyText(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function byNetwork(
  result: Result,
  values: unknown,
  format: (value: unknown) => string,
): string | null {
  const entries = objectValue(values);
  if (!entries) return format(values) || null;

  const labels = Object.entries(entries).flatMap(([id, value]) => {
    const label = format(value);
    const name = result.networks.find((network) => network.id === id)?.name
      ?? NODE_NAMES[id] ?? id;
    return label ? [`${name}: ${label}`] : [];
  });
  return labels.join("\n") || null;
}

export function shortFileProtocols(label: string): string {
  return [...new Set(label.split(";").map((method) => {
    const name = method.split(",", 1)[0]?.trim() ?? "";
    return name.startsWith("USB") ? "USB" : name;
  }).filter(Boolean))].join(" / ");
}

export function usbEndpoint(rule: Rule): "from" | "to" | undefined {
  if (rule.transport !== "usb") return undefined;
  const targetMethods = objectValue(rule.methods_by_node)?.[rule.to];
  return Array.isArray(targetMethods) && targetMethods.some((method) => objectValue(method)?.mode === "USB")
    ? "to" : "from";
}

export function diagramFileMethodLabel(rule: Rule, networkId: string, label: string): string {
  const methods = objectValue(rule.methods_by_node)?.[networkId];
  const automation = Array.isArray(methods)
    ? methods.map((method) => objectValue(method)?.mode)
        .find((mode) => mode === "PULL" || mode === "PUSH")
    : undefined;
  return [automation, shortFileProtocols(label)].filter(Boolean).join(" ");
}

export function fileProtocolsLabel(result: Result, rule: Rule): string | null {
  if (!rule.protocol && rule.transport === "usb") return "USB";
  return byNetwork(result, rule.protocol, (value) => shortFileProtocols(nonemptyText(value)));
}

function formatMethod(value: unknown): string {
  const method = objectValue(value);
  if (!method) return nonemptyText(value);
  const mode = nonemptyText(method.mode);
  const protocol = nonemptyText(method.protocol);
  const storage = nonemptyText(method.storage);
  const trigger = method.trigger === "arrival" ? "при поступлении"
    : method.trigger === "schedule" ? "по расписанию" : "";

  return [FILE_MODE_NAMES[mode] ?? mode, protocol, trigger, storage].filter(Boolean).join(", ");
}

export function methodsLabel(result: Result, rule: Rule): string | null {
  const detail = rule.methods_by_node ?? rule["file_methods"] ?? rule["methods"];
  return byNetwork(result, detail, (value) =>
    Array.isArray(value) ? value.map(formatMethod).filter(Boolean).join("; ") : formatMethod(value),
  ) ?? (rule.transport === "usb" ? "USB-носитель" : null);
}

export function checksLabel(result: Result, rule: Rule): string | null {
  return byNetwork(result, rule.checks_by_node ?? rule["checks"], (value) => {
    if (!Array.isArray(value)) return nonemptyText(value);
    if (value.length === 0) return "Без проверок";
    return value.map(nonemptyText).filter(Boolean).join(", ");
  });
}
