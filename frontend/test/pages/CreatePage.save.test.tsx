import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, createPaste, type ErrorKind } from '../../src/service/api'
import CreatePage from '../../src/pages/CreatePage'
import { renderPage } from '../test-utils'

vi.mock('../../src/service/api', async (importOriginal) => ({ ...(await importOriginal<typeof import('../../src/service/api')>()), createPaste: vi.fn() }))
const mockCreate = vi.mocked(createPaste)

const created = { id: 'abc', share_url: 'http://localhost:5173/view/abc', created_at: '2026-01-01T00:00:00Z' }
const textArea = () => screen.getByLabelText('Paste text')
const saveButton = () => screen.getByRole('button', { name: /save & share|saving/i })

async function typeAndSave(text: string) {
  const user = userEvent.setup()
  renderPage(<CreatePage />)
  await user.type(textArea(), text)
  await user.click(saveButton())
  return user
}

beforeEach(() => {
  mockCreate.mockReset()
})

describe('CreatePage: saving', () => {
  it('sends the exact text, not trimmed', async () => {
    mockCreate.mockResolvedValue(created)
    await typeAndSave('  hi  ')
    expect(mockCreate).toHaveBeenCalledWith('  hi  ')
  })

  it('shows Saving… and ignores double clicks while pending', async () => {
    mockCreate.mockReturnValue(new Promise(() => {}))
    const user = await typeAndSave('hi')
    expect(saveButton()).toHaveTextContent('Saving…')
    expect(saveButton()).toBeDisabled()
    await user.click(saveButton())
    expect(mockCreate).toHaveBeenCalledTimes(1)
  })

  it('opens the share dialog with the link on success', async () => {
    mockCreate.mockResolvedValue(created)
    await typeAndSave('hi')
    expect(await screen.findByDisplayValue(created.share_url)).toBeInTheDocument()
  })

  it.each<[ErrorKind, string, boolean]>([
    ['too_large', 'Too large (max 1 MB)', false],
    ['rate_limited', 'Too many pastes, try again in a minute', false],
    ['network', "Couldn't reach the server", true],
    ['server', 'Something went wrong', true],
  ])('shows the %s message and keeps the text', async (kind, message, retry) => {
    mockCreate.mockRejectedValue(new ApiError(kind))
    await typeAndSave('keep me')

    expect(await screen.findByText(message)).toBeInTheDocument()
    expect(textArea()).toHaveValue('keep me')
    expect(screen.queryByRole('button', { name: 'Retry' }) !== null).toBe(retry)
  })

  it('Retry sends the text again', async () => {
    mockCreate.mockRejectedValueOnce(new ApiError('network')).mockResolvedValueOnce(created)
    const user = await typeAndSave('again')
    await user.click(await screen.findByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(2))
    expect(mockCreate).toHaveBeenLastCalledWith('again')
  })
})
