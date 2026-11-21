// ============================================================
// ВСТРОЕННЫЙ РЕДАКТОР СХЕМЫ DRAW.IO
// ============================================================
//
// Во вкладке «Схема» вместо статичной картинки открывается
// настоящий редактор draw.io (embed.diagrams.net в iframe).
// Схема загружается тем же XML, что уходит в файл .drawio,
// поэтому блоки устройств, сетей, МЭ и «Синоникса» можно
// двигать, переименовывать и перекрашивать прямо на сайте.
//
// Правки автоматически сохраняются в localStorage, а кнопка
// «Скачать .drawio» выгружает именно отредактированную схему.

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

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
  diagramDocumentKey,
  loadDrawioDocument,
  storeDrawioXml,
} from "../lib/drawioDocument";

import DiagramPreview from "./DiagramPreview";

type EditorStatus = "loading" | "ready" | "unavailable";

// Сколько ждём ответа редактора, прежде чем показать сообщение
// «редактор недоступен» (нет сети, закрыт embed.diagrams.net и т. п.)
const INIT_TIMEOUT_MS = 20000;

// Резервное время на ответ экспорта: если draw.io не ответил,
// скачиваем последнюю сохранённую версию схемы.
const EXPORT_TIMEOUT_MS = 2500;

export default function DrawioEditor({
  result,
}: {
  result: Result;
}) {
  const key = useMemo(() => diagramDocumentKey(result), [result]);

  const [xml, setXml] = useState<string>(() =>
    loadDrawioDocument(result, key),
  );

  const xmlRef = useRef(xml);
  const keyRef = useRef(key);

  const [status, setStatus] = useState<EditorStatus>("loading");
  const [expanded, setExpanded] = useState(false);
  const [showStatic, setShowStatic] = useState(false);
  const [attempt, setAttempt] = useState(0);

  const [dark, setDark] = useState(
    () => document.documentElement.dataset.theme === "dark",
  );

  const iframeRef = useRef<HTMLIFrameElement>(null);
  const readyRef = useRef(false);
  const exportPendingRef = useRef(false);

  const origin = useMemo(() => getEditorOrigin(), []);
  const editorUrl = useMemo(() => buildEditorUrl(dark), [dark]);

  // Смена конфигурации → новая схема (сохранённые правки, если есть).
  // Сравниваем ключ документа, чтобы обновление расходов или
  // служебных полей результата не сбрасывало правки пользователя.
  useEffect(() => {
    if (keyRef.current === key) return;

    keyRef.current = key;

    const next = loadDrawioDocument(result, key);

    xmlRef.current = next;
    setXml(next);

    if (readyRef.current) {
      iframeRef.current?.contentWindow?.postMessage(
        JSON.stringify({
          action: "load",
          xml: next,
          autosave: 1,
          title: "Схема сети",
        }),
        origin,
      );
    }
  }, [key, result, origin]);

  // Переключение темы приложения перезагружает iframe с dark=1.
  // Редактор стартует заново, поэтому сразу показываем загрузку.
  useEffect(() => {
    const observer = new MutationObserver(() => {
      const nextDark =
        document.documentElement.dataset.theme === "dark";

      setDark((current) => {
        if (current === nextDark) return current;

        readyRef.current = false;
        setStatus("loading");

        return nextDark;
      });
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    return () => observer.disconnect();
  }, []);

  // Сообщения от редактора
  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== origin) return;

      if (event.source !== iframeRef.current?.contentWindow) return;

      const message = parseDrawioMessage(event.data);

      if (!message) return;

      switch (message.event) {
        case "init": {
          readyRef.current = true;
          setStatus("ready");

          iframeRef.current?.contentWindow?.postMessage(
            JSON.stringify({
              action: "load",
              xml: xmlRef.current,
              autosave: 1,
              title: "Схема сети",
            }),
            origin,
          );

          break;
        }

        // draw.io присылает актуальный XML после правок
        case "autosave":
        case "save": {
          const next = decodeDrawioXml(message.xml);

          if (!next) break;

          xmlRef.current = next;
          setXml(next);
          storeDrawioXml(keyRef.current, next);

          break;
        }

        // Ответ на запрос экспорта для скачивания файла
        case "export": {
          const exported = decodeDrawioXml(message.data);

          exportPendingRef.current = false;

          downloadDrawioXml(exported || xmlRef.current);

          break;
        }

        default:
          break;
      }
    };

    window.addEventListener("message", onMessage);

    return () => window.removeEventListener("message", onMessage);
  }, [origin]);

  // Если редактор не ответил за отведённое время — сообщаем об этом
  useEffect(() => {
    if (status !== "loading") return;

    const timer = window.setTimeout(() => {
      setStatus((current) =>
        current === "loading" ? "unavailable" : current,
      );
    }, INIT_TIMEOUT_MS);

    return () => window.clearTimeout(timer);
  }, [status, editorUrl, attempt]);

  // Esc закрывает развёрнутый редактор
  useEffect(() => {
    if (!expanded) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setExpanded(false);
    };

    window.addEventListener("keydown", onKeyDown);

    return () => window.removeEventListener("keydown", onKeyDown);
  }, [expanded]);

  const handleDownload = useCallback(() => {
    const frame = iframeRef.current?.contentWindow;

    if (!frame) {
      downloadDrawioXml(xml);
      return;
    }

    exportPendingRef.current = true;

    frame.postMessage(
      JSON.stringify({
        action: "export",
        format: "xml",
        xml: xmlRef.current,
      }),
      origin,
    );

    window.setTimeout(() => {
      if (!exportPendingRef.current) return;

      exportPendingRef.current = false;

      downloadDrawioXml(xml);
    }, EXPORT_TIMEOUT_MS);
  }, [origin, xml]);

  const handleReset = useCallback(() => {
    // Сбрасываем сохранённые правки и просим редактор
    // загрузить схему, построенную по результату расчёта
    clearStoredDrawioXml(keyRef.current);

    const generated = buildDrawioXml(result);

    xmlRef.current = generated;
    setXml(generated);

    iframeRef.current?.contentWindow?.postMessage(
      JSON.stringify({
        action: "load",
        xml: generated,
        autosave: 1,
        title: "Схема сети",
      }),
      origin,
    );
  }, [origin, result]);

  const handleRetry = useCallback(() => {
    setShowStatic(false);
    setStatus("loading");
    setAttempt((value) => value + 1);
  }, []);

  const fullscreenClass = expanded
    ? " drawio-editor--expanded"
    : "";

  const frameClass = showStatic
    ? "drawio-editor drawio-editor--static"
    : `drawio-editor${fullscreenClass}`;

  return (
    <div className={frameClass}>
      <div className="diagram-toolbar">
        <div className="diagram-card__title">
          Схема взаимодействия сетей
          <span className="drawio-editor__badge">draw.io</span>
        </div>

        <div className="diagram-controls">
          <button
            type="button"
            onClick={handleDownload}
            className="diagram-btn"
          >
            Скачать .drawio
          </button>

          <button
            type="button"
            onClick={handleReset}
            className="diagram-btn"
            title="Вернуть схему, построенную по результату расчёта"
          >
            Сбросить
          </button>

          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="diagram-btn"
            aria-pressed={expanded}
          >
            {expanded ? "Свернуть" : "Развернуть"}
          </button>
        </div>
      </div>

      {showStatic ? (
        <div className="drawio-editor__static">
          <div className="drawio-editor__staticbar">
            <span>
              Редактор недоступен — показана статичная схема.
            </span>

            <button
              type="button"
              onClick={handleRetry}
              className="diagram-btn"
            >
              Попробовать снова
            </button>
          </div>

          <DiagramPreview result={result} />
        </div>
      ) : (
        <div className="drawio-editor__frame">
          <iframe
            key={`${editorUrl}-${attempt}`}
            ref={iframeRef}
            src={editorUrl}
            title="Редактор схемы draw.io"
            allow="clipboard-read; clipboard-write"
          />

          {status === "loading" && (
            <div className="drawio-editor__overlay">
              <span className="drawio-editor__spinner" aria-hidden="true" />

              Загружаем редактор draw.io…
            </div>
          )}

          {status === "unavailable" && (
            <div className="drawio-editor__overlay drawio-editor__overlay--message">
              <strong>Редактор draw.io не загрузился.</strong>

              <span>
                Проверьте доступ к embed.diagrams.net (нужен интернет)
                или откройте статичную схему — её можно скачать
                в файл .drawio и отредактировать отдельно.
              </span>

              <div className="drawio-editor__overlay-actions">
                <button
                  type="button"
                  onClick={handleRetry}
                  className="diagram-btn"
                >
                  Попробовать снова
                </button>

                <button
                  type="button"
                  onClick={() => setShowStatic(true)}
                  className="diagram-btn"
                >
                  Статичная схема
                </button>

                <button
                  type="button"
                  onClick={handleDownload}
                  className="diagram-btn"
                >
                  Скачать .drawio
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="diagram-note">
        Это полноценный редактор draw.io: блоки можно перетаскивать,
        переименовывать, менять цвета и добавлять новые элементы.
        Правки сохраняются в браузере автоматически, кнопка
        «Скачать .drawio» выгружает отредактированную схему.
      </div>
    </div>
  );
}
