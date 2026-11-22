import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Result } from "../types";
import { buildDrawioXml, downloadDrawioXml } from "../lib/exportDrawio";
import {
  buildEditorUrl,
  decodeDrawioXml,
  getEditorOrigin,
  parseDrawioMessage,
} from "../lib/drawioEmbed";
import {
  clearStoredDrawioXml,
  loadDrawioDocument,
  storeDrawioXml,
} from "../lib/drawioDocument";
import {
  missingCoreCells,
  restoreCoreCells,
} from "../lib/drawioGuards";
import DiagramPreview from "./DiagramPreview";

type EditorStatus = "loading" | "ready" | "unavailable";

const INIT_TIMEOUT_MS = 20_000;
const SVG_DATA_URL = /^data:image\/svg\+xml(?:;[^,]*)?,/i;

export default function DrawioEditor({
  result,
  documentKey,
  preview,
  onPreview,
}: {
  result: Result;
  documentKey: string;
  preview: boolean;
  onPreview: () => void;
}) {
  const canonicalXml = useMemo(() => buildDrawioXml(result), [result]);

  const [xml, setXml] = useState(() => {
    const stored = loadDrawioDocument(result, documentKey);
    const missing = missingCoreCells(stored);

    if (missing.length === 0) return stored;

    const repaired = restoreCoreCells(stored, canonicalXml, missing);

    // Если восстановить не удалось (в сохранённом XML нет даже <root>),
    // показываем эталонную схему — пустой холст хуже потери правок.
    return missingCoreCells(repaired).length === 0 ? repaired : canonicalXml;
  });
  const [svg, setSvg] = useState<{ url: string; xml: string; frame: string }>();
  const [status, setStatus] = useState<EditorStatus>("loading");
  const [expanded, setExpanded] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const [dark, setDark] = useState(
    () => document.documentElement.dataset.theme === "dark",
  );

  const iframeRef = useRef<HTMLIFrameElement>(null);
  const xmlRef = useRef(xml);
  const lastGoodRef = useRef(xml);
  const exportId = useRef(0);
  const origin = getEditorOrigin();
  const editorUrl = buildEditorUrl(dark);
  const frameKey = `${editorUrl}-${attempt}`;

  const post = useCallback((message: object) => {
    iframeRef.current?.contentWindow?.postMessage(JSON.stringify(message), origin);
  }, [origin]);

  const load = useCallback((documentXml: string) => {
    post({
      action: "load",
      xml: documentXml,
      autosave: 1,
      fit: true,
      title: "Схема сети",
    });
  }, [post]);

  useEffect(() => {
    const observer = new MutationObserver(() => {
      const next = document.documentElement.dataset.theme === "dark";
      if (next !== dark) {
        setStatus("loading");
        setDark(next);
      }
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, [dark]);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== origin || event.source !== iframeRef.current?.contentWindow) return;

      const message = parseDrawioMessage(event.data);
      switch (message?.event) {
        case "init":
          load(xmlRef.current);
          break;
        case "load":
          setStatus("ready");
          break;
        case "autosave":
        case "save": {
          const next = decodeDrawioXml(message.xml);
          if (!next || next === xmlRef.current) break;

          // Ядро, Узлы А/Б и блок «Синоникс» удалять нельзя: если редактор
          // всё же вернул XML без них, восстанавливаем ячейки из эталона
          // и перезагружаем схему (остальные правки сохраняются).
          const missing = missingCoreCells(next);

          if (missing.length > 0) {
            const repaired = restoreCoreCells(
              next,
              lastGoodRef.current,
              missing,
            );

            // Если ячейки восстановить не из чего — берём эталонную схему.
            const fixed =
              missingCoreCells(repaired).length === 0
                ? repaired
                : canonicalXml;

            exportId.current += 1;
            xmlRef.current = fixed;
            setXml(fixed);
            storeDrawioXml(documentKey, fixed);
            setNotice(
              "Ядро и узлы «Синоникса» закреплены — их нельзя удалять. Блоки восстановлены.",
            );
            load(fixed);
            break;
          }

          lastGoodRef.current = next;
          exportId.current += 1;
          xmlRef.current = next;
          setXml(next);
          storeDrawioXml(documentKey, next);
          break;
        }
        case "export":
          if (
            message.message?.requestId === exportId.current &&
            typeof message.data === "string" &&
            SVG_DATA_URL.test(message.data)
          ) {
            setSvg({ url: message.data, xml: xmlRef.current, frame: frameKey });
          }
          break;
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [canonicalXml, documentKey, frameKey, load, origin]);

  useEffect(() => {
    if (!preview || status !== "ready") return;
    const requestId = ++exportId.current;
    post({ action: "export", format: "svg", keepTheme: true, requestId });
  }, [post, preview, status, xml]);

  useEffect(() => {
    if (status !== "loading") return;
    const timer = window.setTimeout(() => setStatus("unavailable"), INIT_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [frameKey, status]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 6000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  // Если в сохранённой схеме не было закреплённых блоков, фиксируем
  // восстановленный вариант, чтобы пустой холст не вернулся после F5.
  useEffect(() => {
    storeDrawioXml(documentKey, xmlRef.current);
  }, [documentKey]);

  const isExpanded = expanded && !preview;  useEffect(() => {
    if (!isExpanded) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setExpanded(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isExpanded]);

  const reset = () => {
    const generated = canonicalXml;
    exportId.current += 1;
    xmlRef.current = generated;
    lastGoodRef.current = generated;
    setXml(generated);
    clearStoredDrawioXml(documentKey);
    if (status === "ready") load(generated);
  };

  const retry = () => {
    setStatus("loading");
    setAttempt((value) => value + 1);
  };

  const download = () => downloadDrawioXml(xmlRef.current);
  const currentSvg = svg?.xml === xml && svg.frame === frameKey ? svg.url : undefined;

  return (
    <div className="drawio-workspace">
      <div
        className={`diagram-card drawio-editor${isExpanded ? " drawio-editor--expanded" : ""}${preview ? " drawio-editor--hidden" : ""}`}
        inert={preview}
        aria-hidden={preview}
      >
        <div className="diagram-toolbar">
          <div className="diagram-card__title">
            Схема взаимодействия сетей
            <span className="drawio-editor__badge">draw.io</span>
          </div>
          <div className="diagram-controls">
            <button type="button" onClick={download} className="diagram-btn">
              Скачать .drawio
            </button>
            <button
              type="button"
              onClick={reset}
              className="diagram-btn"
              disabled={status === "loading"}
              title="Вернуть схему, построенную по результату расчёта"
            >
              Сбросить
            </button>
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
              className="diagram-btn"
              aria-pressed={isExpanded}
            >
              {isExpanded ? "Свернуть" : "Развернуть"}
            </button>
          </div>
        </div>

        {notice && (
          <div className="drawio-editor__notice" role="status">
            {notice}
          </div>
        )}

        <div className="drawio-editor__frame">
          <iframe
            key={frameKey}
            ref={iframeRef}
            src={editorUrl}
            title="Редактор схемы draw.io"
            allow="clipboard-read; clipboard-write"
          />
          {status === "loading" && (
            <div className="drawio-editor__overlay" role="status">
              <span className="drawio-editor__spinner" aria-hidden="true" />
              Загружаем редактор draw.io…
            </div>
          )}
          {status === "unavailable" && (
            <div className="drawio-editor__overlay drawio-editor__overlay--message">
              <strong>Редактор draw.io не загрузился.</strong>
              <span>Для редактирования нужен доступ к embed.diagrams.net.</span>
              <div className="drawio-editor__overlay-actions">
                <button type="button" onClick={retry} className="diagram-btn">
                  Попробовать снова
                </button>
                <button type="button" onClick={onPreview} className="diagram-btn">
                  Открыть просмотр
                </button>
              </div>
            </div>
          )}
        </div>
        <div className="diagram-note">
          Ядро, Узлы А/Б и блок «Синоникс» закреплены: их нельзя удалить или
          сдвинуть. Остальные блоки и подписи редактируются. Правки сохраняются
          в этом браузере и входят в файл .drawio. Чтобы изменить расчёт правил,
          уточните параметры обмена в чате.
        </div>
      </div>

      {preview && (
        <DiagramPreview
          result={result}
          imageUrl={currentSvg}
          showingFallback={status !== "ready" || !currentSvg}
          onDownload={download}
        />
      )}
    </div>
  );
}
