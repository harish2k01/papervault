import { AuthUser, AdminSettings, ProviderHealth } from "../../lib/api";
import { humanizeLabel } from "../../lib/utils";
import { Button } from "../../components/ui/button";
import {
  CheckCircle2,
  Database,
  HardDrive,
  Search,
  ShieldCheck,
  Trash2,
  Users,
} from "lucide-react";

export function SettingsWorkspace({
  settings,
  providerHealth,
  users,
  currentUser,
  isLoading,
  isUpdating,
  error,
  onRegistrationChange,
  onUpdateUser,
  onDeleteUser,
}: {
  settings: AdminSettings | undefined;
  providerHealth: ProviderHealth | undefined;
  users: AuthUser[];
  currentUser: AuthUser | undefined;
  isLoading: boolean;
  isUpdating: boolean;
  error: string | null;
  onRegistrationChange: (enabled: boolean) => void;
  onUpdateUser: (
    userId: string,
    input: Partial<{ role: "admin" | "user"; is_active: boolean }>,
  ) => void;
  onDeleteUser: (userId: string, label: string) => void;
}) {
  return (
    <section className="flex min-w-0 flex-col bg-background xl:h-screen xl:min-h-0">
      <header className="border-b border-border bg-card px-5 py-5 xl:px-7">
        <p className="text-xs font-medium uppercase text-muted-foreground">
          Administration
        </p>
        <h1 className="mt-1 text-2xl font-semibold">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage access, users, and the active self-hosted runtime.
        </p>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-5 xl:p-7">
        <div className="mx-auto max-w-5xl space-y-7">
          {error ? (
            <p
              className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-100"
              role="alert"
            >
              {error}
            </p>
          ) : null}

          <section>
            <div className="mb-3 flex items-center gap-2">
              <ShieldCheck
                className="h-4 w-4 text-muted-foreground"
                aria-hidden="true"
              />
              <h2 className="text-sm font-semibold">Access</h2>
            </div>
            <div className="rounded-lg border border-border bg-card p-4">
              {isLoading || !settings ? (
                <p className="text-sm text-muted-foreground">
                  Loading settings...
                </p>
              ) : (
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <p className="text-sm font-medium">
                      Allow local registration
                    </p>
                    <p className="mt-1 max-w-xl text-xs leading-5 text-muted-foreground">
                      New local accounts can register from the sign-in screen.
                      Existing users and OIDC login are unaffected.
                    </p>
                  </div>
                  <Button
                    aria-checked={settings.local_registration_enabled}
                    role="switch"
                    size="sm"
                    type="button"
                    variant={
                      settings.local_registration_enabled
                        ? "default"
                        : "outline"
                    }
                    disabled={isUpdating}
                    onClick={() =>
                      onRegistrationChange(!settings.local_registration_enabled)
                    }
                  >
                    {settings.local_registration_enabled
                      ? "Enabled"
                      : "Disabled"}
                  </Button>
                </div>
              )}
            </div>
          </section>

          <section>
            <div className="mb-3 flex items-center gap-2">
              <Database
                className="h-4 w-4 text-muted-foreground"
                aria-hidden="true"
              />
              <h2 className="text-sm font-semibold">Runtime</h2>
            </div>
            {settings ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <RuntimeItem
                  icon={CheckCircle2}
                  label="AI analysis"
                  value={settings.ai_provider}
                />
                <RuntimeItem
                  icon={CheckCircle2}
                  label="Grounded answers"
                  value={settings.answer_provider}
                />
                <RuntimeItem
                  icon={HardDrive}
                  label="Embeddings"
                  value={settings.embedding_provider}
                />
                <RuntimeItem
                  icon={Search}
                  label="Search"
                  value={
                    settings.search_index_enabled
                      ? settings.search_backend
                      : "Database fallback"
                  }
                />
                <RuntimeItem
                  icon={Database}
                  label="OCR"
                  value={settings.ocr_provider}
                />
              </div>
            ) : null}
            {providerHealth ? (
              <div className="mt-3 overflow-hidden rounded-lg border border-border bg-card">
                {providerHealth.checks.map((check) => (
                  <div
                    className="grid gap-2 border-b border-border px-4 py-3 last:border-b-0 sm:grid-cols-[140px_minmax(0,1fr)_100px] sm:items-center"
                    key={check.capability}
                  >
                    <span className="text-sm font-medium">
                      {check.capability}
                    </span>
                    <span className="truncate text-xs text-muted-foreground">
                      {humanizeLabel(check.provider)} &middot; {check.model}
                    </span>
                    <span
                      className={
                        check.healthy ? "text-emerald-700" : "text-rose-700"
                      }
                      title={check.detail}
                    >
                      {check.healthy ? "Healthy" : "Unavailable"}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </section>

          <section>
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Users
                  className="h-4 w-4 text-muted-foreground"
                  aria-hidden="true"
                />
                <h2 className="text-sm font-semibold">Users</h2>
              </div>
              <span className="text-xs text-muted-foreground">
                {users.length} accounts
              </span>
            </div>
            <div className="overflow-hidden rounded-lg border border-border bg-card">
              {users.map((user) => (
                <div
                  className="grid gap-3 border-b border-border px-4 py-3 last:border-b-0 md:grid-cols-[minmax(0,1fr)_140px_110px_40px] md:items-center"
                  key={user.id}
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {user.display_name || user.email}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {user.email} - {humanizeLabel(user.auth_provider)}
                    </p>
                  </div>
                  <label className="flex items-center gap-2 text-xs text-muted-foreground md:block">
                    <span className="md:sr-only">Role for {user.email}</span>
                    <select
                      aria-label={`Role for ${user.email}`}
                      className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      disabled={isUpdating}
                      value={user.role}
                      onChange={(event) =>
                        onUpdateUser(user.id, {
                          role: event.target.value as "admin" | "user",
                        })
                      }
                    >
                      <option value="user">User</option>
                      <option value="admin">Administrator</option>
                    </select>
                  </label>
                  <Button
                    size="sm"
                    type="button"
                    variant={user.is_active ? "outline" : "secondary"}
                    disabled={isUpdating || user.id === currentUser?.id}
                    onClick={() =>
                      onUpdateUser(user.id, { is_active: !user.is_active })
                    }
                  >
                    {user.is_active ? "Active" : "Disabled"}
                  </Button>
                  <Button
                    aria-label={`Delete ${user.email}`}
                    className="text-muted-foreground hover:bg-rose-50 hover:text-rose-700 dark:hover:bg-rose-950"
                    size="icon"
                    type="button"
                    variant="ghost"
                    disabled={isUpdating || user.id === currentUser?.id}
                    title="Permanently delete user"
                    onClick={() =>
                      onDeleteUser(user.id, user.display_name || user.email)
                    }
                  >
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </div>
              ))}
              {!isLoading && users.length === 0 ? (
                <p className="p-4 text-sm text-muted-foreground">
                  No users found.
                </p>
              ) : null}
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}

function RuntimeItem({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Database;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="h-4 w-4" aria-hidden="true" />
        <span className="text-xs">{label}</span>
      </div>
      <p className="mt-2 truncate text-sm font-medium capitalize">
        {humanizeLabel(value)}
      </p>
    </div>
  );
}
