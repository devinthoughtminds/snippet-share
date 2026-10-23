// navigator.clipboard only exists on https:// and localhost; on plain http (e.g. a LAN IP) it's undefined.
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
