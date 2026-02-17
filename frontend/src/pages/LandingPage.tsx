import { Link } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'

export default function LandingPage() {
  const { isAuthenticated } = useAuthStore()

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="container mx-auto px-4 py-16">
        <nav className="flex justify-between items-center mb-16">
          <h1 className="text-3xl font-bold text-gray-900">秒部</h1>
          <div>
            {isAuthenticated ? (
              <Link
                to="/dashboard"
                className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition"
              >
                控制台
              </Link>
            ) : (
              <Link
                to="/login"
                className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition"
              >
                登录
              </Link>
            )}
          </div>
        </nav>

        <div className="text-center max-w-4xl mx-auto">
          <h2 className="text-5xl font-bold text-gray-900 mb-6">
            一键部署前端项目
            <br />
            <span className="text-blue-600">全球 CDN 加速</span>
          </h2>
          <p className="text-xl text-gray-600 mb-8">
            连接 GitHub 仓库，自动构建并部署到云端，免费 SSL 证书全自动配置
          </p>
          <div className="flex gap-4 justify-center">
            {!isAuthenticated && (
              <Link
                to="/login"
                className="bg-blue-600 text-white px-8 py-3 rounded-lg text-lg font-semibold hover:bg-blue-700 transition"
              >
                立即开始
              </Link>
            )}
          </div>
        </div>

        <div className="mt-20 grid md:grid-cols-3 gap-8 max-w-6xl mx-auto">
          <div className="bg-white p-6 rounded-xl shadow-md">
            <div className="text-3xl mb-4">🚀</div>
            <h3 className="text-xl font-bold mb-2">秒级部署</h3>
            <p className="text-gray-600">
              推送代码到 GitHub，网站即刻上线
            </p>
          </div>
          <div className="bg-white p-6 rounded-xl shadow-md">
            <div className="text-3xl mb-4">🔒</div>
            <h3 className="text-xl font-bold mb-2">自动 HTTPS</h3>
            <p className="text-gray-600">
              全自动申请和续期 SSL 证书，安全无忧
            </p>
          </div>
          <div className="bg-white p-6 rounded-xl shadow-md">
            <div className="text-3xl mb-4">⚡</div>
            <h3 className="text-xl font-bold mb-2">全球加速</h3>
            <p className="text-gray-600">
              边缘节点覆盖全球，访问极速流畅
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
