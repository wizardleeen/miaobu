import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { api } from '../services/api'
import { Loader2, XCircle } from 'lucide-react'

export default function CallbackPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { setAuth } = useAuthStore()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const token = searchParams.get('token')
    const errorMessage = searchParams.get('error')

    if (errorMessage) {
      setError(decodeURIComponent(errorMessage))
      setTimeout(() => navigate('/login'), 3000)
      return
    }

    if (!token) {
      setError('无效的回调参数')
      setTimeout(() => navigate('/login'), 3000)
      return
    }

    handleCallback(token)
  }, [searchParams])

  const handleCallback = async (token: string) => {
    try {
      localStorage.setItem('token', token)
      const user = await api.getCurrentUser()
      setAuth(token, user)
      navigate('/dashboard')
    } catch (error) {
      console.error('Authentication failed:', error)
      localStorage.removeItem('token')
      setError('登录失败，请重试。')
      setTimeout(() => navigate('/login'), 3000)
    }
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[--bg-secondary] flex items-center justify-center px-4">
        <div className="card p-8 max-w-md w-full text-center animate-slide-in">
          <XCircle size={48} className="text-red-500 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-[--text-primary] mb-2">登录失败</h1>
          <p className="text-[--text-secondary] mb-4">{error}</p>
          <p className="text-sm text-[--text-tertiary]">正在跳转到登录页...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[--bg-secondary] flex items-center justify-center px-4">
      <div className="card p-8 max-w-md w-full text-center animate-slide-in">
        <Loader2 size={40} className="text-accent mx-auto mb-4 animate-spin" />
        <h1 className="text-2xl font-bold text-[--text-primary] mb-2">正在登录...</h1>
        <p className="text-[--text-secondary]">请稍候</p>
      </div>
    </div>
  )
}
