// Vercel serverless function: forwards browser calls to the Render API
// and injects the API key server-side so it never reaches the browser.
export default async function handler(req: any, res: any) {
  const target = (process.env.API_PROXY_TARGET ?? '').replace(/\/+$/, '')
  const readKey = process.env.API_READ_KEY
  const adminKey = process.env.API_ADMIN_KEY
  if (!target || !readKey) {
    res.status(500).json({ title: 'Proxy not configured', detail: 'Set API_PROXY_TARGET and API_READ_KEY in Vercel.' })
    return
  }

  const url = new URL(req.url, 'http://localhost')
  const path = (url.searchParams.get('p') ?? '').replace(/^\/+/, '')
  url.searchParams.delete('p')
  const qs = url.searchParams.toString()

  const isAdmin = path.startsWith('api/v1/refresh')
  const key = isAdmin ? adminKey : readKey
  if (!key) {
    res.status(500).json({ title: 'Proxy not configured', detail: 'API_ADMIN_KEY is missing.' })
    return
  }

  const hasBody = !['GET', 'HEAD'].includes(req.method)
  try {
    const upstream = await fetch(`${target}/${path}${qs ? `?${qs}` : ''}`, {
      method: req.method,
      headers: { 'Content-Type': 'application/json', 'X-API-Key': key },
      body: hasBody ? (typeof req.body === 'string' ? req.body : JSON.stringify(req.body ?? {})) : undefined,
    })
    res.status(upstream.status)
    res.setHeader('Content-Type', upstream.headers.get('content-type') ?? 'application/json')
    const requestId = upstream.headers.get('x-request-id')
    if (requestId) res.setHeader('X-Request-ID', requestId)
    res.send(await upstream.text())
  } catch {
    res.status(502).json({ title: 'Upstream unavailable', detail: 'The API did not respond. It may be waking up; retry in a minute.' })
  }
}