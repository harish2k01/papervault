import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Bell,
  CheckCircle2,
  ChevronDown,
  Clock3,
  FileSearch,
  FileText,
  type LucideIcon,
  LogIn,
  LogOut,
  MessageSquareText,
  Moon,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sun,
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
  NotificationItem,
  NotificationStatus,
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
  getAdminSettings,
  getDocument,
  getMe,
  getStoredAccessToken,
  listDocumentTypes,
  listDocuments,
  listDuplicates,
  listNotifications,
  listUsers,
  listRecentSearches,
  listSavedSearches,
  listTags,
  loginAccount,
  mergeDuplicateDocuments,
  parseOidcCallbackHash,
  registerAccount,
  reprocessDocument,
  saveSearch,
  searchDocuments,
  storeAccessToken,
  syncDocumentNotifications,
  updateDocument,
  updateDocumentMetadata,
  updateAdminSettings,
  updateNotificationStatus,
  updateUser,
  uploadDocument,
} from "../../lib/api";
import { cn } from "../../lib/utils";
import { SettingsWorkspace } from "../administration/SettingsWorkspace";
import { QuestionsWorkspace } from "../questions/QuestionsWorkspace";
import { DuplicatesWorkspace } from "./DuplicatesWorkspace";
import { NotificationsWorkspace } from "./NotificationsWorkspace";
import { TagsWorkspace } from "./TagsWorkspace";
import {
  compareNotifications,
  formatDateOnly,
  getDueState,
} from "./notification-utils";

type WorkspaceView =
  | "documents"
  | "questions"
  | "duplicates"
  | "tags"
  | "notifications"
  | "settings";

const DocumentPreview = lazy(async () => {
  const module = await import("../documents/DocumentPreview");
  return { default: module.DocumentPreview };
});

const navItems = [
  { key: "documents", label: "Documents", icon: FileText },
  { key: "questions", label: "Ask", icon: MessageSquareText },
  { key: "duplicates", label: "Duplicates", icon: FileSearch },
  { key: "tags", label: "Tags", icon: Tags },
  { key: "notifications", label: "Notifications", icon: Bell },
] satisfies Array<{
  key: WorkspaceView;
  label: string;
  icon: LucideIcon;
}>;

