// ============================================================
// ВСТРОЕННЫЙ РЕДАКТОР DRAW.IO (embed.diagrams.net)
// ============================================================
//
// Редактор открывается в <iframe> и общается с приложением
// сообщениями postMessage в JSON-протоколе draw.io:
//
//   iframe → приложение: { event: "init" }        — редактор готов
//   приложение → iframe: { action: "load", xml }  — загрузить схему
//   iframe → приложение: { event: "autosave", xml } — правки сохранились
//   приложение → iframe: { action: "export", format: "xml" }
//   iframe → приложение: { event: "export", data } — XML для файла
//
// Адрес редактора можно переопределить переменной окружения
// VITE_DRAWIO_EMBED_URL (например, для собственного self-hosted draw.io).

const DEFAULT_EDITOR_URL = "https://embed.diagrams.net/";

/** Базовый адрес встроенного редактора draw.io. */
export const DRAWIO_EMBED_URL: string =
  (import.meta.env?.VITE_DRAWIO_EMBED_URL as string | undefined) ||
  DEFAULT_EDITOR_URL;

/** Параметры, включающие режим встраивания и JSON-протокол. */
const EMBED_PARAMS: Record<string, string> = {
  embed: "1",
  proto: "json",
  spin: "1",
  libraries: "1",
  lang: "ru",
  modified: "1",
  noSaveBtn: "1",
  noExitBtn: "1",
  autosave: "1",
};

/**
 * Приводит адрес редактора к абсолютному.
 * Относительный путь (например, /drawio/) поддерживается,
 * чтобы можно было поднять self-hosted draw.io за тем же доменом.
 */
function resolveEditorUrl(): URL {
  try {
    return new URL(DRAWIO_EMBED_URL, window.location.origin);
  } catch {
    return new URL(DEFAULT_EDITOR_URL);
  }
}

/** Собирает адрес iframe редактора. */
export function buildEditorUrl(dark: boolean): string {
  const url = resolveEditorUrl();

  Object.entries(EMBED_PARAMS).forEach(([key, value]) => {
    url.searchParams.set(key, value);
  });

  if (dark) {
    url.searchParams.set("dark", "1");
  }

  return url.toString();
}

/** Origin редактора — им проверяются входящие сообщения. */
export function getEditorOrigin(): string {
  return resolveEditorUrl().origin;
}

// ============================================================
// СООБЩЕНИЯ
// ============================================================

export type DrawioEventName =
  | "init"
  | "load"
  | "autosave"
  | "save"
  | "export"
  | "modified"
  | "exit"
  | "configure";

export interface DrawioMessage {
  event?: DrawioEventName | string;
  xml?: string;
  data?: string;
  format?: string;
  modified?: boolean;
}

/** Разбирает сообщение от iframe; чужие сообщения возвращают null. */
export function parseDrawioMessage(value: unknown): DrawioMessage | null {
  if (typeof value !== "string" || !value.startsWith("{")) {
    return null;
  }

  try {
    const parsed: unknown = JSON.parse(value);

    if (
      typeof parsed !== "object" ||
      parsed === null ||
      !("event" in parsed)
    ) {
      return null;
    }

    return parsed as DrawioMessage;
  } catch {
    return null;
  }
}

/**
 * Приводит XML из события к обычной строке.
 * В событии export draw.io отдаёт XML в URL-кодировке,
 * в событиях autosave/save — как есть.
 */
export function decodeDrawioXml(value: string | undefined): string {
  if (!value) return "";

  const looksEncoded =
    value.startsWith("%3C") || value.includes("%3Cmxfile");

  if (!looksEncoded) return value;

  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}
