# frontend

React + Vite + TypeScript, with React Query and axios. See the [root README](../README.md#run-the-frontend-for-development) for how to run it.

## Writing a Playwright test

End-to-end tests live in [e2e/](e2e/) and drive a real Chromium browser against the real Vite dev server, backend and Postgres. [playwright.config.ts](playwright.config.ts) starts the backend (`:8000`) and Vite (`:5173`) for you, or reuses them if they're already running. Postgres must already be up: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up db`.

**1. First run only: install the browser.**

```sh
bunx playwright install chromium
```

**2. Record the steps instead of guessing selectors.** Start the app (`bun run dev`), then:

```sh
bunx playwright codegen http://localhost:5173
```

Click through the flow in the window that opens. Codegen writes the matching code as you go. Copy the useful lines into your test.

**3. Create `e2e/<feature>.spec.ts`.** Pastes created by tests land in your dev database, so assert on what this test created, not on what's already there.

```ts
import { expect, test } from '@playwright/test'

test('a saved paste can be read back', async ({ page }) => {
  await page.goto('/')                                     // baseURL comes from playwright.config.ts
  await page.getByLabel('Paste text').fill('hello e2e')
  await page.getByRole('button', { name: 'Save & Share' }).click()

  const link = page.getByLabel('Share link')
  await expect(link).toBeVisible()

  await page.goto(await link.inputValue())
  await expect(page.getByText('hello e2e')).toBeVisible()
})
```

**4. Follow the conventions in [e2e/paste.spec.ts](e2e/paste.spec.ts).**

- **Find elements the way a user would.** Prefer `getByRole`, `getByLabel` and `getByText` over CSS classes or ids. If an element is hard to select, give it a proper label in the component; that improves accessibility too.
- **Use `await expect(...)` assertions.** They retry until they pass or time out, so never add `waitForTimeout` sleeps.
- **Share steps through helpers.** When several tests repeat a flow, put it in a function like `createPaste(page, text)`.
- **Never touch the real clipboard.** Tests run in parallel and the OS clipboard is shared, so stub it the way `recordClipboard` does.
- **Keep every test independent.** Each one starts from `page.goto(...)` and creates its own data.

**5. Run it.**

```sh
bun run test:e2e                          # all tests, headless
bunx playwright test e2e/paste.spec.ts    # one file
bunx playwright test -g "read back"       # tests whose name matches
bunx playwright test --ui                 # watch mode: step through each action, see the DOM at each step
bunx playwright test --headed --debug     # visible browser, pause on every step
```

**6. When a test fails,** run `bunx playwright show-trace test-results/<test>/trace.zip` to see a timeline with screenshots, DOM snapshots and network calls. Traces are recorded on the first retry; add `--trace on` to record them locally.
