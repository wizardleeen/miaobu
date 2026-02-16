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
      alert('✅ Deployment promoted successfully! Changes will be live in ~30 seconds.')
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
      alert('✅ Domain verified successfully! SSL certificate will be provisioned automatically.')
      setShowInstructions(false)
      setSelectedDomain(null)
    } else {
      alert(`❌ Verification failed: ${result.message}`)
    }
  }

  const handleCheckDNS = async (domainId: number) => {
    const status = await api.checkDomainDNS(domainId)
    setDnsStatus(status)
    alert('DNS status updated. Check the status below.')
  }

  const handlePromoteDeployment = (deploymentId: number) => {
    if (!selectedDomain) return
    if (!confirm('Promote this deployment to production?')) return

    promoteMutation.mutate({ domainId: selectedDomain.id, deploymentId })
  }

  const handleToggleAutoUpdate = async (domainId: number, enabled: boolean) => {
    if (!confirm(
      enabled
        ? 'Enable auto-deploy? New successful deployments will automatically go live on this domain.'
        : 'Disable auto-deploy? You will need to manually promote deployments.'
    )) return

    await updateSettingsMutation.mutateAsync({
      domainId,
      settings: { auto_update_enabled: enabled },
    })
    alert(enabled ? '✅ Auto-deploy enabled' : '✅ Auto-deploy disabled')
  }

  const handleSyncEdgeKV = async (domainId: number) => {
    try {
      await api.syncEdgeKV(domainId)
      queryClient.invalidateQueries({ queryKey: ['domains', projectId] })
      alert('✅ Edge KV synchronized successfully')
    } catch (error: any) {
      alert(`❌ Sync failed: ${error.response?.data?.detail || error.message}`)
    }
  }

  if (isLoading) {
    return <div className="text-center py-4">Loading domains...</div>
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold">Custom Domains</h2>
          <p className="text-gray-600 mt-1">
            Add custom domains to access your deployments with ESA
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowAddDomain(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          + Add Domain
        </button>
      </div>

      {/* Add Domain Modal */}
      {showAddDomain && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full">
            <h3 className="text-xl font-bold mb-4">Add Custom Domain</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Domain Name</label>
                <input
                  type="text"
                  value={newDomain}
                  onChange={(e) => setNewDomain(e.target.value)}
                  placeholder="www.example.com"
                  className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-sm text-gray-500 mt-1">
                  Enter your domain (e.g., www.example.com or blog.example.com)
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
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleAddDomain}
                  disabled={!newDomain || createMutation.isPending}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  {createMutation.isPending ? 'Adding...' : 'Add Domain'}
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
              DNS Configuration: {selectedDomain.domain}
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
                      <div className="font-bold text-green-800">Domain Verified</div>
                      <div className="text-sm text-green-700">
                        Your domain is verified and configured with ESA
                      </div>
                    </div>
                  </>
                ) : (
                  <>
                    <span className="text-2xl">⏳</span>
                    <div>
                      <div className="font-bold text-yellow-800">Verification Pending</div>
                      <div className="text-sm text-yellow-700">
                        Please configure DNS records below and click "Verify Domain"
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* DNS Configuration Steps */}
            <div className="space-y-4 mb-6">
              <h4 className="font-bold text-lg">DNS Configuration Steps</h4>

              {/* Step 1: TXT Record for Verification */}
              {!selectedDomain.is_verified && (
                <div className="border rounded-lg p-4">
                  <div className="flex items-start gap-3">
                    <div className="flex-shrink-0 w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center font-bold">
                      1
                    </div>
                    <div className="flex-1">
                      <h5 className="font-bold mb-2">Add TXT Record for Verification</h5>
                      <p className="text-sm text-gray-600 mb-3">
                        Add this TXT record to verify domain ownership
                      </p>

                      <div className="bg-gray-50 p-3 rounded font-mono text-sm">
                        <div className="grid grid-cols-2 gap-2 mb-2">
                          <div>
                            <span className="text-gray-600">Type:</span>{' '}
                            <span className="font-bold">TXT</span>
                          </div>
                          <div>
                            <span className="text-gray-600">TTL:</span> 300
                          </div>
                        </div>
                        <div className="mb-1">
                          <span className="text-gray-600">Name:</span>{' '}
                          _miaobu-verification.{selectedDomain.domain}
                        </div>
                        <div>
                          <span className="text-gray-600">Value:</span>{' '}
                          <span className="break-all">{selectedDomain.verification_token}</span>
                        </div>
                      </div>

                      <p className="text-sm text-gray-500 mt-2 italic">
                        💡 This record verifies you own the domain
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
                    <h5 className="font-bold mb-2">Add CNAME Record</h5>
                    <p className="text-sm text-gray-600 mb-3">
                      Point your domain to Miaobu's ESA edge network
                    </p>

                    <div className="bg-gray-50 p-3 rounded font-mono text-sm">
                      <div className="grid grid-cols-2 gap-2 mb-2">
                        <div>
                          <span className="text-gray-600">Type:</span>{' '}
                          <span className="font-bold">CNAME</span>
                        </div>
                        <div>
                          <span className="text-gray-600">TTL:</span> 3600
                        </div>
                      </div>
                      <div className="mb-1">
                        <span className="text-gray-600">Name:</span> {selectedDomain.domain}
                      </div>
                      <div>
                        <span className="text-gray-600">Value:</span>{' '}
                        <span className="font-bold text-blue-600">
                          {selectedDomain.cname_target || 'cname.metavm.tech'}
                        </span>
                      </div>
                    </div>

                    <p className="text-sm text-gray-500 mt-2 italic">
                      💡 This routes traffic through ESA for better performance and automatic SSL
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* DNS Status */}
            {dnsStatus && (
              <div className="mb-6 border rounded-lg p-4">
                <h4 className="font-bold mb-3">Current DNS Status</h4>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-600">TXT Record:</span>{' '}
                    {dnsStatus.txt_verification?.verified ? '✅ Found' : '❌ Not Found'}
                  </div>
                  <div>
                    <span className="text-gray-600">CNAME Record:</span>{' '}
                    {dnsStatus.cname_status?.verified ? '✅ Correct' : '⏳ Pending'}
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
                  🔒 SSL Certificate (Automatic via ESA)
                </h4>
                <p className="text-sm text-gray-700 mb-2">
                  SSL certificates are automatically provisioned and managed by Aliyun ESA.
                  HTTPS will be available within a few minutes after domain verification.
                </p>
                <div className="grid grid-cols-2 gap-4 text-sm mt-3">
                  <div>
                    <span className="text-gray-600">ESA Status:</span>{' '}
                    <span
                      className={`font-medium ${
                        selectedDomain.esa_status === 'online'
                          ? 'text-green-600'
                          : 'text-yellow-600'
                      }`}
                    >
                      {selectedDomain.esa_status === 'online' ? '✅ Online' : '⏳ Provisioning'}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-600">HTTPS:</span>{' '}
                    {selectedDomain.esa_status === 'online' ? '✅ Enabled' : '⏳ Pending'}
                  </div>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-2 justify-end flex-wrap">
              <button
                type="button"
                onClick={() => handleCheckDNS(selectedDomain.id)}
                className="px-4 py-2 border rounded-lg hover:bg-gray-50"
              >
                🔄 Check DNS
              </button>
              {!selectedDomain.is_verified && (
                <button
                  type="button"
                  onClick={() => handleVerifyDomain(selectedDomain.id)}
                  disabled={verifyMutation.isPending}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                >
                  {verifyMutation.isPending ? 'Verifying...' : '✓ Verify Domain'}
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
                  📦 Manage Deployments
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
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Deployments Modal */}
      {showDeployments && selectedDomain && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 overflow-y-auto p-4">
          <div className="bg-white rounded-lg p-6 max-w-3xl w-full my-8">
            <h3 className="text-xl font-bold mb-4">
              Manage Deployments: {selectedDomain.domain}
            </h3>

            {/* Auto-Update Toggle */}
            <div className="mb-6 flex items-center justify-between p-4 bg-gray-50 rounded-lg border">
              <div>
                <div className="font-medium">Auto-Deploy</div>
                <div className="text-sm text-gray-600">
                  Automatically deploy new successful builds to this domain
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
                <h4 className="font-bold">Deployments</h4>
                {!selectedDomain.edge_kv_synced && (
                  <button
                    type="button"
                    onClick={() => handleSyncEdgeKV(selectedDomain.id)}
                    className="px-3 py-1 text-sm border border-yellow-400 text-yellow-700 rounded-lg hover:bg-yellow-50"
                  >
                    🔄 Sync Edge KV
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
                              ✓ Live
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
                          {promoteMutation.isPending ? 'Promoting...' : 'Promote to Live'}
                        </button>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-8 border-2 border-dashed rounded-lg">
                  <p className="text-gray-600">No deployments found</p>
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
                Close
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
                        ✓ Verified
                      </span>
                    ) : (
                      <span className="px-2 py-1 bg-yellow-100 text-yellow-800 text-xs rounded-full font-medium">
                        ⏳ Pending
                      </span>
                    )}
                    {domain.esa_status === 'online' && (
                      <span className="px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded-full font-medium">
                        🔒 HTTPS
                      </span>
                    )}
                    {domain.auto_update_enabled && (
                      <span className="px-2 py-1 bg-purple-100 text-purple-800 text-xs rounded-full font-medium">
                        🤖 Auto-Deploy
                      </span>
                    )}
                    {domain.edge_kv_synced ? (
                      <span className="px-2 py-1 bg-green-100 text-green-800 text-xs rounded-full font-medium">
                        ✓ Synced
                      </span>
                    ) : (
                      <span className="px-2 py-1 bg-yellow-100 text-yellow-800 text-xs rounded-full font-medium">
                        ⏳ Syncing
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-4 mt-2 text-sm text-gray-600">
                    {domain.verified_at && (
                      <span>Verified: {new Date(domain.verified_at).toLocaleDateString()}</span>
                    )}
                    {domain.active_deployment_id && (
                      <span>Deployment #{domain.active_deployment_id}</span>
                    )}
                    <span className="text-xs">CNAME: {domain.cname_target || 'cname.metavm.tech'}</span>
                  </div>
                </div>
                <div className="flex gap-2">
                  {domain.is_verified ? (
                    <button
                      type="button"
                      onClick={() => handleShowDeployments(domain)}
                      className="px-3 py-2 border rounded-lg hover:bg-gray-50 text-sm"
                    >
                      📦 Deployments
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleShowInstructions(domain)}
                      className="px-3 py-2 border rounded-lg hover:bg-gray-50 text-sm"
                    >
                      🔧 Setup DNS
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => handleShowInstructions(domain)}
                    className="px-3 py-2 border rounded-lg hover:bg-gray-50 text-sm"
                  >
                    ⚙️ Configure
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (confirm(`Delete domain ${domain.domain}?`)) {
                        deleteMutation.mutate(domain.id)
                      }
                    }}
                    className="px-3 py-2 border border-red-300 text-red-600 rounded-lg hover:bg-red-50 text-sm"
                  >
                    🗑️ Delete
                  </button>
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="text-center py-12 border-2 border-dashed rounded-lg">
            <p className="text-gray-600 mb-4">No custom domains configured</p>
            <button
              type="button"
              onClick={() => setShowAddDomain(true)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Add Your First Domain
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
