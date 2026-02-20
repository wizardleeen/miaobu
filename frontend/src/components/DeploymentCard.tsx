import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../services/api'
import { ExternalLink, ChevronDown, ChevronUp, XCircle, RotateCcw } from 'lucide-react'

interface Deployment {
  id: number
  status: string
  commit_sha: string
  commit_message: string
  commit_author: string
  branch: string
  is_staging?: boolean
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
  activeDeploymentId?: number | null
  stagingDeploymentId?: number | null
  isRollbackDisabled?: boolean
  onCancel?: (id: number) => void
  onRollback?: (id: number) => void
}

export default function DeploymentCard({
  deployment,
  activeDeploymentId,
  stagingDeploymentId,
  isRollbackDisabled,
  onCancel,
  onRollback,
}: DeploymentCardProps) {
  const [showLogs, setShowLogs] = useState(false)
  const [showRollbackConfirm, setShowRollbackConfirm] = useState(false)

  const { data: logsData } = useQuery({
    queryKey: ['deployment-logs', deployment.id],
    queryFn: () => api.getDeploymentLogs(deployment.id),
    enabled: showLogs,
    refetchInterval: ['queued', 'cloning', 'building', 'uploading', 'deploying'].includes(deployment.status) ? 2000 : false,
  })

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'deployed':
        return 'badge-success'
      case 'failed':
      case 'cancelled':
        return 'badge-error'
      case 'purged':
        return 'badge-neutral'
      case 'queued':
      case 'cloning':
      case 'building':
      case 'uploading':
      case 'deploying':
        return 'badge-warning'
      default:
        return 'badge-neutral'
    }
  }

  const getStatusDot = (status: string) => {
    const isActive = ['queued', 'cloning', 'building', 'uploading', 'deploying'].includes(status)
    const color = status === 'deployed' ? 'bg-emerald-500' :
      ['failed', 'cancelled'].includes(status) ? 'bg-red-500' :
      isActive ? 'bg-amber-500' : 'bg-gray-400'
    return (
      <span className={`w-2 h-2 rounded-full ${color} ${isActive ? 'animate-pulse-dot' : ''}`} />
    )
  }

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      queued: '排队中',
      cloning: '克隆中',
      building: '构建中',
      uploading: '上传中',
      deploying: '部署中',
      deployed: '已部署',
      failed: '失败',
      cancelled: '已取消',
      purged: '已清理',
    }
    return labels[status] || status
  }

  const canCancel = ['queued', 'cloning', 'building', 'uploading', 'deploying'].includes(deployment.status)
  const isDeployed = deployment.status === 'deployed' && deployment.deployment_url
  const isActive = deployment.is_staging
    ? stagingDeploymentId === deployment.id
    : activeDeploymentId === deployment.id
  const canRollback = deployment.status === 'deployed' && !isActive && onRollback

  return (
    <div className="py-4 first:pt-0 last:pb-0">
      <div className="flex justify-between items-start">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <span className={getStatusBadge(deployment.status)}>
              {getStatusDot(deployment.status)}
              {getStatusLabel(deployment.status)}
            </span>
            {deployment.is_staging && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-purple-100 text-purple-700 dark:bg-purple-500/20 dark:text-purple-400 border border-purple-200 dark:border-purple-500/30">
                Staging
              </span>
            )}
            {isActive && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/30">
                当前
              </span>
            )}
            {deployment.build_time_seconds && (
              <span className="text-xs text-[--text-tertiary]">
                {deployment.build_time_seconds}s
              </span>
            )}
          </div>
          <p className="text-sm font-medium text-[--text-primary] truncate">
            {deployment.commit_message || '无提交信息'}
          </p>
          <div className="flex items-center gap-2 text-xs text-[--text-tertiary] mt-1">
            <span className="font-mono">#{deployment.commit_sha.substring(0, 7)}</span>
            <span className="text-[--border-secondary]">/</span>
            <span>{deployment.branch}</span>
            <span className="text-[--border-secondary]">/</span>
            <span>{deployment.commit_author}</span>
          </div>
        </div>
        <div className="flex gap-1.5 ml-4 shrink-0">
          {isDeployed && (
            <a
              href={deployment.deployment_url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary text-xs px-2.5 py-1.5 flex items-center gap-1"
            >
              <ExternalLink size={12} />
              预览
            </a>
          )}
          {canRollback && (
            <button
              onClick={() => setShowRollbackConfirm(true)}
              disabled={isRollbackDisabled}
              className="btn-secondary text-xs px-2.5 py-1.5 flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RotateCcw size={12} />
              回滚
            </button>
          )}
          <button
            onClick={() => setShowLogs(!showLogs)}
            className="btn-secondary text-xs px-2.5 py-1.5 flex items-center gap-1"
          >
            {showLogs ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            {showLogs ? '隐藏日志' : '日志'}
          </button>
          {canCancel && onCancel && (
            <button
              onClick={() => onCancel(deployment.id)}
              className="btn-secondary text-xs px-2.5 py-1.5 text-red-600 dark:text-red-400 border-red-200 dark:border-red-500/30 hover:bg-red-50 dark:hover:bg-red-500/10"
            >
              取消
            </button>
          )}
        </div>
      </div>

      {showRollbackConfirm && (
        <div className="mt-3 p-3 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-lg">
          <p className="text-sm text-amber-800 dark:text-amber-300 mb-2">
            确定要回滚到此部署吗？当前版本将被替换。
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => {
                setShowRollbackConfirm(false)
                onRollback?.(deployment.id)
              }}
              className="btn-primary text-xs px-3 py-1.5 bg-amber-600 hover:bg-amber-700 border-amber-600"
            >
              确认回滚
            </button>
            <button
              onClick={() => setShowRollbackConfirm(false)}
              className="btn-secondary text-xs px-3 py-1.5"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {isDeployed && (
        <div className="mt-3 p-2.5 bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 rounded-lg">
          <div className="text-sm space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-xs text-emerald-700 dark:text-emerald-400 font-medium">部署地址:</span>
              <a
                href={deployment.deployment_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent hover:text-[--accent-hover] text-xs truncate inline-flex items-center gap-1"
              >
                {deployment.deployment_url}
                <ExternalLink size={10} />
              </a>
            </div>
            {deployment.cdn_url && deployment.cdn_url !== deployment.deployment_url && (
              <div className="flex items-center gap-2 text-xs text-[--text-tertiary]">
                <span>CDN:</span>
                <span className="truncate">{deployment.cdn_url}</span>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="text-xs text-[--text-tertiary] mt-2">
        {deployment.deployed_at ? (
          <span>部署于 {new Date(deployment.deployed_at).toLocaleString('zh-CN')}</span>
        ) : (
          <span>创建于 {new Date(deployment.created_at).toLocaleString('zh-CN')}</span>
        )}
      </div>

      {deployment.error_message && (
        <div className="mt-3 p-3 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-lg text-sm flex items-start gap-2">
          <XCircle size={16} className="text-red-500 mt-0.5 shrink-0" />
          <span className="text-red-700 dark:text-red-400">{deployment.error_message}</span>
        </div>
      )}

      {showLogs && logsData && (
        <div className="mt-3 bg-[#0d1117] text-gray-300 rounded-lg p-4 font-mono text-xs max-h-96 overflow-y-auto border border-[#30363d]">
          {logsData.logs ? (
            <pre className="whitespace-pre-wrap">{logsData.logs}</pre>
          ) : (
            <p className="text-gray-500">暂无日志...</p>
          )}
        </div>
      )}
    </div>
  )
}
