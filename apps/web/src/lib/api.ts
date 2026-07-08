import { appConfig } from "./config";

const DEV_USER_ID_KEY = "papervault.devUserId";
const DEV_USER_EMAIL = "local@papervault.dev";

export type DocumentItem = {
  id: string;
  owner_id: string;
  title: string;
  original_filename: string;
  content_type: string;
  file_size_bytes: number;
  sha256_hash: string;
  source_kind: string;
  status: string;
  document_type: string;
  created_at: string;
  updated_at: string;
};

export type SearchResult = {
  document_id: string;
  title: string;
  original_filename: string;
  document_type: string;
  status: string;
  summary: string | null;
  created_at: string;
  score: number;
  highlights: string[];
};

export type TimelineEvent = {
  id: string;
  event_type: string;
  payload: Record<string, unknown>;
  occurred_at: string;
};

export type DocumentTag = {
  id: string;
  name: string;
  slug: string;
  color: string | null;
};

export type DocumentDetail = {
  document: DocumentItem;
  ai_analysis: {
    summary: string | null;
    keywords: string[];
    entities: Record<string, unknown>[];
    suggested_tags: string[];
    category: string | null;
    confidence_score: number | null;
  } | null;
  metadata: {
    schema_name: string;
    schema_version: number;
    data: Record<string, unknown>;
    confidence_score: number | null;
  } | null;
  text_extraction: {
    status: string;
    source: string;
    page_count: number | null;
    language: string | null;
    error_message: string | null;
  } | null;
  tags: DocumentTag[];
  timeline_events: TimelineEvent[];
};

export type NotificationItem = {
  id: string;
  document_id: string | null;
  kind: string;
  status: string;
  title: string;
  message: string;
  due_date: string;
  created_at: string;
};

export type DuplicateGroup = {
  method: string;
  documents: Array<{
    id: string;
    title: string;
    original_filename: string;
    sha256_hash: string;
    created_at: string;
  }>;
};

export function getDevUserId() {
  const existing = window.localStorage.getItem(DEV_USER_ID_KEY);
  if (existing) {
    return existing;
  }
  const generated =
    window.crypto?.randomUUID?.() ?? "00000000-0000-0000-0000-000000000001";
  window.localStorage.setItem(DEV_USER_ID_KEY, generated);
  return generated;
}

export async function listDocuments() {
  return apiFetch<DocumentItem[]>("/documents");
}

export async function getDocument(documentId: string) {
  return apiFetch<DocumentDetail>(`/documents/${documentId}`);
}

export async function getDocumentFile(documentId: string) {
  const response = await fetch(`${appConfig.apiBaseUrl}/documents/${documentId}/file`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch document file: ${response.status}`);
  }
  return response.blob();
}

export async function searchDocuments(query: string) {
  const response = await apiFetch<{ results: SearchResult[] }>("/search", {
    method: "POST",
    body: JSON.stringify({
      query,
      mode: "hybrid",
      filters: {},
      limit: 50,
      offset: 0,
    }),
  });
  return response.results;
}

export async function uploadDocument(file: File, documentType = "generic_pdf") {
  const body = new FormData();
  body.append("document_type", documentType);
  body.append("file", file);
  return apiFetch<{ document: DocumentItem; processing_task_id: string | null }>(
    "/documents/uploads",
    {
      method: "POST",
      body,
      skipJsonContentType: true,
    },
  );
}

export async function listNotifications() {
  return apiFetch<NotificationItem[]>("/notifications");
}

export async function listDuplicates() {
  return apiFetch<DuplicateGroup[]>("/documents/duplicates/candidates");
}

async function apiFetch<T>(
  path: string,
  options: RequestInit & { skipJsonContentType?: boolean } = {},
) {
  const headers = new Headers(options.headers);
  for (const [key, value] of Object.entries(authHeaders())) {
    headers.set(key, value);
  }
  if (!options.skipJsonContentType) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
    ...options,
    headers,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function authHeaders() {
  return {
    "X-PaperVault-User-Id": getDevUserId(),
    "X-PaperVault-User-Email": DEV_USER_EMAIL,
  };
}
