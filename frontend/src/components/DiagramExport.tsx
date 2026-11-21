
import type { Result } from "../types";

import { exportDrawio } from "../lib/exportDrawio";
import { exportJson } from "../lib/exportJson";

interface DiagramExportProps {
  result: Result;
}

export default function DiagramExport({
  result,
}: DiagramExportProps) {
  return (
    <div className="diagram-export">
      <button
        type="button"
        onClick={() => exportJson(result)}
        className="app-button app-button-outline app-button-sm"
      >
        JSON для эксперта
      </button>

      <button
        type="button"
        onClick={() => exportDrawio(result)}
        className="app-button app-button-primary app-button-sm"
      >
        Скачать .drawio
      </button>
    </div>
  );
}
