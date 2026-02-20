import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'
import { Lock, Pencil, Trash2, Plus } from 'lucide-react'

interface EnvVar {
  id: number
  project_id: number
  key: string
  value: string
  is_secret: boolean
  environment: string
  created_at: string
  updated_at: string
}

interface Props {
  projectId: number
  stagingEnabled?: boolean
}

export default function EnvironmentVariables({ projectId, stagingEnabled }: Props) {
  const queryClient = useQueryClient()
  const [activeEnvironment, setActiveEnvironment] = useState<string>('production')
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')
  const [newIsSecret, setNewIsSecret] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editValue, setEditValue] = useState('')
  const [bulkMode, setBulkMode] = useState(false)
  const [bulkText, setBulkText] = useState('')
  const [bulkIsSecret, setBulkIsSecret] = useState(false)
  const [bulkAdding, setBulkAdding] = useState(false)
  const [bulkError, setBulkError] = useState('')

  const { data: envVars = [], isLoading } = useQuery({
    queryKey: ['env-vars', projectId, activeEnvironment],
    queryFn: () => api.listEnvVars(projectId, activeEnvironment),
  })

  const createMutation = useMutation({
    mutationFn: (data: { key: string; value: string; is_secret: boolean; environment?: string }) =>
      api.createEnvVar(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['env-vars', projectId, activeEnvironment] })
      setNewKey('')
      setNewValue('')
      setNewIsSecret(false)
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ varId, data }: { varId: number; data: { value: string } }) =>
      api.updateEnvVar(projectId, varId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['env-vars', projectId, activeEnvironment] })
      setEditingId(null)
      setEditValue('')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (varId: number) => api.deleteEnvVar(projectId, varId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['env-vars', projectId, activeEnvironment] })
    },
  })

  const handleAdd = () => {
    if (!newKey.trim() || !newValue.trim()) return
    createMutation.mutate({
      key: newKey.trim(),
      value: newValue,
      is_secret: newIsSecret,
      environment: activeEnvironment,
    })
  }

  const handleUpdate = (varId: number) => {
    if (!editValue.trim()) return
    updateMutation.mutate({ varId, data: { value: editValue } })
  }

  const handleDelete = (varId: number, key: string) => {
    if (confirm(`确定要删除环境变量 "${key}" 吗？`)) {
      deleteMutation.mutate(varId)
    }
  }

  const parseBulkText = (text: string): { key: string; value: string }[] => {
    return text
      .split('\n')
      .map(line => line.trim())
      .filter(line => line && !line.startsWith('#'))
      .map(line => {
        const eqIndex = line.indexOf('=')
        if (eqIndex === -1) return null
        const key = line.slice(0, eqIndex).trim()
        const value = line.slice(eqIndex + 1).trim()
        if (!key) return null
        return { key, value }
      })
      .filter((item): item is { key: string; value: string } => item !== null)
  }

  const handleBulkAdd = async () => {
    const entries = parseBulkText(bulkText)
    if (entries.length === 0) {
      setBulkError('未解析到有效的环境变量，请使用 KEY=VALUE 格式，每行一个。')
      return
    }
    setBulkAdding(true)
    setBulkError('')
    let added = 0
    const errors: string[] = []
    for (const entry of entries) {
      try {
        await api.createEnvVar(projectId, {
          key: entry.key,
          value: entry.value,
          is_secret: bulkIsSecret,
          environment: activeEnvironment,
        })
        added++
      } catch {
        errors.push(entry.key)
      }
    }
    queryClient.invalidateQueries({ queryKey: ['env-vars', projectId, activeEnvironment] })
    setBulkAdding(false)
    if (errors.length > 0) {
      setBulkError(`已添加 ${added} 个变量。以下变量添加失败（可能已存在）：${errors.join(', ')}`)
    } else {
      setBulkText('')
      setBulkError('')
    }
  }

  return (
    <div>
      <h2 className="text-sm font-semibold text-[--text-primary] mb-1">环境变量</h2>
      <p className="text-xs text-[--text-secondary] mb-4">
        配置应用运行时使用的环境变量。敏感值（如密码、API 密钥）会自动加密存储。
      </p>

      {/* Environment tabs */}
      {stagingEnabled && (
        <div className="flex bg-[--bg-tertiary] rounded-lg p-0.5 mb-4 w-fit">
          <button
            type="button"
            onClick={() => setActiveEnvironment('production')}
            className={`px-3 py-1.5 text-xs rounded-md transition-colors ${activeEnvironment === 'production' ? 'bg-[--bg-elevated] shadow-sm text-[--text-primary] font-medium' : 'text-[--text-tertiary] hover:text-[--text-secondary]'}`}
          >
            Production
          </button>
          <button
            type="button"
            onClick={() => setActiveEnvironment('staging')}
            className={`px-3 py-1.5 text-xs rounded-md transition-colors ${activeEnvironment === 'staging' ? 'bg-purple-100 dark:bg-purple-500/20 shadow-sm text-purple-700 dark:text-purple-400 font-medium' : 'text-[--text-tertiary] hover:text-[--text-secondary]'}`}
          >
            Staging
          </button>
        </div>
      )}

      {/* Existing variables */}
      {isLoading ? (
        <div className="text-center py-4">
          <div className="animate-spin rounded-full h-6 w-6 border-2 border-accent border-t-transparent mx-auto"></div>
        </div>
      ) : envVars.length > 0 ? (
        <div className="space-y-1.5 mb-6">
          {envVars.map((env: EnvVar) => (
            <div key={env.id} className="flex items-center gap-2 p-3 bg-[--bg-tertiary] rounded-lg">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-medium text-[--text-primary]">{env.key}</span>
                  {env.is_secret && (
                    <span className="badge-warning">
                      <Lock size={10} />
                      敏感
                    </span>
                  )}
                </div>
                {editingId === env.id ? (
                  <div className="flex items-center gap-2 mt-1.5">
                    <input
                      type="text"
                      className="input text-sm font-mono flex-1"
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      placeholder="输入新值"
                    />
                    <button
                      type="button"
                      onClick={() => handleUpdate(env.id)}
                      className="btn-primary text-xs px-2.5 py-1.5"
                      disabled={updateMutation.isPending}
                    >
                      保存
                    </button>
                    <button
                      type="button"
                      onClick={() => { setEditingId(null); setEditValue('') }}
                      className="btn-secondary text-xs px-2.5 py-1.5"
                    >
                      取消
                    </button>
                  </div>
                ) : (
                  <p className="font-mono text-xs text-[--text-secondary] truncate mt-0.5">
                    {env.value}
                  </p>
                )}
              </div>
              {editingId !== env.id && (
                <div className="flex gap-1 shrink-0">
                  <button
                    type="button"
                    onClick={() => { setEditingId(env.id); setEditValue('') }}
                    className="p-1.5 rounded-lg text-[--text-tertiary] hover:text-[--text-primary] hover:bg-[--bg-secondary] transition-colors"
                    title="编辑"
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(env.id, env.key)}
                    className="p-1.5 rounded-lg text-[--text-tertiary] hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                    disabled={deleteMutation.isPending}
                    title="删除"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-6 text-[--text-tertiary] text-xs mb-6 bg-[--bg-tertiary] rounded-lg">
          暂无环境变量
        </div>
      )}

      {/* Add new variable */}
      <div className="border border-[--border-primary] rounded-lg p-4 bg-[--bg-elevated]">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-semibold text-[--text-primary] flex items-center gap-1.5">
            <Plus size={14} />
            添加环境变量
            {stagingEnabled && activeEnvironment === 'staging' && (
              <span className="text-[10px] font-medium text-purple-600 dark:text-purple-400">(Staging)</span>
            )}
          </h3>
          <div className="flex bg-[--bg-tertiary] rounded-lg p-0.5">
            <button
              type="button"
              onClick={() => setBulkMode(false)}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${!bulkMode ? 'bg-[--bg-elevated] shadow-sm text-[--text-primary]' : 'text-[--text-tertiary] hover:text-[--text-secondary]'}`}
            >
              单个添加
            </button>
            <button
              type="button"
              onClick={() => setBulkMode(true)}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${bulkMode ? 'bg-[--bg-elevated] shadow-sm text-[--text-primary]' : 'text-[--text-tertiary] hover:text-[--text-secondary]'}`}
            >
              批量粘贴
            </button>
          </div>
        </div>

        {!bulkMode ? (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-[--text-tertiary] mb-1">变量名</label>
                <input
                  type="text"
                  className="input font-mono text-sm"
                  placeholder="例如: DATABASE_URL"
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ''))}
                />
              </div>
              <div>
                <label className="block text-xs text-[--text-tertiary] mb-1">值</label>
                <input
                  type="text"
                  className="input font-mono text-sm"
                  placeholder="变量值"
                  value={newValue}
                  onChange={(e) => setNewValue(e.target.value)}
                />
              </div>
            </div>
            <div className="flex items-center justify-between mt-3">
              <label className="flex items-center gap-2 text-xs text-[--text-secondary]">
                <input
                  type="checkbox"
                  checked={newIsSecret}
                  onChange={(e) => setNewIsSecret(e.target.checked)}
                  className="rounded border-[--border-secondary]"
                />
                <span>标记为敏感值（值将被隐藏）</span>
              </label>
              <button
                type="button"
                onClick={handleAdd}
                className="btn-primary text-xs"
                disabled={!newKey.trim() || !newValue.trim() || createMutation.isPending}
              >
                {createMutation.isPending ? '添加中...' : '添加'}
              </button>
            </div>
            {createMutation.isError && (
              <p className="text-red-600 dark:text-red-400 text-xs mt-2">添加失败，请检查变量名是否重复。</p>
            )}
          </>
        ) : (
          <>
            <textarea
              className="input font-mono text-sm h-40 resize-y"
              placeholder={"粘贴 KEY=VALUE 格式的环境变量，每行一个，例如：\nDATABASE_URL=postgres://localhost/mydb\nAPI_KEY=sk-xxxxx\nDEBUG=true\n\n# 以 # 开头的行会被忽略"}
              value={bulkText}
              onChange={(e) => { setBulkText(e.target.value); setBulkError('') }}
            />
            {bulkText && (
              <p className="text-xs text-[--text-tertiary] mt-1">
                已识别 {parseBulkText(bulkText).length} 个变量
              </p>
            )}
            <div className="flex items-center justify-between mt-3">
              <label className="flex items-center gap-2 text-xs text-[--text-secondary]">
                <input
                  type="checkbox"
                  checked={bulkIsSecret}
                  onChange={(e) => setBulkIsSecret(e.target.checked)}
                  className="rounded border-[--border-secondary]"
                />
                <span>全部标记为敏感值</span>
              </label>
              <button
                type="button"
                onClick={handleBulkAdd}
                className="btn-primary text-xs"
                disabled={!bulkText.trim() || bulkAdding}
              >
                {bulkAdding ? '添加中...' : '批量添加'}
              </button>
            </div>
            {bulkError && (
              <p className={`text-xs mt-2 ${bulkError.startsWith('已添加') ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400'}`}>{bulkError}</p>
            )}
          </>
        )}
      </div>
    </div>
  )
}
