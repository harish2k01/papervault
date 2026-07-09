import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  FileText,
  History,
  LogIn,
  LogOut,
  Search,
  ShieldCheck,
  Tags,
  Upload,
  UserPlus,
} from "lucide-react";

import { Button } from "../../components/ui/button";
import {
  AuthConfig,
  AuthUser,
  DocumentDetail,
  DocumentItem,
  TokenResponse,
  buildOidcLoginUrl,
  clearStoredAccessToken,
  getAuthConfig,
  getDocument,
  getDocumentFile,
  getMe,
  getStoredAccessToken,
  listDocuments,
  listDuplicates,
  listNotifications,
  loginAccount,
  parseOidcCallbackHash,
  registerAccount,
  searchDocuments,
  storeAccessToken,
  uploadDocument,
} from "../../lib/api";

const navItems = [
  { label: "Documents", icon: FileText },
  { label: "Tags", icon: Tags },
  { label: "Timeline", icon: History },
  { label: "Notifications", icon: Bell },
  { label: "Security", icon: ShieldCheck },
];

export function AppShell() {
  const queryClient = useQueryClient();
  const [accessToken, setAccessToken] = useState<string | null>(() =>
    getStoredAccessToken(),
  );
  const [showAuthScreen, setShowAuthScreen] = useState(false);
  const [oidcError, setOidcError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(
    null,
  );

  const authConfigQuery = useQuery({
    queryKey: ["auth-config"],
    queryFn: getAuthConfig,
  });
  const meQuery = useQuery({
    queryKey: ["auth", "me", accessToken],
    queryFn: getMe,
    enabled: accessToken !== null,
  });
  const canUseDevIdentity = authConfigQuery.data?.dev_headers_enabled === true;
  const canAccessWorkspace = accessToken !== null || canUseDevIdentity;
  const workspaceEnabled = canAccessWorkspace && !showAuthScreen;

  const documentsQuery = useQuery({
    queryKey: ["documents"],
    queryFn: listDocuments,
    enabled: workspaceEnabled,
  });
  const searchQuery = useQuery({
    queryKey: ["search", submittedQuery],
    queryFn: () => searchDocuments(submittedQuery),
    enabled: workspaceEnabled && submittedQuery.trim().length > 0,
  });
  const notificationsQuery = useQuery({
    queryKey: ["notifications"],
    queryFn: listNotifications,
    enabled: workspaceEnabled,
  });
  const duplicatesQuery = useQuery({
    queryKey: ["duplicates"],
    queryFn: listDuplicates,
    enabled: workspaceEnabled,
  });
  const detailQuery = useQuery({
    queryKey: ["document", selectedDocumentId],
    queryFn: () => getDocument(selectedDocumentId!),
    enabled: workspaceEnabled && selectedDocumentId !== null,
  });
  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadDocument(file),
    onSuccess: async (response) => {
      setSelectedDocumentId(response.document.id);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["documents"] }),
        queryClient.invalidateQueries({ queryKey: ["search"] }),
      ]);
    },
  });

  function handleAuthenticated(response: TokenResponse) {
    storeAccessToken(response.access_token);
    setAccessToken(response.access_token);
    setShowAuthScreen(false);
    setOidcError(null);
    void queryClient.invalidateQueries();
  }

  function handleOidcSignIn() {
    const redirectTo = `${window.location.pathname}${window.location.search}`;
    window.location.assign(buildOidcLoginUrl(redirectTo));
  }

  function handleSignOut() {
    clearStoredAccessToken();
    setAccessToken(null);
    setSelectedDocumentId(null);
    queryClient.clear();
  }

  useEffect(() => {
    if (window.location.pathname !== "/auth/oidc/callback") {
      return;
    }

    const callbackResult = parseOidcCallbackHash(window.location.hash);
    if (!callbackResult) {
      setShowAuthScreen(true);
      setOidcError("OIDC sign-in did not return an access token.");
      window.history.replaceState(null, "", "/");
      return;
    }

    if (callbackResult.status === "error") {
      setShowAuthScreen(true);
      setOidcError(callbackResult.errorDescription ?? callbackResult.error);
      window.history.replaceState(null, "", callbackResult.redirectTo);
      return;
    }

    storeAccessToken(callbackResult.accessToken);
    setAccessToken(callbackResult.accessToken);
    setShowAuthScreen(false);
    setOidcError(null);
    window.history.replaceState(null, "", callbackResult.redirectTo);
    void queryClient.invalidateQueries();
  }, [queryClient]);

  const visibleDocuments = useMemo(() => {
    if (submittedQuery.trim()) {
      return (searchQuery.data ?? []).map((result) => ({
        id: result.document_id,
        title: result.title,
        original_filename: result.original_filename,
        document_type: result.document_type,
        status: result.status,
        created_at: result.created_at,
      }));
    }
    return documentsQuery.data ?? [];
  }, [documentsQuery.data, searchQuery.data, submittedQuery]);

  useEffect(() => {
    if (
      workspaceEnabled &&
      !selectedDocumentId &&
      visibleDocuments.length > 0
    ) {
      setSelectedDocumentId(visibleDocuments[0].id);
    }
  }, [selectedDocumentId, visibleDocuments, workspaceEnabled]);

  const pendingNotifications =
    notificationsQuery.data?.filter((item) => item.status === "pending")
      .length ?? 0;
  const pendingDocuments =
    documentsQuery.data?.filter((item) => item.status.includes("processing"))
      .length ?? 0;
  const duplicateGroups = duplicatesQuery.data?.length ?? 0;

  if (!authConfigQuery.data && accessToken === null) {
    return <AuthLoading />;
  }

  if (!canAccessWorkspace || showAuthScreen) {
    return (
      <AuthScreen
        authConfig={authConfigQuery.data}
        allowDevIdentity={canUseDevIdentity}
        oidcError={oidcError}
        onAuthenticated={handleAuthenticated}
        onDevIdentity={() => setShowAuthScreen(false)}
        onOidcSignIn={handleOidcSignIn}
      />
    );
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="grid min-h-screen lg:grid-cols-[240px_420px_1fr]">
        <aside className="border-r border-border bg-card px-4 py-5">
          <div className="mb-8 flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <FileText className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <p className="text-sm font-semibold">PaperVault</p>
              <p className="text-xs text-muted-foreground">
                Personal knowledge base
              </p>
            </div>
          </div>

          <nav aria-label="Primary navigation" className="space-y-1">
            {navItems.map((item) => (
              <a
                className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
                href="/"
                key={item.label}
              >
                <item.icon className="h-4 w-4" aria-hidden="true" />
                {item.label}
              </a>
            ))}
          </nav>

          <AuthStatus
            user={meQuery.data}
            usingDevIdentity={accessToken === null}
            onSignIn={() => setShowAuthScreen(true)}
            onSignOut={handleSignOut}
          />
        </aside>

        <section className="flex min-w-0 flex-col border-r border-border">
          <header className="border-b border-border px-5 py-4">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h1 className="text-xl font-semibold tracking-normal">
                  Documents
                </h1>
                <p className="text-sm text-muted-foreground">
                  Search, upload, and review extracted knowledge.
                </p>
              </div>
              <UploadButton
                disabled={uploadMutation.isPending}
                onUpload={(file) => uploadMutation.mutate(file)}
              />
            </div>

            <form
              className="relative"
              onSubmit={(event) => {
                event.preventDefault();
                setSubmittedQuery(query.trim());
              }}
            >
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <input
                className="h-11 w-full rounded-md border border-input bg-background pl-10 pr-4 text-sm outline-none ring-offset-background placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="Search documents, tags, issuers, or questions"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </form>
          </header>

          <div className="grid grid-cols-3 gap-3 border-b border-border p-4">
            <Metric
              label="Documents"
              value={documentsQuery.data?.length ?? 0}
            />
            <Metric label="Processing" value={pendingDocuments} />
            <Metric label="Due" value={pendingNotifications} />
          </div>

          <div className="min-h-0 flex-1 overflow-auto p-3">
            {documentsQuery.isLoading ? (
              <p className="p-3 text-sm text-muted-foreground">Loading...</p>
            ) : visibleDocuments.length === 0 ? (
              <p className="p-3 text-sm text-muted-foreground">
                No documents found.
              </p>
            ) : (
              <div className="space-y-2">
                {visibleDocuments.map((document) => (
                  <button
                    className={`w-full rounded-md border p-3 text-left text-sm ${
                      selectedDocumentId === document.id
                        ? "border-primary bg-muted"
                        : "border-border bg-card hover:bg-muted"
                    }`}
                    key={document.id}
                    onClick={() => setSelectedDocumentId(document.id)}
                  >
                    <span className="block font-medium">{document.title}</span>
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {document.document_type.replaceAll("_", " ")} -{" "}
                      {document.status.replaceAll("_", " ")}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="min-w-0 overflow-auto">
          <DocumentPanel
            detail={detailQuery.data}
            duplicateGroups={duplicateGroups}
            notifications={notificationsQuery.data ?? []}
            isLoading={detailQuery.isLoading}
          />
        </section>
      </div>
    </main>
  );
}

function AuthLoading() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background text-foreground">
      <div className="rounded-md border border-border bg-card p-5 text-sm text-muted-foreground">
        Loading authentication settings...
      </div>
    </main>
  );
}

function AuthScreen({
  authConfig,
  allowDevIdentity,
  oidcError,
  onAuthenticated,
  onDevIdentity,
  onOidcSignIn,
}: {
  authConfig: AuthConfig | undefined;
  allowDevIdentity: boolean;
  oidcError: string | null;
  onAuthenticated: (response: TokenResponse) => void;
  onDevIdentity: () => void;
  onOidcSignIn: () => void;
}) {
  const registrationEnabled = authConfig?.local_registration_enabled === true;
  const [mode, setMode] = useState<"login" | "register">(
    registrationEnabled ? "register" : "login",
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const authMutation = useMutation({
    mutationFn: () =>
      mode === "login"
        ? loginAccount({ email, password })
        : registerAccount({
            email,
            password,
            display_name: displayName.trim() || undefined,
          }),
    onSuccess: onAuthenticated,
  });
  const errorMessage =
    authMutation.error instanceof Error ? authMutation.error.message : null;
  const oidcEnabled = authConfig?.oidc_configured === true;

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 text-foreground">
      <section className="w-full max-w-md rounded-md border border-border bg-card p-6">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <ShieldCheck className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-lg font-semibold">PaperVault</h1>
            <p className="text-sm text-muted-foreground">
              Sign in to your document vault.
            </p>
          </div>
        </div>

        <div className="mb-4 grid grid-cols-2 rounded-md bg-muted p-1">
          <button
            className={`rounded px-3 py-2 text-sm ${
              mode === "login"
                ? "bg-background shadow-sm"
                : "text-muted-foreground"
            }`}
            type="button"
            onClick={() => setMode("login")}
          >
            Sign in
          </button>
          <button
            className={`rounded px-3 py-2 text-sm ${
              mode === "register"
                ? "bg-background shadow-sm"
                : "text-muted-foreground"
            }`}
            type="button"
            disabled={!registrationEnabled}
            onClick={() => setMode("register")}
          >
            Register
          </button>
        </div>

        {oidcEnabled ? (
          <Button
            className="mb-4 w-full"
            variant="secondary"
            type="button"
            onClick={onOidcSignIn}
          >
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            Sign in with OIDC
          </Button>
        ) : null}

        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            authMutation.mutate();
          }}
        >
          {mode === "register" ? (
            <label className="block text-sm">
              <span className="mb-1 block text-muted-foreground">
                Display name
              </span>
              <input
                className="h-10 w-full rounded-md border border-input bg-background px-3 outline-none focus-visible:ring-2 focus-visible:ring-ring"
                autoComplete="name"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </label>
          ) : null}

          <label className="block text-sm">
            <span className="mb-1 block text-muted-foreground">Email</span>
            <input
              className="h-10 w-full rounded-md border border-input bg-background px-3 outline-none focus-visible:ring-2 focus-visible:ring-ring"
              autoComplete="email"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>

          <label className="block text-sm">
            <span className="mb-1 block text-muted-foreground">Password</span>
            <input
              className="h-10 w-full rounded-md border border-input bg-background px-3 outline-none focus-visible:ring-2 focus-visible:ring-ring"
              autoComplete={
                mode === "register" ? "new-password" : "current-password"
              }
              type="password"
              required
              minLength={mode === "register" ? 12 : 1}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          {errorMessage ? (
            <p className="rounded-md border border-border bg-muted p-3 text-sm text-foreground">
              {errorMessage}
            </p>
          ) : null}

          {oidcError ? (
            <p className="rounded-md border border-border bg-muted p-3 text-sm text-foreground">
              {oidcError}
            </p>
          ) : null}

          <Button
            className="w-full"
            disabled={
              authMutation.isPending || authConfig?.local_auth_enabled !== true
            }
            type="submit"
          >
            {mode === "login" ? (
              <LogIn className="h-4 w-4" aria-hidden="true" />
            ) : (
              <UserPlus className="h-4 w-4" aria-hidden="true" />
            )}
            {mode === "login" ? "Sign in" : "Create account"}
          </Button>
        </form>

        {allowDevIdentity ? (
          <Button
            className="mt-3 w-full"
            variant="secondary"
            type="button"
            onClick={onDevIdentity}
          >
            Continue with development identity
          </Button>
        ) : null}
      </section>
    </main>
  );
}

