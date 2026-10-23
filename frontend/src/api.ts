import axios from 'axios'
import { QueryClient } from '@tanstack/react-query'

// Relative URL: the Vite proxy (dev) and the nginx gateway (Docker) both route /api, so no CORS.
export const api = axios.create({ baseURL: '/api/v1' })

export const queryClient = new QueryClient({
  defaultOptions: {
    // Pastes never change once saved; errors get a Retry button instead of silent retries.
    queries: { staleTime: Infinity, retry: false },
  },
})
