// ====== Code Summary ======
// A branded stand-in for the native `<input type="file">`, whose OS-chrome button breaks the app's
// visual language. The real input is visually hidden (not `display:none` — some browsers skip a
// hidden input's click-forwarding) and triggered via a themed Button; the chosen filename(s) render
// beside it so the control still reports its own state, same as the native control does.

import { useRef } from "react";
import { theme } from "../theme";
import { Button } from "./Button";

const hiddenInputStyle: React.CSSProperties = {
  position: "absolute", width: 1, height: 1, padding: 0, margin: -1,
  overflow: "hidden", clip: "rect(0,0,0,0)", whiteSpace: "nowrap", border: 0,
};

interface FileInputButtonProps {
  /** Button label — e.g. "Choose file" / "Choose files". */
  label: string;
  /** Rendered beside the button; falls back to "No file chosen" when null. */
  selectedText: string | null;
  onFilesSelected: (files: FileList | null) => void;
  accept?: string;
  multiple?: boolean;
  disabled?: boolean;
}

export function FileInputButton({ label, selectedText, onFilesSelected, accept, multiple, disabled }: FileInputButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: theme.space.s, minWidth: 0 }}>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        disabled={disabled}
        onChange={(e) => onFilesSelected(e.target.files)}
        style={hiddenInputStyle}
      />
      <Button type="button" variant="secondary" size="sm" disabled={disabled} onClick={() => inputRef.current?.click()}>
        {label}
      </Button>
      <span
        style={{
          color: selectedText ? theme.color.text : theme.color.mute, fontSize: theme.font.size.s,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0,
        }}
        title={selectedText ?? undefined}
      >
        {selectedText ?? "No file chosen"}
      </span>
    </div>
  );
}