function AuthStatus({
  user,
  usingDevIdentity,
  onSignIn,
  onSignOut,
}: {
  user: AuthUser | undefined;
  usingDevIdentity: boolean;
  onSignIn: () => void;
  onSignOut: () => void;
}) {
  return (
    <section className="mt-8 rounded-md border border-border bg-background p-3">
      <p className="text-xs uppercase text-muted-foreground">Account</p>
      {usingDevIdentity ? (
        <>
          <p className="mt-2 text-sm font-medium">Development identity</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Header fallback is active for local development.
          </p>
          <Button
            className="mt-3 w-full"
            size="sm"
            type="button"
            onClick={onSignIn}
          >
            Sign in
          </Button>
        </>
      ) : (
        <>
          <p className="mt-2 truncate text-sm font-medium">
            {user?.email ?? "Signed in"}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {user?.role ?? "Loading account"}
          </p>
          <Button
            className="mt-3 w-full"
            size="sm"
            variant="secondary"
            type="button"
            onClick={onSignOut}
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
            Sign out
          </Button>
        </>
      )}
    </section>
  );
}

function UploadButton({
  disabled,
  onUpload,
}: {
  disabled: boolean;
  onUpload: (file: File) => void;
}) {
  return (
    <label>
      <input
        className="sr-only"
        type="file"
        accept="application/pdf,image/jpeg,image/png"
        disabled={disabled}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) {
            onUpload(file);
          }
          event.currentTarget.value = "";
        }}
      />
      <span>
        <Button asChild disabled={disabled}>
          <span>
            <Upload className="h-4 w-4" aria-hidden="true" />
            Upload
          </span>
        </Button>
      </span>
    </label>
  );
}

