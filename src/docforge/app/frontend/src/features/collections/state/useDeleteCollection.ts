// ====== Code Summary ======
// The one shared delete-collection request path — calls DELETE, surfaces a success/error toast,
// and reports whether it worked so each call site (dashboard card, detail header, edit-form danger
// zone) can drive its own confirm UI and post-delete navigation/refresh without duplicating the
// request/toast plumbing.

import { useState } from "react";
import { deleteCollection } from "../../../api/collections";
import { useToast } from "../../../shell/toast";

interface DeleteTarget {
  id: string;
  name: string;
}

interface UseDeleteCollectionResult {
  deleting: boolean;
  error: string | null;
  /** Deletes `target`, toasts the outcome, and resolves `true` on success / `false` on failure. */
  remove: (target: DeleteTarget) => Promise<boolean>;
}

export function useDeleteCollection(): UseDeleteCollectionResult {
  const toast = useToast();
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const remove = async (target: DeleteTarget): Promise<boolean> => {
    setDeleting(true);
    setError(null);
    try {
      await deleteCollection(target.id);
      toast.success(`Collection “${target.name}” deleted`);
      return true;
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      toast.error(`Delete failed — ${message}`);
      return false;
    } finally {
      setDeleting(false);
    }
  };

  return { deleting, error, remove };
}
