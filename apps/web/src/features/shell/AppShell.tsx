import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Bell,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  Clock3,
  FileSearch,
  FileText,
  FolderOpen,
  History,
  LayoutDashboard,
  LogIn,
  LogOut,
  Search,
  ShieldCheck,
  Sparkles,
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
  DocumentTypeDefinition,
  RecentSearch,
  SavedSearch,
  SearchFilters,
  SearchMode,
  SearchRequestInput,
  TagItem,
  TokenResponse,
  archiveDocument,
  attachTag,
  buildOidcLoginUrl,
  clearStoredAccessToken,
  createTag,
  detachTag,
  getAuthConfig,
  getDocument,
  getDocumentFile,
  getMe,
  getStoredAccessToken,
  listDocumentTypes,
  listDocuments,
  listDuplicates,
  listNotifications,
  listRecentSearches,
  listSavedSearches,
  listTags,
  loginAccount,
  parseOidcCallbackHash,
  registerAccount,
  saveSearch,
  searchDocuments,
  storeAccessToken,
  updateDocument,
  updateDocumentMetadata,
  uploadDocument,
} from "../../lib/api";
import { cn } from "../../lib/utils";

const navItems = [
  { label: "Overview", icon: LayoutDashboard, active: false },
  { label: "Documents", icon: FileText, active: true },
  { label: "Tags", icon: Tags, active: false },
  { label: "Timeline", icon: History, active: false },
  { label: "Notifications", icon: Bell, active: false },
  { label: "Security", icon: ShieldCheck, active: false },
];

type DocumentListEntry = Pick<
  DocumentItem,
  | "id"
  | "title"
  | "original_filename"
  | "document_type"
  | "status"
  | "created_at"
>;

const defaultSearchFilters: SearchFilters = {
  document_type: null,
  issuer: null,
  organization: null,
  tag: null,
  date_from: null,
  date_to: null,
  include_archived: false,
};

