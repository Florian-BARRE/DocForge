// ====== Code Summary ======
// TypeScript mirror of the documents upload contract + its typed client (multipart/form-data).

import { apiFetch } from "./http";

const BASE = "/api/v1/documents";

export interface UploadAccepted {
  document_id: string;
  job_id: string;
  duplicate: boolean;
}

export interface UploadDocumentArgs {
  file: File;
  collectionId: string;
  metadata: Record<string, unknown>;
}

export function uploadDocument({ file, collectionId, metadata }: UploadDocumentArgs): Promise<UploadAccepted> {
  const form = new FormData();
  form.append("file", file);
  form.append("collection_id", collectionId);
  form.append("metadata", JSON.stringify(metadata));
  return apiFetch(BASE, { method: "POST", body: form });
}
