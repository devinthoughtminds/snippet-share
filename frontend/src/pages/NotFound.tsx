import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <section className="empty">
      <h1 className="display">Page not found</h1>
      <p className="muted">There's nothing at this address.</p>
      <Link to="/" className="button primary">
        New paste
      </Link>
    </section>
  )
}
