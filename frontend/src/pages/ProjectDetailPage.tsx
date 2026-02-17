import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'
import Layout from '../components/Layout'
import DeploymentCard from '../components/DeploymentCard'

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [isDeploying, setIsDeploying] = useState(false)

  const { data: project, isLoading, refetch } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => api.getProject(Number(projectId)),
    enabled: !!projectId,
    refetchInterval: 5000, // 每5秒刷新一次以更新部署状态
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
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
        </div>
      </Layout>
    )
  }

  if (!project) {
    return (
      <Layout>
        <div className="text-center py-16">
          <h2 className="text-2xl font-bold mb-2">项目不存在</h2>
        </div>
      </Layout>
    )
  }

  // 检查是否有正在进行的部署
  const hasActiveDeployment = project.deployments?.some((d: any) =>
    ['queued', 'cloning', 'building', 'uploading', 'deploying'].includes(d.status)
  )

  return (
    <Layout>
      <div className="flex justify-between items-start mb-8">
        <div>
          <h1 className="text-3xl font-bold mb-2">{project.name}</h1>
          <p className="text-gray-600">{project.github_repo_name}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleDeploy}
            disabled={isDeploying || hasActiveDeployment}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isDeploying ? '部署中...' : hasActiveDeployment ? '构建中' : '🚀 部署'}
          </button>
          <button
            onClick={() => navigate(`/projects/${projectId}/settings`)}
            className="px-4 py-2 border rounded-lg hover:bg-gray-50"
          >
            ⚙️ 设置
          </button>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6 mb-8">
        <div className="bg-white p-6 rounded-lg shadow-md">
          <h2 className="text-xl font-bold mb-4">
            {project.project_type === 'python' ? '部署配置' : '构建配置'}
          </h2>
          <div className="space-y-3">
            {project.project_type === 'python' ? (
              <>
                <div>
                  <label className="text-sm text-gray-600">项目类型</label>
                  <p className="text-sm">
                    <span className="inline-flex items-center gap-1.5 px-2 py-1 bg-blue-100 text-blue-800 rounded">
                      Python 后端
                      {project.python_framework && ` (${project.python_framework})`}
                    </span>
                  </p>
                </div>
                <div>
                  <label className="text-sm text-gray-600">启动命令</label>
                  <p className="font-mono text-sm bg-gray-100 p-2 rounded">{project.start_command || '—'}</p>
                </div>
                <div>
                  <label className="text-sm text-gray-600">Python 版本</label>
                  <p className="font-mono text-sm bg-gray-100 p-2 rounded">{project.python_version || '3.11'}</p>
                </div>
                {project.fc_endpoint_url && (
                  <div>
                    <label className="text-sm text-gray-600">服务端点</label>
                    <p className="font-mono text-xs bg-gray-100 p-2 rounded truncate">{project.fc_endpoint_url}</p>
                  </div>
                )}
              </>
            ) : (
              <>
                <div>
                  <label className="text-sm text-gray-600">构建命令</label>
                  <p className="font-mono text-sm bg-gray-100 p-2 rounded">{project.build_command}</p>
                </div>
                <div>
                  <label className="text-sm text-gray-600">安装命令</label>
                  <p className="font-mono text-sm bg-gray-100 p-2 rounded">{project.install_command}</p>
                </div>
                <div>
                  <label className="text-sm text-gray-600">输出目录</label>
                  <p className="font-mono text-sm bg-gray-100 p-2 rounded">{project.output_directory}</p>
                </div>
                <div>
                  <label className="text-sm text-gray-600">Node 版本</label>
                  <p className="font-mono text-sm bg-gray-100 p-2 rounded">{project.node_version}</p>
                </div>
              </>
            )}
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-md">
          <h2 className="text-xl font-bold mb-4">部署信息</h2>
          <div className="space-y-3">
            <div>
              <label className="text-sm text-gray-600">默认域名</label>
              <p className="text-sm">
                <a
                  href={`https://${project.default_domain}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:underline"
                >
                  {project.default_domain}
                </a>
              </p>
            </div>
            <div>
              <label className="text-sm text-gray-600">默认分支</label>
              <p className="text-sm">{project.default_branch}</p>
            </div>
            <div>
              <label className="text-sm text-gray-600">代码仓库</label>
              <p className="text-sm">
                <a
                  href={project.github_repo_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:underline"
                >
                  {project.github_repo_name}
                </a>
              </p>
            </div>
            <div>
              <label className="text-sm text-gray-600">自动部署</label>
              <div className="flex items-center gap-2">
                {project.webhook_id ? (
                  <>
                    <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                      ✓ 已启用
                    </span>
                    <span className="text-xs text-gray-500">
                      推送到 {project.default_branch} 时自动部署
                    </span>
                  </>
                ) : (
                  <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                    仅手动
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-2xl font-bold mb-4">部署记录</h2>
        {project.deployments && project.deployments.length > 0 ? (
          <div className="space-y-4">
            {project.deployments.map((deployment: any) => (
              <DeploymentCard
                key={deployment.id}
                deployment={deployment}
                onCancel={handleCancel}
              />
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-gray-600">
            <p className="mb-4">暂无部署记录</p>
            <button
              onClick={handleDeploy}
              disabled={isDeploying}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              立即部署
            </button>
          </div>
        )}
      </div>
    </Layout>
  )
}
