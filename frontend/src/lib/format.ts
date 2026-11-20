
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

// Форматирование значений
function fmt(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "не указано";
  }

  if (Array.isArray(value)) {
    return value.map(fmt).join(", ");
  }

  if (typeof value === "object") {
    return Object.values(value as Record<string, unknown>)
      .map(fmt)
      .join(", ");
  }

  if (typeof value === "boolean") {
    return value ? "Да" : "Нет";
  }

  return String(value);
}

// Методы файлового обмена
export function methodsLabel(rule: Rule): string | null {
  // USB отображается как самостоятельный способ передачи
  if (rule.transport === "usb") {
    return "USB-носитель";
  }

  const methods =
    rule["methods_by_node"] ??
    rule["file_methods"] ??
    rule["methods"];

  if (
    methods === undefined ||
    methods === null ||
    methods === ""
  ) {
    return null;
  }

  return fmt(methods);
}

// Проверки файлового обмена
export function checksLabel(rule: Rule): string | null {
  const checks = rule["checks_by_node"];

  if (
    checks === undefined ||
    checks === null ||
    checks === ""
  ) {
    return null;
  }

  return fmt(checks);
}
