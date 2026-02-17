import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../services/api'
import { X } from 'lucide-react'

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
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-start justify-center z-50 overflow-y-auto p-4 animate-fade-in">
      <div className="card shadow-xl max-w-2xl w-full my-8">
        <div className="flex items-center justify-between p-5 border-b border-[--border-primary]">
          <h2 className="text-lg font-semibold text-[--text-primary]">创建新项目</h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-[--text-tertiary] hover:text-[--text-primary] hover:bg-[--bg-tertiary] transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="block text-sm font-medium text-[--text-secondary] mb-1">项目名称 *</label>
            <input
              type="text"
              required
              className="input"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="我的项目"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[--text-secondary] mb-1">GitHub 仓库 *</label>
            <input
              type="text"
              required
              className="input"
              value={formData.github_repo_name}
              onChange={(e) => setFormData({ ...formData, github_repo_name: e.target.value })}
              placeholder="username/repository"
            />
            <p className="text-xs text-[--text-tertiary] mt-1">格式: owner/repo</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-[--text-secondary] mb-1">仓库地址 *</label>
            <input
              type="url"
              required
              className="input"
              value={formData.github_repo_url}
              onChange={(e) => setFormData({ ...formData, github_repo_url: e.target.value })}
              placeholder="https://github.com/username/repository"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[--text-secondary] mb-1">仓库 ID *</label>
            <input
              type="number"
              required
              className="input"
              value={formData.github_repo_id || ''}
              onChange={(e) => setFormData({ ...formData, github_repo_id: Number(e.target.value) })}
              placeholder="123456789"
            />
            <p className="text-xs text-[--text-tertiary] mt-1">从 GitHub API 响应中获取</p>
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-[--text-secondary] mb-1">构建命令</label>
              <input
                type="text"
                className="input font-mono text-sm"
                value={formData.build_command}
                onChange={(e) => setFormData({ ...formData, build_command: e.target.value })}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-[--text-secondary] mb-1">输出目录</label>
              <input
                type="text"
                className="input font-mono text-sm"
                value={formData.output_directory}
                onChange={(e) => setFormData({ ...formData, output_directory: e.target.value })}
              />
            </div>
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-[--text-secondary] mb-1">默认分支</label>
              <input
                type="text"
                className="input"
                value={formData.default_branch}
                onChange={(e) => setFormData({ ...formData, default_branch: e.target.value })}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-[--text-secondary] mb-1">Node 版本</label>
              <select
                className="input"
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
            <div className="p-3 rounded-lg text-sm bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-500/20">
              创建项目失败，请检查输入并重试。
            </div>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="btn-secondary text-sm"
              disabled={createProjectMutation.isPending}
            >
              取消
            </button>
            <button
              type="submit"
              className="btn-primary text-sm"
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
