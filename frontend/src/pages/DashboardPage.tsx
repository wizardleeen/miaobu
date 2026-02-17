import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../services/api'
import { useAuthStore } from '../stores/authStore'
import Layout from '../components/Layout'

export default function DashboardPage() {
  const { user } = useAuthStore()
  const { data: projects, isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.getProjects(),
  })

  return (
    <Layout>
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">欢迎回来，{user?.github_username}！</h1>
        <p className="text-gray-600">管理您的部署和项目</p>
      </div>

      <div className="grid md:grid-cols-3 gap-6 mb-8">
        <div className="bg-white p-6 rounded-lg shadow-md">
          <div className="text-3xl mb-2">📦</div>
          <div className="text-2xl font-bold">{projects?.length || 0}</div>
          <div className="text-gray-600">项目总数</div>
        </div>
        <div className="bg-white p-6 rounded-lg shadow-md">
          <div className="text-3xl mb-2">🚀</div>
          <div className="text-2xl font-bold">0</div>
          <div className="text-gray-600">活跃部署</div>
        </div>
        <div className="bg-white p-6 rounded-lg shadow-md">
          <div className="text-3xl mb-2">⚡</div>
          <div className="text-2xl font-bold">0</div>
          <div className="text-gray-600">本月构建次数</div>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-2xl font-bold">最近的项目</h2>
          <Link
            to="/projects"
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition"
          >
            查看所有项目
          </Link>
        </div>

        {isLoading ? (
          <div className="text-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
          </div>
        ) : projects && projects.length > 0 ? (
          <div className="space-y-4">
            {projects.slice(0, 5).map((project: any) => (
              <Link
                key={project.id}
                to={`/projects/${project.id}`}
                className="block p-4 border rounded-lg hover:border-blue-500 hover:shadow-md transition"
              >
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="font-semibold text-lg">{project.name}</h3>
                    <p className="text-sm text-gray-600">{project.github_repo_name}</p>
                  </div>
                  <span className="text-sm text-gray-500">
                    {new Date(project.updated_at).toLocaleDateString()}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <p className="text-gray-600 mb-4">暂无项目</p>
            <Link
              to="/projects"
              className="text-blue-600 hover:underline"
            >
              创建您的第一个项目
            </Link>
          </div>
        )}
      </div>
    </Layout>
  )
}
