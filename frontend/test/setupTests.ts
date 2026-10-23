import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// jsdom has no <dialog> modal API; browsers do. Just enough for open/close and the close event.
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute('open')
    this.dispatchEvent(new Event('close'))
  }
}

// No vitest globals, so Testing Library can't register its own cleanup.
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})
