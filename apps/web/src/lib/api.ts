import { appConfig } from "./config";

const DEV_USER_ID_KEY = "papervault.devUserId";
const DEV_USER_EMAIL = "local@papervault.dev";
const ACCESS_TOKEN_KEY = "papervault.accessToken";

export type AuthConfig = {
  local_auth_enabled: boolean;
  local_registration_enabled: boolean;
  dev_headers_enabled: boolean;
  oidc_configured: boolean;
};

export type AuthUser = {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
  auth_provider: string;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
  user: AuthUser;
};

export type OidcCallbackResult =
  | {
      status: "authenticated";
      accessToken: string;
      redirectTo: string;
    }
  | {
      status: "error";
      error: string;
      errorDescription: string | null;
      redirectTo: string;
    };

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
  document_date: string | null;
  issuer: string | null;
  organization: string | null;
  archived_at: string | null;
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

export type SearchMode = "keyword" | "semantic" | "hybrid";

export type SearchFilters = {
  document_type?: string | null;
  issuer?: string | null;
  organization?: string | null;
  tag?: string | null;
  date_from?: string | null;
  date_to?: string | null;
  include_archived?: boolean;
};

export type SearchRequestInput = {
  query: string;
  mode: SearchMode;
  filters: SearchFilters;
  limit?: number;
  offset?: number;
};

export type SavedSearch = {
  id: string;
  name: string;
  query: string;
  mode: SearchMode;
  filters: Record<string, unknown>;
  created_at: string;
};

export type RecentSearch = {
  id: string;
  query: string;
  mode: SearchMode;
  filters: Record<string, unknown>;
  searched_at: string;
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

export type TagItem = DocumentTag & {
  description: string | null;
  source: string;
  created_at: string;
};

export type DocumentTypeDefinition = {
  key: string;
  label: string;
  metadata_fields: Array<{
    key: string;
    label: string;
    field_type: string;
    required: boolean;
  }>;
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
  versions: Array<{
    id: string;
    version_number: number;
    sha256_hash: string;
    file_size_bytes: number;
    change_reason: string | null;
    created_by_id: string | null;
    created_at: string;
  }>;
};

export type DocumentTextSearchResult = {
  query: string;
  total_matches: number;
  page_mapping_available: boolean;
  matches: Array<{
    page_number: number | null;
    before: string;
    match: string;
    after: string;
  }>;
};

export type NotificationStatus = "pending" | "read" | "dismissed";

export type NotificationItem = {
  id: string;
  document_id: string | null;
  kind: string;
  status: NotificationStatus;
  title: string;
  message: string;
  due_date: string;
  payload: Record<string, unknown>;
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

export type DuplicateMergeResult = {
  kept_document: DocumentItem;
  archived_documents: DocumentItem[];
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

export function getStoredAccessToken() {
  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function storeAccessToken(token: string) {
  window.localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function clearStoredAccessToken() {
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
}

export function buildOidcLoginUrl(redirectTo = "/") {
  const params = new URLSearchParams({
    redirect_to: sanitizeRedirectPath(redirectTo),
  });
  return `${appConfig.apiBaseUrl}/auth/oidc/start?${params.toString()}`;
}

export function parseOidcCallbackHash(hash: string): OidcCallbackResult | null {
  const normalizedHash = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!normalizedHash) {
    return null;
  }

  const params = new URLSearchParams(normalizedHash);
  const redirectTo = sanitizeRedirectPath(params.get("redirect_to") ?? "/");
  const error = params.get("error");
  if (error) {
    return {
      status: "error",
      error,
      errorDescription: params.get("error_description"),
      redirectTo,
    };
  }

  const accessToken = params.get("access_token");
  if (!accessToken) {
    return null;
  }
  return {
    status: "authenticated",
    accessToken,
    redirectTo,
  };
}

export async function getAuthConfig() {
  return apiFetch<AuthConfig>("/auth/config", { skipAuth: true });
}

export async function getMe() {
  return apiFetch<AuthUser>("/auth/me");
}

export async function registerAccount(input: {
  email: string;
  password: string;
  display_name?: string;
}) {
  return apiFetch<TokenResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
    skipAuth: true,
  });
}

export async function loginAccount(input: { email: string; password: string }) {
  return apiFetch<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
    skipAuth: true,
  });
}

export async function listDocuments() {
  return apiFetch<DocumentItem[]>("/documents");
}

export async function listDocumentTypes() {
  return apiFetch<DocumentTypeDefinition[]>("/documents/types");
}

export async function getDocument(documentId: string) {
  return apiFetch<DocumentDetail>(`/documents/${documentId}`);
}