function DocumentPanel({
  detail,
  duplicateGroups,
  notifications,
  isLoading,
}: {
  detail: DocumentDetail | undefined;
  duplicateGroups: number;
  notifications: Array<{ id: string; title: string; due_date: string }>;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <p className="p-5 text-sm text-muted-foreground">Loading document...</p>
    );
  }
  if (!detail) {
    return (
      <p className="p-5 text-sm text-muted-foreground">Select a document.</p>
    );
  }

  return (
    <div className="grid min-h-screen xl:grid-cols-[1fr_360px]">
      <div className="min-h-[480px] border-r border-border bg-muted/40">
        <DocumentPreview document={detail.document} />
      </div>
      <aside className="space-y-5 p-5">
        <div>
          <p className="text-xs uppercase text-muted-foreground">
            {detail.document.document_type.replaceAll("_", " ")}
          </p>
          <h2 className="mt-1 text-lg font-semibold">
            {detail.document.title}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {detail.document.original_filename}
          </p>
        </div>

        <Panel title="AI Summary">
          <p className="text-sm text-muted-foreground">
            {detail.ai_analysis?.summary ?? "No summary generated yet."}
          </p>
          {detail.ai_analysis?.suggested_tags?.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {detail.ai_analysis.suggested_tags.map((tag) => (
                <span
                  className="rounded-md bg-muted px-2 py-1 text-xs"
                  key={tag}
                >
                  {tag}
                </span>
              ))}
            </div>
          ) : null}
        </Panel>

        <Panel title="Metadata">
          {detail.metadata ? (
            <dl className="space-y-2 text-sm">
              {Object.entries(detail.metadata.data).map(([key, value]) => (
                <div className="grid grid-cols-[130px_1fr] gap-3" key={key}>
                  <dt className="text-muted-foreground">
                    {key.replaceAll("_", " ")}
                  </dt>
                  <dd>{String(value)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">
              No metadata extracted.
            </p>
          )}
        </Panel>

        <Panel title="Tags">
          {detail.tags.length ? (
            <div className="flex flex-wrap gap-2">
              {detail.tags.map((tag) => (
                <span
                  className="rounded-md border border-border px-2 py-1 text-xs"
                  key={tag.id}
                >
                  {tag.name}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No tags assigned.</p>
          )}
        </Panel>

        <Panel title="Timeline">
          <div className="space-y-3">
            {detail.timeline_events.slice(0, 6).map((event) => (
              <div className="text-sm" key={event.id}>
                <p>{event.event_type.replaceAll("_", " ")}</p>
                <p className="text-xs text-muted-foreground">
                  {new Date(event.occurred_at).toLocaleString()}
                </p>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="System">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <Metric label="Duplicates" value={duplicateGroups} />
            <Metric label="Notifications" value={notifications.length} />
          </div>
        </Panel>
      </aside>
    </div>
  );
}

function DocumentPreview({ document }: { document: DocumentItem }) {
  const fileQuery = useQuery({
    queryKey: ["document-file", document.id],
    queryFn: async () =>
      URL.createObjectURL(await getDocumentFile(document.id)),
  });

  useEffect(() => {
    return () => {
      if (fileQuery.data) {
        URL.revokeObjectURL(fileQuery.data);
      }
    };
  }, [fileQuery.data]);

  if (fileQuery.isLoading) {
    return (
      <p className="p-5 text-sm text-muted-foreground">Loading preview...</p>
    );
  }
  if (!fileQuery.data) {
    return (
      <p className="p-5 text-sm text-muted-foreground">Preview unavailable.</p>
    );
  }
  if (document.content_type.startsWith("image/")) {
    return (
      <img
        alt={document.title}
        className="h-full max-h-screen w-full object-contain p-4"
        src={fileQuery.data}
      />
    );
  }
  return (
    <iframe
      className="h-screen min-h-[640px] w-full"
      src={fileQuery.data}
      title={document.title}
    />
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-sm font-medium">{title}</h3>
      <div className="rounded-md border border-border bg-card p-3">
        {children}
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border bg-card p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}
