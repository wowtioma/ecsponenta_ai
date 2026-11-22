// ============================================================
// ЗАЩИТА КЛЮЧЕВЫХ БЛОКОВ «СИНОНИКСА» В РЕДАКТОРЕ DRAW.IO
// ============================================================
//
// Ядро, Узлы А/Б и сам блок «Синоникс» — смысловые элементы схемы:
// без них схема перестаёт описывать размещение ПАК. Поэтому:
//
// 1) в XML они помечаются style-флагами draw.io (locked, movable=0,
//    resizable=0, rotatable=0, deletable=0) — редактор не даёт их
//    удалить/сдвинуть;
// 2) на случай, если редактор всё равно вернёт документ без них
//    (например, удаление через контекстное меню или старый кеш),
//    на autosave выполняется проверка и восстановление этих ячеек
//    из эталонного XML — остальные правки сохраняются.

export const CORE_CELL_IDS = [
  "synonyx-area",
  "synonyx-node-a",
  "synonyx-core",
  "synonyx-node-b",
  "synonyx-label",
] as const;

/** Флаги draw.io: блок закреплён, не двигается и не удаляется. */
export const CORE_CELL_STYLE =
  "locked=1;movable=0;resizable=0;rotatable=0;deletable=0;";

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function cellPattern(id: string): RegExp {
  const safe = escapeRegExp(id);

  return new RegExp(
    `<mxCell\\b[^>]*\\bid="${safe}"[^>]*(?:/>|>[\\s\\S]*?</mxCell>)`,
  );
}

/** Идентификаторы закреплённых ячеек, которых нет в XML. */
export function missingCoreCells(xml: string): string[] {
  return CORE_CELL_IDS.filter((id) => !xml.includes(`id="${id}"`));
}

/**
 * Возвращает XML, в который добавлены пропавшие ячейки из эталонного XML.
 * Вставляем в начало <root>, чтобы блок «Синоникс» остался позади узлов.
 */
export function restoreCoreCells(
  xml: string,
  canonicalXml: string,
  missing: string[] = missingCoreCells(xml),
): string {
  const missingSet = new Set(missing);

  const cells = CORE_CELL_IDS.filter((id) => missingSet.has(id))
    .map((id) => canonicalXml.match(cellPattern(id))?.[0])
    .filter((cell): cell is string => Boolean(cell));

  if (cells.length === 0) return xml;

  const rootOpen = xml.indexOf("<root>");

  if (rootOpen === -1) return xml;

  const insertAt = rootOpen + "<root>".length;

  return `${xml.slice(0, insertAt)}\n${cells.join("\n")}\n${xml.slice(insertAt)}`;
}