export async function getDocumentFile(documentId: string) {
  const response = await fetch(
    `${appConfig.apiBaseUrl}/documents/${documentId}/file`,
    {
      headers: authHeaders(),
    },
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch document file: ${response.status}`);
  }
  return response.blob();
}

export async function searchDocumentText(documentId: string, query: string) {
  const params = new URLSearchParams({ query });
  return apiFetch<DocumentTextSearchResult>(
    `/documents/${documentId}/text-search?${params.toString()}`,
  );
}

export async function searchDocuments(input: SearchRequestInput) {
  const response = await apiFetch<{ results: SearchResult[] }>("/search", {
    method: "POST",
    body: JSON.stringify({
      query: input.query,
      mode: input.mode,
      filters: normalizeSearchFilters(input.filters),
      limit: input.limit ?? 50,
      offset: input.offset ?? 0,
    }),
  });
  return response.results;
}

export async function listSavedSearches() {
  return apiFetch<SavedSearch[]>("/search/saved");
}

export async function listRecentSearches() {
  return apiFetch<RecentSearch[]>("/search/recent");
}

export async function saveSearch(input: {
  name: string;
  query: string;
  mode: SearchMode;
  filters: SearchFilters;
}) {
  return apiFetch<SavedSearch>("/search/saved", {
    method: "POST",
    body: JSON.stringify({
      name: input.name,
      query: input.query,
      mode: input.mode,
      filters: normalizeSearchFilters(input.filters),
    }),
  });
}

export async function uploadDocument(file: File, documentType = "generic_pdf") {
  const body = new FormData();
  body.append("document_type", documentType);
  body.append("file", file);
  return apiFetch<{
    document: DocumentItem;
    processing_task_id: string | null;
  }>("/documents/uploads", {
    method: "POST",
    body,
    skipJsonContentType: true,
  });
}

export async function updateDocument(
  documentId: string,
  input: Partial<{
    title: string;
    document_type: string;
    document_date: string | null;
    issuer: string | null;
    organization: string | null;
  }>,
) {
  return apiFetch<DocumentItem>(`/documents/${documentId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function updateDocumentMetadata(
  documentId: string,
  input: {
    schema_name?: string;
    data: Record<string, unknown>;
    document_date?: string | null;
    issuer?: string | null;
    organization?: string | null;
  },
) {
  return apiFetch<DocumentDetail["metadata"]>(
    `/documents/${documentId}/metadata`,
    {
      method: "PUT",
      body: JSON.stringify(input),
    },
  );
}

export async function archiveDocument(documentId: string) {
  return apiFetch<DocumentItem>(`/documents/${documentId}/archive`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function listNotifications() {
  return apiFetch<NotificationItem[]>("/notifications");
}

export async function syncDocumentNotifications(documentId: string) {
  return apiFetch<NotificationItem[]>(`/notifications/sync/${documentId}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function updateNotificationStatus(
  notificationId: string,
  status: NotificationStatus,
) {
  return apiFetch<NotificationItem>(`/notifications/${notificationId}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export async function listTags() {
  return apiFetch<TagItem[]>("/tags");
}

export async function createTag(input: {
  name: string;
  description?: string | null;
  color?: string | null;
}) {
  return apiFetch<TagItem>("/tags", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function attachTag(documentId: string, tagId: string) {
  return apiFetch<{ attached: boolean }>(
    `/documents/${documentId}/tags/${tagId}`,
    {
      method: "POST",
      body: JSON.stringify({}),
    },
  );
}

export async function detachTag(documentId: string, tagId: string) {
  await apiFetch<void>(`/documents/${documentId}/tags/${tagId}`, {
    method: "DELETE",
  });
}

export async function listDuplicates() {
  return apiFetch<DuplicateGroup[]>("/documents/duplicates/candidates");
}

export async function mergeDuplicateDocuments(input: {
  keep_document_id: string;
  duplicate_document_ids: string[];
}) {
  return apiFetch<DuplicateMergeResult>("/documents/duplicates/merge", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

async function apiFetch<T>(
  path: string,
  options: RequestInit & {
    skipAuth?: boolean;
    skipJsonContentType?: boolean;
  } = {},
) {
  const headers = new Headers(options.headers);
  if (!options.skipAuth) {
    for (const [key, value] of Object.entries(authHeaders())) {
      headers.set(key, value);
    }
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
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

function authHeaders(): Record<string, string> {
  const token = getStoredAccessToken();
  if (token) {
    return {
      Authorization: `Bearer ${token}`,
    };
  }
  return {
    "X-PaperVault-User-Id": getDevUserId(),
    "X-PaperVault-User-Email": DEV_USER_EMAIL,
  };
}

function normalizeSearchFilters(filters: SearchFilters): SearchFilters {
  return {
    document_type: blankToNull(filters.document_type),
    issuer: blankToNull(filters.issuer),
    organization: blankToNull(filters.organization),
    tag: blankToNull(filters.tag),
    date_from: blankToNull(filters.date_from),
    date_to: blankToNull(filters.date_to),
    include_archived: filters.include_archived === true,
  };
}

function blankToNull(value: string | null | undefined) {
  const normalized = value?.trim();
  return normalized ? normalized : null;
}

function sanitizeRedirectPath(value: string) {
  if (
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.includes("\\")
  ) {
    return "/";
  }
  return value;
}
