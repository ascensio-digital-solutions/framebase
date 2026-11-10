import { useRef } from "react";
import type { KeyboardEvent, PointerEvent } from "react";

interface Props {
  label: string;
  value: number;
  min: number;
  max: number;
  /** +1 when dragging right grows the panel, -1 when dragging left grows it. */
  direction: 1 | -1;
  disabled?: boolean;
  onChange: (width: number) => void;
}

export function ResizeHandle({ label, value, min, max, direction, disabled, onChange }: Props) {
  const drag = useRef<{ startX: number; startValue: number } | null>(null);

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (disabled) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { startX: event.clientX, startValue: value };
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    onChange(drag.current.startValue + (event.clientX - drag.current.startX) * direction);
  };
  const endDrag = () => {
    drag.current = null;
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    const step = event.shiftKey ? 64 : 16;
    if (event.key === "ArrowRight") onChange(value + step * direction);
    else if (event.key === "ArrowLeft") onChange(value - step * direction);
    else return;
    event.preventDefault();
  };

  return (
    <div
      className="resize-handle"
      role="separator"
      aria-orientation="vertical"
      aria-label={`Resize ${label}`}
      aria-valuenow={value}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-disabled={disabled}
      tabIndex={disabled ? -1 : 0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onKeyDown={onKeyDown}
    />
  );
}
