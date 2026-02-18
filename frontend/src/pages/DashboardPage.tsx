import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import Layout from '../components/Layout'
import { Package, Rocket, Activity } from 'lucide-react'

export default function DashboardPage() {
  const { user } = useAuthStore()
  const { data: projects, isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.getProjects(),
  })
  const { data: stats } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: () => api.getDashboardStats(),
  })

  return (
    <Layout>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[--text-primary] mb-1">
          欢迎回来，{user?.github_username}
        </h1>
        <p className="text-[--text-secondary] text-sm">管理您的部署和项目</p>
      </div>

      <div className="grid md:grid-cols-3 gap-4 mb-8">
        {[
          { icon: Package, label: '项目总数', value: projects?.length || 0, color: 'text-blue-500' },
          { icon: Rocket, label: '活跃部署', value: stats?.active_deployments || 0, color: 'text-emerald-500' },
          { icon: Activity, label: '本月构建次数', value: stats?.builds_this_month || 0, color: 'text-amber-500' },
        ].map((stat) => (
          <div key={stat.label} className="card p-5">
            <div className="flex items-center gap-3 mb-3">
              <stat.icon size={20} className={stat.color} />
              <span className="text-sm text-[--text-secondary]">{stat.label}</span>
            </div>
            <div className="text-2xl font-bold text-[--text-primary]">{stat.value}</div>
          </div>
        ))}
      </div>

      <div className="card p-6">
        <div className="flex justify-between items-center mb-5">
          <h2 className="text-lg font-semibold text-[--text-primary]">最近的项目</h2>
          <Link to="/projects" className="btn-primary text-sm">
            查看所有项目
          </Link>
        </div>

        {isLoading ? (
          <div className="text-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-accent border-t-transparent mx-auto"></div>
          </div>
        ) : projects && projects.length > 0 ? (
          <div className="divide-y divide-[--border-primary]">
            {projects.slice(0, 5).map((project: any) => (
              <Link
                key={project.id}
                to={`/projects/${project.id}`}
                className="flex justify-between items-center py-3.5 px-3 -mx-3 rounded-lg hover:bg-[--bg-tertiary] transition-colors"
              >
                <div>
                  <h3 className="font-medium text-[--text-primary]">{project.name}</h3>
                  <p className="text-sm text-[--text-secondary]">{project.github_repo_name}</p>
                </div>
                <span className="text-xs text-[--text-tertiary]">
                  {new Date(project.updated_at).toLocaleDateString()}
                </span>
              </Link>
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <p className="text-[--text-secondary] mb-3">暂无项目</p>
            <Link to="/projects" className="text-accent hover:text-[--accent-hover] text-sm font-medium">
              创建您的第一个项目
            </Link>
          </div>
        )}
      </div>
    </Layout>
  )
}
