import { expect, test } from "@playwright/test";
import { signInAsFixtureUser } from "./auth-fixture";

test("shows a Keycloak sign-in gate when unauthenticated", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "RAG Console" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Sign in with Keycloak/i })).toBeVisible();
});

test("renders the Week 3 RAG workspace once authenticated", async ({ page }) => {
  await signInAsFixtureUser(page);
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "RAG Console" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Document intake" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ask authorized knowledge" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Citations" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Upload and ingest" })).toBeVisible();
});

test("keeps query action disabled until a question exists", async ({ page }) => {
  await signInAsFixtureUser(page);
  await page.goto("/");

  await expect(page.getByRole("button", { name: "Retrieve answer" })).toBeDisabled();
  await page.getByPlaceholder(/Ask about a policy/i).fill("What does Redis cache improve?");
  await expect(page.getByRole("button", { name: "Retrieve answer" })).toBeEnabled();
});

test("A&A panel reflects the signed-in user's tenant and roles", async ({ page }) => {
  await signInAsFixtureUser(page, { roles: ["finance", "support"], username: "farah.finance" });
  await page.goto("/");

  await expect(page.getByText("farah.finance").first()).toBeVisible();
  await expect(page.getByText("finance, support").first()).toBeVisible();
});
