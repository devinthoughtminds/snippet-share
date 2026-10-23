import { expect, test, type Page } from '@playwright/test'

const snippet = [
  'function greet(name) {',
  '    if (!name) {',
  '        return "hello, world";',
  '    }',
  '    return `hello, ${name}`;',
  '}',
  '',
  'console.log(greet("e2e"));',
].join('\n')

// The real OS clipboard is shared by parallel workers (and by you), so record what the page writes instead.
async function recordClipboard(page: Page) {
  await page.addInitScript(() => {
    navigator.clipboard.writeText = async (text: string) => {
      ;(window as { __copied?: string }).__copied = text
    }
  })
  return () => page.evaluate(() => (window as { __copied?: string }).__copied)
}

async function createPaste(page: Page, text: string) {
  await page.goto('/')
  await page.getByLabel('Paste text').fill(text)
  await page.getByRole('button', { name: 'Save & Share' }).click()
  const link = page.getByLabel('Share link')
  await expect(link).toBeVisible()
  return link.inputValue()
}

test.describe('create and share', () => {
  test('saves a paste and shows the share link', async ({ page }) => {
    const shareUrl = await createPaste(page, snippet)
    expect(shareUrl).toMatch(/\/view\/[0-9a-f-]{36}$/)
  })

  test('counts characters and words, and blocks empty text', async ({ page }) => {
    await page.goto('/')
    const save = page.getByRole('button', { name: 'Save & Share' })
    await expect(page.getByLabel('Paste text')).toBeFocused()
    await expect(save).toBeDisabled()

    await page.getByLabel('Paste text').fill('hello world')
    await expect(page.getByText('11 characters · 2 words')).toBeVisible()
    await expect(save).toBeEnabled()

    await page.getByLabel('Paste text').fill('   \n\t')
    await expect(save).toBeDisabled()
  })

  test('blocks text over 1 MB in UTF-8 bytes before sending', async ({ page }) => {
    await page.goto('/')
    await page.getByLabel('Paste text').fill('é'.repeat(600_000)) // 600k characters, 1.2 MB
    await expect(page.getByText('Too large (max 1 MB)')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Save & Share' })).toBeDisabled()
  })

  test('Copy link puts the link on the clipboard', async ({ page }) => {
    const copied = await recordClipboard(page)
    const shareUrl = await createPaste(page, 'copy me')
    await page.getByRole('button', { name: 'Copy link' }).click()
    await expect(page.getByText('Copied!')).toBeVisible()
    expect(await copied()).toBe(shareUrl)
  })

  test('Close and Escape close the dialog and refocus the text area', async ({ page }) => {
    await createPaste(page, 'close me')
    await page.getByRole('button', { name: 'Close' }).click()
    await expect(page.getByRole('dialog')).toBeHidden()
    await expect(page.getByLabel('Paste text')).toBeFocused()

    await page.getByRole('button', { name: 'Save & Share' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toBeHidden()
    await expect(page.getByLabel('Paste text')).toBeFocused()
  })
})

test.describe('errors on save keep the text', () => {
  test('rate limit (429) shows a message without Retry', async ({ page }) => {
    await page.route('**/api/v1/pastes', (route) => route.fulfill({ status: 429, body: '<html>429</html>' }))
    await page.goto('/')
    await page.getByLabel('Paste text').fill('keep me')
    await page.getByRole('button', { name: 'Save & Share' }).click()

    await expect(page.getByText('Too many pastes, try again in a minute')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Retry' })).toHaveCount(0)
    await expect(page.getByLabel('Paste text')).toHaveValue('keep me')
  })

  test('network failure offers Retry, which then succeeds', async ({ page }) => {
    await page.route('**/api/v1/pastes', (route) => route.abort())
    await page.goto('/')
    await page.getByLabel('Paste text').fill('retry me')
    await page.getByRole('button', { name: 'Save & Share' }).click()
    await expect(page.getByText("Couldn't reach the server")).toBeVisible()

    await page.unroute('**/api/v1/pastes')
    await page.getByRole('button', { name: 'Retry' }).click()
    await expect(page.getByLabel('Share link')).toBeVisible()
  })
})

test.describe('reading a paste', () => {
  test('shows the exact text with line numbers that are not part of it', async ({ page }) => {
    const shareUrl = await createPaste(page, snippet)
    await page.goto(shareUrl)

    const code = page.locator('pre.code')
    await expect(code).toBeVisible()
    expect(await code.textContent()).toBe(snippet)
    await expect(code.locator('.line')).toHaveCount(snippet.split('\n').length)

    // What a user gets when selecting the code: no line numbers.
    const selected = await code.evaluate((pre) => {
      getSelection()!.selectAllChildren(pre)
      return getSelection()!.toString()
    })
    expect(selected.replace(/\r/g, '')).toBe(snippet)
  })

  test('Copy raw text copies the paste', async ({ page }) => {
    const copied = await recordClipboard(page)
    await page.goto(await createPaste(page, snippet))
    await page.getByRole('button', { name: 'Copy raw text' }).click()
    await expect(page.getByText('Copied!')).toBeVisible()
    expect(await copied()).toBe(snippet)
  })

  test('Open raw serves the exact text as text/plain', async ({ page, request }) => {
    await page.goto(await createPaste(page, snippet))
    const rawLink = page.getByRole('link', { name: 'Open raw' })
    await expect(rawLink).toHaveAttribute('target', '_blank')

    const response = await request.get((await rawLink.getAttribute('href'))!)
    expect(response.headers()['content-type']).toBe('text/plain; charset=utf-8')
    expect(await response.text()).toBe(snippet)
  })

  test('HTML in a paste is shown as text and never runs', async ({ page }) => {
    const html = '<img src=x onerror="window.__xss = true">'
    await page.goto(await createPaste(page, html))

    await expect(page.locator('pre.code')).toHaveText(html)
    await expect(page.locator('pre.code img')).toHaveCount(0)
    expect(await page.evaluate(() => (window as { __xss?: boolean }).__xss)).toBeUndefined()
  })

  test('New paste goes back to the create page', async ({ page }) => {
    await page.goto(await createPaste(page, 'back home'))
    await page.locator('.view-head').getByRole('link', { name: 'New paste' }).click()
    await expect(page).toHaveURL('/')
    await expect(page.getByLabel('Paste text')).toBeVisible()
  })
})

test.describe('not found', () => {
  test('an unknown snippet id shows Snippet not found', async ({ page }) => {
    await page.goto('/view/00000000-0000-4000-8000-000000000000')
    await expect(page.getByText('Snippet not found.')).toBeVisible()
  })

  test('a malformed snippet id shows Snippet not found', async ({ page }) => {
    await page.goto('/view/not-a-uuid')
    await expect(page.getByText('Snippet not found.')).toBeVisible()
  })

  test('an unknown page shows Page not found', async ({ page }) => {
    await page.goto('/nope')
    await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible()
  })
})
