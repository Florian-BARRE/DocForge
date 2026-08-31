// ====== Code Summary ======
// A tag-entry membership filter ("in" any of these values) — language (no closed enum) and any
// list-typed metadata field (keyword_list/text_list/integer_list/float_list). Thin wrapper over
// the shared TagsInput primitive, sized down to fit a header filter row.

import { TagsInput } from "../../../components/TagsInput";

interface ListFilterInputProps {
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
}

export function ListFilterInput({ values, onChange, placeholder }: ListFilterInputProps) {
  return (
    <div style={{ fontSize: 12 }}>
      <TagsInput values={values} onChange={onChange} placeholder={placeholder ?? "add + enter"} />
    </div>
  );
}
