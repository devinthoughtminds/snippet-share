import { Link, Outlet } from 'react-router-dom'

export default function Layout() {
  return (
    <>
      <div className="mesh" aria-hidden="true" />
      <header className="nav">
        <Link to="/" className="wordmark">
          snippet<span>·</span>share
        </Link>
        <Link to="/" className="nav-link">
          New paste
        </Link>
      </header>
      <main className="page">
        <Outlet />
      </main>
    </>
  )
}
