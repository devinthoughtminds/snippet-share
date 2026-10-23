import { AxiosError, type AxiosResponse } from 'axios'
import { describe, expect, it, vi } from 'vitest'
import { api, createPaste, getPaste } from '../../src/service/api'

function httpError(status: number) {
  return new AxiosError('failed', 'ERR_BAD_RESPONSE', undefined, undefined, { status } as AxiosResponse)
}

const created = { id: 'abc', share_url: 'http://x/view/abc', created_at: '2026-01-01T00:00:00Z' }

describe('createPaste', () => {
  it('POSTs the text to /pastes and resolves with the body', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValue({ status: 201, data: created })

    await expect(createPaste('x')).resolves.toEqual(created)
    expect(post).toHaveBeenCalledWith('/pastes', { text: 'x' })
  })

  it.each([
    [413, 'too_large'],
    [429, 'rate_limited'],
    [422, 'invalid'],
    [500, 'server'],
    [502, 'server'],
  ])('maps HTTP %i to kind %s', async (status, kind) => {
    vi.spyOn(api, 'post').mockRejectedValue(httpError(status))
    await expect(createPaste('x')).rejects.toMatchObject({ kind })
  })

  it('maps an error with no response to kind network', async () => {
    vi.spyOn(api, 'post').mockRejectedValue(new AxiosError('Network Error', 'ERR_NETWORK'))
    await expect(createPaste('x')).rejects.toMatchObject({ kind: 'network' })
  })
})

describe('getPaste', () => {
  it('GETs /pastes/{id} and resolves with the body', async () => {
    const paste = { id: 'abc', text: 'hi', created_at: '2026-01-01T00:00:00Z' }
    const get = vi.spyOn(api, 'get').mockResolvedValue({ status: 200, data: paste })

    await expect(getPaste('abc')).resolves.toEqual(paste)
    expect(get).toHaveBeenCalledWith('/pastes/abc')
  })

  it('maps 404 to kind not_found', async () => {
    vi.spyOn(api, 'get').mockRejectedValue(httpError(404))
    await expect(getPaste('abc')).rejects.toMatchObject({ kind: 'not_found' })
  })
})
