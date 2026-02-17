import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'
import Layout from '../components/Layout'
import DomainsManagement from '../components/DomainsManagement'
import EnvironmentVariables from '../components/EnvironmentVariables'

export default function ProjectSettingsPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [formData, setFormData] = useState({
    name: '',
    root_directory: '',
    build_command: '',
    install_command: '',
    output_directory: '',
    node_version: '18',
    python_version: '',
    start_command: '',
    python_framework: '',
  })

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const { data: project, isLoading } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => api.getProject(Number(projectId)),
    enabled: !!projectId,
  })

  useEffect(() => {
    if (project) {
      setFormData({
        name: project.name,
        root_directory: project.root_directory || '',
        build_command: project.build_command || '',
        install_command: project.install_command || '',
        output_directory: project.output_directory || '',
        node_version: project.node_version || '18',
        python_version: project.python_version || '',
        start_command: project.start_command || '',
        python_framework: project.python_framework || '',
      })
    }
  }, [project])

  const updateMutation = useMutation({
    mutationFn: (data: any) => api.updateProject(Number(projectId), data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId] })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      alert('项目设置更新成功！')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteProject(Number(projectId)),
    onSuccess: () => {
      navigate('/projects')
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    updateMutation.mutate(formData)
  }

  const handleDelete = () => {
    if (showDeleteConfirm) {
      deleteMutation.mutate()
    } else {
      setShowDeleteConfirm(true)
    }
  }

  if (isLoading) {
    return (
      <Layout>
        <div className="text-center py-16">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
        </div>
      </Layout>
    )
  }

  if (!project) {
    return (
      <Layout>
        <div className="text-center py-16">
          <h2 className="text-2xl font-bold mb-2">未找到项目</h2>
        </div>
      </Layout>
    )
  }

  return (
    <Layout>
      <div className="max-w-4xl mx-auto">
        <div className="mb-8">
          <button
            onClick={() => navigate(`/projects/${projectId}`)}
            className="text-blue-600 hover:underline mb-4"
          >
            ← 返回项目
          </button>
          <h1 className="text-3xl font-bold mb-2">项目设置</h1>
          <p className="text-gray-600">{project.github_repo_name}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* General Settings */}
          <div className="bg-white p-6 rounded-lg shadow-md">
            <h2 className="text-xl font-bold mb-4">常规</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">项目名称</label>
                <input
                  type="text"
                  required
                  className="w-full border rounded-lg px-3 py-2"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">项目标识</label>
                <input
                  type="text"
                  disabled
                  className="w-full border rounded-lg px-3 py-2 bg-gray-50 text-gray-600"
                  value={project.slug}
                />
                <p className="text-xs text-gray-500 mt-1">
                  项目标识创建后无法修改
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">默认域名</label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    disabled
                    className="flex-1 border rounded-lg px-3 py-2 bg-gray-50 text-gray-600"
                    value={project.default_domain}
                  />
                  <a
                    href={`https://${project.default_domain}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-4 py-2 bg-gray-100 rounded-lg hover:bg-gray-200 text-sm"
                  >
                    访问
                  </a>
                </div>
              </div>
            </div>
          </div>

          {/* Build Settings */}
          <div className="bg-white p-6 rounded-lg shadow-md">
            <h2 className="text-xl font-bold mb-4">
              {project.project_type === 'python' ? '部署配置' : '构建配置'}
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">
                  根目录（支持 Monorepo）
                </label>
                <input
                  type="text"
                  className="w-full border rounded-lg px-3 py-2 font-mono text-sm"
                  value={formData.root_directory}
                  onChange={(e) => setFormData({ ...formData, root_directory: e.target.value })}
                  placeholder="例如：frontend（单项目仓库留空）"
                />
                <p className="text-xs text-gray-500 mt-1">
                  包含项目文件的子目录
                </p>
              </div>

              {project.project_type === 'python' ? (
                <>
                  <div>
                    <label className="block text-sm font-medium mb-1">启动命令</label>
                    <input
                      type="text"
                      className="w-full border rounded-lg px-3 py-2 font-mono text-sm"
                      value={formData.start_command}
                      onChange={(e) => setFormData({ ...formData, start_command: e.target.value })}
                      placeholder="uvicorn main:app --host 0.0.0.0 --port 9000"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      应用必须监听端口 9000
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-1">Python 版本</label>
                    <select
                      className="w-full border rounded-lg px-3 py-2"
                      value={formData.python_version || '3.11'}
                      onChange={(e) => setFormData({ ...formData, python_version: e.target.value })}
                    >
                      <option value="3.9">3.9</option>
                      <option value="3.10">3.10</option>
                      <option value="3.11">3.11</option>
                      <option value="3.12">3.12</option>
                    </select>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <label className="block text-sm font-medium mb-1">构建命令</label>
                    <input
                      type="text"
                      required
                      className="w-full border rounded-lg px-3 py-2 font-mono text-sm"
                      value={formData.build_command}
                      onChange={(e) => setFormData({ ...formData, build_command: e.target.value })}
                      placeholder="npm run build"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-1">安装命令</label>
                    <input
                      type="text"
                      required
                      className="w-full border rounded-lg px-3 py-2 font-mono text-sm"
                      value={formData.install_command}
                      onChange={(e) => setFormData({ ...formData, install_command: e.target.value })}
                      placeholder="npm install"
                    />
                  </div>

                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium mb-1">输出目录</label>
                      <input
                        type="text"
                        required
                        className="w-full border rounded-lg px-3 py-2 font-mono text-sm"
                        value={formData.output_directory}
                        onChange={(e) =>
                          setFormData({ ...formData, output_directory: e.target.value })
                        }
                        placeholder="dist"
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
                </>
              )}
            </div>
          </div>

          {/* Git Settings */}
          <div className="bg-white p-6 rounded-lg shadow-md">
            <h2 className="text-xl font-bold mb-4">代码仓库</h2>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium mb-1">仓库</label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    disabled
                    className="flex-1 border rounded-lg px-3 py-2 bg-gray-50 text-gray-600"
                    value={project.github_repo_name}
                  />
                  <a
                    href={project.github_repo_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-4 py-2 bg-gray-100 rounded-lg hover:bg-gray-200 text-sm"
                  >
                    在 GitHub 查看
                  </a>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">默认分支</label>
                <input
                  type="text"
                  disabled
                  className="w-full border rounded-lg px-3 py-2 bg-gray-50 text-gray-600"
                  value={project.default_branch}
                />
              </div>
            </div>
          </div>

          {/* Environment Variables (shown for all project types, most useful for Python) */}
          <div className="bg-white p-6 rounded-lg shadow-md">
            <EnvironmentVariables projectId={Number(projectId)} />
          </div>

          {/* Custom Domains */}
          <div className="bg-white p-6 rounded-lg shadow-md">
            <DomainsManagement projectId={Number(projectId)} />
          </div>

          {/* Save Button */}
          <div className="flex justify-end">
            <button
              type="submit"
              className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              disabled={updateMutation.isPending}
            >
              {updateMutation.isPending ? '保存中...' : '保存更改'}
            </button>
          </div>

          {updateMutation.isError && (
            <div className="bg-red-50 text-red-800 p-3 rounded-lg text-sm">
              更新项目设置失败，请重试。
            </div>
          )}
        </form>

        {/* Danger Zone */}
        <div className="mt-8 bg-red-50 border border-red-200 p-6 rounded-lg">
          <h2 className="text-xl font-bold text-red-800 mb-2">危险操作</h2>
          <p className="text-sm text-red-700 mb-4">
            删除项目是永久性操作，无法撤销。所有部署和设置都将丢失。
          </p>
          {showDeleteConfirm && (
            <div className="mb-4 p-3 bg-red-100 border border-red-300 rounded-lg">
              <p className="text-sm text-red-800 font-semibold">
                确认操作？此操作无法撤销！
              </p>
            </div>
          )}
          <div className="flex gap-3">
            {showDeleteConfirm && (
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                取消
              </button>
            )}
            <button
              onClick={handleDelete}
              className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending
                ? '删除中...'
                : showDeleteConfirm
                ? '确认删除'
                : '删除项目'}
            </button>
          </div>
        </div>
      </div>
    </Layout>
  )
}
