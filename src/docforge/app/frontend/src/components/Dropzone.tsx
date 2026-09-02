// ====== Code Summary ======
// A drag-and-drop file picker styled as a dashed dropzone — the branded alternative to the native
// `<input type="file">` chrome for panels where a single bundle/file is the whole point of the
// screen (import, in contrast to `FileInputButton`'s compact inline picker used inside a longer
// form). Click-to-browse and drag-and-drop both funnel through the same hidden `<input>`, so the
// caller only ever sees `onFilesSelected`.

import { useRef, useState } from "react";
import { theme } from "../theme";

const hiddenInputStyle: React.CSSProperties = {
  position: "absolute", width: 1, height: 1, padding: 0, margin: -1,
  overflow: "hidden", clip: "rect(0,0,0,0)", whiteSpace: "nowrap", border: 0,
};

interface DropzoneProps {
  /** The prompt shown when nothing is selected, e.g. "Drop a .dcexport bundle here, or click to browse". */
  prompt: string;
  /** A short caption under the prompt, e.g. the accepted extension. */
  hint?: string;
  /** The chosen file's name — rendered in place of the prompt, with a "clear" action beside it. */
  selectedName: string | null;
  onFileSelected: (file: File | null) => void;
  accept?: string;
  disabled?: boolean;
}

export function Dropzone({ prompt, hint, selectedName, onFileSelected, accept, disabled }: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);

  const open = () => !disabled && inputRef.current?.click();

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
    if (disabled) return;
    const file = e.dataTransfer.files?.[0] ?? null;
    if (file) onFileSelected(file);
  };

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      onClick={open}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), open())}
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragActive(true); }}
      onDragLeave={() => setDragActive(false)}
      onDrop={handleDrop}
      style={{
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 6,
        padding: `${theme.space.l}px ${theme.space.m}px`, textAlign: "center",
        borderRadius: theme.radius.l,
        border: `1.5px dashed ${dragActive ? theme.color.accent : theme.color.line}`,
        background: dragActive ? theme.color.accentSoft : theme.color.surface2,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.6 : 1,
        transition: "background .15s ease, border-color .15s ease",
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        disabled={disabled}
        onChange={(e) => onFileSelected(e.target.files?.[0] ?? null)}
        style={hiddenInputStyle}
      />
      {selectedName ? (
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.s, minWidth: 0, maxWidth: "100%" }}>
          <span
            style={{
              color: theme.color.text, fontSize: theme.font.size.s, fontWeight: theme.font.weight.semibold,
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 320,
            }}
            title={selectedName}
          >
            {selectedName}
          </span>
          <span
            role="button"
            tabIndex={disabled ? -1 : 0}
            onClick={(e) => { e.stopPropagation(); onFileSelected(null); }}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); e.preventDefault(); onFileSelected(null); } }}
            title="Clear selection"
            style={{ color: theme.color.dim, fontSize: theme.font.size.m, cursor: "pointer", lineHeight: 1 }}
          >
            ✕
          </span>
        </div>
      ) : (
        <>
          <span style={{ color: theme.color.text, fontSize: theme.font.size.s, fontWeight: theme.font.weight.semibold }}>
            {prompt}
          </span>
          {hint && <span style={{ color: theme.color.mute, fontSize: theme.font.size.xs }}>{hint}</span>}
        </>
      )}
    </div>
  );
}
