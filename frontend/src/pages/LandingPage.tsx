import { Link } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import Logo from '../components/Logo'
import { Rocket, ShieldCheck, Zap } from 'lucide-react'

export default function LandingPage() {
  const { isAuthenticated } = useAuthStore()

  return (
    <div className="min-h-screen bg-[--bg-primary]">
      {/* Navbar */}
      <nav className="sticky top-0 z-50 backdrop-blur-md bg-[--bg-primary]/80 border-b border-[--border-primary]">
        <div className="container mx-auto px-4 h-16 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <Logo size={32} />
            <span className="text-lg font-bold text-[--text-primary]">秒部</span>
          </div>
          <div>
            {isAuthenticated ? (
              <Link to="/dashboard" className="btn-primary">
                控制台
              </Link>
            ) : (
              <Link to="/login" className="btn-primary">
                登录
              </Link>
            )}
          </div>
        </div>
      </nav>

      {/* Hero */}
      <div className="container mx-auto px-4 pt-24 pb-16">
        <div className="text-center max-w-4xl mx-auto">
          <h1 className="text-5xl sm:text-6xl font-bold text-[--text-primary] mb-6 tracking-tight leading-tight">
            一键部署你的项目
            <br />
            <span className="mt-2 inline-block bg-gradient-to-r from-blue-500 to-cyan-400 bg-clip-text text-transparent">
              前端与后端全栈支持
            </span>
          </h1>
          <p className="text-xl text-[--text-secondary] mb-10 max-w-2xl mx-auto">
            连接 GitHub 仓库，自动构建并部署到云端。支持主流前端框架、Node.js 和 Python 后端。
          </p>
          <div className="flex gap-4 justify-center">
            {isAuthenticated ? (
              <Link to="/dashboard" className="btn-primary px-8 py-3 text-lg">
                进入控制台
              </Link>
            ) : (
              <Link to="/login" className="btn-primary px-8 py-3 text-lg">
                立即开始
              </Link>
            )}
          </div>
        </div>

        {/* Features */}
        <div className="mt-24 grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
          {[
            {
              icon: Rocket,
              color: 'text-blue-500 bg-blue-500/10',
              title: '一键部署',
              desc: '推送代码到 GitHub，项目即刻上线',
            },
            {
              icon: ShieldCheck,
              color: 'text-emerald-500 bg-emerald-500/10',
              title: '自动 HTTPS',
              desc: '全自动申请和续期 SSL 证书，安全无忧',
            },
            {
              icon: Zap,
              color: 'text-amber-500 bg-amber-500/10',
              title: '全球加速',
              desc: '边缘节点覆盖全球，访问极速流畅',
            },
          ].map((feature) => (
            <div key={feature.title} className="card p-6">
              <div className={`w-10 h-10 rounded-lg ${feature.color} flex items-center justify-center mb-4`}>
                <feature.icon size={20} />
              </div>
              <h3 className="text-lg font-semibold text-[--text-primary] mb-2">{feature.title}</h3>
              <p className="text-[--text-secondary] text-sm">{feature.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
