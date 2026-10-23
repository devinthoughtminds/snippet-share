import { fireEvent, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPaste } from '../../src/service/api'
import CreatePage from '../../src/pages/CreatePage'
import { renderPage } from '../test-utils'

vi.mock('../../src/service/api', async (importOriginal) => ({ ...(await importOriginal<typeof import('../../src/service/api')>()), createPaste: vi.fn() }))

const shareUrl = 'http://localhost:5173/view/abc'

function setClipboard(value: unknown) {
  Object.defineProperty(navigator, 'clipboard', { value, configurable: true })
}

async function openDialog() {
  const user = userEvent.setup()
  renderPage(<CreatePage />)
  await user.type(screen.getByLabelText('Paste text'), 'hi')
  await user.click(screen.getByRole('button', { name: 'Save & Share' }))
  await screen.findByDisplayValue(shareUrl)
  return user
}

beforeEach(() => {
  vi.mocked(createPaste).mockResolvedValue({ id: 'abc', share_url: shareUrl, created_at: '2026-01-01T00:00:00Z' })
})

describe('ShareDialog', () => {
  it('shows the link read-only with Copy link and Open', async () => {
    await openDialog()
    expect(screen.getByLabelText('Share link')).toHaveAttribute('readonly')
    expect(screen.getByRole('button', { name: 'Copy link' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute('href', shareUrl)
  })

  it('copies the link to the clipboard', async () => {
    const user = await openDialog()
    const writeText = vi.fn().mockResolvedValue(undefined)
    setClipboard({ writeText }) // after userEvent.setup(), which installs its own clipboard

    await user.click(screen.getByRole('button', { name: 'Copy link' }))

    expect(writeText).toHaveBeenCalledWith(shareUrl)
    expect(await screen.findByText('Copied!')).toBeInTheDocument()
  })

  it('falls back to selecting the link when there is no clipboard (plain http)', async () => {
    const user = await openDialog()
    setClipboard(undefined)

    await user.click(screen.getByRole('button', { name: 'Copy link' }))

    const input = screen.getByLabelText<HTMLInputElement>('Share link')
    expect(screen.getByText('Press Ctrl+C to copy')).toBeInTheDocument()
    expect([input.selectionStart, input.selectionEnd]).toEqual([0, shareUrl.length])
  })

  it('Close closes the dialog and returns focus to the text area', async () => {
    const user = await openDialog()
    await user.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByDisplayValue(shareUrl)).not.toBeInTheDocument()
    expect(screen.getByLabelText('Paste text')).toHaveFocus()
  })

  it('Escape (the native close event) also returns focus to the text area', async () => {
    await openDialog()
    // Browsers fire "close" after Escape; jsdom has no native dialog behaviour.
    fireEvent(screen.getByRole('dialog', { hidden: true }), new Event('close'))
    expect(screen.queryByDisplayValue(shareUrl)).not.toBeInTheDocument()
    expect(screen.getByLabelText('Paste text')).toHaveFocus()
  })
})
