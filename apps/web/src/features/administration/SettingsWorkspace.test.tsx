import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SettingsWorkspace } from "./SettingsWorkspace";

describe("SettingsWorkspace", () => {
  it("updates registration policy and user roles", () => {
    const onRegistrationChange = vi.fn();
    const onUpdateUser = vi.fn();
    render(
      <SettingsWorkspace
        settings={{
          local_registration_enabled: true,
          local_auth_enabled: true,
          oidc_configured: false,
          ai_provider: "local",
          embedding_provider: "local",
          ocr_provider: "tesseract",
          search_backend: "opensearch",
          search_index_enabled: true,
          max_upload_size_bytes: 104857600,
        }}
        users={[
          {
            id: "user-1",
            email: "owner@example.com",
            display_name: "Owner",
            role: "admin",
            auth_provider: "local",
            is_active: true,
            created_at: "2026-07-11T00:00:00Z",
            last_login_at: null,
          },
          {
            id: "user-2",
            email: "reader@example.com",
            display_name: null,
            role: "user",
            auth_provider: "oidc",
            is_active: true,
            created_at: "2026-07-11T00:00:00Z",
            last_login_at: null,
          },
        ]}
        currentUser={undefined}
        isLoading={false}
        isUpdating={false}
        error={null}
        onRegistrationChange={onRegistrationChange}
        onUpdateUser={onUpdateUser}
      />,
    );

    fireEvent.click(screen.getByRole("switch", { name: "Enabled" }));
    fireEvent.change(screen.getByLabelText("Role for reader@example.com"), {
      target: { value: "admin" },
    });

    expect(onRegistrationChange).toHaveBeenCalledWith(false);
    expect(onUpdateUser).toHaveBeenCalledWith("user-2", { role: "admin" });
  });
});
