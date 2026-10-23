import { Fragment, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useCopy } from '../hooks/useCopy'
import { getPaste, type ErrorKind } from '../service/api'

export default function ViewPage() {
  const { id = '' } = useParams()
  const { data, error, isPending, refetch } = useQuery({ queryKey: ['paste', id], queryFn: () => getPaste(id) })
  const preRef = useRef<HTMLPreElement>(null)
  const { status, copy } = useCopy(() => window.getSelection()?.selectAllChildren(preRef.current!))

  if (isPending) return <p className="status">Loading…</p>

  if (error) {
    if ((error as { kind?: ErrorKind }).kind === 'not_found') {
      return (
        <section className="empty">
          <h1 className="display">Snippet not found.</h1>
          <p className="muted">The link may be wrong, or the snippet never existed.</p>
          <Link to="/" className="button primary">
            New paste
          </Link>
        </section>
      )
    }
    return (
      <section className="empty" role="alert">
        <h1 className="display">Couldn't load this snippet</h1>
        <p className="muted">Check your connection and try again.</p>
        <button className="button primary" onClick={() => refetch()}>
          Retry
        </button>
      </section>
    )
  }

  return (
    <>
      <div className="view-head">
        <div>
          <h1 className="display">Snippet</h1>
          <p className="tabular muted">
            Created <time dateTime={data.created_at}>{new Date(data.created_at).toLocaleString()}</time>
          </p>
        </div>
        <div className="actions">
          <span className="status" aria-live="polite">
            {status}
          </span>
          <button className="button primary" onClick={() => copy(data.text)}>
            Copy raw text
          </button>
          <a className="button" href={`/api/v1/pastes/${encodeURIComponent(id)}/raw`} target="_blank" rel="noopener noreferrer">
            Open raw
          </a>
          <Link to="/" className="button">
            New paste
          </Link>
        </div>
      </div>
      <div className="card">
        {/* Text nodes only, never HTML. The "\n" between spans keeps textContent equal to the paste. */}
        <pre ref={preRef} className="code">
          {data.text.split('\n').map((line, i) => (
            <Fragment key={i}>
              {i > 0 && '\n'}
              <span className="line">{line}</span>
            </Fragment>
          ))}
        </pre>
      </div>
    </>
  )
}
