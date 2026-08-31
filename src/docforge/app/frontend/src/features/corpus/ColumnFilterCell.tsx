// ====== Code Summary ======
// Dispatches one column's header filter cell to the right control by `filterKind` (from the
// column's TanStack `meta`), reading/writing that column's slice of the grid's filter state.

import { BoolTriStateSelect } from "./filters/BoolTriStateSelect";
import { DateRangeInputs } from "./filters/DateRangeInputs";
import { EnumMultiSelect } from "./filters/EnumMultiSelect";
import { ListFilterInput } from "./filters/ListFilterInput";
import { NumberRangeInputs } from "./filters/NumberRangeInputs";
import { TextFilterInput } from "./filters/TextFilterInput";
import { emptyFilterValue, type ColumnFilterKind, type ColumnFilterValue } from "./types";

interface ColumnFilterCellProps {
  columnId: string;
  filterKind: ColumnFilterKind;
  enumOptions?: string[];
  value: ColumnFilterValue | undefined;
  onChange: (columnId: string, value: ColumnFilterValue) => void;
}

export function ColumnFilterCell({ columnId, filterKind, enumOptions, value, onChange }: ColumnFilterCellProps) {
  const current = value ?? emptyFilterValue(filterKind);
  const set = (next: ColumnFilterValue) => onChange(columnId, next);

  switch (current.kind) {
    case "text":
      return <TextFilterInput value={current.contains} onChange={(contains) => set({ kind: "text", contains })} />;
    case "enumMulti":
      return <EnumMultiSelect options={enumOptions ?? []} values={current.values} onChange={(values) => set({ kind: "enumMulti", values })} />;
    case "listIn":
      return <ListFilterInput values={current.values} onChange={(values) => set({ kind: "listIn", values })} />;
    case "bool":
      return <BoolTriStateSelect value={current.value} onChange={(v) => set({ kind: "bool", value: v })} />;
    case "numberRange":
      return <NumberRangeInputs gte={current.gte} lte={current.lte} onChange={(next) => set({ kind: "numberRange", ...next })} />;
    case "dateRange":
      return <DateRangeInputs gte={current.gte} lte={current.lte} onChange={(next) => set({ kind: "dateRange", ...next })} />;
    default:
      return null;
  }
}
