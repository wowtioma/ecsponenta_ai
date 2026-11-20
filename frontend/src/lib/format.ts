import type { Result, Rule } from "../types";

export function plural(n: number, forms: [string, string, string]): string {
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

export const typeLabel = (t: Rule["type"]) => (t === "file" ? "Файлы" : "Данные");

export function fileUsersLabel(r: Result): string {
  if (r.file_users_count !== null) return String(r.file_users_count);
  if (r.file_users_range) {
    const { min, max } = r.file_users_range;
    if (max === null) return `не менее ${min}`;
    return min === max ? String(min) : `от ${min} до ${max}`;
  }
  return "не определено";
}

function fmt(v: unknown): string {
  if (Array.isArray(v)) return v.map(fmt).join(", ");
  if (v && typeof v === "object") {
    return Object.entries(v as Record<string, unknown>)
      .map(([k, x]) => `${k}: ${fmt(x)}`)
      .join("; ");
  }
  return String(v);
}

// Проверки файлового правила по сторонам (поле checks_by_node, если бэкенд его прислал)
export function checksLabel(rule: Rule): string | null {
  const c = rule["checks_by_node"];
  if (c === undefined || c === null || c === "") return null;
  return fmt(c);
}