import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../services/api'

interface Deployment {
  id: number
  status: string
  commit_sha: string
  commit_message: string
  commit_author: string
  branch: string
  created_at: string
  deployed_at?: string
  error_message?: string
  build_time_seconds?: number
  deployment_url?: string
  oss_url?: string
  cdn_url?: string
}

interface DeploymentCardProps {
  deployment: Deployment
  onCancel?: (id: number) => void
}

export default function DeploymentCard({ deployment, onCancel }: DeploymentCardProps) {
  const [showLogs, setShowLogs] = useState(false)

  const { data: logsData } = useQuery({
    queryKey: ['deployment-logs', deployment.id],
    queryFn: () => api.getDeploymentLogs(deployment.id),
    enabled: showLogs,
    refetchInterval: deployment.status === 'queued' || deployment.status === 'cloning' || deployment.status === 'building' || deployment.status === 'uploading' ? 2000 : false,
  })

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'deployed':
        return 'bg-green-100 text-green-800'
      case 'failed':
      case 'cancelled':
        return 'bg-red-100 text-red-800'
      case 'queued':
      case 'cloning':
      case 'building':
      case 'uploading':
        return 'bg-yellow-100 text-yellow-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  const canCancel = ['queued', 'cloning', 'building', 'uploading'].includes(deployment.status)
  const isDeployed = deployment.status === 'deployed' && deployment.deployment_url

  return (
    <div className="border rounded-lg p-4">
      <div className="flex justify-between items-start mb-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className={`px-3 py-1 rounded-full text-sm font-semibold ${getStatusColor(deployment.status)}`}>
              {deployment.status}
            </span>
            {deployment.build_time_seconds && (
              <span className="text-sm text-gray-500">
                {deployment.build_time_seconds}s
              </span>
            )}
          </div>
          <p className="font-semibold">{deployment.commit_message || '无提交信息'}</p>
          <div className="flex items-center gap-3 text-sm text-gray-600 mt-1">
            <span>#{deployment.commit_sha.substring(0, 7)}</span>
            <span>•</span>
            <span>{deployment.branch}</span>
            <span>•</span>
            <span>{deployment.commit_author}</span>
          </div>
        </div>
        <div className="flex gap-2">
          {isDeployed && (
            <a
              href={deployment.deployment_url}
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
            >
              预览
            </a>
          )}
          <button
            onClick={() => setShowLogs(!showLogs)}
            className="px-3 py-1 text-sm border rounded hover:bg-gray-50"
          >
            {showLogs ? '隐藏日志' : '查看日志'}
          </button>
          {canCancel && onCancel && (
            <button
              onClick={() => onCancel(deployment.id)}
              className="px-3 py-1 text-sm border border-red-300 text-red-700 rounded hover:bg-red-50"
            >
              取消
            </button>
          )}
        </div>
      </div>

      {isDeployed && (
        <div className="mb-3 p-3 bg-green-50 border border-green-200 rounded-lg">
          <div className="text-sm space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-green-700 font-semibold">部署地址:</span>
              <a
                href={deployment.deployment_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline truncate"
              >
                {deployment.deployment_url}
              </a>
            </div>
            {deployment.cdn_url && deployment.cdn_url !== deployment.deployment_url && (
              <div className="flex items-center gap-2 text-xs text-gray-600">
                <span>CDN:</span>
                <span className="truncate">{deployment.cdn_url}</span>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="text-sm text-gray-500">
        {deployment.deployed_at ? (
          <span>部署于 {new Date(deployment.deployed_at).toLocaleString('zh-CN')}</span>
        ) : (
          <span>创建于 {new Date(deployment.created_at).toLocaleString('zh-CN')}</span>
        )}
      </div>

      {deployment.error_message && (
        <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
          <strong>错误:</strong> {deployment.error_message}
        </div>
      )}

      {showLogs && logsData && (
        <div className="mt-3 bg-gray-900 text-gray-100 rounded-lg p-4 font-mono text-sm max-h-96 overflow-y-auto">
          {logsData.logs ? (
            <pre className="whitespace-pre-wrap">{logsData.logs}</pre>
          ) : (
            <p className="text-gray-400">暂无日志...</p>
          )}
        </div>
      )}
    </div>
  )
}
