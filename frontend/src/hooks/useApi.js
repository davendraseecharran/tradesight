import { useState, useEffect, useCallback, useRef } from 'react'
import { apiFetch } from '../utils/api'

export function useApi(url, { interval = 0, deps = [] } = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const mountedRef = useRef(true)

  const fetch = useCallback(async () => {
    if (!url) { setLoading(false); return }
    setLoading(true)
    try {
      const result = await apiFetch(url)
      if (mountedRef.current) { setData(result); setError(null) }
    } catch (err) {
      if (mountedRef.current) setError(err.message)
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [url, ...deps])

  useEffect(() => {
    mountedRef.current = true
    fetch()
    if (interval > 0) {
      const id = setInterval(fetch, interval)
      return () => { mountedRef.current = false; clearInterval(id) }
    }
    return () => { mountedRef.current = false }
  }, [fetch, interval])

  return { data, loading, error, refetch: fetch }
}

export function usePost(url) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const post = useCallback(async (body) => {
    setLoading(true)
    setError(null)
    try {
      const result = await apiFetch(url, {
        method: 'POST',
        body: body ? JSON.stringify(body) : undefined,
      })
      return { data: result, error: null }
    } catch (err) {
      setError(err.message)
      return { data: null, error: err.message }
    } finally {
      setLoading(false)
    }
  }, [url])

  return { post, loading, error }
}
