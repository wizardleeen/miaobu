import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'
import Layout from '../components/Layout'
import DeploymentCard from '../components/DeploymentCard'
import { Rocket, Settings, Check, ExternalLink } from 'lucide-react'

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [isDeploying, setIsDeploying] = useState(false)

  const { data: project, isLoading, refetch } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => api.getProject(Number(projectId)),
    enabled: !!projectId,
    refetchInterval: 5000,
  })

  const deployMutation = useMutation({
    mutationFn: () => api.triggerDeployment(Number(projectId)),
    onSuccess: async () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId] })
      await refetch()
      setIsDeploying(false)
    },
    onError: () => {
      setIsDeploying(false)
      alert('触发部署失败，请重试')
    },
  })

  const cancelMutation = useMutation({
    mutationFn: (deploymentId: number) => api.cancelDeployment(deploymentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId] })
      refetch()
    },
  })

  const handleDeploy = () => {
    setIsDeploying(true)
    deployMutation.mutate()
  }

  const handleCancel = (deploymentId: number) => {
    if (confirm('确定要取消此次部署吗？')) {
      cancelMutation.mutate(deploymentId)
    }
  }

  if (isLoading) {
    return (
      <Layout>
        <div className="text-center py-16">
          <div className="animate-spin rounded-full h-10 w-10 border-2 border-accent border-t-transparent mx-auto"></div>
        </div>
      </Layout>
    )
  }

  if (!project) {
    return (
      <Layout>
        <div className="text-center py-16">
          <h2 className="text-xl font-semibold text-[--text-primary] mb-2">项目不存在</h2>
        </div>
      </Layout>
    )
  }

  const hasActiveDeployment = project.deployments?.some((d: any) =>
    ['queued', 'cloning', 'building', 'uploading', 'deploying'].includes(d.status)
  )

  return (
    <Layout>
      <div className="flex justify-between items-start mb-8">
        <div>
          <h1 className="text-2xl font-bold text-[--text-primary] mb-1">{project.name}</h1>
          <p className="text-sm text-[--text-secondary]">{project.github_repo_name}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleDeploy}
            disabled={isDeploying || hasActiveDeployment}
            className="btn-primary flex items-center gap-2 text-sm"
          >
            <Rocket size={16} />
            {isDeploying ? '部署中...' : hasActiveDeployment ? '构建中' : '部署'}
          </button>
          <button
            onClick={() => navigate(`/projects/${projectId}/settings`)}
            className="btn-secondary flex items-center gap-2 text-sm"
          >
            <Settings size={16} />
            设置
          </button>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-4 mb-8">
        <div className="card p-5">
          <h2 className="text-sm font-semibold text-[--text-primary] mb-4">
            {project.project_type === 'python' ? '部署配置' : '构建配置'}
          </h2>
          <div className="space-y-3">
            {project.project_type === 'python' ? (
              <>
                <div>
                  <label className="text-xs text-[--text-tertiary]">项目类型</label>
                  <p className="text-sm mt-0.5">
                    <span className="badge-info">
                      Python 后端
                      {project.python_framework && ` (${project.python_framework})`}
                    </span>
                  </p>
                </div>
                <div>
                  <label className="text-xs text-[--text-tertiary]">启动命令</label>
                  <p className="font-mono text-sm bg-[--bg-tertiary] p-2 rounded-lg mt-0.5">{project.start_command || '—'}</p>
                </div>
                <div>
                  <label className="text-xs text-[--text-tertiary]">Python 版本</label>
                  <p className="font-mono text-sm bg-[--bg-tertiary] p-2 rounded-lg mt-0.5">{project.python_version || '3.11'}</p>
                </div>
                {project.fc_endpoint_url && (
                  <div>
                    <label className="text-xs text-[--text-tertiary]">服务端点</label>
                    <p className="font-mono text-xs bg-[--bg-tertiary] p-2 rounded-lg mt-0.5 truncate">{project.fc_endpoint_url}</p>
                  </div>
                )}
              </>
            ) : (
              <>
                <div>
                  <label className="text-xs text-[--text-tertiary]">构建命令</label>
                  <p className="font-mono text-sm bg-[--bg-tertiary] p-2 rounded-lg mt-0.5">{project.build_command}</p>
                </div>
                <div>
                  <label className="text-xs text-[--text-tertiary]">安装命令</label>
                  <p className="font-mono text-sm bg-[--bg-tertiary] p-2 rounded-lg mt-0.5">{project.install_command}</p>
                </div>
                <div>
                  <label className="text-xs text-[--text-tertiary]">输出目录</label>
                  <p className="font-mono text-sm bg-[--bg-tertiary] p-2 rounded-lg mt-0.5">{project.output_directory}</p>
                </div>
                <div>
                  <label className="text-xs text-[--text-tertiary]">Node 版本</label>
                  <p className="font-mono text-sm bg-[--bg-tertiary] p-2 rounded-lg mt-0.5">{project.node_version}</p>
                </div>
              </>
            )}
          </div>
        </div>

        <div className="card p-5">
          <h2 className="text-sm font-semibold text-[--text-primary] mb-4">部署信息</h2>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-[--text-tertiary]">默认域名</label>
              <p className="text-sm mt-0.5">
                <a
                  href={`https://${project.default_domain}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent hover:text-[--accent-hover] inline-flex items-center gap-1"
                >
                  {project.default_domain}
                  <ExternalLink size={12} />
                </a>
              </p>
            </div>
            <div>
              <label className="text-xs text-[--text-tertiary]">默认分支</label>
              <p className="text-sm text-[--text-primary] mt-0.5">{project.default_branch}</p>
            </div>
            <div>
              <label className="text-xs text-[--text-tertiary]">代码仓库</label>
              <p className="text-sm mt-0.5">
                <a
                  href={project.github_repo_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent hover:text-[--accent-hover] inline-flex items-center gap-1"
                >
                  {project.github_repo_name}
                  <ExternalLink size={12} />
                </a>
              </p>
            </div>
            <div>
              <label className="text-xs text-[--text-tertiary]">自动部署</label>
              <div className="flex items-center gap-2 mt-0.5">
                {project.webhook_id ? (
                  <>
                    <span className="badge-success">
                      <Check size={12} />
                      已启用
                    </span>
                    <span className="text-xs text-[--text-tertiary]">
                      推送到 {project.default_branch} 时自动部署
                    </span>
                  </>
                ) : (
                  <span className="badge-neutral">仅手动</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="card p-6">
        <h2 className="text-lg font-semibold text-[--text-primary] mb-4">部署记录</h2>
        {project.deployments && project.deployments.length > 0 ? (
          <div className="divide-y divide-[--border-primary]">
            {project.deployments.map((deployment: any) => (
              <DeploymentCard
                key={deployment.id}
                deployment={deployment}
                onCancel={handleCancel}
              />
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <p className="text-[--text-secondary] mb-4">暂无部署记录</p>
            <button
              onClick={handleDeploy}
              disabled={isDeploying}
              className="btn-primary text-sm"
            >
              立即部署
            </button>
          </div>
        )}
      </div>
    </Layout>
  )
}
