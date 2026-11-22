import { useCallback, useEffect, useRef, useState } from "react";
import type { PointerEvent } from "react";

interface Size {
  width: number;
  height: number;
}

interface Camera {
  x: number;
  y: number;
  scale: number;
}

const fitPadding = 16;

export function useDiagramViewport({ width, height }: Size) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<Size>({ width: 0, height: 0 });
  const [camera, setCamera] = useState<Camera | null>(null);
  const [dragging, setDragging] = useState(false);
  const drag = useRef<{ id: number; x: number; y: number } | null>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => setSize({
      width: element.clientWidth,
      height: element.clientHeight,
    });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const fitScale = size.width && size.height
    ? Math.min(
        1,
        Math.max(1, size.width - fitPadding * 2) / width,
        Math.max(1, size.height - fitPadding * 2) / height,
      )
    : 1;
  const fit = {
    scale: fitScale,
    x: (size.width - width * fitScale) / 2,
    y: (size.height - height * fitScale) / 2,
  };

  const { x: fitX, y: fitY } = fit;
  const zoom = useCallback((factor: number, x = size.width / 2, y = size.height / 2) => {
    setCamera((previous) => {
      const current = previous ?? { x: fitX, y: fitY, scale: fitScale };
      const scale = Math.max(Math.min(0.15, fitScale), Math.min(4, current.scale * factor));
      const ratio = scale / current.scale;
      return {
        scale,
        x: x - (x - current.x) * ratio,
        y: y - (y - current.y) * ratio,
      };
    });
  }, [fitScale, fitX, fitY, size.height, size.width]);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const onWheel = (event: WheelEvent) => {
      if (!event.deltaY) return;
      event.preventDefault();
      const rect = element.getBoundingClientRect();
      zoom(
        event.deltaY < 0 ? 1.12 : 1 / 1.12,
        event.clientX - rect.left - element.clientLeft,
        event.clientY - rect.top - element.clientTop,
      );
    };

    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  }, [zoom]);

  const startPan = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || drag.current) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY };
    setDragging(true);
  };

  const movePan = (event: PointerEvent<HTMLDivElement>) => {
    const previous = drag.current;
    if (previous?.id !== event.pointerId) return;

    const dx = event.clientX - previous.x;
    const dy = event.clientY - previous.y;
    drag.current = { id: previous.id, x: event.clientX, y: event.clientY };
    setCamera((value) => {
      const current = value ?? fit;
      return { ...current, x: current.x + dx, y: current.y + dy };
    });
  };

  const stopPan = (event: PointerEvent<HTMLDivElement>) => {
    if (drag.current?.id !== event.pointerId) return;
    drag.current = null;
    setDragging(false);
  };

  return {
    ref,
    camera: camera ?? fit,
    dragging,
    zoom,
    reset: () => setCamera(null),
    startPan,
    movePan,
    stopPan,
  };
}
