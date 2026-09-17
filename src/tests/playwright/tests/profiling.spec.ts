import { test, expect, Page } from '@playwright/test';

// The service the harness agent reports as (see docker-compose.e2e.yml).
const SERVICE = process.env.E2E_UI_SERVICE || 'e2e-sample-app';
const BULK_URL = '/api/metrics/profile_request/bulk';

async function openConsoleAndSelectService(page: Page) {
  await page.goto('/profiling');

  // The DataGrid renders one row per workload; wait for our service to appear.
  const row = page.getByRole('row', { name: new RegExp(SERVICE) }).first();
  await expect(row).toBeVisible({ timeout: 30_000 });

  // Select the row via its checkbox (MUI DataGrid checkboxSelection).
  await row.getByRole('checkbox').check();
  return row;
}

async function confirmAndAwaitSubmit(page: Page, action: 'Start' | 'Stop') {
  // Open the confirmation dialog from the top-panel action button.
  await page.getByRole('button', { name: new RegExp(`${action} Profiling \\(\\d+\\)`) }).click();

  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();

  // The confirm button is gated on a server-side dry-run validation:
  //   disabled={dryRunValidation.isValidating || !dryRunValidation.isValid}
  // So it only enables when the request validates. For a host/service-level
  // STOP this is exactly the regression that previously failed with
  // "No PIDs should be provided when request_type is 'stop' ...".
  const confirm = dialog.getByRole('button', { name: new RegExp(`^${action} Profiling$`) });
  await expect(confirm).toBeEnabled({ timeout: 15_000 });

  // Submit and assert the real (non dry-run) bulk request succeeds.
  const [resp] = await Promise.all([
    page.waitForResponse((r) => {
      if (!r.url().includes(BULK_URL) || r.request().method() !== 'POST') return false;
      try {
        return JSON.parse(r.request().postData() || '{}').dry_run === false;
      } catch {
        return false;
      }
    }),
    confirm.click(),
  ]);
  expect(resp.status()).toBe(200);
  return resp;
}

test.describe('profiling console', () => {
  test('service/host-level STOP validates and submits (regression AT for the stop bug)', async ({ page }) => {
    await openConsoleAndSelectService(page);
    await confirmAndAwaitSubmit(page, 'Stop');
    // No "No PIDs should be provided" validation error should ever surface.
    await expect(page.getByText(/No PIDs should be provided/i)).toHaveCount(0);
  });

  test('service/host-level START validates and submits', async ({ page }) => {
    await openConsoleAndSelectService(page);
    await confirmAndAwaitSubmit(page, 'Start');
  });
});
