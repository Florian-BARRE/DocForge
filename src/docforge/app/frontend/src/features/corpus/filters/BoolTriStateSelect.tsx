// ====== Code Summary ======
// A three-state choice (Any / true / false) for boolean columns — `enabled` and any bool-typed
// metadata field. Built on the shared SegmentedControl instead of a native <select>: a native
// dropdown's popup chrome never picks up the app's tokens (see corpus filter-row audit, 2026-09),
// while a segmented control is themed end-to-end and reads its single active choice the same way
// every other structural picker in the app already does.

import { SegmentedControl } from "../../../components/SegmentedControl";

type BoolFilterOption = "any" | "true" | "false";

interface BoolTriStateSelectProps {
  value: boolean | null;
  onChange: (value: boolean | null) => void;
  trueLabel?: string;
  falseLabel?: string;
  /** The column's header text — becomes this control's fieldset legend (it renders its own, so the
   *  filter panel skips wrapping it in a second, redundant label). */
  label: string;
}

function toOption(value: boolean | null): BoolFilterOption {
  return value === null ? "any" : value ? "true" : "false";
}

function fromOption(option: BoolFilterOption): boolean | null {
  return option === "any" ? null : option === "true";
}

export function BoolTriStateSelect({ value, onChange, trueLabel = "true", falseLabel = "false", label }: BoolTriStateSelectProps) {
  return (
    <SegmentedControl<BoolFilterOption>
      legend={label}
      value={toOption(value)}
      onChange={(next) => onChange(fromOption(next))}
      options={[
        { value: "any", label: "any" },
        { value: "true", label: trueLabel },
        { value: "false", label: falseLabel },
      ]}
    />
  );
}
