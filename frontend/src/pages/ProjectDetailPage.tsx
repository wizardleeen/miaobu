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
    refetchInterval: 5000, // Refetch every 5 seconds to update deployment status
  })

  const deployMutation = useMutation({
    mutationFn: () => api.triggerDeployment(Number(projectId)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId] })
      setIsDeploying(false)
      refetch()
    },
    onError: () => {
      setIsDeploying(false)
      alert('Failed to trigger deployment. Please try again.')
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
    if (confirm('Are you sure you want to cancel this deployment?')) {
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
          <h2 className="text-2xl font-bold mb-2">Project not found</h2>
        </div>
      </Layout>
    )
  }

  // Check if there's an active deployment
  const hasActiveDeployment = project.deployments?.some((d: any) =>
    ['queued', 'cloning', 'building', 'uploading'].includes(d.status)
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
            {isDeploying ? 'Deploying...' : hasActiveDeployment ? 'Build in Progress' : '🚀 Deploy'}
          </button>
          <button
            onClick={() => navigate(`/projects/${projectId}/settings`)}
            className="px-4 py-2 border rounded-lg hover:bg-gray-50"
          >
            ⚙️ Settings
          </button>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6 mb-8">
        <div className="bg-white p-6 rounded-lg shadow-md">
          <h2 className="text-xl font-bold mb-4">Build Configuration</h2>
          <div className="space-y-3">
            <div>
              <label className="text-sm text-gray-600">Build Command</label>
              <p className="font-mono text-sm bg-gray-100 p-2 rounded">{project.build_command}</p>
            </div>
            <div>
              <label className="text-sm text-gray-600">Install Command</label>
              <p className="font-mono text-sm bg-gray-100 p-2 rounded">{project.install_command}</p>
            </div>
            <div>
              <label className="text-sm text-gray-600">Output Directory</label>
              <p className="font-mono text-sm bg-gray-100 p-2 rounded">{project.output_directory}</p>
            </div>
            <div>
              <label className="text-sm text-gray-600">Node Version</label>
              <p className="font-mono text-sm bg-gray-100 p-2 rounded">{project.node_version}</p>
            </div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-md">
          <h2 className="text-xl font-bold mb-4">Deployment Info</h2>
          <div className="space-y-3">
            <div>
              <label className="text-sm text-gray-600">Default Domain</label>
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
              <label className="text-sm text-gray-600">Default Branch</label>
              <p className="text-sm">{project.default_branch}</p>
            </div>
            <div>
              <label className="text-sm text-gray-600">Repository</label>
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
              <label className="text-sm text-gray-600">Auto Deploy</label>
              <div className="flex items-center gap-2">
                {project.webhook_id ? (
                  <>
                    <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                      ✓ Enabled
                    </span>
                    <span className="text-xs text-gray-500">
                      Deploys on push to {project.default_branch}
                    </span>
                  </>
                ) : (
                  <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                    Manual Only
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-2xl font-bold mb-4">Deployments</h2>
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
            <p className="mb-4">No deployments yet</p>
            <button
              onClick={handleDeploy}
              disabled={isDeploying}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Deploy Now
            </button>
          </div>
        )}
      </div>
    </Layout>
  )
}
