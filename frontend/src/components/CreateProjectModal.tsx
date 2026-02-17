import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../services/api'

interface CreateProjectModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
}

export default function CreateProjectModal({ isOpen, onClose, onSuccess }: CreateProjectModalProps) {
  const [formData, setFormData] = useState({
    name: '',
    github_repo_id: 0,
    github_repo_name: '',
    github_repo_url: '',
    default_branch: 'main',
    build_command: 'npm run build',
    install_command: 'npm install',
    output_directory: 'dist',
    node_version: '18',
  })

  const createProjectMutation = useMutation({
    mutationFn: (data: any) => api.createProject(data),
    onSuccess: () => {
      onSuccess()
      setFormData({
        name: '',
        github_repo_id: 0,
        github_repo_name: '',
        github_repo_url: '',
        default_branch: 'main',
        build_command: 'npm run build',
        install_command: 'npm install',
        output_directory: 'dist',
        node_version: '18',
      })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createProjectMutation.mutate(formData)
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b">
          <h2 className="text-2xl font-bold">创建新项目</h2>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">项目名称 *</label>
            <input
              type="text"
              required
              className="w-full border rounded-lg px-3 py-2"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="我的项目"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">GitHub 仓库 *</label>
            <input
              type="text"
              required
              className="w-full border rounded-lg px-3 py-2"
              value={formData.github_repo_name}
              onChange={(e) => setFormData({ ...formData, github_repo_name: e.target.value })}
              placeholder="username/repository"
            />
            <p className="text-sm text-gray-500 mt-1">格式: owner/repo</p>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">仓库地址 *</label>
            <input
              type="url"
              required
              className="w-full border rounded-lg px-3 py-2"
              value={formData.github_repo_url}
              onChange={(e) => setFormData({ ...formData, github_repo_url: e.target.value })}
              placeholder="https://github.com/username/repository"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">仓库 ID *</label>
            <input
              type="number"
              required
              className="w-full border rounded-lg px-3 py-2"
              value={formData.github_repo_id || ''}
              onChange={(e) => setFormData({ ...formData, github_repo_id: Number(e.target.value) })}
              placeholder="123456789"
            />
            <p className="text-sm text-gray-500 mt-1">从 GitHub API 响应中获取</p>
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">构建命令</label>
              <input
                type="text"
                className="w-full border rounded-lg px-3 py-2"
                value={formData.build_command}
                onChange={(e) => setFormData({ ...formData, build_command: e.target.value })}
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">输出目录</label>
              <input
                type="text"
                className="w-full border rounded-lg px-3 py-2"
                value={formData.output_directory}
                onChange={(e) => setFormData({ ...formData, output_directory: e.target.value })}
              />
            </div>
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">默认分支</label>
              <input
                type="text"
                className="w-full border rounded-lg px-3 py-2"
                value={formData.default_branch}
                onChange={(e) => setFormData({ ...formData, default_branch: e.target.value })}
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Node 版本</label>
              <select
                className="w-full border rounded-lg px-3 py-2"
                value={formData.node_version}
                onChange={(e) => setFormData({ ...formData, node_version: e.target.value })}
              >
                <option value="16">16</option>
                <option value="18">18</option>
                <option value="20">20</option>
              </select>
            </div>
          </div>

          {createProjectMutation.isError && (
            <div className="bg-red-50 text-red-800 p-3 rounded-lg text-sm">
              创建项目失败，请检查输入并重试。
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border rounded-lg hover:bg-gray-50"
              disabled={createProjectMutation.isPending}
            >
              取消
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              disabled={createProjectMutation.isPending}
            >
              {createProjectMutation.isPending ? '创建中...' : '创建项目'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
