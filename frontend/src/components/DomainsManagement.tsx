import { useState, useCallback, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'
import {
  Copy,
  Check,
  CheckCircle2,
  Clock,
  Lock,
  RefreshCw,
  Wrench,
  Trash2,
  Repeat,
  AlertTriangle,
  Globe,
  Package,
  X,
  Lightbulb,
  Shield,
  Info,
} from 'lucide-react'

type ToastType = 'success' | 'error' | 'warning' | 'info'
interface Toast {
  id: number
  message: string
  type: ToastType
  leaving: boolean
}

interface DomainsManagementProps {
  projectId: number
}

export default function DomainsManagement({ projectId }: DomainsManagementProps) {
  const queryClient = useQueryClient()
  const [showAddDomain, setShowAddDomain] = useState(false)
  const [newDomain, setNewDomain] = useState('')
  const [selectedDomain, setSelectedDomain] = useState<any>(null)
  const [showInstructions, setShowInstructions] = useState(false)
  const [dnsStatus, setDnsStatus] = useState<any>(null)
  const [showDeployments, setShowDeployments] = useState(false)
  const [copiedField, setCopiedField] = useState<string | null>(null)
  const [refreshingSSL, setRefreshingSSL] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])
  const toastIdRef = useRef(0)

  const dismissToast = useCallback((id: number) => {
    setToasts(prev => prev.map(t => t.id === id ? { ...t, leaving: true } : t))
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 200)
  }, [])

  const toast = useCallback((message: string, type: ToastType = 'info') => {
    const id = ++toastIdRef.current
    setToasts(prev => [...prev, { id, message, type, leaving: false }])
    const duration = type === 'error' || type === 'warning' ? 6000 : 4000
    setTimeout(() => dismissToast(id), duration)
  }, [dismissToast])

  const copyToClipboard = async (text: string, fieldName: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedField(fieldName)
      setTimeout(() => setCopiedField(null), 2000)
    } catch (error) {
      console.error('Failed to copy:', error)
      toast('复制到剪贴板失败', 'error')
    }
  }

  const CopyButton = ({ text, fieldName, label }: { text: string; fieldName: string; label?: string }) => {
    const isCopied = copiedField === fieldName
    return (
      <button
        type="button"
        onClick={() => copyToClipboard(text, fieldName)}
        className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-md transition-all ${
          isCopied
            ? 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/20'
            : 'bg-[--bg-tertiary] text-[--text-secondary] border border-[--border-primary] hover:bg-[--bg-secondary]'
        }`}
        title={`复制${label || '到剪贴板'}`}
      >
        {isCopied ? <Check size={11} /> : <Copy size={11} />}
        {isCopied ? '已复制' : '复制'}
      </button>
    )
  }

  const { data: domains, isLoading } = useQuery({
    queryKey: ['domains', projectId],
    queryFn: () => api.listDomains(projectId),
  })

  const { data: deployments } = useQuery({
    queryKey: ['domain-deployments', selectedDomain?.id],
    queryFn: () => api.getDomainDeployments(selectedDomain.id),
    enabled: !!selectedDomain && showDeployments,
  })

  const createMutation = useMutation({
    mutationFn: (domain: string) => api.createDomain(projectId, domain),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['domains', projectId] })
      setShowAddDomain(false)
      setNewDomain('')
    },
  })

  const verifyMutation = useMutation({
    mutationFn: (domainId: number) => api.verifyDomain(domainId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['domains', projectId] })
    },
  })

  const promoteMutation = useMutation({
    mutationFn: ({ domainId, deploymentId }: { domainId: number; deploymentId: number }) =>
      api.promoteDeployment(domainId, deploymentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['domains', projectId] })
      queryClient.invalidateQueries({ queryKey: ['domain-deployments', selectedDomain?.id] })
      toast('部署已成功上线！变更将在约30秒内生效。', 'success')
    },
  })

  const updateSettingsMutation = useMutation({
    mutationFn: ({ domainId, settings }: { domainId: number; settings: any }) =>
      api.updateDomainSettings(domainId, settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['domains', projectId] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (domainId: number) => api.deleteDomain(domainId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['domains', projectId] })
      setSelectedDomain(null)
      setShowInstructions(false)
      setShowDeployments(false)
    },
  })

  const handleAddDomain = () => {
    if (!newDomain) return
    createMutation.mutate(newDomain)
  }

  const handleShowInstructions = async (domain: any) => {
    setSelectedDomain(domain)
    setShowInstructions(true)
    setShowDeployments(false)

    try {
      const dnsCheck = await api.checkDomainDNS(domain.id)
      setDnsStatus(dnsCheck)
    } catch (error) {
      console.error('Failed to check DNS:', error)
    }
  }

  const handleShowDeployments = async (domain: any) => {
    setSelectedDomain(domain)
    setShowDeployments(true)
    setShowInstructions(false)
  }

  const handleVerifyDomain = async (domainId: number) => {
    const result = await verifyMutation.mutateAsync(domainId)

    if (result.verified) {
      if (result.icp_required) {
        toast(result.message, 'warning')
      } else {
        toast('域名验证成功！SSL 证书将自动配置。', 'success')
      }
      setShowInstructions(false)
      setSelectedDomain(null)
    } else {
      toast(`验证失败：${result.message}`, 'error')
    }
  }

  const handleCheckDNS = async (domainId: number) => {
    const status = await api.checkDomainDNS(domainId)
    setDnsStatus(status)
    toast('DNS 状态已更新。请查看下方状态信息。', 'info')
  }

  const handlePromoteDeployment = (deploymentId: number) => {
    if (!selectedDomain) return
    if (!confirm('确定要将此部署上线到生产环境吗？')) return

    promoteMutation.mutate({ domainId: selectedDomain.id, deploymentId })
  }

  const handleToggleAutoUpdate = async (domainId: number, enabled: boolean) => {
    if (!confirm(
      enabled
        ? '确定要启用自动部署吗？新的成功部署将自动在此域名上线。'
        : '确定要禁用自动部署吗？您将需要手动上线部署。'
    )) return

    await updateSettingsMutation.mutateAsync({
      domainId,
      settings: { auto_update_enabled: enabled },
    })
    setSelectedDomain((prev: any) => prev ? { ...prev, auto_update_enabled: enabled } : prev)
    toast(enabled ? '自动部署已启用' : '自动部署已禁用', 'success')
  }

  const handleSyncEdgeKV = async (domainId: number) => {
    try {
      await api.syncEdgeKV(domainId)
      queryClient.invalidateQueries({ queryKey: ['domains', projectId] })
      toast('边缘配置同步成功', 'success')
    } catch (error: any) {
      toast(`同步失败：${error.response?.data?.detail || error.message}`, 'error')
    }
  }

  const handleRefreshSSL = async (domainId: number) => {
    setRefreshingSSL(true)
    try {
      const result = await api.refreshSSLStatus(domainId)
      queryClient.invalidateQueries({ queryKey: ['domains', projectId] })

      if (result.is_https_ready) {
        toast('HTTPS 已就绪！您的网站现在可以通过 HTTPS 访问。', 'success')
      } else {
        const statusText = result.ssl_status === 'issuing' ? '签发中' :
                          result.ssl_status === 'verifying' ? '验证中' : '待处理'
        toast(`SSL 状态：${statusText}。证书仍在配置中。`, 'info')
      }
    } catch (error: any) {
      toast(`刷新 SSL 状态失败：${error.response?.data?.detail || error.message}`, 'error')
    } finally {
      setRefreshingSSL(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-4">
        <div className="w-5 h-5 border-2 border-[--accent] border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-[--text-primary]">自定义域名</h2>
          <p className="text-xs text-[--text-secondary] mt-0.5">
            添加自定义域名，通过边缘加速访问您的部署
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowAddDomain(true)}
          className="btn-primary text-sm"
        >
          添加域名
        </button>
      </div>

      {/* Add Domain Modal */}
      {showAddDomain && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
          <div className="card p-5 max-w-md w-full mx-4 shadow-xl animate-slide-in">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold text-[--text-primary]">添加自定义域名</h3>
              <button
                type="button"
                onClick={() => { setShowAddDomain(false); setNewDomain('') }}
                className="p-1 rounded-lg hover:bg-[--bg-tertiary] text-[--text-tertiary]"
              >
                <X size={16} />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[--text-primary] mb-1">域名</label>
                <input
                  type="text"
                  value={newDomain}
                  onChange={(e) => setNewDomain(e.target.value)}
                  placeholder="www.example.com"
                  className="input"
                />
                <p className="text-xs text-[--text-tertiary] mt-1">
                  输入您的域名（例如：www.example.com 或 blog.example.com）
                </p>
              </div>
              <div className="flex gap-2 justify-end">
                <button
                  type="button"
                  onClick={() => { setShowAddDomain(false); setNewDomain('') }}
                  className="btn-secondary text-sm"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={handleAddDomain}
                  disabled={!newDomain || createMutation.isPending}
                  className="btn-primary text-sm"
                >
                  {createMutation.isPending ? '添加中...' : '添加域名'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* DNS Instructions Modal */}
      {showInstructions && selectedDomain && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-start justify-center z-50 overflow-y-auto p-4 animate-fade-in">
          <div className="card p-5 max-w-3xl w-full my-8 shadow-xl animate-slide-in">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-base font-semibold text-[--text-primary]">
                DNS 配置：{selectedDomain.domain}
              </h3>
              <button
                type="button"
                onClick={() => { setShowInstructions(false); setSelectedDomain(null); setDnsStatus(null) }}
                className="p-1 rounded-lg hover:bg-[--bg-tertiary] text-[--text-tertiary]"
              >
                <X size={16} />
              </button>
            </div>

            {/* Verification Status */}
            <div className={`mb-5 p-4 rounded-lg border ${
              selectedDomain.is_verified
                ? 'bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20'
                : 'bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/20'
            }`}>
              <div className="flex items-center gap-3">
                {selectedDomain.is_verified ? (
                  <>
                    <CheckCircle2 size={22} className="text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
                    <div>
                      <div className="font-medium text-emerald-800 dark:text-emerald-300 text-sm">域名已验证</div>
                      <div className="text-xs text-emerald-700 dark:text-emerald-400/80">
                        您的域名已验证并配置边缘加速
                      </div>
                    </div>
                  </>
                ) : (
                  <>
                    <Clock size={22} className="text-amber-600 dark:text-amber-400 flex-shrink-0" />
                    <div>
                      <div className="font-medium text-amber-800 dark:text-amber-300 text-sm">待验证</div>
                      <div className="text-xs text-amber-700 dark:text-amber-400/80">
                        请按照下方说明配置 DNS 记录，然后点击"验证域名"
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* DNS Configuration Steps */}
            <div className="space-y-4 mb-5">
              <h4 className="text-sm font-semibold text-[--text-primary]">DNS 配置步骤</h4>

              {/* Step 1: TXT Record for Verification */}
              {!selectedDomain.is_verified && (
                <div className="border border-[--border-primary] rounded-lg p-4">
                  <div className="flex items-start gap-3">
                    <div className="flex-shrink-0 w-7 h-7 bg-[--accent] text-white rounded-full flex items-center justify-center text-xs font-bold">
                      1
                    </div>
                    <div className="flex-1 min-w-0">
                      <h5 className="text-sm font-medium text-[--text-primary] mb-1">添加 TXT 记录以验证域名</h5>
                      <p className="text-xs text-[--text-secondary] mb-3">
                        添加此 TXT 记录以验证域名所有权
                      </p>

                      <div className="bg-[--bg-tertiary] p-3 rounded-lg font-mono text-xs space-y-3">
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <span className="text-[--text-tertiary]">类型：</span>{' '}
                            <span className="font-bold text-[--text-primary]">TXT</span>
                          </div>
                          <div>
                            <span className="text-[--text-tertiary]">TTL：</span>
                            <span className="text-[--text-primary]"> 300</span>
                          </div>
                        </div>
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-[--text-tertiary]">记录名称：</span>
                            <CopyButton
                              text={`_miaobu-verification.${selectedDomain.domain}`}
                              fieldName="txt-name"
                              label="TXT 记录名称"
                            />
                          </div>
                          <div className="bg-[--bg-elevated] p-2 rounded border border-[--border-primary] break-all text-[--text-primary]">
                            _miaobu-verification.{selectedDomain.domain}
                          </div>
                        </div>
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-[--text-tertiary]">记录值：</span>
                            <CopyButton
                              text={selectedDomain.verification_token}
                              fieldName="txt-value"
                              label="TXT 记录值"
                            />
                          </div>
                          <div className="bg-[--bg-elevated] p-2 rounded border border-[--border-primary] break-all text-[--text-primary]">
                            {selectedDomain.verification_token}
                          </div>
                        </div>
                      </div>

                      <p className="text-xs text-[--text-tertiary] mt-2 flex items-center gap-1.5">
                        <Lightbulb size={12} />
                        此记录用于验证您拥有该域名
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Step 2: CNAME Record */}
              <div className="border border-[--border-primary] rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 w-7 h-7 bg-[--accent] text-white rounded-full flex items-center justify-center text-xs font-bold">
                    {selectedDomain.is_verified ? '1' : '2'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h5 className="text-sm font-medium text-[--text-primary] mb-1">添加 CNAME 记录</h5>
                    <p className="text-xs text-[--text-secondary] mb-3">
                      将您的域名指向 Miaobu 边缘网络
                    </p>

                    <div className="bg-[--bg-tertiary] p-3 rounded-lg font-mono text-xs space-y-3">
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <span className="text-[--text-tertiary]">类型：</span>{' '}
                          <span className="font-bold text-[--text-primary]">CNAME</span>
                        </div>
                        <div>
                          <span className="text-[--text-tertiary]">TTL：</span>
                          <span className="text-[--text-primary]"> 3600</span>
                        </div>
                      </div>
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-[--text-tertiary]">记录名称：</span>
                          <CopyButton
                            text={selectedDomain.domain}
                            fieldName="cname-name"
                            label="CNAME 记录名称"
                          />
                        </div>
                        <div className="bg-[--bg-elevated] p-2 rounded border border-[--border-primary] break-all text-[--text-primary]">
                          {selectedDomain.domain}
                        </div>
                      </div>
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-[--text-tertiary]">记录值：</span>
                          <CopyButton
                            text={selectedDomain.cname_target || 'cname.metavm.tech'}
                            fieldName="cname-value"
                            label="CNAME 记录值"
                          />
                        </div>
                        <div className="bg-[--bg-elevated] p-2 rounded border border-[--border-primary] break-all font-bold text-[--accent]">
                          {selectedDomain.cname_target || 'cname.metavm.tech'}
                        </div>
                      </div>
                    </div>

                    <p className="text-xs text-[--text-tertiary] mt-2 flex items-center gap-1.5">
                      <Lightbulb size={12} />
                      通过边缘网络路由流量以获得更好的性能和自动 SSL
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* DNS Status */}
            {dnsStatus && (
              <div className="mb-5 border border-[--border-primary] rounded-lg p-4">
                <h4 className="text-sm font-medium text-[--text-primary] mb-3">当前 DNS 状态</h4>
                <div className="grid grid-cols-2 gap-4 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="text-[--text-secondary]">TXT 记录：</span>
                    {dnsStatus.txt_verification?.verified ? (
                      <span className="badge-success"><CheckCircle2 size={11} />已找到</span>
                    ) : (
                      <span className="badge-error"><AlertTriangle size={11} />未找到</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[--text-secondary]">CNAME 记录：</span>
                    {dnsStatus.cname_status?.verified ? (
                      <span className="badge-success"><CheckCircle2 size={11} />正确</span>
                    ) : (
                      <span className="badge-warning"><Clock size={11} />待处理</span>
                    )}
                  </div>
                </div>

                {dnsStatus.txt_verification && !dnsStatus.txt_verification.verified && (
                  <div className="mt-3 text-xs p-2.5 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-lg text-amber-700 dark:text-amber-400">
                    {dnsStatus.txt_verification.message}
                  </div>
                )}
              </div>
            )}

            {/* ESA SSL Status */}
            {selectedDomain.is_verified && (
              <div className="mb-5 border border-[--border-primary] rounded-lg p-4 bg-[--accent-bg]">
                <h4 className="text-sm font-medium text-[--text-primary] mb-2 flex items-center gap-2">
                  <Lock size={14} />
                  SSL 证书（自动配置）
                </h4>
                <p className="text-xs text-[--text-secondary] mb-3">
                  SSL 证书将在域名验证后自动配置和管理。HTTPS 将在域名验证后几分钟内可用。
                </p>
                {selectedDomain.esa_status === 'pending' && (
                  <div className="mb-3 p-2.5 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-lg text-red-700 dark:text-red-400 text-xs flex items-start gap-2">
                    <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="font-medium">需要 ICP 备案</div>
                      <div className="mt-0.5">该域名需要完成 ICP 备案后才能正常使用。请前往 <a href="https://beian.aliyun.com" target="_blank" rel="noopener noreferrer" className="underline font-medium">阿里云备案系统</a> 完成备案，备案通过后 SSL 证书将自动签发。</div>
                    </div>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-4 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="text-[--text-secondary]">边缘加速状态：</span>
                    {selectedDomain.esa_status === 'online' ? (
                      <span className="badge-success"><CheckCircle2 size={11} />在线</span>
                    ) : selectedDomain.esa_status === 'pending' ? (
                      <span className="badge-error"><AlertTriangle size={11} />需要备案</span>
                    ) : (
                      <span className="badge-warning"><Clock size={11} />配置中</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[--text-secondary]">HTTPS：</span>
                    {selectedDomain.ssl_status === 'active' ? (
                      <span className="badge-success"><Shield size={11} />就绪</span>
                    ) : selectedDomain.ssl_status === 'issuing' ? (
                      <span className="badge-warning"><Clock size={11} />签发中</span>
                    ) : selectedDomain.ssl_status === 'verifying' ? (
                      <span className="badge-warning"><Clock size={11} />验证中</span>
                    ) : (
                      <span className="badge-warning"><Clock size={11} />待处理</span>
                    )}
                  </div>
                </div>

                {selectedDomain.ssl_status !== 'active' && (
                  <div className="mt-3">
                    <button
                      type="button"
                      onClick={() => handleRefreshSSL(selectedDomain.id)}
                      disabled={refreshingSSL}
                      className="btn-primary text-xs w-full inline-flex items-center justify-center gap-1.5"
                    >
                      <RefreshCw size={12} className={refreshingSSL ? 'animate-spin' : ''} />
                      {refreshingSSL ? '检查中...' : '刷新 SSL 状态'}
                    </button>
                    <p className="text-xs text-[--text-tertiary] mt-2 text-center">
                      SSL 证书配置通常需要 5-30 分钟
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-2 justify-end flex-wrap">
              <button
                type="button"
                onClick={() => handleCheckDNS(selectedDomain.id)}
                className="btn-secondary text-xs inline-flex items-center gap-1.5"
              >
                <RefreshCw size={12} />
                检查 DNS
              </button>
              {!selectedDomain.is_verified && (
                <button
                  type="button"
                  onClick={() => handleVerifyDomain(selectedDomain.id)}
                  disabled={verifyMutation.isPending}
                  className="px-3 py-1.5 bg-emerald-600 text-white text-xs rounded-lg hover:bg-emerald-700 disabled:opacity-50 transition-colors inline-flex items-center gap-1.5 font-medium"
                >
                  <Check size={12} />
                  {verifyMutation.isPending ? '验证中...' : '验证域名'}
                </button>
              )}
              {selectedDomain.is_verified && (
                <button
                  type="button"
                  onClick={() => {
                    setShowInstructions(false)
                    handleShowDeployments(selectedDomain)
                  }}
                  className="btn-primary text-xs inline-flex items-center gap-1.5"
                >
                  <Package size={12} />
                  管理部署
                </button>
              )}
              <button
                type="button"
                onClick={() => { setShowInstructions(false); setSelectedDomain(null); setDnsStatus(null) }}
                className="btn-secondary text-xs"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Deployments Modal */}
      {showDeployments && selectedDomain && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-start justify-center z-50 overflow-y-auto p-4 animate-fade-in">
          <div className="card p-5 max-w-3xl w-full my-8 shadow-xl animate-slide-in">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-base font-semibold text-[--text-primary]">
                管理部署：{selectedDomain.domain}
              </h3>
              <button
                type="button"
                onClick={() => { setShowDeployments(false); setSelectedDomain(null) }}
                className="p-1 rounded-lg hover:bg-[--bg-tertiary] text-[--text-tertiary]"
              >
                <X size={16} />
              </button>
            </div>

            {/* Auto-Update Toggle */}
            <div className="mb-5 flex items-center justify-between p-4 bg-[--bg-tertiary] rounded-lg border border-[--border-primary]">
              <div>
                <div className="text-sm font-medium text-[--text-primary]">自动部署</div>
                <div className="text-xs text-[--text-secondary]">
                  自动将新的成功构建部署到此域名
                </div>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={selectedDomain.auto_update_enabled || false}
                  onChange={(e) => handleToggleAutoUpdate(selectedDomain.id, e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-10 h-5 bg-[--border-secondary] peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-[--accent] rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-[--accent]" />
              </label>
            </div>

            {/* Deployments List */}
            <div className="space-y-3 mb-5">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-medium text-[--text-primary]">部署列表</h4>
                {!selectedDomain.edge_kv_synced && (
                  <button
                    type="button"
                    onClick={() => handleSyncEdgeKV(selectedDomain.id)}
                    className="text-xs px-2.5 py-1 border border-amber-300 dark:border-amber-500/30 text-amber-700 dark:text-amber-400 rounded-lg hover:bg-amber-50 dark:hover:bg-amber-500/10 transition-colors inline-flex items-center gap-1"
                  >
                    <RefreshCw size={11} />
                    同步边缘配置
                  </button>
                )}
              </div>

              {deployments?.deployments && deployments.deployments.length > 0 ? (
                deployments.deployments.map((dep: any) => (
                  <div
                    key={dep.id}
                    className={`border rounded-lg p-4 transition-colors ${
                      dep.is_active
                        ? 'border-emerald-300 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/5'
                        : 'border-[--border-primary] hover:border-[--accent]/30'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-mono text-xs font-bold text-[--text-primary]">
                            {dep.commit_sha.slice(0, 7)}
                          </span>
                          {dep.is_active && (
                            <span className="badge-success">
                              <Check size={10} />
                              在线
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-[--text-primary] truncate">{dep.commit_message}</div>
                        <div className="text-xs text-[--text-tertiary] mt-0.5">
                          {dep.commit_author} / {new Date(dep.created_at).toLocaleString()} / {dep.branch}
                        </div>
                      </div>
                      {!dep.is_active && (
                        <button
                          type="button"
                          onClick={() => handlePromoteDeployment(dep.id)}
                          disabled={promoteMutation.isPending}
                          className="btn-primary text-xs ml-4 flex-shrink-0"
                        >
                          {promoteMutation.isPending ? '上线中...' : '上线此部署'}
                        </button>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-8 border-2 border-dashed border-[--border-primary] rounded-lg">
                  <p className="text-xs text-[--text-secondary]">暂无部署记录</p>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => { setShowDeployments(false); setSelectedDomain(null) }}
                className="btn-secondary text-xs"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast Notifications */}
      {toasts.length > 0 && (
        <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 max-w-sm">
          {toasts.map((t) => {
            const styles = {
              success: {
                bg: 'bg-emerald-50 dark:bg-emerald-950 border-emerald-200 dark:border-emerald-800',
                text: 'text-emerald-800 dark:text-emerald-200',
                icon: <CheckCircle2 size={16} className="text-emerald-500 dark:text-emerald-400 flex-shrink-0" />,
              },
              error: {
                bg: 'bg-red-50 dark:bg-red-950 border-red-200 dark:border-red-800',
                text: 'text-red-800 dark:text-red-200',
                icon: <AlertTriangle size={16} className="text-red-500 dark:text-red-400 flex-shrink-0" />,
              },
              warning: {
                bg: 'bg-amber-50 dark:bg-amber-950 border-amber-200 dark:border-amber-800',
                text: 'text-amber-800 dark:text-amber-200',
                icon: <AlertTriangle size={16} className="text-amber-500 dark:text-amber-400 flex-shrink-0" />,
              },
              info: {
                bg: 'bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800',
                text: 'text-blue-800 dark:text-blue-200',
                icon: <Info size={16} className="text-blue-500 dark:text-blue-400 flex-shrink-0" />,
              },
            }[t.type]
            return (
              <div
                key={t.id}
                className={`${styles.bg} ${t.leaving ? 'animate-toast-out' : 'animate-toast-in'} border rounded-lg p-3 shadow-lg flex items-start gap-2.5`}
              >
                {styles.icon}
                <span className={`${styles.text} text-sm leading-snug flex-1`}>{t.message}</span>
                <button
                  type="button"
                  onClick={() => dismissToast(t.id)}
                  className={`${styles.text} opacity-50 hover:opacity-100 flex-shrink-0 mt-0.5`}
                >
                  <X size={14} />
                </button>
              </div>
            )
          })}
        </div>
      )}

      {/* Domains List */}
      <div className="space-y-3">
        {domains && domains.length > 0 ? (
          domains.map((domain: any) => (
            <div key={domain.id} className="border border-[--border-primary] rounded-lg p-4 hover:border-[--accent]/30 transition-colors">
              <div className="flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Globe size={14} className="text-[--text-tertiary] flex-shrink-0" />
                    <span className="font-mono font-semibold text-sm text-[--text-primary]">{domain.domain}</span>
                    {domain.is_verified ? (
                      <span className="badge-success"><CheckCircle2 size={11} />已验证</span>
                    ) : (
                      <span className="badge-warning"><Clock size={11} />待验证</span>
                    )}
                    {domain.is_verified && domain.esa_status === 'pending' && (
                      <span className="badge-error"><AlertTriangle size={10} />需要 ICP 备案</span>
                    )}
                    {domain.ssl_status === 'active' && (
                      <span className="badge-success"><Lock size={10} />HTTPS</span>
                    )}
                    {(domain.ssl_status === 'issuing' || domain.ssl_status === 'verifying') && (
                      <span className="badge-warning"><Clock size={10} />SSL {domain.ssl_status === 'issuing' ? '签发中' : '验证中'}</span>
                    )}
                    {domain.auto_update_enabled && (
                      <span className="badge-info"><Repeat size={10} />自动部署</span>
                    )}
                    {domain.edge_kv_synced ? (
                      <span className="badge-success"><Check size={10} />已同步</span>
                    ) : (
                      <span className="badge-warning"><Clock size={10} />同步中</span>
                    )}
                  </div>
                  <div className="flex items-center gap-4 mt-1.5 text-xs text-[--text-tertiary]">
                    {domain.verified_at && (
                      <span>验证时间：{new Date(domain.verified_at).toLocaleDateString('zh-CN')}</span>
                    )}
                    {domain.active_deployment_id && (
                      <span>部署 #{domain.active_deployment_id}</span>
                    )}
                    <span>CNAME：{domain.cname_target || 'cname.metavm.tech'}</span>
                  </div>
                </div>
                <div className="flex gap-1.5 ml-4 flex-shrink-0">
                  {domain.is_verified ? (
                    <button
                      type="button"
                      onClick={() => handleShowDeployments(domain)}
                      className="btn-secondary text-xs py-1 px-2.5 inline-flex items-center gap-1"
                    >
                      <Package size={12} />
                      部署管理
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleShowInstructions(domain)}
                      className="btn-secondary text-xs py-1 px-2.5 inline-flex items-center gap-1"
                    >
                      <Wrench size={12} />
                      配置 DNS
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => handleShowInstructions(domain)}
                    className="btn-secondary text-xs py-1 px-2.5 inline-flex items-center gap-1"
                  >
                    <Wrench size={12} />
                    配置
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (confirm(`确定要删除域名 ${domain.domain} 吗？`)) {
                        deleteMutation.mutate(domain.id)
                      }
                    }}
                    className="p-1.5 rounded-lg border border-red-200 dark:border-red-500/20 text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                    title="删除"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="text-center py-10 border-2 border-dashed border-[--border-primary] rounded-lg">
            <Globe size={28} className="mx-auto mb-3 text-[--text-tertiary]" />
            <p className="text-sm text-[--text-secondary] mb-4">暂无自定义域名</p>
            <button
              type="button"
              onClick={() => setShowAddDomain(true)}
              className="btn-primary text-sm"
            >
              添加您的第一个域名
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
