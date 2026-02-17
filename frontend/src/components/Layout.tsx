import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'

interface LayoutProps {
  children: React.ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow-sm border-b">
        <div className="container mx-auto px-4">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-8">
              <Link to="/dashboard" className="text-2xl font-bold text-gray-900">
                Miaobu
              </Link>
              <div className="hidden md:flex gap-4">
                <Link
                  to="/dashboard"
                  className="text-gray-700 hover:text-gray-900 px-3 py-2 rounded-md"
                >
                  控制台
                </Link>
                <Link
                  to="/projects"
                  className="text-gray-700 hover:text-gray-900 px-3 py-2 rounded-md"
                >
                  项目
                </Link>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                {user?.github_avatar_url && (
                  <img
                    src={user.github_avatar_url}
                    alt={user.github_username}
                    className="w-8 h-8 rounded-full"
                  />
                )}
                <span className="text-gray-700">{user?.github_username}</span>
              </div>
              <button
                onClick={handleLogout}
                className="text-gray-700 hover:text-gray-900 px-3 py-2 rounded-md"
              >
                退出登录
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="container mx-auto px-4 py-8">
        {children}
      </main>
    </div>
  )
}