const settingsNavItem = {
  key: "settings",
  label: "Settings",
  icon: Settings2,
} satisfies { key: WorkspaceView; label: string; icon: LucideIcon };

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
  const [activeView, setActiveView] = useState<WorkspaceView>("documents");
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("hybrid");
  const [filters, setFilters] = useState<SearchFilters>(defaultSearchFilters);
  const [submittedSearch, setSubmittedSearch] =
    useState<SearchRequestInput | null>(null);
  const [saveSearchName, setSaveSearchName] = useState("");
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(
    null,
  );
  const [darkMode, setDarkMode] = useState(
    () => window.localStorage.getItem("papervault.theme") === "dark",
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
  const isAdmin = meQuery.data?.role === "admin";
  const visibleNavItems = isAdmin ? [...navItems, settingsNavItem] : navItems;

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
  const adminSettingsQuery = useQuery({
    queryKey: ["admin", "settings"],
    queryFn: getAdminSettings,
    enabled: workspaceEnabled && isAdmin,
  });
  const usersQuery = useQuery({
    queryKey: ["admin", "users"],
    queryFn: listUsers,
    enabled: workspaceEnabled && isAdmin,
  });
  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadDocument(file),
    onSuccess: async (response) => {
      setActiveView("documents");
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
  const reprocessingMutation = useMutation({
    mutationFn: reprocessDocument,
    onSuccess: async (response) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["documents"] }),
        queryClient.invalidateQueries({
          queryKey: ["document", response.document.id],
        }),
      ]);
    },
  });
  const adminSettingsMutation = useMutation({
    mutationFn: updateAdminSettings,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin", "settings"] }),
        queryClient.invalidateQueries({ queryKey: ["auth-config"] }),
      ]);
    },
  });
  const userUpdateMutation = useMutation({
    mutationFn: (input: {
      userId: string;
      updates: Parameters<typeof updateUser>[1];
    }) => updateUser(input.userId, input.updates),
    onSuccess: async (user) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin", "users"] }),
        queryClient.invalidateQueries({ queryKey: ["auth", "me"] }),
      ]);
      if (user.id === meQuery.data?.id && user.role !== "admin") {
        setActiveView("documents");
      }
    },
  });
  const notificationStatusMutation = useMutation({
    mutationFn: (input: {
      notificationId: string;
      status: NotificationStatus;
    }) => updateNotificationStatus(input.notificationId, input.status),
    onSuccess: async (notification) => {
      const invalidations = [
        queryClient.invalidateQueries({ queryKey: ["notifications"] }),
      ];
      if (notification.document_id) {
        invalidations.push(
          queryClient.invalidateQueries({
            queryKey: ["document", notification.document_id],
          }),
        );
      }
      await Promise.all(invalidations);
    },
  });
  const notificationSyncMutation = useMutation({
    mutationFn: (documentId: string) => syncDocumentNotifications(documentId),
    onSuccess: async (_notifications, documentId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["notifications"] }),
        queryClient.invalidateQueries({ queryKey: ["document", documentId] }),
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
      notificationSyncMutation.mutate(input.documentId);
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
  const duplicateMergeMutation = useMutation({
    mutationFn: (input: Parameters<typeof mergeDuplicateDocuments>[0]) =>
      mergeDuplicateDocuments(input),
    onSuccess: async (result) => {
      const affectedDocumentIds = [
        result.kept_document.id,
        ...result.archived_documents.map((document) => document.id),
      ];
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["documents"] }),
        queryClient.invalidateQueries({ queryKey: ["duplicates"] }),
        queryClient.invalidateQueries({ queryKey: ["search"] }),
        ...affectedDocumentIds.map((documentId) =>
          queryClient.invalidateQueries({ queryKey: ["document", documentId] }),
        ),
      ]);
      setSelectedDocumentId(result.kept_document.id);
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
  const tagCreateMutation = useMutation({
    mutationFn: (name: string) => createTag({ name: name.trim() }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["tags"] });
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
    setActiveView("documents");
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

  function createVaultTag(name: string) {
    const normalizedName = name.trim();
    if (!normalizedName) {
      return;
    }
    tagCreateMutation.mutate(normalizedName);
  }

  function openDocument(documentId: string | null) {
    if (!documentId) {
      return;
    }
    setSelectedDocumentId(documentId);
    setActiveView("documents");
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

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
    window.localStorage.setItem(
      "papervault.theme",
      darkMode ? "dark" : "light",
    );
  }, [darkMode]);

  useEffect(() => {
    if (activeView === "settings" && !isAdmin) {
      setActiveView("documents");
    }
  }, [activeView, isAdmin]);

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
  const documentCount = documentsQuery.data?.length ?? 0;
  const workspaceIsEmpty =
    !documentsQuery.isLoading &&
    documentCount === 0 &&
    submittedSearch === null;
  const duplicateGroups = duplicatesQuery.data?.length ?? 0;
  const tagCreateError =
    tagCreateMutation.error instanceof Error
      ? tagCreateMutation.error.message
      : null;
  const duplicateMergeError =
    duplicateMergeMutation.error instanceof Error
      ? duplicateMergeMutation.error.message
      : null;
  const notificationActionError =
    notificationStatusMutation.error instanceof Error
      ? notificationStatusMutation.error.message
      : notificationSyncMutation.error instanceof Error
        ? notificationSyncMutation.error.message
        : null;
  const tagMutationError =
    [
      tagCreateAttachMutation.error,
      tagAttachMutation.error,
      tagDetachMutation.error,
    ].find((error): error is Error => error instanceof Error)?.message ?? null;
  const reprocessingError =
    reprocessingMutation.error instanceof Error
      ? reprocessingMutation.error.message
      : null;
  const administrationError =
    adminSettingsMutation.error instanceof Error
      ? adminSettingsMutation.error.message
      : userUpdateMutation.error instanceof Error
        ? userUpdateMutation.error.message
        : adminSettingsQuery.error instanceof Error
          ? adminSettingsQuery.error.message
          : usersQuery.error instanceof Error
            ? usersQuery.error.message
            : null;

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
    <main className="min-h-screen bg-background text-foreground xl:h-screen xl:overflow-hidden">
      <div
        className={cn(
          "grid min-h-screen content-start xl:h-screen xl:content-normal",
          workspaceIsEmpty
            ? "xl:grid-cols-[252px_minmax(0,1fr)]"
            : "xl:grid-cols-[252px_minmax(0,1fr)]",
        )}
      >
        <aside className="flex flex-col border-b border-border bg-card px-4 py-3 xl:h-screen xl:border-b-0 xl:border-r xl:py-5">
          <div className="mb-3 flex items-center justify-between gap-3 px-1 xl:mb-7 xl:justify-start">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
                <FileText className="h-5 w-5" aria-hidden="true" />
              </div>
              <div>
                <p className="text-sm font-semibold">PaperVault</p>
                <p className="text-xs text-muted-foreground">
                  Document intelligence
                </p>
              </div>
            </div>
            <div className="flex items-center xl:hidden">
              <ThemeButton
                darkMode={darkMode}
                onToggle={() => setDarkMode(!darkMode)}
              />
              <Button
                aria-label={accessToken === null ? "Sign in" : "Sign out"}
                size="icon"
                type="button"
                variant="ghost"
                onClick={
                  accessToken === null
                    ? () => setShowAuthScreen(true)
                    : handleSignOut
                }
              >
                {accessToken === null ? (
                  <LogIn className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <LogOut className="h-4 w-4" aria-hidden="true" />
                )}
              </Button>
            </div>
          </div>

          <nav
            aria-label="Primary navigation"
            className="grid grid-cols-3 gap-1 xl:block xl:space-y-1"
          >
            {visibleNavItems.map((item) => {
              const active = activeView === item.key;
              return (
                <button
                  className={cn(
                    "flex min-w-0 w-full flex-col items-center justify-center gap-1 rounded-lg px-1.5 py-2 text-center text-xs transition-colors xl:flex-row xl:justify-between xl:px-3 xl:py-2.5 xl:text-left xl:text-sm",
                    active
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                  key={item.label}
                  type="button"
                  aria-current={active ? "page" : undefined}
                  onClick={() => setActiveView(item.key)}
                >
                  <span className="flex min-w-0 flex-col items-center gap-1 xl:flex-row xl:gap-3">
                    <item.icon className="h-4 w-4" aria-hidden="true" />
                    <span className="truncate">{item.label}</span>
                  </span>
                  {item.label === "Duplicates" && duplicateGroups > 0 ? (
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-xs",
                        active
                          ? "bg-background/20"
                          : "bg-primary/10 text-primary",
                      )}
                    >
                      {duplicateGroups}
                    </span>
                  ) : null}
                  {item.label === "Notifications" &&
                  pendingNotifications > 0 ? (
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-xs",
                        active
                          ? "bg-background/20"
                          : "bg-primary/10 text-primary",
                      )}
                    >
                      {pendingNotifications}
                    </span>
                  ) : null}
                </button>
              );
            })}
          </nav>

          <div className="mt-auto hidden xl:block">
            <div className="mb-3 flex items-center justify-between border-t border-border pt-3">
              <span className="text-xs text-muted-foreground">
                {documentCount} documents · {pendingNotifications} due
              </span>
              <ThemeButton
                darkMode={darkMode}
                onToggle={() => setDarkMode(!darkMode)}
              />
            </div>
            <AuthStatus
              user={meQuery.data}
              usingDevIdentity={accessToken === null}
              onSignIn={() => setShowAuthScreen(true)}
              onSignOut={handleSignOut}
            />
          </div>
        </aside>

        {activeView === "questions" ? (
          <QuestionsWorkspace onOpenDocument={openDocument} />
        ) : activeView === "settings" && isAdmin ? (
          <SettingsWorkspace
            settings={adminSettingsQuery.data}
            users={usersQuery.data ?? []}
            currentUser={meQuery.data}
            isLoading={adminSettingsQuery.isLoading || usersQuery.isLoading}
            isUpdating={
              adminSettingsMutation.isPending || userUpdateMutation.isPending
            }
            error={administrationError}
            onRegistrationChange={(enabled) =>
              adminSettingsMutation.mutate({
                local_registration_enabled: enabled,
              })
            }
            onUpdateUser={(userId, updates) =>
              userUpdateMutation.mutate({ userId, updates })
            }
          />
        ) : activeView === "notifications" ? (
          <NotificationsWorkspace
            notifications={notificationsQuery.data ?? []}
            documents={documentsQuery.data ?? []}
            isLoading={notificationsQuery.isLoading}
            isUpdating={notificationStatusMutation.isPending}
            error={notificationActionError}
            onOpenDocument={openDocument}
            onUpdateStatus={(notificationId, status) =>
              notificationStatusMutation.mutate({ notificationId, status })
            }
          />
        ) : activeView === "duplicates" ? (
          <DuplicatesWorkspace
            groups={duplicatesQuery.data ?? []}
            isLoading={duplicatesQuery.isLoading}
            isResolving={duplicateMergeMutation.isPending}
            error={duplicateMergeError}
            onOpenDocument={openDocument}
            onMerge={(input) => duplicateMergeMutation.mutate(input)}
          />
        ) : activeView === "tags" ? (
          <TagsWorkspace
            tags={tagsQuery.data ?? []}
            isLoading={tagsQuery.isLoading}
            isCreating={tagCreateMutation.isPending}
            error={tagCreateError}
            onCreateTag={createVaultTag}
          />
        ) : workspaceIsEmpty ? (
          <EmptyWorkspace
            isUploading={uploadMutation.isPending}
            onUpload={(file) => uploadMutation.mutate(file)}
          />
        ) : (
          <section className="flex min-w-0 flex-col bg-background xl:h-screen xl:min-h-0">
            <header className="border-b border-border bg-card px-5 py-4 xl:px-6">
              <div className="flex flex-col gap-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <h1 className="text-xl font-semibold tracking-normal">
                    Documents
                  </h1>
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
              </div>
            </header>

            <div className="grid min-h-0 flex-1 xl:grid-cols-[390px_minmax(0,1fr)] xl:overflow-hidden">
              <section className="min-h-0 border-b border-border bg-background/70 p-4 xl:flex xl:flex-col xl:border-b-0 xl:border-r">
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-sm font-semibold">Documents</h2>
                  <span className="text-xs text-muted-foreground">
                    {visibleDocuments.length} shown
                  </span>
                </div>
                <div className="min-h-0 xl:flex-1 xl:overflow-auto">
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

              <DocumentPanel
                detail={detailQuery.data}
                duplicateGroups={duplicateGroups}
                notifications={notificationsQuery.data ?? []}
                tags={tagsQuery.data ?? []}
                isLoading={detailQuery.isLoading}
                isUpdating={
                  documentUpdateMutation.isPending ||
                  metadataUpdateMutation.isPending ||
                  archiveMutation.isPending
                }
                isSyncingNotifications={notificationSyncMutation.isPending}
                isReprocessing={reprocessingMutation.isPending}
                isTagUpdating={
                  tagCreateAttachMutation.isPending ||
                  tagAttachMutation.isPending ||
                  tagDetachMutation.isPending
                }
                tagError={tagMutationError}
                notificationError={notificationActionError}
                processingError={reprocessingError}
                onArchive={(documentId) => archiveMutation.mutate(documentId)}
                onReprocess={(documentId) =>
                  reprocessingMutation.mutate(documentId)
                }
                onSyncNotifications={(documentId) =>
                  notificationSyncMutation.mutate(documentId)
                }
                onUpdateNotificationStatus={(notificationId, status) =>
                  notificationStatusMutation.mutate({ notificationId, status })
                }
                onUpdateDocument={(documentId, updates) =>
                  documentUpdateMutation.mutate({ documentId, updates })
                }
                onUpdateMetadata={(documentId, metadata) =>
                  metadataUpdateMutation.mutate({ documentId, metadata })
                }
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
            </div>
          </section>
        )}
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
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-10 text-foreground">
      <section className="grid w-full max-w-4xl overflow-hidden rounded-xl border border-border bg-card shadow-sm lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="hidden border-r border-border bg-muted/40 p-8 lg:block">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            <FileText className="h-5 w-5" aria-hidden="true" />
          </div>
          <h1 className="mt-8 max-w-sm text-3xl font-semibold tracking-normal">
            Your private document intelligence workspace.
          </h1>
          <p className="mt-4 max-w-sm text-sm leading-6 text-muted-foreground">
            Upload personal records, extract searchable knowledge, and keep the
            source files separate from metadata.
          </p>
          <div className="mt-8 grid gap-3 text-sm">
            <AuthFeature label="OCR and metadata extraction" />
            <AuthFeature label="Keyword, semantic, and filtered search" />
            <AuthFeature label="Self-hosted storage and identity controls" />
          </div>
        </div>

        <div className="p-6 sm:p-8">
          <div className="mb-7 flex items-center gap-3 lg:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <ShieldCheck className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <h1 className="text-lg font-semibold">PaperVault</h1>
              <p className="text-sm text-muted-foreground">
                Sign in to your document vault.
              </p>
            </div>
          </div>

          <div className="mb-6">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Secure access
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-normal">
              {mode === "login" ? "Welcome back" : "Create your vault"}
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              {mode === "login"
                ? "Use local login or your configured identity provider."
                : "Local registration creates the first account for this instance."}
            </p>
          </div>

          <div className="mb-4 grid grid-cols-2 rounded-lg bg-muted p-1">
            <button
              className={cn(
                "rounded-md px-3 py-2 text-sm font-medium transition-colors",
                mode === "login"
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
              type="button"
              onClick={() => setMode("login")}
            >
              Sign in
            </button>
            <button
              className={cn(
                "rounded-md px-3 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                mode === "register"
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
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
                  className="h-10 w-full rounded-md border border-input bg-background px-3 outline-none transition-shadow focus-visible:ring-2 focus-visible:ring-ring"
                  autoComplete="name"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                />
              </label>
            ) : null}

            <label className="block text-sm">
              <span className="mb-1 block text-muted-foreground">Email</span>
              <input
                className="h-10 w-full rounded-md border border-input bg-background px-3 outline-none transition-shadow focus-visible:ring-2 focus-visible:ring-ring"
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
                className="h-10 w-full rounded-md border border-input bg-background px-3 outline-none transition-shadow focus-visible:ring-2 focus-visible:ring-ring"
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
              <p className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-100">
                {errorMessage}
              </p>
            ) : null}

            {oidcError ? (
              <p className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-100">
                {oidcError}
              </p>
            ) : null}

            <Button
              className="w-full"
              disabled={
                authMutation.isPending ||
                authConfig?.local_auth_enabled !== true
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
        </div>
      </section>
    </main>
  );
}

