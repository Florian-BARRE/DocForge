// ====== Code Summary ======
// The wizard's dedicated `tags` control — free-form labels via the shared `TagsInput`. Wired
// explicitly rather than through SchemaForm: `tags` lives on `CreateCollectionRequest`/
// `UpdateCollectionRequest`, not on the backend's `CollectionContractModel` (the schema StepIdentity
// otherwise renders off `GET /collections/contract-schema` — see that model's own docstring), so no
// generic schema-driven field ever appears for it. Always optional — an untagged collection is valid.

import { useId } from "react";
import { TagsInput } from "../../../components/TagsInput";
import { theme } from "../../../theme";

interface TagsFieldProps {
  values: string[];
  onChange: (values: string[]) => void;
}

export function TagsField({ values, onChange }: TagsFieldProps) {
  // Mirrors FormatsField's own `<label htmlFor>` pairing so this dedicated control reads as part
  // of the same form despite living outside SchemaForm.
  const controlId = useId();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: theme.font.size.s }}>
      <label htmlFor={controlId} style={{ color: theme.color.text }}>
        Tags
      </label>
      <TagsInput
        id={controlId}
        values={values}
        onChange={onChange}
        placeholder="Type a label and press Enter…"
        ariaLabel="Collection tags"
      />
      <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs, lineHeight: 1.35 }}>
        Free-form labels to group and find this collection later — optional.
      </span>
    </div>
  );
}
