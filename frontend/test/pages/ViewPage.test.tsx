import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, getPaste } from '../../src/service/api'
import { renderPage } from '../test-utils'
import ViewPage from '../../src/pages/ViewPage'

vi.mock('../../src/service/api', async (importOriginal) => ({ ...(await importOriginal<typeof import('../../src/service/api')>()), getPaste: vi.fn() }))
const mockGet = vi.mocked(getPaste)

const text = 'def main():\n    print("hi")\n\nmain()'
const paste = { id: 'abc', text, created_at: '2026-01-01T00:00:00Z' }

const renderView = () => renderPage(<ViewPage />, { path: '/view/:id', route: '/view/abc' })

beforeEach(() => {
  mockGet.mockReset()
})

describe('ViewPage: loading and showing', () => {
  it('shows Loading… while the request is pending', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    renderView()
    expect(screen.getByText('Loading…')).toBeInTheDocument()
    expect(mockGet).toHaveBeenCalledWith('abc')
  })

  it('shows every line in order, keeping indentation', async () => {
    mockGet.mockResolvedValue(paste)
    const { container } = renderView()
    await screen.findByText('main()')

    const lines = [...container.querySelectorAll('pre .line')].map((l) => l.textContent)
    expect(lines).toEqual(['def main():', '    print("hi")', '', 'main()'])
  })

  it('shows Snippet not found and a New paste link for not_found', async () => {
    mockGet.mockRejectedValue(new ApiError('not_found'))
    renderView()
    expect(await screen.findByText('Snippet not found.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'New paste' })).toHaveAttribute('href', '/')
  })

  it.each(['network', 'server'] as const)('shows a Retry button for %s errors', async (kind) => {
    mockGet.mockRejectedValueOnce(new ApiError(kind)).mockResolvedValueOnce(paste)
    const user = userEvent.setup()
    renderView()

    expect(await screen.findByText("Couldn't load this snippet")).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('main()')).toBeInTheDocument()
  })
})

describe('ViewPage: line numbers', () => {
  it('keeps line numbers out of the text content', async () => {
    const tricky = '\tone\r\n  two 🎉\n\nlast\n'
    mockGet.mockResolvedValue({ ...paste, text: tricky })
    const { container } = renderView()
    await screen.findByText('last')
    expect(container.querySelector('pre')!.textContent).toBe(tricky)
  })
})

describe('ViewPage: actions', () => {
  it('Copy raw text copies the paste and shows Copied!', async () => {
    mockGet.mockResolvedValue(paste)
    const user = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    renderView()

    await user.click(await screen.findByRole('button', { name: 'Copy raw text' }))

    expect(writeText).toHaveBeenCalledWith(text)
    expect(await screen.findByText('Copied!')).toBeInTheDocument()
  })

  it('selects the text when there is no clipboard', async () => {
    mockGet.mockResolvedValue(paste)
    const user = userEvent.setup()
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
    const { container } = renderView()

    await user.click(await screen.findByRole('button', { name: 'Copy raw text' }))

    expect(window.getSelection()!.toString()).toBe(container.querySelector('pre')!.textContent)
    expect(screen.getByText('Press Ctrl+C to copy')).toBeInTheDocument()
  })

  it('Open raw links to the raw endpoint in a new tab', async () => {
    mockGet.mockResolvedValue(paste)
    renderView()
    const link = await screen.findByRole('link', { name: 'Open raw' })
    expect(link).toHaveAttribute('href', '/api/v1/pastes/abc/raw')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('New paste links home', async () => {
    mockGet.mockResolvedValue(paste)
    renderView()
    expect(await screen.findByRole('link', { name: 'New paste' })).toHaveAttribute('href', '/')
  })

  it('renders HTML in a paste as literal text', async () => {
    const html = '<img src=x onerror=alert(1)>'
    mockGet.mockResolvedValue({ ...paste, text: html })
    const { container } = renderView()
    expect(await screen.findByText(html)).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })
})
