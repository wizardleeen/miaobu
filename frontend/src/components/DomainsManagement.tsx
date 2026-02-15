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
  const [dnsInstructions, setDnsInstructions] = useState<any>(null)
  const [dnsStatus, setDnsStatus] = useState<any>(null)
  const [sslStatus, setSslStatus] = useState<any>(null)

  const { data: domains, isLoading } = useQuery({
    queryKey: ['domains', projectId],
    queryFn: () => api.listDomains(projectId),
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
      alert('Domain verification check complete. Check the verification status.')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (domainId: number) => api.deleteDomain(domainId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['domains', projectId] })
      setSelectedDomain(null)
      setShowInstructions(false)
    },
  })

  const handleAddDomain = () => {
    if (!newDomain) return
    createMutation.mutate(newDomain)
  }

  const handleShowInstructions = async (domain: any) => {
    setSelectedDomain(domain)
    setShowInstructions(true)

    // Fetch DNS instructions
    const instructions = await api.getDNSInstructions(domain.id)
    setDnsInstructions(instructions)

    // Check DNS status
    const status = await api.checkDomainDNS(domain.id)
    setDnsStatus(status)

    // Check SSL status
    const ssl = await api.getSSLStatus(domain.id)
    setSslStatus(ssl)
  }

  const handleVerifyDomain = async (domainId: number) => {
    const result = await verifyMutation.mutateAsync(domainId)

    if (result.verified) {
      alert('✅ Domain verified successfully!')
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

  const handleIssueSSL = async (domainId: number) => {
    if (!confirm('Issue SSL certificate? This may take 1-2 minutes.')) return

    try {
      const result = await api.issueSSL(domainId, false)
      alert(`✅ ${result.message}\n\nCertificate issuance started. This may take 1-2 minutes.`)

      // Refresh SSL status after a delay
      setTimeout(async () => {
        const ssl = await api.getSSLStatus(domainId)
        setSslStatus(ssl)
        queryClient.invalidateQueries({ queryKey: ['domains', projectId] })
      }, 5000)
    } catch (error: any) {
      alert(`❌ Failed to issue certificate: ${error.response?.data?.detail || error.message}`)
    }
  }

  const handleRenewSSL = async (domainId: number) => {
    if (!confirm('Renew SSL certificate?')) return

    try {
      const result = await api.renewSSL(domainId, false)
      alert(`✅ ${result.message}`)

      // Refresh SSL status
      setTimeout(async () => {
        const ssl = await api.getSSLStatus(domainId)
        setSslStatus(ssl)
        queryClient.invalidateQueries({ queryKey: ['domains', projectId] })
      }, 5000)
    } catch (error: any) {
      alert(`❌ Failed to renew certificate: ${error.response?.data?.detail || error.message}`)
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
            Add custom domains to access your deployments
          </p>
        </div>
        <button
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
                  onClick={() => {
                    setShowAddDomain(false)
                    setNewDomain('')
                  }}
                  className="px-4 py-2 border rounded-lg hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
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
                        Your domain is verified and ready to use
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

            {/* DNS Instructions */}
            {dnsInstructions && (
              <div className="space-y-4 mb-6">
                <h4 className="font-bold text-lg">DNS Configuration Steps</h4>

                {dnsInstructions.steps.map((step: any) => (
                  <div key={step.step} className="border rounded-lg p-4">
                    <div className="flex items-start gap-3">
                      <div className="flex-shrink-0 w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center font-bold">
                        {step.step}
                      </div>
                      <div className="flex-1">
                        <h5 className="font-bold mb-2">{step.title}</h5>
                        <p className="text-sm text-gray-600 mb-3">{step.description}</p>

                        <div className="bg-gray-50 p-3 rounded font-mono text-sm">
                          <div className="grid grid-cols-2 gap-2 mb-2">
                            <div>
                              <span className="text-gray-600">Type:</span>{' '}
                              <span className="font-bold">{step.record_type}</span>
                            </div>
                            <div>
                              <span className="text-gray-600">TTL:</span> {step.ttl}
                            </div>
                          </div>
                          <div className="mb-1">
                            <span className="text-gray-600">Name:</span> {step.name}
                          </div>
                          <div>
                            <span className="text-gray-600">Value:</span>{' '}
                            <span className="break-all">{step.value}</span>
                          </div>
                        </div>

                        {step.note && (
                          <p className="text-sm text-gray-500 mt-2 italic">💡 {step.note}</p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* DNS Status */}
            {dnsStatus && dnsStatus.dns_status && (
              <div className="mb-6 border rounded-lg p-4">
                <h4 className="font-bold mb-3">Current DNS Status</h4>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-600">Domain Exists:</span>{' '}
                    {dnsStatus.dns_status.exists ? '✅ Yes' : '❌ No'}
                  </div>
                  <div>
                    <span className="text-gray-600">Has TXT Record:</span>{' '}
                    {dnsStatus.dns_status.has_txt_record ? '✅ Yes' : '❌ No'}
                  </div>
                  <div>
                    <span className="text-gray-600">Has CNAME:</span>{' '}
                    {dnsStatus.dns_status.has_cname_record ? '✅ Yes' : '❌ No'}
                  </div>
                  <div>
                    <span className="text-gray-600">Verification:</span>{' '}
                    {dnsStatus.txt_verification?.verified ? '✅ Verified' : '⏳ Pending'}
                  </div>
                </div>

                {dnsStatus.txt_verification && !dnsStatus.txt_verification.verified && (
                  <div className="mt-3 text-sm text-yellow-700 bg-yellow-50 p-3 rounded">
                    {dnsStatus.txt_verification.message}
                  </div>
                )}
              </div>
            )}

            {/* SSL Status */}
            {sslStatus && selectedDomain.is_verified && (
              <div className="mb-6 border rounded-lg p-4">
                <h4 className="font-bold mb-3 flex items-center gap-2">
                  🔒 SSL Certificate Status
                </h4>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-600">Status:</span>{' '}
                    <span
                      className={`font-medium ${
                        sslStatus.ssl_status === 'active'
                          ? 'text-green-600'
                          : sslStatus.ssl_status === 'issuing'
                          ? 'text-yellow-600'
                          : sslStatus.ssl_status === 'failed'
                          ? 'text-red-600'
                          : 'text-gray-600'
                      }`}
                    >
                      {sslStatus.ssl_status === 'active'
                        ? '✅ Active'
                        : sslStatus.ssl_status === 'issuing'
                        ? '⏳ Issuing'
                        : sslStatus.ssl_status === 'failed'
                        ? '❌ Failed'
                        : '⏳ Pending'}
                    </span>
                  </div>
                  {sslStatus.expires_at && (
                    <div>
                      <span className="text-gray-600">Expires:</span>{' '}
                      {new Date(sslStatus.expires_at).toLocaleDateString()}
                    </div>
                  )}
                  {sslStatus.days_until_expiry !== null && (
                    <div>
                      <span className="text-gray-600">Days Remaining:</span>{' '}
                      <span
                        className={`font-medium ${
                          sslStatus.days_until_expiry <= 30 ? 'text-red-600' : 'text-green-600'
                        }`}
                      >
                        {sslStatus.days_until_expiry} days
                      </span>
                    </div>
                  )}
                  <div>
                    <span className="text-gray-600">HTTPS:</span>{' '}
                    {sslStatus.is_https_enabled ? '✅ Enabled' : '❌ Disabled'}
                  </div>
                </div>
                {sslStatus.needs_renewal && (
                  <div className="mt-3 text-sm text-yellow-700 bg-yellow-50 p-3 rounded">
                    ⚠️ Certificate expires soon. Renewal recommended.
                  </div>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-2 justify-end flex-wrap">
              <button
                onClick={() => handleCheckDNS(selectedDomain.id)}
                className="px-4 py-2 border rounded-lg hover:bg-gray-50"
              >
                🔄 Check DNS
              </button>
              {!selectedDomain.is_verified && (
                <button
                  onClick={() => handleVerifyDomain(selectedDomain.id)}
                  disabled={verifyMutation.isPending}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                >
                  {verifyMutation.isPending ? 'Verifying...' : '✓ Verify Domain'}
                </button>
              )}
              {selectedDomain.is_verified && !sslStatus?.certificate_id && (
                <button
                  onClick={() => handleIssueSSL(selectedDomain.id)}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  🔒 Issue SSL Certificate
                </button>
              )}
              {selectedDomain.is_verified && sslStatus?.needs_renewal && (
                <button
                  onClick={() => handleRenewSSL(selectedDomain.id)}
                  className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700"
                >
                  🔄 Renew SSL
                </button>
              )}
              <button
                onClick={() => {
                  setShowInstructions(false)
                  setSelectedDomain(null)
                  setDnsInstructions(null)
                  setDnsStatus(null)
                  setSslStatus(null)
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
                    {domain.ssl_status === 'active' && (
                      <span className="px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded-full font-medium">
                        🔒 HTTPS
                      </span>
                    )}
                    {domain.ssl_status === 'issuing' && (
                      <span className="px-2 py-1 bg-yellow-100 text-yellow-800 text-xs rounded-full font-medium">
                        ⏳ Issuing SSL
                      </span>
                    )}
                  </div>
                  {domain.verified_at && (
                    <p className="text-sm text-gray-500 mt-1">
                      Verified: {new Date(domain.verified_at).toLocaleDateString()}
                    </p>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleShowInstructions(domain)}
                    className="px-3 py-2 border rounded-lg hover:bg-gray-50 text-sm"
                  >
                    {domain.is_verified ? '⚙️ Configure' : '🔧 Setup DNS'}
                  </button>
                  <button
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
