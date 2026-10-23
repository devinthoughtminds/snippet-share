import { useEffect, useRef } from 'react'
import { useCopy } from '../hooks/useCopy'

type Props = { shareUrl: string; onClose: () => void }

export default function ShareDialog({ shareUrl, onClose }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const { status, copy } = useCopy(() => inputRef.current?.select())

  // Native modal: focus trapping and Escape come for free.
  useEffect(() => {
    dialogRef.current?.showModal()
  }, [])

  return (
    <dialog ref={dialogRef} className="dialog" aria-labelledby="share-title" onClose={onClose}>
      <h2 id="share-title">Your snippet is ready</h2>
      <p className="muted">Anyone with this link can read it.</p>
      <input
        ref={inputRef}
        className="share-input"
        aria-label="Share link"
        readOnly
        value={shareUrl}
        onFocus={(e) => e.target.select()}
      />
      <div className="actions">
        <button className="button primary" onClick={() => copy(shareUrl)}>
          Copy link
        </button>
        <a className="button" href={shareUrl}>
          Open
        </a>
        <span className="spacer" />
        <span className="status" aria-live="polite">
          {status}
        </span>
        <button className="button" onClick={() => dialogRef.current?.close()}>
          Close
        </button>
      </div>
    </dialog>
  )
}
