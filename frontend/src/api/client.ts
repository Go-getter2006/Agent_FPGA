// 统一的请求封装：带 Cookie，错误统一成 ApiError（后端格式 {"error": {"code", "message"}}）
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message)
  }
}

export async function api<T>(method: string, url: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, {
      method,
      credentials: 'same-origin',
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'NETWORK', '网络连接不上，请检查网络后重试')
  }
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) {
    const err = data?.error ?? {}
    throw new ApiError(res.status, err.code ?? 'HTTP_ERROR', err.message ?? '出了点问题，请重试')
  }
  return data as T
}

export const get = <T>(url: string) => api<T>('GET', url)
export const post = <T>(url: string, body: unknown = {}) => api<T>('POST', url, body)
