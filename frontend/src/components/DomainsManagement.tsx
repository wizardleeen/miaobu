import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'

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

  const copyToClipboard = async (text: string, fieldName: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedField(fieldName)
      setTimeout(() => setCopiedField(null), 2000)
    } catch (error) {
      console.error('Failed to copy:', error)
      alert('复制到剪贴板失败')
    }
  }

  const CopyButton = ({ text, fieldName, label }: { text: string; fieldName: string; label?: string }) => {
    const isCopied = copiedField === fieldName
    return (
      <button
        type="button"
        onClick={() => copyToClipboard(text, fieldName)}
        className={`px-3 py-1 text-xs rounded-lg transition-all ${
          isCopied
            ? 'bg-green-100 text-green-700 border border-green-300'
            : 'bg-gray-100 text-gray-700 border border-gray-300 hover:bg-gray-200'
        }`}
        title={`复制${label || '到剪贴板'}`}
      >
        {isCopied ? '✓ 已复制' : '📋 复制'}
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
      alert('✅ 部署已成功上线！变更将在约30秒内生效。')
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

    // Check DNS status
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
      alert('✅ 域名验证成功！SSL 证书将自动配置。')
      setShowInstructions(false)
      setSelectedDomain(null)
    } else {
      alert(`❌ 验证失败：${result.message}`)
    }
  }

  const handleCheckDNS = async (domainId: number) => {
    const status = await api.checkDomainDNS(domainId)
    setDnsStatus(status)
    alert('DNS 状态已更新。请查看下方状态信息。')
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
    alert(enabled ? '✅ 自动部署已启用' : '✅ 自动部署已禁用')
  }

  const handleSyncEdgeKV = async (domainId: number) => {
    try {
      await api.syncEdgeKV(domainId)
      queryClient.invalidateQueries({ queryKey: ['domains', projectId] })
      alert('✅ 边缘配置同步成功')
    } catch (error: any) {
      alert(`❌ 同步失败：${error.response?.data?.detail || error.message}`)
    }
  }

  const handleRefreshSSL = async (domainId: number) => {
    setRefreshingSSL(true)
    try {
      const result = await api.refreshSSLStatus(domainId)
      queryClient.invalidateQueries({ queryKey: ['domains', projectId] })

      if (result.is_https_ready) {
        alert('🔒 HTTPS 已就绪！您的网站现在可以通过 HTTPS 访问。')
      } else {
        const statusText = result.ssl_status === 'issuing' ? '签发中' :
                          result.ssl_status === 'verifying' ? '验证中' : '待处理'
        alert(`⏳ SSL 状态：${statusText}。证书仍在配置中。`)
      }
    } catch (error: any) {
      alert(`❌ 刷新 SSL 状态失败：${error.response?.data?.detail || error.message}`)
    } finally {
      setRefreshingSSL(false)
    }
  }

  if (isLoading) {
    return <div className="text-center py-4">加载域名列表...</div>
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold">自定义域名</h2>
          <p className="text-gray-600 mt-1">
            添加自定义域名，通过边缘加速访问您的部署
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowAddDomain(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          + 添加域名
        </button>
      </div>

      {/* Add Domain Modal */}
      {showAddDomain && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full">
            <h3 className="text-xl font-bold mb-4">添加自定义域名</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">域名</label>
                <input
                  type="text"
                  value={newDomain}
                  onChange={(e) => setNewDomain(e.target.value)}
                  placeholder="www.example.com"
                  className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-sm text-gray-500 mt-1">
                  输入您的域名（例如：www.example.com 或 blog.example.com）
                </p>
              </div>
              <div className="flex gap-2 justify-end">
                <button
                  type="button"
                  onClick={() => {
                    setShowAddDomain(false)
                    setNewDomain('')
                  }}
                  className="px-4 py-2 border rounded-lg hover:bg-gray-50"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={handleAddDomain}
                  disabled={!newDomain || createMutation.isPending}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
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
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 overflow-y-auto p-4">
          <div className="bg-white rounded-lg p-6 max-w-3xl w-full my-8">
            <h3 className="text-xl font-bold mb-4">
              DNS 配置：{selectedDomain.domain}
            </h3>

            {/* Verification Status */}
            <div
              className={`mb-6 p-4 rounded-lg ${
                selectedDomain.is_verified
                  ? 'bg-green-100 border border-green-300'
                  : 'bg-yellow-100 border border-yellow-300'
              }`}
            >
              <div className="flex items-center gap-2">
                {selectedDomain.is_verified ? (
                  <>
                    <span className="text-2xl">✅</span>
                    <div>
                      <div className="font-bold text-green-800">域名已验证</div>
                      <div className="text-sm text-green-700">
                        您的域名已验证并配置边缘加速
                      </div>
                    </div>
                  </>
                ) : (
                  <>
                    <span className="text-2xl">⏳</span>
                    <div>
                      <div className="font-bold text-yellow-800">待验证</div>
                      <div className="text-sm text-yellow-700">
                        请按照下方说明配置 DNS 记录，然后点击"验证域名"
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* DNS Configuration Steps */}
            <div className="space-y-4 mb-6">
              <h4 className="font-bold text-lg">DNS 配置步骤</h4>

              {/* Step 1: TXT Record for Verification */}
              {!selectedDomain.is_verified && (
                <div className="border rounded-lg p-4">
                  <div className="flex items-start gap-3">
                    <div className="flex-shrink-0 w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center font-bold">
                      1
                    </div>
                    <div className="flex-1">
                      <h5 className="font-bold mb-2">添加 TXT 记录以验证域名</h5>
                      <p className="text-sm text-gray-600 mb-3">
                        添加此 TXT 记录以验证域名所有权
                      </p>

                      <div className="bg-gray-50 p-3 rounded font-mono text-sm space-y-3">
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <span className="text-gray-600">类型：</span>{' '}
                            <span className="font-bold">TXT</span>
                          </div>
                          <div>
                            <span className="text-gray-600">TTL：</span> 300
                          </div>
                        </div>
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-gray-600">记录名称：</span>
                            <CopyButton
                              text={`_miaobu-verification.${selectedDomain.domain}`}
                              fieldName="txt-name"
                              label="TXT 记录名称"
                            />
                          </div>
                          <div className="bg-white p-2 rounded border break-all">
                            _miaobu-verification.{selectedDomain.domain}
                          </div>
                        </div>
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-gray-600">记录值：</span>
                            <CopyButton
                              text={selectedDomain.verification_token}
                              fieldName="txt-value"
                              label="TXT 记录值"
                            />
                          </div>
                          <div className="bg-white p-2 rounded border break-all">
                            {selectedDomain.verification_token}
                          </div>
                        </div>
                      </div>

                      <p className="text-sm text-gray-500 mt-2 italic">
                        💡 此记录用于验证您拥有该域名
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Step 2: CNAME Record */}
              <div className="border rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center font-bold">
                    {selectedDomain.is_verified ? '1' : '2'}
                  </div>
                  <div className="flex-1">
                    <h5 className="font-bold mb-2">添加 CNAME 记录</h5>
                    <p className="text-sm text-gray-600 mb-3">
                      将您的域名指向 Miaobu 边缘网络
                    </p>

                    <div className="bg-gray-50 p-3 rounded font-mono text-sm space-y-3">
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <span className="text-gray-600">类型：</span>{' '}
                          <span className="font-bold">CNAME</span>
                        </div>
                        <div>
                          <span className="text-gray-600">TTL：</span> 3600
                        </div>
                      </div>
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-gray-600">记录名称：</span>
                          <CopyButton
                            text={selectedDomain.domain}
                            fieldName="cname-name"
                            label="CNAME 记录名称"
                          />
                        </div>
                        <div className="bg-white p-2 rounded border break-all">
                          {selectedDomain.domain}
                        </div>
                      </div>
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-gray-600">记录值：</span>
                          <CopyButton
                            text={selectedDomain.cname_target || 'cname.metavm.tech'}
                            fieldName="cname-value"
                            label="CNAME 记录值"
                          />
                        </div>
                        <div className="bg-white p-2 rounded border break-all font-bold text-blue-600">
                          {selectedDomain.cname_target || 'cname.metavm.tech'}
                        </div>
                      </div>
                    </div>

                    <p className="text-sm text-gray-500 mt-2 italic">
                      💡 通过边缘网络路由流量以获得更好的性能和自动 SSL
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* DNS Status */}
            {dnsStatus && (
              <div className="mb-6 border rounded-lg p-4">
                <h4 className="font-bold mb-3">当前 DNS 状态</h4>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-600">TXT 记录：</span>{' '}
                    {dnsStatus.txt_verification?.verified ? '✅ 已找到' : '❌ 未找到'}
                  </div>
                  <div>
                    <span className="text-gray-600">CNAME 记录：</span>{' '}
                    {dnsStatus.cname_status?.verified ? '✅ 正确' : '⏳ 待处理'}
                  </div>
                </div>

                {dnsStatus.txt_verification && !dnsStatus.txt_verification.verified && (
                  <div className="mt-3 text-sm text-yellow-700 bg-yellow-50 p-3 rounded">
                    {dnsStatus.txt_verification.message}
                  </div>
                )}
              </div>
            )}

            {/* ESA SSL Status */}
            {selectedDomain.is_verified && (
              <div className="mb-6 border rounded-lg p-4 bg-blue-50">
                <h4 className="font-bold mb-2 flex items-center gap-2">
                  🔒 SSL 证书（自动配置）
                </h4>
                <p className="text-sm text-gray-700 mb-2">
                  SSL 证书将在域名验证后自动配置和管理。
                  HTTPS 将在域名验证后几分钟内可用。
                </p>
                <div className="grid grid-cols-2 gap-4 text-sm mt-3">
                  <div>
                    <span className="text-gray-600">边缘加速状态：</span>{' '}
                    <span
                      className={`font-medium ${
                        selectedDomain.esa_status === 'online'
                          ? 'text-green-600'
                          : 'text-yellow-600'
                      }`}
                    >
                      {selectedDomain.esa_status === 'online' ? '✅ 在线' : '⏳ 配置中'}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-600">HTTPS：</span>{' '}
                    {selectedDomain.ssl_status === 'active' ? '✅ 就绪' :
                     selectedDomain.ssl_status === 'issuing' ? '⏳ 签发中' :
                     selectedDomain.ssl_status === 'verifying' ? '⏳ 验证中' : '⏳ 待处理'}
                  </div>
                </div>

                {/* Refresh SSL Status Button (only show if not active) */}
                {selectedDomain.ssl_status !== 'active' && (
                  <div className="mt-3">
                    <button
                      type="button"
                      onClick={() => handleRefreshSSL(selectedDomain.id)}
                      disabled={refreshingSSL}
                      className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm"
                    >
                      {refreshingSSL ? '⏳ 检查中...' : '🔄 刷新 SSL 状态'}
                    </button>
                    <p className="text-xs text-gray-600 mt-2 text-center">
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
                className="px-4 py-2 border rounded-lg hover:bg-gray-50"
              >
                🔄 检查 DNS
              </button>
              {!selectedDomain.is_verified && (
                <button
                  type="button"
                  onClick={() => handleVerifyDomain(selectedDomain.id)}
                  disabled={verifyMutation.isPending}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                >
                  {verifyMutation.isPending ? '验证中...' : '✓ 验证域名'}
                </button>
              )}
              {selectedDomain.is_verified && (
                <button
                  type="button"
                  onClick={() => {
                    setShowInstructions(false)
                    handleShowDeployments(selectedDomain)
                  }}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  📦 管理部署
                </button>
              )}
              <button
                type="button"
                onClick={() => {
                  setShowInstructions(false)
                  setSelectedDomain(null)
                  setDnsStatus(null)
                }}
                className="px-4 py-2 border rounded-lg hover:bg-gray-50"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Deployments Modal */}
      {showDeployments && selectedDomain && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 overflow-y-auto p-4">
          <div className="bg-white rounded-lg p-6 max-w-3xl w-full my-8">
            <h3 className="text-xl font-bold mb-4">
              管理部署：{selectedDomain.domain}
            </h3>

            {/* Auto-Update Toggle */}
            <div className="mb-6 flex items-center justify-between p-4 bg-gray-50 rounded-lg border">
              <div>
                <div className="font-medium">自动部署</div>
                <div className="text-sm text-gray-600">
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
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              </label>
            </div>

            {/* Deployments List */}
            <div className="space-y-3 mb-6">
              <div className="flex items-center justify-between">
                <h4 className="font-bold">部署列表</h4>
                {!selectedDomain.edge_kv_synced && (
                  <button
                    type="button"
                    onClick={() => handleSyncEdgeKV(selectedDomain.id)}
                    className="px-3 py-1 text-sm border border-yellow-400 text-yellow-700 rounded-lg hover:bg-yellow-50"
                  >
                    🔄 同步边缘配置
                  </button>
                )}
              </div>

              {deployments?.deployments && deployments.deployments.length > 0 ? (
                deployments.deployments.map((dep: any) => (
                  <div
                    key={dep.id}
                    className={`border rounded-lg p-4 ${
                      dep.is_active ? 'border-green-500 bg-green-50' : 'hover:shadow-md'
                    } transition`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-mono text-sm font-bold">
                            {dep.commit_sha.slice(0, 7)}
                          </span>
                          {dep.is_active && (
                            <span className="px-2 py-1 bg-green-600 text-white text-xs rounded-full font-medium">
                              ✓ 在线
                            </span>
                          )}
                        </div>
                        <div className="text-sm text-gray-700">{dep.commit_message}</div>
                        <div className="text-xs text-gray-500 mt-1">
                          {dep.commit_author} • {new Date(dep.created_at).toLocaleString()} •{' '}
                          {dep.branch}
                        </div>
                      </div>
                      {!dep.is_active && (
                        <button
                          type="button"
                          onClick={() => handlePromoteDeployment(dep.id)}
                          disabled={promoteMutation.isPending}
                          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm"
                        >
                          {promoteMutation.isPending ? '上线中...' : '上线此部署'}
                        </button>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-8 border-2 border-dashed rounded-lg">
                  <p className="text-gray-600">暂无部署记录</p>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => {
                  setShowDeployments(false)
                  setSelectedDomain(null)
                }}
                className="px-4 py-2 border rounded-lg hover:bg-gray-50"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Domains List */}
      <div className="space-y-3">
        {domains && domains.length > 0 ? (
          domains.map((domain: any) => (
            <div key={domain.id} className="border rounded-lg p-4 hover:shadow-md transition">
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="font-mono font-bold text-lg">{domain.domain}</span>
                    {domain.is_verified ? (
                      <span className="px-2 py-1 bg-green-100 text-green-800 text-xs rounded-full font-medium">
                        ✓ 已验证
                      </span>
                    ) : (
                      <span className="px-2 py-1 bg-yellow-100 text-yellow-800 text-xs rounded-full font-medium">
                        ⏳ 待验证
                      </span>
                    )}
                    {/* SSL Status Badge */}
                    {domain.ssl_status === 'active' && (
                      <span className="px-2 py-1 bg-green-100 text-green-800 text-xs rounded-full font-medium">
                        🔒 HTTPS
                      </span>
                    )}
                    {domain.ssl_status === 'issuing' && (
                      <span className="px-2 py-1 bg-yellow-100 text-yellow-800 text-xs rounded-full font-medium">
                        ⏳ SSL 签发中
                      </span>
                    )}
                    {domain.ssl_status === 'verifying' && (
                      <span className="px-2 py-1 bg-yellow-100 text-yellow-800 text-xs rounded-full font-medium">
                        ⏳ SSL 验证中
                      </span>
                    )}
                    {domain.auto_update_enabled && (
                      <span className="px-2 py-1 bg-purple-100 text-purple-800 text-xs rounded-full font-medium">
                        🤖 自动部署
                      </span>
                    )}
                    {domain.edge_kv_synced ? (
                      <span className="px-2 py-1 bg-green-100 text-green-800 text-xs rounded-full font-medium">
                        ✓ 已同步
                      </span>
                    ) : (
                      <span className="px-2 py-1 bg-yellow-100 text-yellow-800 text-xs rounded-full font-medium">
                        ⏳ 同步中
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-4 mt-2 text-sm text-gray-600">
                    {domain.verified_at && (
                      <span>验证时间：{new Date(domain.verified_at).toLocaleDateString('zh-CN')}</span>
                    )}
                    {domain.active_deployment_id && (
                      <span>部署 #{domain.active_deployment_id}</span>
                    )}
                    <span className="text-xs">CNAME：{domain.cname_target || 'cname.metavm.tech'}</span>
                  </div>
                </div>
                <div className="flex gap-2">
                  {domain.is_verified ? (
                    <button
                      type="button"
                      onClick={() => handleShowDeployments(domain)}
                      className="px-3 py-2 border rounded-lg hover:bg-gray-50 text-sm"
                    >
                      📦 部署管理
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleShowInstructions(domain)}
                      className="px-3 py-2 border rounded-lg hover:bg-gray-50 text-sm"
                    >
                      🔧 配置 DNS
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => handleShowInstructions(domain)}
                    className="px-3 py-2 border rounded-lg hover:bg-gray-50 text-sm"
                  >
                    ⚙️ 配置
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (confirm(`确定要删除域名 ${domain.domain} 吗？`)) {
                        deleteMutation.mutate(domain.id)
                      }
                    }}
                    className="px-3 py-2 border border-red-300 text-red-600 rounded-lg hover:bg-red-50 text-sm"
                  >
                    🗑️ 删除
                  </button>
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="text-center py-12 border-2 border-dashed rounded-lg">
            <p className="text-gray-600 mb-4">暂无自定义域名</p>
            <button
              type="button"
              onClick={() => setShowAddDomain(true)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              添加您的第一个域名
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
