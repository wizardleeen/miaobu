import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { api } from '../services/api'

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
      // Temporarily store token for API call
      localStorage.setItem('token', token)

      // Fetch user info using the token
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
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center">
        <div className="bg-white p-8 rounded-xl shadow-lg max-w-md w-full text-center">
          <div className="text-red-500 text-5xl mb-4">✕</div>
          <h1 className="text-2xl font-bold mb-2">登录失败</h1>
          <p className="text-gray-600 mb-4">{error}</p>
          <p className="text-sm text-gray-500">正在跳转到登录页...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center">
      <div className="bg-white p-8 rounded-xl shadow-lg max-w-md w-full text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
        <h1 className="text-2xl font-bold mb-2">正在登录...</h1>
        <p className="text-gray-600">请稍候</p>
      </div>
    </div>
  )
}