export function AppShell() {
  const queryClient = useQueryClient();
  const [accessToken, setAccessToken] = useState<string | null>(() =>
    getStoredAccessToken(),
  );
  const [showAuthScreen, setShowAuthScreen] = useState(false);
  const [oidcError, setOidcError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("hybrid");
  const [filters, setFilters] = useState<SearchFilters>(defaultSearchFilters);
  const [submittedSearch, setSubmittedSearch] =
    useState<SearchRequestInput | null>(null);
  const [saveSearchName, setSaveSearchName] = useState("");
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
  const documentTypesQuery = useQuery({
    queryKey: ["document-types"],
    queryFn: listDocumentTypes,
    enabled: workspaceEnabled,
  });
  const tagsQuery = useQuery({
    queryKey: ["tags"],
    queryFn: listTags,
    enabled: workspaceEnabled,
  });
  const savedSearchesQuery = useQuery({
    queryKey: ["search", "saved"],
    queryFn: listSavedSearches,
    enabled: workspaceEnabled,
  });
  const recentSearchesQuery = useQuery({
    queryKey: ["search", "recent"],
    queryFn: listRecentSearches,
    enabled: workspaceEnabled,
  });
  const searchQuery = useQuery({
    queryKey: ["search", "results", submittedSearch],
    queryFn: async () => {
      const results = await searchDocuments(submittedSearch!);
      await queryClient.invalidateQueries({ queryKey: ["search", "recent"] });
      return results;
    },
    enabled: workspaceEnabled && submittedSearch !== null,
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
  const documentUpdateMutation = useMutation({
    mutationFn: (input: {
      documentId: string;
      updates: Parameters<typeof updateDocument>[1];
    }) => updateDocument(input.documentId, input.updates),
    onSuccess: async (document) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["documents"] }),
        queryClient.invalidateQueries({ queryKey: ["document", document.id] }),
        queryClient.invalidateQueries({ queryKey: ["search"] }),
      ]);
    },
  });
  const metadataUpdateMutation = useMutation({
    mutationFn: (input: {
      documentId: string;
      metadata: Parameters<typeof updateDocumentMetadata>[1];
    }) => updateDocumentMetadata(input.documentId, input.metadata),
    onSuccess: async (_metadata, input) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ["document", input.documentId],
        }),
        queryClient.invalidateQueries({ queryKey: ["documents"] }),
        queryClient.invalidateQueries({ queryKey: ["search"] }),
      ]);
    },
  });
  const archiveMutation = useMutation({
    mutationFn: archiveDocument,
    onSuccess: async (document) => {
      setSelectedDocumentId(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["documents"] }),
        queryClient.invalidateQueries({ queryKey: ["document", document.id] }),
        queryClient.invalidateQueries({ queryKey: ["search"] }),
        queryClient.invalidateQueries({ queryKey: ["duplicates"] }),
      ]);
    },
  });
  const tagAttachMutation = useMutation({
    mutationFn: (input: { documentId: string; tagId: string }) =>
      attachTag(input.documentId, input.tagId),
    onSuccess: async (_response, input) => {
      await invalidateDocumentTags(input.documentId);
    },
  });
  const tagDetachMutation = useMutation({
    mutationFn: (input: { documentId: string; tagId: string }) =>
      detachTag(input.documentId, input.tagId),
    onSuccess: async (_response, input) => {
      await invalidateDocumentTags(input.documentId);
    },
  });
  const tagCreateAttachMutation = useMutation({
    mutationFn: async (input: { documentId: string; name: string }) => {
      const tagName = input.name.trim();
      if (!tagName) {
        throw new Error("Tag name is required.");
      }
      const existingTag = (tagsQuery.data ?? []).find(
        (tag) => tag.slug === slugifyTagName(tagName),
      );
      const tag = existingTag ?? (await createTag({ name: tagName }));
      await attachTag(input.documentId, tag.id);
      return { documentId: input.documentId };
    },
    onSuccess: async (response) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["tags"] }),
        invalidateDocumentTags(response.documentId),
      ]);
    },
  });
  const saveSearchMutation = useMutation({
    mutationFn: saveSearch,
    onSuccess: async () => {
      setSaveSearchName("");
      await queryClient.invalidateQueries({ queryKey: ["search", "saved"] });
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

  function currentSearchInput(): SearchRequestInput {
    return {
      query: query.trim(),
      mode: searchMode,
      filters: normalizeUiFilters(filters),
      limit: 50,
      offset: 0,
    };
  }

  function submitSearch(input = currentSearchInput()) {
    const normalizedInput = {
      ...input,
      filters: normalizeUiFilters(input.filters),
    };
    setQuery(normalizedInput.query);
    setSearchMode(normalizedInput.mode);
    setFilters(normalizedInput.filters);
    setSubmittedSearch(normalizedInput);
  }

  function clearSearch() {
    setQuery("");
    setSearchMode("hybrid");
    setFilters(defaultSearchFilters);
    setSubmittedSearch(null);
  }

  function saveCurrentSearch() {
    const name = saveSearchName.trim();
    if (!name) {
      return;
    }
    saveSearchMutation.mutate({
      name,
      query: query.trim(),
      mode: searchMode,
      filters: normalizeUiFilters(filters),
    });
  }

  async function invalidateDocumentTags(documentId: string) {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["document", documentId] }),
      queryClient.invalidateQueries({ queryKey: ["search"] }),
    ]);
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

  const visibleDocuments = useMemo<DocumentListEntry[]>(() => {
    if (submittedSearch) {
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
  }, [documentsQuery.data, searchQuery.data, submittedSearch]);

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
  const documentCount = documentsQuery.data?.length ?? 0;
  const readyDocuments =
    documentsQuery.data?.filter((item) => item.status === "ready").length ?? 0;
  const duplicateGroups = duplicatesQuery.data?.length ?? 0;
  const tagMutationError =
    [
      tagCreateAttachMutation.error,
      tagAttachMutation.error,
      tagDetachMutation.error,
    ].find((error): error is Error => error instanceof Error)?.message ?? null;

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
      <div className="grid min-h-screen xl:grid-cols-[280px_minmax(440px,520px)_minmax(0,1fr)]">
        <aside className="flex min-h-screen flex-col border-r border-border bg-card px-5 py-6">
          <div className="mb-8 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
              <FileText className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <p className="text-base font-semibold">PaperVault</p>
              <p className="text-xs text-muted-foreground">
                Personal document intelligence
              </p>
            </div>
          </div>

          <nav aria-label="Primary navigation" className="space-y-1">
            {navItems.map((item) => (
              <a
                className={cn(
                  "flex items-center justify-between rounded-lg px-3 py-2.5 text-sm transition-colors",
                  item.active
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
                href="/"
                key={item.label}
                aria-current={item.active ? "page" : undefined}
              >
                <span className="flex items-center gap-3">
                  <item.icon className="h-4 w-4" aria-hidden="true" />
                  {item.label}
                </span>
                {item.label === "Notifications" && pendingNotifications > 0 ? (
                  <span className="rounded-full bg-background/20 px-2 py-0.5 text-xs">
                    {pendingNotifications}
                  </span>
                ) : null}
              </a>
            ))}
          </nav>

          <section className="mt-8 rounded-lg border border-border bg-background p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Vault health
            </p>
            <div className="mt-4 space-y-3">
              <SidebarStat label="Ready" value={readyDocuments} />
              <SidebarStat label="Processing" value={pendingDocuments} />
              <SidebarStat label="Due soon" value={pendingNotifications} />
            </div>
          </section>

          <div className="mt-auto">
            <AuthStatus
              user={meQuery.data}
              usingDevIdentity={accessToken === null}
              onSignIn={() => setShowAuthScreen(true)}
              onSignOut={handleSignOut}
            />
          </div>
        </aside>

        <section className="flex min-w-0 flex-col border-r border-border bg-card/80">
          <header className="border-b border-border bg-card px-6 py-5">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Document workspace
                </p>
                <h1 className="mt-1 text-2xl font-semibold tracking-normal">
                  Documents
                </h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Search, upload, classify, and review extracted knowledge.
                </p>
              </div>
              <UploadButton
                disabled={uploadMutation.isPending}
                onUpload={(file) => uploadMutation.mutate(file)}
              />
            </div>

            <SearchControls
              query={query}
              mode={searchMode}
              filters={filters}
              saveSearchName={saveSearchName}
              documentTypes={documentTypesQuery.data ?? []}
              tags={tagsQuery.data ?? []}
              savedSearches={savedSearchesQuery.data ?? []}
              recentSearches={recentSearchesQuery.data ?? []}
              isSaving={saveSearchMutation.isPending}
              onQueryChange={setQuery}
              onModeChange={setSearchMode}
              onFiltersChange={setFilters}
              onSaveNameChange={setSaveSearchName}
              onSubmit={() => submitSearch()}
              onClear={clearSearch}
              onSave={saveCurrentSearch}
              onApplySearch={submitSearch}
            />
          </header>

          <div className="grid grid-cols-3 gap-3 border-b border-border bg-background/70 p-4">
            <Metric
              label="Documents"
              value={documentCount}
              icon={FolderOpen}
              detail="In vault"
              tone="primary"
            />
            <Metric
              label="Processing"
              value={pendingDocuments}
              icon={Clock3}
              detail="In queue"
              tone="warning"
            />
            <Metric
              label="Due"
              value={pendingNotifications}
              icon={CalendarClock}
              detail="Reminders"
              tone="danger"
            />
          </div>

          <div className="min-h-0 flex-1 overflow-auto bg-background/60 p-4">
            {documentsQuery.isLoading ? (
              <DocumentListSkeleton />
            ) : visibleDocuments.length === 0 ? (
              <DocumentListEmptyState
                hasSearch={submittedSearch !== null}
                isUploading={uploadMutation.isPending}
                onClear={clearSearch}
                onUpload={(file) => uploadMutation.mutate(file)}
              />
            ) : (
              <div className="space-y-2">
                {visibleDocuments.map((document) => (
                  <DocumentListItem
                    document={document}
                    key={document.id}
                    selected={selectedDocumentId === document.id}
                    onSelect={() => setSelectedDocumentId(document.id)}
                  />
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="min-w-0 overflow-auto bg-background">
          <DocumentPanel
            detail={detailQuery.data}
            duplicateGroups={duplicateGroups}
            notifications={notificationsQuery.data ?? []}
            tags={tagsQuery.data ?? []}
            isUploading={uploadMutation.isPending}
            isLoading={detailQuery.isLoading}
            isUpdating={
              documentUpdateMutation.isPending ||
              metadataUpdateMutation.isPending ||
              archiveMutation.isPending
            }
            isTagUpdating={
              tagCreateAttachMutation.isPending ||
              tagAttachMutation.isPending ||
              tagDetachMutation.isPending
            }
            tagError={tagMutationError}
            onArchive={(documentId) => archiveMutation.mutate(documentId)}
            onUpdateDocument={(documentId, updates) =>
              documentUpdateMutation.mutate({ documentId, updates })
            }
            onUpdateMetadata={(documentId, metadata) =>
              metadataUpdateMutation.mutate({ documentId, metadata })
            }
            onUpload={(file) => uploadMutation.mutate(file)}
            onAttachTag={(documentId, tagId) =>
              tagAttachMutation.mutate({ documentId, tagId })
            }
            onCreateAndAttachTag={(documentId, name) =>
              tagCreateAttachMutation.mutate({ documentId, name })
            }
            onDetachTag={(documentId, tagId) =>
              tagDetachMutation.mutate({ documentId, tagId })
            }
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
    <section className="rounded-lg border border-border bg-background p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Account
      </p>
      {usingDevIdentity ? (
        <>
          <p className="mt-2 text-sm font-semibold">Development identity</p>
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
          <p className="mt-2 truncate text-sm font-semibold">
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

function SidebarStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-semibold">{value}</span>
    </div>
  );
}

function UploadButton({
  disabled,
  onUpload,
  className,
  variant = "default",
}: {
  disabled: boolean;
  onUpload: (file: File) => void;
  className?: string;
  variant?: "default" | "secondary" | "ghost";
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
        <Button
          asChild
          className={className}
          disabled={disabled}
          variant={variant}
        >
          <span>
            <Upload className="h-4 w-4" aria-hidden="true" />
            Upload
          </span>
        </Button>
      </span>
    </label>
  );
}

function DocumentListSkeleton() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((item) => (
        <div
          className="h-24 animate-pulse rounded-lg border border-border bg-card"
          key={item}
        />
      ))}
    </div>
  );
}

function DocumentListEmptyState({
  hasSearch,
  isUploading,
  onClear,
  onUpload,
}: {
  hasSearch: boolean;
  isUploading: boolean;
  onClear: () => void;
  onUpload: (file: File) => void;
}) {
  return (
    <section className="rounded-lg border border-dashed border-border bg-card p-6 text-center">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <FileSearch className="h-6 w-6" aria-hidden="true" />
      </div>
      <h2 className="mt-4 text-base font-semibold">
        {hasSearch ? "No matching documents" : "Start building your vault"}
      </h2>
      <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
        {hasSearch
          ? "Try clearing filters or broadening your query."
          : "Upload PDFs, scanned files, or images and PaperVault will extract text, metadata, summaries, and tags."}
      </p>
      <div className="mt-5 flex flex-wrap justify-center gap-2">
        {hasSearch ? (
          <Button type="button" variant="secondary" onClick={onClear}>
            Clear search
          </Button>
        ) : null}
        <UploadButton
          disabled={isUploading}
          onUpload={onUpload}
          className="shadow-sm"
        />
      </div>
    </section>
  );
}

function DocumentListItem({
  document,
  selected,
  onSelect,
}: {
  document: DocumentListEntry;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={cn(
        "group w-full rounded-lg border bg-card p-4 text-left text-sm shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md",
        selected ? "border-primary/60 bg-primary/5 shadow-md" : "border-border",
      )}
      type="button"
      onClick={onSelect}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary">
          <FileText className="h-5 w-5" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <span className="line-clamp-2 font-semibold leading-5">
              {document.title}
            </span>
            <StatusBadge status={document.status} />
          </div>
          <p className="mt-1 truncate text-xs text-muted-foreground">
            {document.original_filename}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="rounded-md bg-muted px-2 py-1 capitalize">
              {document.document_type.replaceAll("_", " ")}
            </span>
            <span>{formatDateTime(document.created_at)}</span>
          </div>
        </div>
      </div>
    </button>
  );
}

function StatusBadge({ status }: { status: string }) {
  const normalizedStatus = status.replaceAll("_", " ");
  const ready = status === "ready";
  const processing = status.includes("processing");
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-1 text-xs font-medium capitalize",
        ready && "bg-emerald-50 text-emerald-700",
        processing && "bg-amber-50 text-amber-700",
        !ready && !processing && "bg-muted text-muted-foreground",
      )}
    >
      {ready ? <CheckCircle2 className="h-3 w-3" aria-hidden="true" /> : null}
      {processing ? <Clock3 className="h-3 w-3" aria-hidden="true" /> : null}
      {normalizedStatus}
    </span>
  );
}

function MiniMetric({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: number;
  icon: typeof FileText;
}) {
  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">{label}</p>
        <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
      </div>
      <p className="mt-2 text-lg font-semibold">{value}</p>
    </div>
  );
}

function SearchControls({
  query,
  mode,
  filters,
  saveSearchName,
  documentTypes,
  tags,
  savedSearches,
  recentSearches,
  isSaving,
  onQueryChange,
  onModeChange,
  onFiltersChange,
  onSaveNameChange,
  onSubmit,
  onClear,
  onSave,
  onApplySearch,
}: {
  query: string;
  mode: SearchMode;
  filters: SearchFilters;
  saveSearchName: string;
  documentTypes: DocumentTypeDefinition[];
  tags: TagItem[];
  savedSearches: SavedSearch[];
  recentSearches: RecentSearch[];
  isSaving: boolean;
  onQueryChange: (query: string) => void;
  onModeChange: (mode: SearchMode) => void;
  onFiltersChange: (filters: SearchFilters) => void;
  onSaveNameChange: (name: string) => void;
  onSubmit: () => void;
  onClear: () => void;
  onSave: () => void;
  onApplySearch: (search: SearchRequestInput) => void;
}) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const activeFilterCount = countActiveFilters(filters);

  function updateFilter<K extends keyof SearchFilters>(
    key: K,
    value: SearchFilters[K],
  ) {
    onFiltersChange({ ...filters, [key]: value });
  }

  return (
    <div className="rounded-lg border border-border bg-background p-3 shadow-sm">
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <div className="flex gap-2">
          <div className="relative min-w-0 flex-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <input
              className="h-11 w-full rounded-md border border-input bg-card pl-10 pr-4 text-sm outline-none ring-offset-background placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="Search documents, tags, issuers, or questions"
              type="search"
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
            />
          </div>
          <Button type="submit">Search</Button>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <button
            className="inline-flex items-center gap-2 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
            type="button"
            onClick={() => setAdvancedOpen((current) => !current)}
          >
            Filters
            {activeFilterCount > 0 ? (
              <span className="rounded-full bg-primary px-2 py-0.5 text-primary-foreground">
                {activeFilterCount}
              </span>
            ) : null}
            <ChevronDown
              className={cn(
                "h-3.5 w-3.5 transition-transform",
                advancedOpen && "rotate-180",
              )}
              aria-hidden="true"
            />
          </button>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              type="button"
              onClick={onClear}
            >
              Clear
            </Button>
          </div>
        </div>

        {advancedOpen ? (
          <div className="grid grid-cols-2 gap-2 rounded-lg border border-border bg-card p-3 text-sm">
            <label>
              <span className="mb-1 block text-xs text-muted-foreground">
                Mode
              </span>
              <select
                className="h-9 w-full rounded-md border border-input bg-background px-2 outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={mode}
                onChange={(event) =>
                  onModeChange(event.target.value as SearchMode)
                }
              >
                <option value="hybrid">Hybrid</option>
                <option value="keyword">Keyword</option>
                <option value="semantic">Semantic</option>
              </select>
            </label>
            <label>
              <span className="mb-1 block text-xs text-muted-foreground">
                Type
              </span>
              <select
                className="h-9 w-full rounded-md border border-input bg-background px-2 outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={filters.document_type ?? ""}
                onChange={(event) =>
                  updateFilter("document_type", event.target.value || null)
                }
              >
                <option value="">Any type</option>
                {documentTypes.map((documentType) => (
                  <option key={documentType.key} value={documentType.key}>
                    {documentType.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="mb-1 block text-xs text-muted-foreground">
                Tag
              </span>
              <select
                className="h-9 w-full rounded-md border border-input bg-background px-2 outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={filters.tag ?? ""}
                onChange={(event) =>
                  updateFilter("tag", event.target.value || null)
                }
              >
                <option value="">Any tag</option>
                {tags.map((tag) => (
                  <option key={tag.id} value={tag.slug}>
                    {tag.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="mb-1 block text-xs text-muted-foreground">
                Issuer
              </span>
              <input
                className="h-9 w-full rounded-md border border-input bg-background px-2 outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={filters.issuer ?? ""}
                onChange={(event) => updateFilter("issuer", event.target.value)}
              />
            </label>
            <label>
              <span className="mb-1 block text-xs text-muted-foreground">
                Organization
              </span>
              <input
                className="h-9 w-full rounded-md border border-input bg-background px-2 outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={filters.organization ?? ""}
                onChange={(event) =>
                  updateFilter("organization", event.target.value)
                }
              />
            </label>
            <label>
              <span className="mb-1 block text-xs text-muted-foreground">
                From
              </span>
              <input
                className="h-9 w-full rounded-md border border-input bg-background px-2 outline-none focus-visible:ring-2 focus-visible:ring-ring"
                type="date"
                value={filters.date_from ?? ""}
                onChange={(event) =>
                  updateFilter("date_from", event.target.value || null)
                }
              />
            </label>
            <label>
              <span className="mb-1 block text-xs text-muted-foreground">
                To
              </span>
              <input
                className="h-9 w-full rounded-md border border-input bg-background px-2 outline-none focus-visible:ring-2 focus-visible:ring-ring"
                type="date"
                value={filters.date_to ?? ""}
                onChange={(event) =>
                  updateFilter("date_to", event.target.value || null)
                }
              />
            </label>
            <label className="flex items-center gap-2 pt-6 text-xs text-muted-foreground">
              <input
                className="h-4 w-4"
                type="checkbox"
                checked={filters.include_archived === true}
                onChange={(event) =>
                  updateFilter("include_archived", event.target.checked)
                }
              />
              Include archived
            </label>
          </div>
        ) : null}
      </form>

      <div className="mt-3 flex gap-2 border-t border-border pt-3">
        <input
          className="h-9 min-w-0 flex-1 rounded-md border border-input bg-card px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          placeholder="Saved search name"
          value={saveSearchName}
          onChange={(event) => onSaveNameChange(event.target.value)}
        />
        <Button
          size="sm"
          variant="secondary"
          type="button"
          disabled={isSaving || !saveSearchName.trim()}
          onClick={onSave}
        >
          Save
        </Button>
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <SearchShortcutList
          title="Saved"
          emptyText="No saved searches."
          items={savedSearches.map((savedSearch) => ({
            id: savedSearch.id,
            title: savedSearch.name,
            description: describeSearch(savedSearch.query, savedSearch.filters),
            input: searchInputFromStoredSearch(savedSearch),
          }))}
          onApply={onApplySearch}
        />
        <SearchShortcutList
          title="Recent"
          emptyText="No recent searches."
          items={recentSearches.map((recentSearch) => ({
            id: recentSearch.id,
            title: recentSearch.query || "Filtered documents",
            description: describeSearch(
              recentSearch.query,
              recentSearch.filters,
            ),
            input: searchInputFromStoredSearch(recentSearch),
          }))}
          onApply={onApplySearch}
        />
      </div>
    </div>
  );
}

function SearchShortcutList({
  title,
  emptyText,
  items,
  onApply,
}: {
  title: string;
  emptyText: string;
  items: Array<{
    id: string;
    title: string;
    description: string;
    input: SearchRequestInput;
  }>;
  onApply: (input: SearchRequestInput) => void;
}) {
  return (
    <section>
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {title}
      </p>
      {items.length ? (
        <div className="space-y-1">
          {items.slice(0, 4).map((item) => (
            <button
              className="w-full rounded-md border border-border bg-card px-3 py-2 text-left text-xs shadow-sm transition-colors hover:border-primary/40 hover:bg-primary/5"
              key={item.id}
              type="button"
              onClick={() => onApply(item.input)}
            >
              <span className="block truncate font-medium">{item.title}</span>
              <span className="mt-1 block truncate text-muted-foreground">
                {item.description}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className="rounded-md border border-dashed border-border bg-card px-3 py-2 text-xs text-muted-foreground">
          {emptyText}
        </p>
      )}
    </section>
  );
}

function searchInputFromStoredSearch(
  search: SavedSearch | RecentSearch,
): SearchRequestInput {
  return {
    query: search.query,
    mode: search.mode,
    filters: coerceStoredFilters(search.filters),
    limit: 50,
    offset: 0,
  };
}

function normalizeUiFilters(filters: SearchFilters): SearchFilters {
  return {
    document_type: normalizeFilterText(filters.document_type),
    issuer: normalizeFilterText(filters.issuer),
    organization: normalizeFilterText(filters.organization),
    tag: normalizeFilterText(filters.tag),
    date_from: normalizeFilterText(filters.date_from),
    date_to: normalizeFilterText(filters.date_to),
    include_archived: filters.include_archived === true,
  };
}

function coerceStoredFilters(filters: Record<string, unknown>): SearchFilters {
  return {
    document_type: storedFilterText(filters.document_type),
    issuer: storedFilterText(filters.issuer),
    organization: storedFilterText(filters.organization),
    tag: storedFilterText(filters.tag),
    date_from: storedFilterText(filters.date_from),
    date_to: storedFilterText(filters.date_to),
    include_archived:
      filters.include_archived === true || filters.include_archived === "true",
  };
}

function describeSearch(
  query: string,
  filters: Record<string, unknown>,
): string {
  const normalized = coerceStoredFilters(filters);
  const parts = [];
  if (query.trim()) {
    parts.push(query.trim());
  }
  if (normalized.document_type) {
    parts.push(normalized.document_type.replaceAll("_", " "));
  }
  if (normalized.tag) {
    parts.push(`#${normalized.tag}`);
  }
  if (normalized.issuer) {
    parts.push(`issuer ${normalized.issuer}`);
  }
  if (normalized.organization) {
    parts.push(`org ${normalized.organization}`);
  }
  if (normalized.date_from || normalized.date_to) {
    parts.push(
      `${normalized.date_from ?? "any"} to ${normalized.date_to ?? "any"}`,
    );
  }
  if (normalized.include_archived) {
    parts.push("with archived");
  }
  return parts.join(" - ") || "All active documents";
}

function normalizeFilterText(value: string | null | undefined) {
  const normalized = value?.trim();
  return normalized ? normalized : null;
}

function storedFilterText(value: unknown) {
  if (typeof value !== "string") {
    return null;
  }
  return normalizeFilterText(value);
}

function slugifyTagName(value: string) {
  const slug = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "tag";
}

function countActiveFilters(filters: SearchFilters) {
  return [
    filters.document_type,
    filters.issuer,
    filters.organization,
    filters.tag,
    filters.date_from,
    filters.date_to,
    filters.include_archived === true ? "archived" : null,
  ].filter(Boolean).length;
}

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "No date";
  }
  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function DocumentOverviewEmptyState({
  isUploading,
  onUpload,
}: {
  isUploading: boolean;
  onUpload: (file: File) => void;
}) {
  return (
    <div className="min-h-screen bg-background p-8">
      <section className="mx-auto grid max-w-5xl gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-lg border border-border bg-card p-8 shadow-sm">
          <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <FileSearch className="h-6 w-6" aria-hidden="true" />
          </div>
          <p className="mt-6 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Ready for review
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-normal">
            Select a document or upload one to start.
          </h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground">
            PaperVault keeps source files separate from metadata, extracts text,
            identifies document type, and builds searchable summaries for your
            personal records.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <UploadButton
              disabled={isUploading}
              onUpload={onUpload}
              className="shadow-sm"
            />
            <div className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-muted-foreground">
              <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
              AI summary and tags after processing
            </div>
          </div>
        </div>

        <div className="grid gap-4">
          <OverviewCard
            icon={FileText}
            title="Upload PDFs and scans"
            description="Drop in statements, invoices, certificates, IDs, policies, and receipts."
          />
          <OverviewCard
            icon={Search}
            title="Ask natural questions"
            description="Find documents by meaning, metadata, issuer, tags, dates, or exact text."
          />
          <OverviewCard
            icon={CalendarClock}
            title="Track expiry and due dates"
            description="Surface warranties, renewals, policy expiry, and upcoming payments."
          />
        </div>
      </section>
    </div>
  );
}

function OverviewCard({
  icon: Icon,
  title,
  description,
}: {
  icon: typeof FileText;
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <Icon className="h-5 w-5 text-primary" aria-hidden="true" />
      <h3 className="mt-3 text-sm font-semibold">{title}</h3>
      <p className="mt-1 text-sm leading-6 text-muted-foreground">
        {description}
      </p>
    </div>
  );
}

function DocumentPanel({
  detail,
  duplicateGroups,
  notifications,
  tags,
  isUploading,
  isLoading,
  isUpdating,
  isTagUpdating,
  tagError,
  onArchive,
  onUpdateDocument,
  onUpdateMetadata,
  onUpload,
  onAttachTag,
  onCreateAndAttachTag,
  onDetachTag,
}: {
  detail: DocumentDetail | undefined;
  duplicateGroups: number;
  notifications: Array<{ id: string; title: string; due_date: string }>;
  tags: TagItem[];
  isUploading: boolean;
  isLoading: boolean;
  isUpdating: boolean;
  isTagUpdating: boolean;
  tagError: string | null;
  onArchive: (documentId: string) => void;
  onUpdateDocument: (
    documentId: string,
    updates: Parameters<typeof updateDocument>[1],
  ) => void;
  onUpdateMetadata: (
    documentId: string,
    metadata: Parameters<typeof updateDocumentMetadata>[1],
  ) => void;
  onUpload: (file: File) => void;
  onAttachTag: (documentId: string, tagId: string) => void;
  onCreateAndAttachTag: (documentId: string, name: string) => void;
  onDetachTag: (documentId: string, tagId: string) => void;
}) {
  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center p-8">
        <div className="rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted-foreground shadow-sm">
          Loading document...
        </div>
      </div>
    );
  }
  if (!detail) {
    return (
      <DocumentOverviewEmptyState
        isUploading={isUploading}
        onUpload={onUpload}
      />
    );
  }

  return (
    <div className="grid min-h-screen xl:grid-cols-[minmax(0,1fr)_400px]">
      <div className="flex min-h-screen flex-col bg-muted/50">
        <div className="flex items-center justify-between border-b border-border bg-card px-5 py-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Preview
            </p>
            <p className="mt-0.5 truncate text-sm font-medium">
              {detail.document.original_filename}
            </p>
          </div>
          <StatusBadge status={detail.document.status} />
        </div>
        <DocumentPreview document={detail.document} />
      </div>
      <aside className="border-l border-border bg-card">
        <div className="sticky top-0 z-10 border-b border-border bg-card px-5 py-5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {detail.document.document_type.replaceAll("_", " ")}
              </p>
              <h2 className="mt-1 line-clamp-2 text-xl font-semibold">
                {detail.document.title}
              </h2>
              <p className="mt-1 truncate text-sm text-muted-foreground">
                {detail.document.original_filename}
              </p>
            </div>
            <Button
              size="sm"
              variant="secondary"
              type="button"
              disabled={detail.document.status === "archived" || isUpdating}
              onClick={() => onArchive(detail.document.id)}
            >
              Archive
            </Button>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <MiniMetric
              label="Duplicates"
              value={duplicateGroups}
              icon={AlertCircle}
            />
            <MiniMetric
              label="Reminders"
              value={notifications.length}
              icon={CalendarClock}
            />
          </div>
          {detail.document.archived_at ? (
            <p className="mt-2 rounded-md border border-border bg-muted p-2 text-xs text-muted-foreground">
              Archived {new Date(detail.document.archived_at).toLocaleString()}
            </p>
          ) : null}
        </div>

        <div className="space-y-5 p-5">
          <Panel title="Document Fields">
            <DocumentFieldsEditor
              document={detail.document}
              disabled={isUpdating}
              onSave={(updates) =>
                onUpdateDocument(detail.document.id, updates)
              }
            />
          </Panel>

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
            <MetadataEditor
              metadata={detail.metadata}
              document={detail.document}
              disabled={isUpdating}
              onSave={(metadata) =>
                onUpdateMetadata(detail.document.id, metadata)
              }
            />
          </Panel>

          <Panel title="Tags">
            <TagEditor
              assignedTags={detail.tags}
              availableTags={tags}
              disabled={isTagUpdating}
              error={tagError}
              suggestedTags={detail.ai_analysis?.suggested_tags ?? []}
              onAttachTag={(tagId) => onAttachTag(detail.document.id, tagId)}
              onCreateAndAttachTag={(name) =>
                onCreateAndAttachTag(detail.document.id, name)
              }
              onDetachTag={(tagId) => onDetachTag(detail.document.id, tagId)}
            />
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

          <Panel title="Versions">
            {detail.versions.length ? (
              <div className="space-y-3 text-sm">
                {detail.versions.map((version) => (
                  <div key={version.id}>
                    <p>Version {version.version_number}</p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(version.created_at).toLocaleString()} -{" "}
                      {Math.round(version.file_size_bytes / 1024)} KB
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No versions recorded.
              </p>
            )}
          </Panel>
        </div>
      </aside>
    </div>
  );
}

function TagEditor({
  assignedTags,
  availableTags,
  suggestedTags,
  disabled,
  error,
  onAttachTag,
  onCreateAndAttachTag,
  onDetachTag,
}: {
  assignedTags: DocumentDetail["tags"];
  availableTags: TagItem[];
  suggestedTags: string[];
  disabled: boolean;
  error: string | null;
  onAttachTag: (tagId: string) => void;
  onCreateAndAttachTag: (name: string) => void;
  onDetachTag: (tagId: string) => void;
}) {
  const [selectedTagId, setSelectedTagId] = useState("");
  const [tagName, setTagName] = useState("");
  const assignedTagIds = useMemo(
    () => new Set(assignedTags.map((tag) => tag.id)),
    [assignedTags],
  );
  const assignedTagSlugs = useMemo(
    () => new Set(assignedTags.map((tag) => tag.slug)),
    [assignedTags],
  );
  const attachableTags = useMemo(
    () => availableTags.filter((tag) => !assignedTagIds.has(tag.id)),
    [assignedTagIds, availableTags],
  );
  const attachableSuggestedTags = useMemo(() => {
    const seen = new Set<string>();
    return suggestedTags
      .map((tag) => tag.trim())
      .filter((tag) => {
        if (!tag) {
          return false;
        }
        const slug = slugifyTagName(tag);
        if (assignedTagSlugs.has(slug) || seen.has(slug)) {
          return false;
        }
        seen.add(slug);
        return true;
      });
  }, [assignedTagSlugs, suggestedTags]);

  useEffect(() => {
    if (
      selectedTagId &&
      !attachableTags.some((tag) => tag.id === selectedTagId)
    ) {
      setSelectedTagId("");
    }
  }, [attachableTags, selectedTagId]);

  return (
    <div className="space-y-4 text-sm">
      {assignedTags.length ? (
        <div className="flex flex-wrap gap-2">
          {assignedTags.map((tag) => (
            <span
              className="inline-flex items-center gap-2 rounded-md border border-border px-2 py-1 text-xs"
              key={tag.id}
            >
              {tag.name}
              <button
                className="text-muted-foreground hover:text-foreground"
                type="button"
                disabled={disabled}
                onClick={() => onDetachTag(tag.id)}
              >
                Remove
              </button>
            </span>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No tags assigned.</p>
      )}

      <div className="space-y-2">
        <label className="block">
          <span className="mb-1 block text-muted-foreground">Existing tag</span>
          <div className="flex gap-2">
            <select
              className="h-9 min-w-0 flex-1 rounded-md border border-input bg-background px-3 outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={selectedTagId}
              disabled={disabled || attachableTags.length === 0}
              onChange={(event) => setSelectedTagId(event.target.value)}
            >
              <option value="">Select a tag</option>
              {attachableTags.map((tag) => (
                <option key={tag.id} value={tag.id}>
                  {tag.name}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              type="button"
              disabled={disabled || !selectedTagId}
              onClick={() => {
                onAttachTag(selectedTagId);
                setSelectedTagId("");
              }}
            >
              Attach
            </Button>
          </div>
        </label>
      </div>

      <form
        className="space-y-2"
        onSubmit={(event) => {
          event.preventDefault();
          const normalizedName = tagName.trim();
          if (!normalizedName) {
            return;
          }
          onCreateAndAttachTag(normalizedName);
          setTagName("");
        }}
      >
        <label className="block">
          <span className="mb-1 block text-muted-foreground">New tag</span>
          <div className="flex gap-2">
            <input
              className="h-9 min-w-0 flex-1 rounded-md border border-input bg-background px-3 outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="e.g. tax, warranty, payroll"
              value={tagName}
              disabled={disabled}
              onChange={(event) => setTagName(event.target.value)}
            />
            <Button
              size="sm"
              type="submit"
              disabled={disabled || !tagName.trim()}
            >
              Create
            </Button>
          </div>
        </label>
      </form>

      {attachableSuggestedTags.length ? (
        <div>
          <p className="mb-2 text-xs uppercase text-muted-foreground">
            Suggested
          </p>
          <div className="flex flex-wrap gap-2">
            {attachableSuggestedTags.map((tag) => (
              <Button
                key={slugifyTagName(tag)}
                size="sm"
                variant="secondary"
                type="button"
                disabled={disabled}
                onClick={() => onCreateAndAttachTag(tag)}
              >
                Add {tag}
              </Button>
            ))}
          </div>
        </div>
      ) : null}

      {error ? (
        <p
          className="rounded-md border border-border bg-muted p-2 text-xs"
          role="alert"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}

function DocumentFieldsEditor({
  document,
  disabled,
  onSave,
}: {
  document: DocumentItem;
  disabled: boolean;
  onSave: (updates: Parameters<typeof updateDocument>[1]) => void;
}) {
  const [title, setTitle] = useState(document.title);
  const [documentType, setDocumentType] = useState(document.document_type);
  const [documentDate, setDocumentDate] = useState(
    document.document_date ?? "",
  );
  const [issuer, setIssuer] = useState(document.issuer ?? "");
  const [organization, setOrganization] = useState(document.organization ?? "");

  useEffect(() => {
    setTitle(document.title);
    setDocumentType(document.document_type);
    setDocumentDate(document.document_date ?? "");
    setIssuer(document.issuer ?? "");
    setOrganization(document.organization ?? "");
  }, [document]);

  return (
    <form
      className="space-y-3 text-sm"
      onSubmit={(event) => {
        event.preventDefault();
        onSave({
          title: title.trim(),
          document_type: documentType.trim(),
          document_date: documentDate || null,
          issuer: issuer.trim() || null,
          organization: organization.trim() || null,
        });
      }}
    >
      <label className="block">
        <span className="mb-1 block text-muted-foreground">Title</span>
        <input
          className="h-9 w-full rounded-md border border-input bg-background px-3 outline-none focus-visible:ring-2 focus-visible:ring-ring"
          value={title}
          disabled={disabled}
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>
      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className="mb-1 block text-muted-foreground">Type</span>
          <input
            className="h-9 w-full rounded-md border border-input bg-background px-3 outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={documentType}
            disabled={disabled}
            onChange={(event) => setDocumentType(event.target.value)}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-muted-foreground">Date</span>
          <input
            className="h-9 w-full rounded-md border border-input bg-background px-3 outline-none focus-visible:ring-2 focus-visible:ring-ring"
            type="date"
            value={documentDate}
            disabled={disabled}
            onChange={(event) => setDocumentDate(event.target.value)}
          />
        </label>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className="mb-1 block text-muted-foreground">Issuer</span>
          <input
            className="h-9 w-full rounded-md border border-input bg-background px-3 outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={issuer}
            disabled={disabled}
            onChange={(event) => setIssuer(event.target.value)}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-muted-foreground">Organization</span>
          <input
            className="h-9 w-full rounded-md border border-input bg-background px-3 outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={organization}
            disabled={disabled}
            onChange={(event) => setOrganization(event.target.value)}
          />
        </label>
      </div>
      <Button size="sm" type="submit" disabled={disabled || !title.trim()}>
        Save fields
      </Button>
    </form>
  );
}

function MetadataEditor({
  metadata,
  document,
  disabled,
  onSave,
}: {
  metadata: DocumentDetail["metadata"];
  document: DocumentItem;
  disabled: boolean;
  onSave: (metadata: Parameters<typeof updateDocumentMetadata>[1]) => void;
}) {
  const [schemaName, setSchemaName] = useState(
    metadata?.schema_name ?? document.document_type,
  );
  const [dataText, setDataText] = useState(
    JSON.stringify(metadata?.data ?? {}, null, 2),
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSchemaName(metadata?.schema_name ?? document.document_type);
    setDataText(JSON.stringify(metadata?.data ?? {}, null, 2));
    setError(null);
  }, [document, metadata]);

  return (
    <form
      className="space-y-3 text-sm"
      onSubmit={(event) => {
        event.preventDefault();
        try {
          const parsed = JSON.parse(dataText) as unknown;
          if (
            parsed === null ||
            typeof parsed !== "object" ||
            Array.isArray(parsed)
          ) {
            throw new Error("Metadata must be a JSON object.");
          }
          setError(null);
          onSave({
            schema_name: schemaName.trim() || document.document_type,
            data: parsed as Record<string, unknown>,
          });
        } catch (metadataError) {
          setError(
            metadataError instanceof Error
              ? metadataError.message
              : "Metadata JSON is invalid.",
          );
        }
      }}
    >
      <label className="block">
        <span className="mb-1 block text-muted-foreground">Schema</span>
        <input
          className="h-9 w-full rounded-md border border-input bg-background px-3 outline-none focus-visible:ring-2 focus-visible:ring-ring"
          value={schemaName}
          disabled={disabled}
          onChange={(event) => setSchemaName(event.target.value)}
        />
      </label>
      <label className="block">
        <span className="mb-1 block text-muted-foreground">JSON</span>
        <textarea
          className="min-h-40 w-full rounded-md border border-input bg-background p-3 font-mono text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
          value={dataText}
          disabled={disabled}
          onChange={(event) => setDataText(event.target.value)}
        />
      </label>
      {error ? (
        <p className="rounded-md border border-border bg-muted p-2 text-xs">
          {error}
        </p>
      ) : null}
      <Button size="sm" type="submit" disabled={disabled}>
        Save metadata
      </Button>
    </form>
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
      <div className="flex flex-1 items-center justify-center p-5 text-sm text-muted-foreground">
        Loading preview...
      </div>
    );
  }
  if (!fileQuery.data) {
    return (
      <div className="flex flex-1 items-center justify-center p-5 text-sm text-muted-foreground">
        Preview unavailable.
      </div>
    );
  }
  if (document.content_type.startsWith("image/")) {
    return (
      <img
        alt={document.title}
        className="min-h-0 flex-1 object-contain p-6"
        src={fileQuery.data}
      />
    );
  }
  return (
    <iframe
      className="min-h-[calc(100vh-61px)] flex-1 bg-card"
      src={fileQuery.data}
      title={document.title}
    />
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-border bg-background shadow-sm">
      <div className="border-b border-border px-4 py-3">
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function Metric({
  label,
  value,
  detail,
  icon: Icon,
  tone = "neutral",
}: {
  label: string;
  value: number;
  detail: string;
  icon: typeof FileText;
  tone?: "neutral" | "primary" | "warning" | "danger";
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-3 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">{label}</p>
        <span
          className={cn(
            "flex h-7 w-7 items-center justify-center rounded-md",
            tone === "primary" && "bg-primary/10 text-primary",
            tone === "warning" && "bg-amber-50 text-amber-700",
            tone === "danger" && "bg-rose-50 text-rose-700",
            tone === "neutral" && "bg-muted text-muted-foreground",
          )}
        >
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
      </div>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
      <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
    </div>
  );
}
