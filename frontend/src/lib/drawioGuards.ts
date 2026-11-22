// Эти ячейки образуют статичный блок ПАК в экспортируемой схеме.
const CORE_CELL_IDS = new Set([
  "synonyx-area",
  "synonyx-node-a",
  "synonyx-core",
  "synonyx-node-b",
  "synonyx-label",
  "synonyx-version",
]);

export const CORE_CELL_STYLE =
  "locked=1;movable=0;editable=0;resizable=0;rotatable=0;deletable=0;";

function readGraphRoot(xml: string): Element | null {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  if (doc.querySelector("parsererror")) return null;
  const root = doc.querySelector("mxGraphModel > root");
  if (!root) return null;

  const ids = new Set(Array.from(root.children, (cell) => cell.id));
  return ids.has("0") && ids.has("1") ? root : null;
}

function styleParts(cell: Element): string[] {
  return (cell.getAttribute("style") ?? "").split(";").filter(Boolean).sort();
}

function matchesCoreCell(cell: Element, expected: Element): boolean {
  if (cell.tagName !== "mxCell") return false;
  const attributes = ["value", "parent", "vertex", "visible"];
  if (attributes.some((name) =>
    (cell.getAttribute(name) ?? "") !== (expected.getAttribute(name) ?? ""),
  )) return false;

  const actualStyle = styleParts(cell);
  const expectedStyle = styleParts(expected);
  if (actualStyle.length !== expectedStyle.length ||
      actualStyle.some((part, index) => part !== expectedStyle[index])) return false;

  const geometry = cell.firstElementChild;
  const reference = expected.firstElementChild;
  return geometry?.tagName === "mxGeometry" && reference !== null &&
    cell.childElementCount === 1 && geometry.childElementCount === 0 &&
    geometry.getAttribute("as") === "geometry" &&
    ["x", "y", "width", "height", "relative"].every((name) =>
      Number(geometry.getAttribute(name)) === Number(reference.getAttribute(name)),
    );
}

/** Восстанавливает статичный блок, сохраняя правки остальных ячеек. */
export function guardCoreCells(xml: string, canonicalXml: string): string {
  const root = readGraphRoot(xml);
  if (!root) return canonicalXml;

  const cells = Array.from(root.children);
  const coreCells = cells.filter((cell) => CORE_CELL_IDS.has(cell.id));
  if (!cells.some((cell) => !["0", "1"].includes(cell.id) && !CORE_CELL_IDS.has(cell.id))) {
    return canonicalXml;
  }

  const canonicalRoot = readGraphRoot(canonicalXml);
  if (!canonicalRoot) return canonicalXml;
  const expected = Array.from(canonicalRoot.children).filter((cell) => CORE_CELL_IDS.has(cell.id));
  if (coreCells.length === expected.length && expected.every((reference) =>
    coreCells.some((cell) => cell.id === reference.id && matchesCoreCell(cell, reference)),
  )) return xml;

  coreCells.forEach((cell) => cell.remove());
  // После фона и сетей: фон не перекроет восстановленный блок.
  expected.forEach((cell) => root.appendChild(root.ownerDocument.importNode(cell, true)));
  return new XMLSerializer().serializeToString(root.ownerDocument);
}
