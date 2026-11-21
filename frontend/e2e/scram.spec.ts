import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

/**
 * The operator's core loop, end to end through the real backend and database:
 * sign in -> withdraw rods until power alarms -> acknowledge -> SCRAM -> power collapses.
 */

const username = process.env.E2E_USERNAME ?? "";
const password = process.env.E2E_PASSWORD ?? "";

async function powerPercent(page: Page): Promise<number> {
  const value = await page.getByRole("meter", { name: "Reactor power" }).getAttribute("aria-valuenow");
  return Number(value);
}

test("operator raises a power alarm, acknowledges it, and scrams the reactor", async ({ page }) => {
  test.skip(!username || !password, "Set E2E_USERNAME and E2E_PASSWORD for an operator account");

  // Sign in: the dashboard redirects to the login page first.
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByTestId("role")).toHaveText("Operator");
  await expect(page.getByTestId("connection")).toHaveText("Live");
  await expect.poll(() => powerPercent(page)).toBeCloseTo(100, 0);

  // Withdraw the rods 2 % (within the operator's 5 % per-command limit).
  await page.getByLabel("New target (% inserted)").fill("18");
  await page.getByRole("button", { name: "Move rods" }).click();
  await expect(page.getByText("Rods moving to 18.0 %")).toBeVisible();

  // Power climbs past the 105 % limit: a flashing, unacknowledged alarm.
  const banner = page.getByTestId("alarm-banner");
  await expect(banner).toHaveClass(/banner-unacked/, { timeout: 30_000 });
  await expect(banner).toContainText("Reactor power high");
  const powerAlarm = page.getByRole("row").filter({ hasText: "Reactor power high" });
  await expect(powerAlarm).toContainText("Unacknowledged");

  // Acknowledge it: the row (pushed live over the WebSocket) changes state.
  await powerAlarm.getByRole("button", { name: "Acknowledge" }).click();
  await expect(powerAlarm).toContainText("Acknowledged");
  await expect(powerAlarm.getByRole("button", { name: "Acknowledge" })).toHaveCount(0);

  const powerBeforeScram = await powerPercent(page);
  expect(powerBeforeScram).toBeGreaterThan(105);

  // SCRAM is a guarded switch: lifting the cover alone does nothing.
  await page.getByRole("button", { name: "Lift cover to SCRAM" }).click();
  await expect(page.getByText("Scrammed.")).toHaveCount(0);
  await page.getByRole("button", { name: "SCRAM", exact: true }).click();

  // Rods drive fully in at scram speed and power collapses.
  await expect(page.getByText(/^Scrammed\./)).toBeVisible();
  await expect(page.getByTestId("rod-position")).toHaveText("100.0 %", { timeout: 10_000 });
  await expect.poll(() => powerPercent(page), { timeout: 10_000 }).toBeLessThan(10);

  // While scrammed, the operator's rod controls are locked and there is no reset.
  await expect(page.getByRole("button", { name: "Insert 1 %" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Reset scram" })).toHaveCount(0);
});
