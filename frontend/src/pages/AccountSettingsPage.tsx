import { useState, useEffect, useCallback } from 'react'
import { Copy, Check, Plus, Trash2, Key, AlertTriangle } from 'lucide-react'
import Layout from '../components/Layout'
import { api } from '../services/api'
import { useToast } from '../components/Toast'

interface ApiToken {
  id: number
  name: string
  prefix: string
  last_used_at: string | null
  expires_at: string | null
  created_at: string
}

export default function AccountSettingsPage() {
  const { toast } = useToast()
  const [tokens, setTokens] = useState<ApiToken[]>([])
  const [loading, setLoading] = useState(true)

  // Create modal state
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [expiresDays, setExpiresDays] = useState<string>('')
  const [creating, setCreating] = useState(false)

  // One-time token display
  const [createdToken, setCreatedToken] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  // Revoke confirmation
  const [revokeId, setRevokeId] = useState<number | null>(null)

  const fetchTokens = useCallback(async () => {
    try {
      const data = await api.listApiTokens()
      setTokens(data)
    } catch {
      toast('加载令牌失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { fetchTokens() }, [fetchTokens])

  const handleCreate = async () => {
    if (!newName.trim()) return
    setCreating(true)
    try {
      const result = await api.createApiToken({
        name: newName.trim(),
        expires_in_days: expiresDays ? parseInt(expiresDays) : undefined,
      })
      setCreatedToken(result.token)
      setShowCreate(false)
      setNewName('')
      setExpiresDays('')
      fetchTokens()
      toast('令牌创建成功', 'success')
    } catch {
      toast('创建令牌失败', 'error')
    } finally {
      setCreating(false)
    }
  }

  const handleRevoke = async (id: number) => {
    try {
      await api.revokeApiToken(id)
      setTokens(prev => prev.filter(t => t.id !== id))
      setRevokeId(null)
      toast('令牌已撤销', 'success')
    } catch {
      toast('撤销令牌失败', 'error')
    }
  }

  const handleCopy = () => {
    if (createdToken) {
      navigator.clipboard.writeText(createdToken)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const formatDate = (s: string | null) => {
    if (!s) return '—'
    return new Date(s).toLocaleDateString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
  }

  return (
    <Layout>
      <div className="space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-[--text-primary]">设置</h1>
          <p className="mt-1 text-sm text-[--text-secondary]">管理你的账户和 API 令牌</p>
        </div>

        {/* API Tokens Section */}
        <div className="bg-[--bg-elevated] rounded-xl border border-[--border-primary] overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 border-b border-[--border-primary]">
            <div className="flex items-center gap-2">
              <Key size={18} className="text-[--text-secondary]" />
              <h2 className="text-lg font-semibold text-[--text-primary]">API 令牌</h2>
            </div>
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-accent hover:bg-accent/90 rounded-lg transition-colors"
            >
              <Plus size={16} />
              创建令牌
            </button>
          </div>

          <div className="p-6">
            <p className="text-sm text-[--text-secondary] mb-4">
              使用 API 令牌通过编程方式访问秒部 API。令牌创建后仅显示一次，请妥善保管。
            </p>

            {loading ? (
              <div className="text-center py-8 text-[--text-secondary]">加载中...</div>
            ) : tokens.length === 0 ? (
              <div className="text-center py-8 text-[--text-tertiary]">
                还没有 API 令牌。创建一个以开始使用 API。
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[--border-primary] text-[--text-secondary]">
                      <th className="text-left py-2 px-3 font-medium">名称</th>
                      <th className="text-left py-2 px-3 font-medium">前缀</th>
                      <th className="text-left py-2 px-3 font-medium">最后使用</th>
                      <th className="text-left py-2 px-3 font-medium">过期时间</th>
                      <th className="text-left py-2 px-3 font-medium">创建时间</th>
                      <th className="text-right py-2 px-3 font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tokens.map(token => (
                      <tr key={token.id} className="border-b border-[--border-primary] last:border-0">
                        <td className="py-3 px-3 text-[--text-primary] font-medium">{token.name}</td>
                        <td className="py-3 px-3">
                          <code className="px-2 py-0.5 rounded bg-[--bg-tertiary] text-[--text-secondary] text-xs">
                            {token.prefix}...
                          </code>
                        </td>
                        <td className="py-3 px-3 text-[--text-secondary]">{formatDate(token.last_used_at)}</td>
                        <td className="py-3 px-3 text-[--text-secondary]">
                          {token.expires_at ? (
                            new Date(token.expires_at) < new Date() ? (
                              <span className="text-red-500">已过期</span>
                            ) : formatDate(token.expires_at)
                          ) : '永不过期'}
                        </td>
                        <td className="py-3 px-3 text-[--text-secondary]">{formatDate(token.created_at)}</td>
                        <td className="py-3 px-3 text-right">
                          {revokeId === token.id ? (
                            <div className="flex items-center justify-end gap-2">
                              <span className="text-xs text-[--text-secondary]">确认撤销？</span>
                              <button
                                onClick={() => handleRevoke(token.id)}
                                className="text-xs px-2 py-1 bg-red-500 text-white rounded hover:bg-red-600 transition-colors"
                              >
                                确认
                              </button>
                              <button
                                onClick={() => setRevokeId(null)}
                                className="text-xs px-2 py-1 bg-[--bg-tertiary] text-[--text-secondary] rounded hover:bg-[--bg-secondary] transition-colors"
                              >
                                取消
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => setRevokeId(token.id)}
                              className="p-1.5 rounded-lg text-[--text-tertiary] hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                              title="撤销令牌"
                            >
                              <Trash2 size={16} />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Create Token Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/50" onClick={() => setShowCreate(false)}>
          <div className="bg-[--bg-elevated] rounded-xl border border-[--border-primary] shadow-xl w-full max-w-md mx-4" onClick={e => e.stopPropagation()}>
            <div className="px-6 py-4 border-b border-[--border-primary]">
              <h3 className="text-lg font-semibold text-[--text-primary]">创建 API 令牌</h3>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-[--text-secondary] mb-1">令牌名称</label>
                <input
                  type="text"
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  placeholder="例如：CI/CD 部署"
                  className="w-full px-3 py-2 rounded-lg border border-[--border-primary] bg-[--bg-secondary] text-[--text-primary] placeholder:text-[--text-tertiary] focus:outline-none focus:ring-2 focus:ring-accent/50"
                  autoFocus
                  onKeyDown={e => e.key === 'Enter' && handleCreate()}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[--text-secondary] mb-1">
                  过期时间 <span className="text-[--text-tertiary]">（可选）</span>
                </label>
                <select
                  value={expiresDays}
                  onChange={e => setExpiresDays(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-[--border-primary] bg-[--bg-secondary] text-[--text-primary] focus:outline-none focus:ring-2 focus:ring-accent/50"
                >
                  <option value="">永不过期</option>
                  <option value="7">7 天</option>
                  <option value="30">30 天</option>
                  <option value="60">60 天</option>
                  <option value="90">90 天</option>
                  <option value="180">180 天</option>
                  <option value="365">365 天</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-3 px-6 py-4 border-t border-[--border-primary]">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 text-sm font-medium text-[--text-secondary] hover:text-[--text-primary] rounded-lg hover:bg-[--bg-tertiary] transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleCreate}
                disabled={!newName.trim() || creating}
                className="px-4 py-2 text-sm font-medium text-white bg-accent hover:bg-accent/90 rounded-lg transition-colors disabled:opacity-50"
              >
                {creating ? '创建中...' : '创建'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Token Created Modal */}
      {createdToken && (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/50">
          <div className="bg-[--bg-elevated] rounded-xl border border-[--border-primary] shadow-xl w-full max-w-lg mx-4">
            <div className="px-6 py-4 border-b border-[--border-primary]">
              <h3 className="text-lg font-semibold text-[--text-primary]">令牌已创建</h3>
            </div>
            <div className="p-6 space-y-4">
              <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20">
                <AlertTriangle size={18} className="text-amber-500 mt-0.5 shrink-0" />
                <p className="text-sm text-amber-700 dark:text-amber-400">
                  请立即复制此令牌。关闭此窗口后将无法再次查看。
                </p>
              </div>
              <div className="flex items-center gap-2">
                <code className="flex-1 px-3 py-2 rounded-lg bg-[--bg-tertiary] text-[--text-primary] text-sm font-mono break-all select-all">
                  {createdToken}
                </code>
                <button
                  onClick={handleCopy}
                  className="p-2 rounded-lg border border-[--border-primary] hover:bg-[--bg-tertiary] transition-colors shrink-0"
                  title="复制"
                >
                  {copied ? <Check size={18} className="text-green-500" /> : <Copy size={18} className="text-[--text-secondary]" />}
                </button>
              </div>
            </div>
            <div className="flex justify-end px-6 py-4 border-t border-[--border-primary]">
              <button
                onClick={() => { setCreatedToken(null); setCopied(false) }}
                className="px-4 py-2 text-sm font-medium text-white bg-accent hover:bg-accent/90 rounded-lg transition-colors"
              >
                完成
              </button>
            </div>
          </div>
        </div>
      )}
    </Layout>
  )
}
