
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
    <div className="flex items-center justify-end gap-2 mb-3">
      <button
        type="button"
        onClick={() => exportJson(result)}
        className="
          rounded-lg
          border border-zinc-700
          px-3 py-2
          text-xs font-medium
          text-zinc-300
          hover:bg-zinc-800
          transition-colors
        "
      >
        JSON для эксперта
      </button>

      <button
        type="button"
        onClick={() => exportDrawio(result)}
        className="
          rounded-lg
          bg-blue-600
          px-3 py-2
          text-xs font-medium
          text-white
          hover:bg-blue-500
          transition-colors
        "
      >
        Скачать .drawio
      </button>
    </div>
  );
}
