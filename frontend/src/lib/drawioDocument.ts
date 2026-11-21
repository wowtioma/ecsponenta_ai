// ============================================================
// ДОКУМЕНТ СХЕМЫ ДЛЯ РЕДАКТОРА DRAW.IO
// ============================================================
//
// Схема строится по результату расчёта (buildDrawioXml).
// Правки пользователя сохраняются в localStorage под ключом,
// который зависит от конфигурации: при новом расчёте схема
// перестраивается, а при возврате к прежней конфигурации
// (например, после переключения вкладок) правки остаются.

import type { Result } from "../types";
import { buildDrawioXml } from "./exportDrawio";

const STORAGE_PREFIX = "synonyx:drawio:";

function hashString(value: string): string {
  // djb2 — короткий стабильный хеш для ключа localStorage
  let hash = 5381;

  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash << 5) + hash + value.charCodeAt(index)) | 0;
  }

  return Math.abs(hash).toString(36);
}

/** Ключ документа: зависит только от конфигурации сети, не от расходов. */
export function diagramDocumentKey(result: Result): string {
  return hashString(
    JSON.stringify({
      networks: result.networks,
      devices: result.devices,
      rules: result.rules,
      synonyx: result.synonyx ?? null,
      firewall: result.firewall ?? null,
    }),
  );
}

export function readStoredDrawioXml(key: string): string | null {
  try {
    const value = localStorage.getItem(STORAGE_PREFIX + key);

    return value && value.trim() ? value : null;
  } catch {
    return null;
  }
}

export function storeDrawioXml(key: string, xml: string): void {
  try {
    localStorage.setItem(STORAGE_PREFIX + key, xml);
  } catch {
    // Приватный режим браузера может запрещать localStorage
  }
}

export function clearStoredDrawioXml(key: string): void {
  try {
    localStorage.removeItem(STORAGE_PREFIX + key);
  } catch {
    // см. выше
  }
}

/** Исходное содержимое редактора: сохранённые правки или свежая схема. */
export function loadDrawioDocument(result: Result, key: string): string {
  return readStoredDrawioXml(key) ?? buildDrawioXml(result);
}
