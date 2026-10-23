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

export type PasteCreated = { id: string; share_url: string; created_at: string }
export type Paste = { id: string; text: string; created_at: string }

export type ErrorKind = 'too_large' | 'rate_limited' | 'invalid' | 'not_found' | 'network' | 'server'

export class ApiError extends Error {
  kind: ErrorKind
  constructor(kind: ErrorKind) {
    super(kind)
    this.kind = kind
  }
}

const KIND_BY_STATUS: Record<number, ErrorKind> = {
  404: 'not_found',
  413: 'too_large',
  422: 'invalid',
  429: 'rate_limited',
}

// Map on the status only: nginx answers 413 and 429 with HTML pages, not JSON.
function toApiError(err: unknown): ApiError {
  if (axios.isAxiosError(err) && !err.response) return new ApiError('network')
  const status = axios.isAxiosError(err) ? err.response?.status : undefined
  return new ApiError((status && KIND_BY_STATUS[status]) || 'server')
}

export async function createPaste(text: string): Promise<PasteCreated> {
  try {
    return (await api.post<PasteCreated>('/pastes', { text })).data
  } catch (err) {
    throw toApiError(err)
  }
}

export async function getPaste(id: string): Promise<Paste> {
  try {
    return (await api.get<Paste>(`/pastes/${encodeURIComponent(id)}`)).data
  } catch (err) {
    throw toApiError(err)
  }
}
