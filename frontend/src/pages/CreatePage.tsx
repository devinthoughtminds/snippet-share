import { useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { createPaste, type ErrorKind } from '../service/api'
import ShareDialog from '../components/ShareDialog'

// The Docker build has no .env, so the fallback is the real default. Must match MAX_PASTE_BYTES.
const MAX_BYTES = Number(import.meta.env.VITE_MAX_PASTE_BYTES ?? 1048576)
const MAX_LABEL = `${+(MAX_BYTES / 1048576).toFixed(1)} MB`

const ERROR_MESSAGES: Record<ErrorKind, string> = {
  too_large: `Too large (max ${MAX_LABEL})`,
  rate_limited: 'Too many pastes, try again in a minute',
  invalid: "This text can't be saved",
  not_found: 'Something went wrong',
  network: "Couldn't reach the server",
  server: 'Something went wrong',
}
const RETRYABLE: ErrorKind[] = ['network', 'server', 'not_found']

const plural = (n: number, word: string) => `${n.toLocaleString()} ${word}${n === 1 ? '' : 's'}`

export default function CreatePage() {
  const [text, setText] = useState('')
  const [shareUrl, setShareUrl] = useState<string | null>(null)
  const textAreaRef = useRef<HTMLTextAreaElement>(null)
  const { mutate, isPending, error, reset } = useMutation({
    mutationFn: (value: string) => createPaste(value),
    onSuccess: (paste) => setShareUrl(paste.share_url),
  })

  const characters = [...text].length
  const words = text.trim().split(/\s+/).filter(Boolean).length
  const tooLarge = new TextEncoder().encode(text).length > MAX_BYTES
  const canSave = text.trim() !== '' && !tooLarge && !isPending
  // createPaste only ever throws ApiError.
  const errorKind = (error as { kind?: ErrorKind } | null)?.kind ?? (error ? 'server' : null)

  function closeDialog() {
    setShareUrl(null)
    reset()
    textAreaRef.current?.focus()
  }

  return (
    <>
      <h1 className="display">Share a snippet</h1>
      <p className="lead">Paste text, save it, and send the link. Whitespace and indentation are kept exactly.</p>
      <div className="card">
        <textarea
          ref={textAreaRef}
          className="editor"
          aria-label="Paste text"
          placeholder="Paste or type here…"
          autoFocus
          spellCheck={false}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="toolbar">
          <span className="tabular muted">
            {plural(characters, 'character')} · {plural(words, 'word')}
          </span>
          {tooLarge && <span className="error">Too large (max {MAX_LABEL})</span>}
          {errorKind && !tooLarge && (
            <span className="error-row" role="alert">
              <span className="error">{ERROR_MESSAGES[errorKind]}</span>
              {RETRYABLE.includes(errorKind) && (
                <button className="button" onClick={() => mutate(text)}>
                  Retry
                </button>
              )}
            </span>
          )}
          <span className="spacer" />
          <button className="button primary" disabled={!canSave} onClick={() => mutate(text)}>
            {isPending ? 'Saving…' : 'Save & Share'}
          </button>
        </div>
      </div>
      {shareUrl && <ShareDialog shareUrl={shareUrl} onClose={closeDialog} />}
    </>
  )
}
