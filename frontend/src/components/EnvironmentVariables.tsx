import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'

interface EnvVar {
  id: number
  project_id: number
  key: string
  value: string
  is_secret: boolean
  created_at: string
  updated_at: string
}

interface Props {
  projectId: number
}

export default function EnvironmentVariables({ projectId }: Props) {
  const queryClient = useQueryClient()
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')
  const [newIsSecret, setNewIsSecret] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editValue, setEditValue] = useState('')

  const { data: envVars = [], isLoading } = useQuery({
    queryKey: ['env-vars', projectId],
    queryFn: () => api.listEnvVars(projectId),
  })

  const createMutation = useMutation({
    mutationFn: (data: { key: string; value: string; is_secret: boolean }) =>
      api.createEnvVar(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['env-vars', projectId] })
      setNewKey('')
      setNewValue('')
      setNewIsSecret(false)
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ varId, data }: { varId: number; data: { value: string } }) =>
      api.updateEnvVar(projectId, varId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['env-vars', projectId] })
      setEditingId(null)
      setEditValue('')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (varId: number) => api.deleteEnvVar(projectId, varId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['env-vars', projectId] })
    },
  })

  const handleAdd = () => {
    if (!newKey.trim() || !newValue.trim()) return
    createMutation.mutate({ key: newKey.trim(), value: newValue, is_secret: newIsSecret })
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

  return (
    <div>
      <h2 className="text-xl font-bold mb-4">环境变量</h2>
      <p className="text-sm text-gray-600 mb-4">
        配置应用运行时使用的环境变量。敏感值（如密码、API 密钥）会自动加密存储。
      </p>

      {/* Existing variables */}
      {isLoading ? (
        <div className="text-center py-4">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600 mx-auto"></div>
        </div>
      ) : envVars.length > 0 ? (
        <div className="space-y-2 mb-6">
          {envVars.map((env: EnvVar) => (
            <div key={env.id} className="flex items-center gap-2 p-3 bg-gray-50 rounded-lg">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-semibold">{env.key}</span>
                  {env.is_secret && (
                    <span className="px-1.5 py-0.5 bg-yellow-100 text-yellow-800 text-xs rounded">
                      敏感
                    </span>
                  )}
                </div>
                {editingId === env.id ? (
                  <div className="flex items-center gap-2 mt-1">
                    <input
                      type="text"
                      className="flex-1 border rounded px-2 py-1 text-sm font-mono"
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      placeholder="输入新值"
                    />
                    <button
                      onClick={() => handleUpdate(env.id)}
                      className="px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
                      disabled={updateMutation.isPending}
                    >
                      保存
                    </button>
                    <button
                      onClick={() => { setEditingId(null); setEditValue('') }}
                      className="px-2 py-1 text-xs border rounded hover:bg-gray-100"
                    >
                      取消
                    </button>
                  </div>
                ) : (
                  <p className="font-mono text-sm text-gray-600 truncate mt-0.5">
                    {env.value}
                  </p>
                )}
              </div>
              {editingId !== env.id && (
                <div className="flex gap-1">
                  <button
                    onClick={() => { setEditingId(env.id); setEditValue('') }}
                    className="px-2 py-1 text-xs border rounded hover:bg-gray-100"
                  >
                    编辑
                  </button>
                  <button
                    onClick={() => handleDelete(env.id, env.key)}
                    className="px-2 py-1 text-xs border border-red-300 text-red-700 rounded hover:bg-red-50"
                    disabled={deleteMutation.isPending}
                  >
                    删除
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-6 text-gray-500 text-sm mb-6 bg-gray-50 rounded-lg">
          暂无环境变量
        </div>
      )}

      {/* Add new variable */}
      <div className="border rounded-lg p-4 bg-white">
        <h3 className="text-sm font-semibold mb-3">添加环境变量</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-gray-600 mb-1">变量名</label>
            <input
              type="text"
              className="w-full border rounded px-3 py-2 font-mono text-sm"
              placeholder="例如: DATABASE_URL"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ''))}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">值</label>
            <input
              type="text"
              className="w-full border rounded px-3 py-2 font-mono text-sm"
              placeholder="变量值"
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
            />
          </div>
        </div>
        <div className="flex items-center justify-between mt-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={newIsSecret}
              onChange={(e) => setNewIsSecret(e.target.checked)}
              className="rounded"
            />
            <span>标记为敏感值（值将被隐藏）</span>
          </label>
          <button
            onClick={handleAdd}
            className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50"
            disabled={!newKey.trim() || !newValue.trim() || createMutation.isPending}
          >
            {createMutation.isPending ? '添加中...' : '添加'}
          </button>
        </div>
        {createMutation.isError && (
          <p className="text-red-600 text-sm mt-2">添加失败，请检查变量名是否重复。</p>
        )}
      </div>
    </div>
  )
}
