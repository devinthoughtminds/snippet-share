import { fireEvent, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import CreatePage from '../../src/pages/CreatePage'
import { renderPage } from '../test-utils'

const textArea = () => screen.getByLabelText('Paste text')
const saveButton = () => screen.getByRole('button', { name: /save & share/i })

describe('CreatePage: text area and counters', () => {
  it('focuses the text area on load', () => {
    renderPage(<CreatePage />)
    expect(textArea()).toHaveFocus()
  })

  it('counts characters and words', async () => {
    const user = userEvent.setup()
    renderPage(<CreatePage />)
    await user.type(textArea(), 'hello world')
    expect(screen.getByText('11 characters · 2 words')).toBeInTheDocument()
  })

  it('disables Save & Share for empty or whitespace-only text', async () => {
    const user = userEvent.setup()
    renderPage(<CreatePage />)
    expect(saveButton()).toBeDisabled()
    await user.type(textArea(), '   ')
    expect(saveButton()).toBeDisabled()
  })

  it('blocks text over the limit in UTF-8 bytes, not characters', () => {
    renderPage(<CreatePage />)
    // 600,000 characters but 1,200,000 bytes
    fireEvent.change(textArea(), { target: { value: 'é'.repeat(600_000) } })
    expect(screen.getByText('Too large (max 1 MB)')).toBeInTheDocument()
    expect(saveButton()).toBeDisabled()
  })
})
