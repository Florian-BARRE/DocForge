// ====== Code Summary ======
// Fetch wrapper around the wizard's edit mode: loads the collection to edit (the wizard itself
// takes an already-resolved `initial` collection, it never fetches on its own), then hands off.

import { useEffect, useState } from "react";
import { getCollection, type Collection } from "../../api/collections";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import type { Navigate } from "../../shell/view";
import { CollectionWizard } from "./wizard/CollectionWizard";

interface CollectionEditPageProps {
  collectionId: string;
  onNavigate: Navigate;
}

export function CollectionEditPage({ collectionId, onNavigate }: CollectionEditPageProps) {
  const [collection, setCollection] = useState<Collection | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    getCollection(collectionId)
      .then(setCollection)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };

  useEffect(load, [collectionId]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!collection) return <LoadingState label="loading collection…" />;

  return (
    <CollectionWizard mode="edit" collectionId={collectionId} initial={collection} onNavigate={onNavigate} />
  );
}
