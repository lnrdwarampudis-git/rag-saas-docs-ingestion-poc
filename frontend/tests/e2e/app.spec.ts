import { expect, test } from "@playwright/test";

test("renders the Week 3 RAG workspace", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "RAG Console" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Document intake" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ask authorized knowledge" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Citations" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Upload and ingest" })).toBeVisible();
});

test("keeps query action disabled until a question exists", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("button", { name: "Retrieve answer" })).toBeDisabled();
  await page.getByPlaceholder(/Ask about a policy/i).fill("What does Redis cache improve?");
  await expect(page.getByRole("button", { name: "Retrieve answer" })).toBeEnabled();
});
