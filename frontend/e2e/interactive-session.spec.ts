import { expect, test } from '@playwright/test';

const HARNESS = 'codex';
const FIXTURE_ARTIFACT_ID = 'rollout-interactive-fixture.jsonl';
const DETAIL_ROUTE = `/sessions/${HARNESS}/${FIXTURE_ARTIFACT_ID}`;
const INTERACTIVE_ROUTE = `${DETAIL_ROUTE}/interactive`;

function buildRoutePattern(route: string): RegExp {
  return new RegExp(`${route.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`);
}

test.describe('interactive session skeleton', () => {
  test.skip('tail snapshot shows last messages', async ({ page }) => {
    await page.goto(DETAIL_ROUTE);
    await expect(page).toHaveURL(buildRoutePattern(DETAIL_ROUTE));
  });

  test.skip('detail CTA opens interactive route', async ({ page }) => {
    await page.goto(DETAIL_ROUTE);
    await expect(page).toHaveURL(buildRoutePattern(DETAIL_ROUTE));

    await page.goto(INTERACTIVE_ROUTE);
    await expect(page).toHaveURL(buildRoutePattern(INTERACTIVE_ROUTE));
  });

  test.skip('interactive prompt roundtrip', async ({ page }) => {
    await page.goto(INTERACTIVE_ROUTE);
    await expect(page).toHaveURL(buildRoutePattern(INTERACTIVE_ROUTE));
  });
});