function AuthFeature({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3">
      <CheckCircle2 className="h-4 w-4 text-primary" aria-hidden="true" />
      <span className="text-muted-foreground">{label}</span>
    </div>
  );
}

function ThemeButton({
  darkMode,
  onToggle,
}: {
  darkMode: boolean;
  onToggle: () => void;
}) {
  return (
    <Button
      aria-label={darkMode ? "Use light theme" : "Use dark theme"}
      size="icon"
      title={darkMode ? "Use light theme" : "Use dark theme"}
      type="button"
      variant="ghost"
      onClick={onToggle}
    >
      {darkMode ? (
        <Sun className="h-4 w-4" aria-hidden="true" />
      ) : (
        <Moon className="h-4 w-4" aria-hidden="true" />
      )}
    </Button>
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
    <section className="border-t border-border pt-4">
      {usingDevIdentity ? (
        <div className="space-y-3">
          <div>
            <p className="text-sm font-semibold">Development identity</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Header fallback is active.
            </p>
          </div>
          <Button size="sm" type="button" onClick={onSignIn}>
            Sign in
          </Button>
        </div>
      ) : (
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">
              {user?.email ?? "Signed in"}
            </p>
            <p className="mt-0.5 text-xs capitalize text-muted-foreground">
              {user?.role ?? "Loading account"}
            </p>
          </div>
          <Button
            size="sm"
            variant="ghost"
            type="button"
            title="Sign out"
            aria-label="Sign out"
            onClick={onSignOut}
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      )}
    </section>
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

function EmptyWorkspace({
  isUploading,
  onUpload,
}: {
  isUploading: boolean;
  onUpload: (file: File) => void;
}) {
  return (
    <section className="flex min-h-[420px] min-w-0 items-center justify-center bg-background px-6 py-10 sm:min-h-[480px] xl:min-h-screen xl:px-8">
      <div className="w-full max-w-2xl text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
          <FileSearch className="h-7 w-7" aria-hidden="true" />
        </div>
        <p className="mt-8 text-sm font-medium uppercase tracking-wide text-muted-foreground">
          Empty vault
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-normal sm:text-4xl">
          Add your first document.
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-base leading-7 text-muted-foreground">
          Upload a PDF, scanned document, or image. PaperVault will extract
          text, classify it, generate a summary, and make it searchable.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <UploadButton
            disabled={isUploading}
            onUpload={onUpload}
            className="h-11 px-5"
          />
          <span className="text-sm text-muted-foreground">
            PDF, JPG, and PNG are supported
          </span>
        </div>
      </div>
    </section>
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
        ) : (
          <UploadButton
            disabled={isUploading}
            onUpload={onUpload}
            className="shadow-sm"
          />
        )}
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
        "group w-full rounded-lg border bg-card p-4 text-left text-sm transition-colors hover:border-primary/40 hover:bg-primary/5",
        selected ? "border-primary/60 bg-primary/5" : "border-border",
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
  const failed = status.includes("failed") || status === "error";
  const archived = status === "archived";
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-1 text-xs font-medium capitalize",
        ready &&
          "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
        processing &&
          "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
        failed &&
          "bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
        archived && "bg-slate-100 text-slate-600",
        !ready &&
          !processing &&
          !failed &&
          !archived &&
          "bg-muted text-muted-foreground",
      )}
    >
      {ready ? <CheckCircle2 className="h-3 w-3" aria-hidden="true" /> : null}
      {processing ? <Clock3 className="h-3 w-3" aria-hidden="true" /> : null}
      {failed ? <AlertCircle className="h-3 w-3" aria-hidden="true" /> : null}
      {normalizedStatus}
    </span>
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
  const [saveOpen, setSaveOpen] = useState(false);
  const activeFilterCount = countActiveFilters(filters);
  const canSaveSearch = query.trim().length > 0 || activeFilterCount > 0;
  const hasSearchShortcuts =
    savedSearches.length > 0 || recentSearches.length > 0;

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
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative min-w-0 flex-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <input
              className="h-11 w-full rounded-md border border-input bg-card pl-10 pr-4 text-sm outline-none ring-offset-background placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="Search documents, issuers, tags, or questions"
              type="search"
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
            />
          </div>
          <Button className="sm:w-auto" type="submit">
            Search
          </Button>
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
          {canSaveSearch ? (
            <Button size="sm" variant="ghost" type="button" onClick={onClear}>
              Clear
            </Button>
          ) : null}
        </div>

        {advancedOpen ? (
          <div className="grid gap-2 rounded-lg border border-border bg-card p-3 text-sm sm:grid-cols-2">
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

      {canSaveSearch ? (
        <div className="mt-3 border-t border-border pt-3">
          <button
            className="text-xs font-medium text-muted-foreground hover:text-foreground"
            type="button"
            onClick={() => setSaveOpen((current) => !current)}
          >
            Save this search
          </button>
          {saveOpen ? (
            <div className="mt-3 flex flex-col gap-2 sm:flex-row">
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
          ) : null}
        </div>
      ) : null}

      {hasSearchShortcuts ? (
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {savedSearches.length > 0 ? (
            <SearchShortcutList
              title="Saved"
              items={savedSearches.map((savedSearch) => ({
                id: savedSearch.id,
                title: savedSearch.name,
                description: describeSearch(
                  savedSearch.query,
                  savedSearch.filters,
                ),
                input: searchInputFromStoredSearch(savedSearch),
              }))}
              onApply={onApplySearch}
            />
          ) : null}
          {recentSearches.length > 0 ? (
            <SearchShortcutList
              title="Recent"
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
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function SearchShortcutList({
  title,
  items,
  onApply,
}: {
  title: string;
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

function DocumentOverviewEmptyState() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-8 text-center">
      <div className="max-w-sm">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-muted text-muted-foreground">
          <FileText className="h-6 w-6" aria-hidden="true" />
        </div>
        <h2 className="mt-5 text-xl font-semibold">Choose a document</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Select a document from the list to review its preview, summary,
          metadata, tags, and timeline.
        </p>
      </div>
    </div>
  );
}

function DocumentPanel({
  detail,
  duplicateGroups,
  notifications,
  tags,
  isLoading,
  isUpdating,
  isSyncingNotifications,
  isReprocessing,
  isTagUpdating,
  tagError,
  notificationError,
  processingError,
  onArchive,
  onReprocess,
  onSyncNotifications,
  onUpdateNotificationStatus,
  onUpdateDocument,
  onUpdateMetadata,
  onAttachTag,
  onCreateAndAttachTag,
  onDetachTag,
}: {
  detail: DocumentDetail | undefined;
  duplicateGroups: number;
  notifications: NotificationItem[];
  tags: TagItem[];
  isLoading: boolean;
  isUpdating: boolean;
  isSyncingNotifications: boolean;
  isReprocessing: boolean;
  isTagUpdating: boolean;
  tagError: string | null;
  notificationError: string | null;
  processingError: string | null;
  onArchive: (documentId: string) => void;
  onReprocess: (documentId: string) => void;
  onSyncNotifications: (documentId: string) => void;
  onUpdateNotificationStatus: (
    notificationId: string,
    status: NotificationStatus,
  ) => void;
  onUpdateDocument: (
    documentId: string,
    updates: Parameters<typeof updateDocument>[1],
  ) => void;
  onUpdateMetadata: (
    documentId: string,
    metadata: Parameters<typeof updateDocumentMetadata>[1],
  ) => void;
  onAttachTag: (documentId: string, tagId: string) => void;
  onCreateAndAttachTag: (documentId: string, name: string) => void;
  onDetachTag: (documentId: string, tagId: string) => void;
}) {
  const [fieldsEditorOpen, setFieldsEditorOpen] = useState(false);
  const [metadataEditorOpen, setMetadataEditorOpen] = useState(false);

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
    return <DocumentOverviewEmptyState />;
  }

  const metadataEntries = Object.entries(detail.metadata?.data ?? {});
  const documentDate =
    detail.document.document_date ?? formatDateTime(detail.document.created_at);
  const confidence = detail.ai_analysis?.confidence_score;
  const documentNotifications = notifications
    .filter((notification) => notification.document_id === detail.document.id)
    .sort(compareNotifications);
  const activeDocumentNotifications = documentNotifications.filter(
    (notification) => notification.status !== "dismissed",
  );
  const pendingDocumentNotifications = documentNotifications.filter(
    (notification) => notification.status === "pending",
  );

  return (
    <article className="min-h-screen min-w-0 overflow-auto bg-background xl:h-full xl:min-h-0">
      <header className="border-b border-border bg-card px-5 py-5 xl:px-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="rounded-md bg-muted px-2 py-1 text-xs font-medium capitalize text-muted-foreground">
                {detail.document.document_type.replaceAll("_", " ")}
              </span>
              <StatusBadge status={detail.document.status} />
            </div>
            <h2 className="max-w-full break-words text-2xl font-semibold tracking-normal">
              {detail.document.title}
            </h2>
            <p className="mt-1 max-w-3xl truncate text-sm text-muted-foreground">
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
      </header>

      <div className="grid min-w-0 2xl:grid-cols-[minmax(0,1fr)_340px]">
        <main className="min-w-0 space-y-6 p-5 xl:p-7">
          <DocumentStatusNotice
            document={detail.document}
            extractionError={detail.text_extraction?.error_message}
            mutationError={processingError}
            isRetrying={isReprocessing}
            onRetry={() => onReprocess(detail.document.id)}
          />

          <section>
            <div className="mb-3">
              <h3 className="text-sm font-semibold">Preview</h3>
              <p className="text-xs text-muted-foreground">
                Source file stays separate from metadata.
              </p>
            </div>
            <Suspense fallback={<PreviewLoadingState />}>
              <DocumentPreview document={detail.document} />
            </Suspense>
          </section>

          <section className="border-t border-border pt-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h3 className="text-sm font-semibold">AI Summary</h3>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                  {detail.ai_analysis?.summary ?? "No summary generated yet."}
                </p>
              </div>
              {confidence !== null && confidence !== undefined ? (
                <span className="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">
                  {Math.round(confidence * 100)}% confidence
                </span>
              ) : null}
            </div>
            {detail.ai_analysis?.keywords?.length ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {detail.ai_analysis.keywords.slice(0, 8).map((keyword) => (
                  <span
                    className="rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground"
                    key={keyword}
                  >
                    {keyword}
                  </span>
                ))}
              </div>
            ) : null}
          </section>

          <section className="border-t border-border pt-5">
            <h3 className="text-sm font-semibold">Document Details</h3>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <ReadOnlyField
                label="Type"
                value={detail.document.document_type.replaceAll("_", " ")}
              />
              <ReadOnlyField label="Date" value={documentDate} />
              <ReadOnlyField label="Issuer" value={detail.document.issuer} />
              <ReadOnlyField
                label="Organization"
                value={detail.document.organization}
              />
            </div>

            {metadataEntries.length ? (
              <div className="mt-5">
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Extracted metadata
                </p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {metadataEntries.slice(0, 8).map(([key, value]) => (
                    <ReadOnlyField
                      key={key}
                      label={key.replaceAll("_", " ")}
                      value={formatMetadataValue(value)}
                    />
                  ))}
                </div>
              </div>
            ) : null}
          </section>

          <section className="border-t border-border pt-5">
            <button
              className="text-sm font-semibold hover:text-primary"
              type="button"
              onClick={() => setFieldsEditorOpen((current) => !current)}
            >
              Edit document fields
            </button>
            {fieldsEditorOpen ? (
              <div className="mt-4 max-w-2xl">
                <DocumentFieldsEditor
                  document={detail.document}
                  disabled={isUpdating}
                  onSave={(updates) =>
                    onUpdateDocument(detail.document.id, updates)
                  }
                />
              </div>
            ) : null}
          </section>

          <section className="border-t border-border pt-5">
            <button
              className="text-sm font-semibold hover:text-primary"
              type="button"
              onClick={() => setMetadataEditorOpen((current) => !current)}
            >
              Raw metadata JSON
            </button>
            {metadataEditorOpen ? (
              <div className="mt-4 max-w-2xl">
                <MetadataEditor
                  metadata={detail.metadata}
                  document={detail.document}
                  disabled={isUpdating}
                  onSave={(metadata) =>
                    onUpdateMetadata(detail.document.id, metadata)
                  }
                />
              </div>
            ) : null}
          </section>
        </main>

        <aside className="min-w-0 border-t border-border bg-card/70 p-5 2xl:border-l 2xl:border-t-0">
          <div className="space-y-6">
            <section>
              <h3 className="text-sm font-semibold">Tags</h3>
              <div className="mt-3">
                <TagEditor
                  assignedTags={detail.tags}
                  availableTags={tags}
                  disabled={isTagUpdating}
                  error={tagError}
                  suggestedTags={detail.ai_analysis?.suggested_tags ?? []}
                  onAttachTag={(tagId) =>
                    onAttachTag(detail.document.id, tagId)
                  }
                  onCreateAndAttachTag={(name) =>
                    onCreateAndAttachTag(detail.document.id, name)
                  }
                  onDetachTag={(tagId) =>
                    onDetachTag(detail.document.id, tagId)
                  }
                />
              </div>
            </section>

            <section className="border-t border-border pt-5">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold">Signals</h3>
                <Button
                  size="sm"
                  variant="ghost"
                  type="button"
                  disabled={isSyncingNotifications}
                  onClick={() => onSyncNotifications(detail.document.id)}
                >
                  <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                  Refresh
                </Button>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <SignalItem label="Duplicates" value={duplicateGroups} />
                <SignalItem
                  label="Reminders"
                  value={pendingDocumentNotifications.length}
                />
              </div>
              {notificationError ? (
                <p
                  className="mt-3 rounded-md border border-rose-200 bg-rose-50 p-2 text-xs text-rose-900 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-100"
                  role="alert"
                >
                  {notificationError}
                </p>
              ) : null}
              {activeDocumentNotifications.length ? (
                <div className="mt-3 space-y-2">
                  {activeDocumentNotifications
                    .slice(0, 3)
                    .map((notification) => (
                      <DocumentReminder
                        key={notification.id}
                        notification={notification}
                        disabled={isSyncingNotifications}
                        onUpdateStatus={(status) =>
                          onUpdateNotificationStatus(notification.id, status)
                        }
                      />
                    ))}
                </div>
              ) : (
                <p className="mt-3 rounded-md border border-dashed border-border bg-background p-3 text-xs leading-5 text-muted-foreground">
                  No active reminders for this document. Refresh after adding
                  due, expiry, renewal, or warranty dates to metadata.
                </p>
              )}
              {detail.document.archived_at ? (
                <p className="mt-3 rounded-md border border-border bg-muted p-2 text-xs text-muted-foreground">
                  Archived{" "}
                  {new Date(detail.document.archived_at).toLocaleString()}
                </p>
              ) : null}
            </section>

            <details className="border-t border-border pt-5">
              <summary className="cursor-pointer text-sm font-semibold hover:text-primary">
                Activity and versions
              </summary>
              <section className="mt-4">
                <h3 className="text-xs font-medium uppercase text-muted-foreground">
                  Timeline
                </h3>
                {detail.timeline_events.length ? (
                  <div className="mt-3 space-y-3">
                    {detail.timeline_events.slice(0, 6).map((event) => (
                      <div className="text-sm" key={event.id}>
                        <p>{event.event_type.replaceAll("_", " ")}</p>
                        <p className="text-xs text-muted-foreground">
                          {new Date(event.occurred_at).toLocaleString()}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-muted-foreground">
                    No timeline events yet.
                  </p>
                )}
              </section>

              <section className="mt-5 border-t border-border pt-4">
                <h3 className="text-xs font-medium uppercase text-muted-foreground">
                  Versions
                </h3>
                {detail.versions.length ? (
                  <div className="mt-3 space-y-3 text-sm">
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
                  <p className="mt-2 text-sm text-muted-foreground">
                    No versions recorded.
                  </p>
                )}
              </section>
            </details>
          </div>
        </aside>
      </div>
    </article>
  );
}

function DocumentStatusNotice({
  document,
  extractionError,
  mutationError,
  isRetrying,
  onRetry,
}: {
  document: DocumentItem;
  extractionError: string | null | undefined;
  mutationError: string | null;
  isRetrying: boolean;
  onRetry: () => void;
}) {
  if (document.status === "ready") {
    return null;
  }
  const failed = document.status.includes("failed");
  const queuedTooLong =
    document.status === "pending_processing" &&
    Date.now() - new Date(document.updated_at).getTime() > 2 * 60 * 1000;
  const canRetry = failed || queuedTooLong;
  const detail =
    document.processing_error ||
    extractionError ||
    (failed
      ? "The source file is safe, but processing did not complete."
      : queuedTooLong
        ? "This document has been queued longer than expected."
        : "Text extraction, analysis, and indexing are still running.");
  return (
    <div
      className={cn(
        "rounded-lg border px-4 py-3 text-sm",
        failed
          ? "border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-100"
          : "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100",
      )}
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 h-4 w-4" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="font-medium">
            {failed ? "Processing failed" : "Processing in progress"}
          </p>
          <p className="mt-1 text-xs opacity-80">{detail}</p>
          {mutationError ? (
            <p className="mt-2 text-xs font-medium" role="alert">
              {mutationError}
            </p>
          ) : null}
          {canRetry ? (
            <Button
              className="mt-3"
              disabled={isRetrying}
              size="sm"
              type="button"
              variant="outline"
              onClick={onRetry}
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              {isRetrying ? "Queueing..." : "Retry processing"}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function PreviewLoadingState() {
  return (
    <div className="flex min-h-64 items-center justify-center rounded-lg border border-border bg-card p-5 text-sm text-muted-foreground">
      Loading viewer...
    </div>
  );
}

function ReadOnlyField({
  label,
  value,
}: {
  label: string;
  value: string | number | null | undefined;
}) {
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2">
      <p className="text-xs capitalize text-muted-foreground">{label}</p>
      <p className="mt-1 truncate text-sm font-medium">
        {value === null || value === undefined || value === ""
          ? "Not set"
          : value}
      </p>
    </div>
  );
}

function SignalItem({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border bg-background px-3 py-2">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}

function DocumentReminder({
  notification,
  disabled,
  onUpdateStatus,
}: {
  notification: NotificationItem;
  disabled: boolean;
  onUpdateStatus: (status: NotificationStatus) => void;
}) {
  const dueState = getDueState(notification.due_date);

  return (
    <div className="rounded-lg border border-border bg-background p-3 text-sm">
      <div className="flex items-start gap-2">
        <Clock3 className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <p className="break-words font-medium">{notification.title}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {dueState.label} - {formatDateOnly(notification.due_date)}
          </p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {notification.status === "pending" ? (
          <Button
            size="sm"
            variant="secondary"
            type="button"
            disabled={disabled}
            onClick={() => onUpdateStatus("read")}
          >
            Mark read
          </Button>
        ) : null}
        <Button
          size="sm"
          variant={notification.status === "dismissed" ? "secondary" : "ghost"}
          type="button"
          disabled={disabled}
          onClick={() =>
            onUpdateStatus(
              notification.status === "dismissed" ? "pending" : "dismissed",
            )
          }
        >
          {notification.status === "dismissed" ? "Reopen" : "Dismiss"}
        </Button>
      </div>
    </div>
  );
}

function formatMetadataValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "Not set";
  }
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  return JSON.stringify(value);
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
  const [manageTagsOpen, setManageTagsOpen] = useState(false);
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

      <div>
        <button
          className="text-xs font-medium text-muted-foreground hover:text-foreground"
          type="button"
          onClick={() => setManageTagsOpen((current) => !current)}
        >
          Manage tags
        </button>
        {manageTagsOpen ? (
          <div className="mt-3 space-y-3">
            <label className="block">
              <span className="mb-1 block text-muted-foreground">
                Existing tag
              </span>
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
                <span className="mb-1 block text-muted-foreground">
                  New tag
                </span>
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
          </div>
        ) : null}
      </div>

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
      <div className="grid gap-3 sm:grid-cols-2">
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
      <div className="grid gap-3 sm:grid-cols-2">
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
