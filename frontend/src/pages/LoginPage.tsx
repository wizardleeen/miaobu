import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { api } from '../services/api'
import { useToast } from '../components/Toast'
import Logo from '../components/Logo'
import { Github } from 'lucide-react'

export default function LoginPage() {
  const navigate = useNavigate()
  const { isAuthenticated } = useAuthStore()

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard')
    }
  }, [isAuthenticated, navigate])

  const { toast } = useToast()

  const handleGitHubLogin = async () => {
    try {
      const { url } = await api.getGitHubLoginUrl()
      window.location.href = url
    } catch (error) {
      console.error('Failed to get GitHub login URL:', error)
      toast('登录失败，请重试', 'error')
    }
  }

  return (
    <div className="min-h-screen bg-[--bg-secondary] flex items-center justify-center px-4">
      <div className="card p-8 max-w-md w-full animate-slide-in">
        <div className="text-center mb-8">
          <div className="mx-auto mb-4 w-12 h-12">
            <Logo size={48} />
          </div>
          <h1 className="text-2xl font-bold text-[--text-primary] mb-2">欢迎使用秒部</h1>
          <p className="text-[--text-secondary] text-sm">
            使用 GitHub 账号登录，即刻开始部署
          </p>
        </div>

        <button
          onClick={handleGitHubLogin}
          className="w-full bg-[--text-primary] text-[--bg-primary] px-6 py-3 rounded-lg font-medium hover:opacity-90 transition flex items-center justify-center gap-2"
        >
          <Github size={20} />
          使用 GitHub 登录
        </button>
      </div>
    </div>
  )
}
