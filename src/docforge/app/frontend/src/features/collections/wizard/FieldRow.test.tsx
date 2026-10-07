// ====== Code Summary ======
// Render smoke-tests for the schema editor's per-field description input and the title-field
// selector (options come from the draft schema, document scope only).

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FieldRow } from "./FieldRow";
import { TitleFieldSelect } from "./TitleFieldSelect";
import { blankField, type DraftField } from "./wizardTypes";

function draft(name: string, overrides: Partial<DraftField> = {}): DraftField {
  return { ...blankField(), field_name: name, ...overrides };
}

describe("FieldRow description", () => {
  it("renders the description textarea and reports edits (cleared text becomes null)", () => {
    const onChange = vi.fn();
    const field = draft("author", { description: "Who wrote it" });
    render(<table><tbody><FieldRow field={field} onChange={onChange} onRemove={() => {}} /></tbody></table>);

    const box = screen.getByLabelText("Description for author") as HTMLTextAreaElement;
    expect(box.value).toBe("Who wrote it");
    expect(box.maxLength).toBe(1000);

    fireEvent.change(box, { target: { value: "The author" } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ description: "The author" }));
    fireEvent.change(box, { target: { value: "" } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ description: null }));
  });
});

describe("TitleFieldSelect", () => {
  const fields = [draft("headline"), draft("chunk_summary", { scope: "chunk", origin: "generated" }), draft("")];

  it("lists only document-scope fields plus the None option", () => {
    render(<TitleFieldSelect fields={fields} value={null} onChange={() => {}} />);
    const options = screen.getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["None (use the parsed title)", "headline"]);
  });

  it("emits the chosen field, and null for None; shows an inline error", () => {
    const onChange = vi.fn();
    render(<TitleFieldSelect fields={fields} value={null} onChange={onChange} error="title_field must be one of: headline" />);
    fireEvent.change(screen.getByLabelText("Title field"), { target: { value: "headline" } });
    expect(onChange).toHaveBeenLastCalledWith("headline");
    fireEvent.change(screen.getByLabelText("Title field"), { target: { value: "" } });
    expect(onChange).toHaveBeenLastCalledWith(null);
    expect(screen.getByRole("alert")).toHaveTextContent("headline");
  });
});
