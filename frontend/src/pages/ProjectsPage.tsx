import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../services/api'
import Layout from '../components/Layout'
import CreateProjectModal from '../components/CreateProjectModal'
import { Globe, PackageOpen, Plus } from 'lucide-react'

export default function ProjectsPage() {
  const navigate = useNavigate()
  const [isModalOpen, setIsModalOpen] = useState(false)
  const { data: projects, isLoading, refetch } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.getProjects(),
  })

  return (
    <Layout>
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-2xl font-bold text-[--text-primary] mb-1">项目</h1>
          <p className="text-sm text-[--text-secondary]">管理您的部署项目</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setIsModalOpen(true)} className="btn-secondary text-sm">
            手动导入
          </button>
          <button onClick={() => navigate('/projects/import')} className="btn-primary text-sm flex items-center gap-1.5">
            <Plus size={16} />
            从 GitHub 导入
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-center py-16">
          <div className="animate-spin rounded-full h-10 w-10 border-2 border-accent border-t-transparent mx-auto"></div>
        </div>
      ) : projects && projects.length > 0 ? (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project: any) => (
            <Link
              key={project.id}
              to={`/projects/${project.id}`}
              className="card p-5 hover:border-accent/50 transition-colors group"
            >
              <h3 className="text-base font-semibold text-[--text-primary] mb-1 group-hover:text-accent transition-colors">
                {project.name}
              </h3>
              <p className="text-sm text-[--text-secondary] mb-4">{project.github_repo_name}</p>
              <div className="flex items-center gap-2 text-sm text-[--text-tertiary]">
                <Globe size={14} />
                <span className="truncate">{project.default_domain}</span>
              </div>
              <div className="mt-4 pt-3 border-t border-[--border-primary] text-xs text-[--text-tertiary]">
                更新于 {new Date(project.updated_at).toLocaleDateString('zh-CN')}
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <div className="card text-center py-16">
          <PackageOpen size={48} className="text-[--text-tertiary] mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-[--text-primary] mb-2">暂无项目</h2>
          <p className="text-[--text-secondary] mb-6 text-sm">从 GitHub 导入您的第一个项目开始使用</p>
          <button onClick={() => navigate('/projects/import')} className="btn-primary">
            从 GitHub 导入
          </button>
        </div>
      )}

      <CreateProjectModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSuccess={() => {
          setIsModalOpen(false)
          refetch()
        }}
      />
    </Layout>
  )
}
