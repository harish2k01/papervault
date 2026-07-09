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

export async function listDuplicates() {
  return apiFetch<DuplicateGroup[]>("/documents/duplicates/candidates");
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
