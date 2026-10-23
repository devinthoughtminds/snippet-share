import { useState } from 'react'
import { copyText } from '../service/clipboard'

// Copy to the clipboard; without one (plain http), run `selectFallback` so the user can press Ctrl+C.
export function useCopy(selectFallback: () => void) {
  const [status, setStatus] = useState('')

  async function copy(text: string) {
    if (await copyText(text)) {
      setStatus('Copied!')
    } else {
      selectFallback()
      setStatus('Press Ctrl+C to copy')
    }
  }

  return { status, copy }
}
