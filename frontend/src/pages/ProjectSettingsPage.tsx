import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'
import Layout from '../components/Layout'
import { useToast } from '../components/Toast'
import DomainsManagement from '../components/DomainsManagement'
import EnvironmentVariables from '../components/EnvironmentVariables'
import { ArrowLeft, ExternalLink, AlertTriangle, FlaskConical } from 'lucide-react'

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
    is_spa: true,
    node_version: '18',
    python_version: '',
    start_command: '',
    python_framework: '',
  })

  const { toast } = useToast()
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [stagingEnabled, setStagingEnabled] = useState(false)
  const [stagingPassword, setStagingPassword] = useState('')

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
        is_spa: project.is_spa ?? true,
        node_version: project.node_version || '18',
        python_version: project.python_version || '',
        start_command: project.start_command || '',
        python_framework: project.python_framework || '',
      })
      setStagingEnabled(project.staging_enabled ?? false)
    }
  }, [project])

  const updateMutation = useMutation({
    mutationFn: (data: any) => api.updateProject(Number(projectId), data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId] })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      toast('项目设置更新成功！', 'success')
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
          <div className="animate-spin rounded-full h-10 w-10 border-2 border-accent border-t-transparent mx-auto"></div>
        </div>
      </Layout>
    )
  }

  if (!project) {
    return (
      <Layout>
        <div className="text-center py-16">
          <h2 className="text-xl font-semibold text-[--text-primary] mb-2">未找到项目</h2>
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
            className="flex items-center gap-1.5 text-sm text-accent hover:text-[--accent-hover] mb-4 font-medium"
          >
            <ArrowLeft size={16} />
            返回项目
          </button>
          <h1 className="text-2xl font-bold text-[--text-primary] mb-1">项目设置</h1>
          <p className="text-sm text-[--text-secondary]">{project.github_repo_name}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* General Settings */}
          <div className="card p-5">
            <h2 className="text-sm font-semibold text-[--text-primary] mb-4">常规</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[--text-secondary] mb-1">项目名称</label>
                <input
                  type="text"
                  required
                  className="input"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-[--text-secondary] mb-1">项目标识</label>
                <input
                  type="text"
                  disabled
                  className="input opacity-60 cursor-not-allowed"
                  value={project.slug}
                />
                <p className="text-xs text-[--text-tertiary] mt-1">
                  项目标识创建后无法修改
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-[--text-secondary] mb-1">默认域名</label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    disabled
                    className="input flex-1 opacity-60 cursor-not-allowed"
                    value={project.default_domain}
                  />
                  <a
                    href={`https://${project.default_domain}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-secondary text-sm flex items-center gap-1.5"
                  >
                    <ExternalLink size={14} />
                    访问
                  </a>
                </div>
              </div>
            </div>
          </div>

          {/* Build Settings */}
          <div className="card p-5">
            <h2 className="text-sm font-semibold text-[--text-primary] mb-4">
              {project.project_type === 'python' || project.project_type === 'node' ? '部署配置' : '构建配置'}
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[--text-secondary] mb-1">
                  根目录（支持 Monorepo）
                </label>
                <input
                  type="text"
                  className="input font-mono text-sm"
                  value={formData.root_directory}
                  onChange={(e) => setFormData({ ...formData, root_directory: e.target.value })}
                  placeholder="例如：frontend（单项目仓库留空）"
                />
                <p className="text-xs text-[--text-tertiary] mt-1">
                  包含项目文件的子目录
                </p>
              </div>

              {project.project_type === 'python' ? (
                <>
                  <div>
                    <label className="block text-sm font-medium text-[--text-secondary] mb-1">启动命令</label>
                    <input
                      type="text"
                      className="input font-mono text-sm"
                      value={formData.start_command}
                      onChange={(e) => setFormData({ ...formData, start_command: e.target.value })}
                      placeholder="uvicorn main:app --host 0.0.0.0 --port 9000"
                    />
                    <p className="text-xs text-[--text-tertiary] mt-1">
                      应用必须监听端口 9000
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-[--text-secondary] mb-1">Python 版本</label>
                    <select
                      className="input"
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
              ) : project.project_type === 'node' ? (
                <>
                  <div>
                    <label className="block text-sm font-medium text-[--text-secondary] mb-1">启动命令</label>
                    <input
                      type="text"
                      className="input font-mono text-sm"
                      value={formData.start_command}
                      onChange={(e) => setFormData({ ...formData, start_command: e.target.value })}
                      placeholder="npm start"
                    />
                    <p className="text-xs text-[--text-tertiary] mt-1">
                      应用必须监听端口 9000（通过 PORT 环境变量）
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-[--text-secondary] mb-1">安装命令</label>
                    <input
                      type="text"
                      className="input font-mono text-sm"
                      value={formData.install_command}
                      onChange={(e) => setFormData({ ...formData, install_command: e.target.value })}
                      placeholder="npm install"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-[--text-secondary] mb-1">构建命令（可选）</label>
                    <input
                      type="text"
                      className="input font-mono text-sm"
                      value={formData.build_command}
                      onChange={(e) => setFormData({ ...formData, build_command: e.target.value })}
                      placeholder="留空则跳过构建步骤"
                    />
                    <p className="text-xs text-[--text-tertiary] mt-1">
                      TypeScript 项目通常需要 npm run build
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-[--text-secondary] mb-1">Node 版本</label>
                    <select
                      className="input"
                      value={formData.node_version}
                      onChange={(e) => setFormData({ ...formData, node_version: e.target.value })}
                    >
                      <option value="18">18</option>
                      <option value="20">20</option>
                    </select>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <label className="block text-sm font-medium text-[--text-secondary] mb-1">构建命令</label>
                    <input
                      type="text"
                      required
                      className="input font-mono text-sm"
                      value={formData.build_command}
                      onChange={(e) => setFormData({ ...formData, build_command: e.target.value })}
                      placeholder="npm run build"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-[--text-secondary] mb-1">安装命令</label>
                    <input
                      type="text"
                      required
                      className="input font-mono text-sm"
                      value={formData.install_command}
                      onChange={(e) => setFormData({ ...formData, install_command: e.target.value })}
                      placeholder="npm install"
                    />
                  </div>

                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-[--text-secondary] mb-1">输出目录</label>
                      <input
                        type="text"
                        required
                        className="input font-mono text-sm"
                        value={formData.output_directory}
                        onChange={(e) =>
                          setFormData({ ...formData, output_directory: e.target.value })
                        }
                        placeholder="dist"
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

                  <div>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        className="w-4 h-4 rounded border-[--border] text-accent focus:ring-accent"
                        checked={formData.is_spa}
                        onChange={(e) =>
                          setFormData({ ...formData, is_spa: e.target.checked })
                        }
                      />
                      <span className="text-sm font-medium text-[--text-secondary]">单页应用 (SPA)</span>
                    </label>
                    <p className="text-xs text-[--text-tertiary] mt-1 ml-6">
                      开启后，所有路径将指向 index.html（适用于 React、Vue 等前端路由项目）
                    </p>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Git Settings */}
          <div className="card p-5">
            <h2 className="text-sm font-semibold text-[--text-primary] mb-4">代码仓库</h2>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-[--text-secondary] mb-1">仓库</label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    disabled
                    className="input flex-1 opacity-60 cursor-not-allowed"
                    value={project.github_repo_name}
                  />
                  <a
                    href={project.github_repo_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-secondary text-sm flex items-center gap-1.5"
                  >
                    <ExternalLink size={14} />
                    在 GitHub 查看
                  </a>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-[--text-secondary] mb-1">默认分支</label>
                <input
                  type="text"
                  disabled
                  className="input opacity-60 cursor-not-allowed"
                  value={project.default_branch}
                />
              </div>
            </div>
          </div>

          {/* Staging Environment */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <FlaskConical size={16} className="text-purple-600 dark:text-purple-400" />
              <h2 className="text-sm font-semibold text-[--text-primary]">Staging 环境</h2>
            </div>
            <div className="space-y-4">
              <div>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    className="w-4 h-4 rounded border-[--border] text-purple-600 focus:ring-purple-500"
                    checked={stagingEnabled}
                    onChange={(e) => {
                      const enabled = e.target.checked
                      setStagingEnabled(enabled)
                      api.updateProject(Number(projectId), { staging_enabled: enabled }).then(() => {
                        queryClient.invalidateQueries({ queryKey: ['project', projectId] })
                        toast(enabled ? 'Staging 环境已启用' : 'Staging 环境已关闭', 'success')
                      }).catch(() => {
                        setStagingEnabled(!enabled)
                        toast('更新失败，请重试', 'error')
                      })
                    }}
                  />
                  <span className="text-sm font-medium text-[--text-secondary]">启用 Staging 环境</span>
                </label>
                <p className="text-xs text-[--text-tertiary] mt-1 ml-6">
                  推送到 staging 分支时自动部署到独立的预览环境
                </p>
              </div>

              {stagingEnabled && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-[--text-secondary] mb-1">Staging 域名</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        disabled
                        className="input flex-1 opacity-60 cursor-not-allowed font-mono text-sm"
                        value={project?.staging_domain || `${project?.slug}-staging.metavm.tech`}
                      />
                      {project?.staging_domain && (
                        <a
                          href={`https://${project.staging_domain}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="btn-secondary text-sm flex items-center gap-1.5"
                        >
                          <ExternalLink size={14} />
                          访问
                        </a>
                      )}
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-[--text-secondary] mb-1">访问密码</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="password"
                        className="input flex-1 font-mono text-sm"
                        value={stagingPassword}
                        onChange={(e) => setStagingPassword(e.target.value)}
                        placeholder="设置密码以保护 Staging 环境"
                      />
                      <button
                        type="button"
                        className="btn-secondary text-sm"
                        disabled={!stagingPassword.trim()}
                        onClick={() => {
                          api.updateProject(Number(projectId), { staging_password: stagingPassword }).then(() => {
                            queryClient.invalidateQueries({ queryKey: ['project', projectId] })
                            toast('Staging 密码已更新', 'success')
                            setStagingPassword('')
                          }).catch(() => {
                            toast('更新失败，请重试', 'error')
                          })
                        }}
                      >
                        保存密码
                      </button>
                    </div>
                    <p className="text-xs text-[--text-tertiary] mt-1">
                      设置后，访问 Staging 站点需要输入密码。搜索引擎不会索引 Staging 页面。
                    </p>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Environment Variables */}
          <div className="card p-5">
            <EnvironmentVariables projectId={Number(projectId)} stagingEnabled={stagingEnabled} />
          </div>

          {/* Custom Domains */}
          <div className="card p-5">
            <DomainsManagement projectId={Number(projectId)} />
          </div>

          {/* Save Button */}
          <div className="flex justify-end">
            <button type="submit" className="btn-primary" disabled={updateMutation.isPending}>
              {updateMutation.isPending ? '保存中...' : '保存更改'}
            </button>
          </div>

          {updateMutation.isError && (
            <div className="p-3 rounded-lg text-sm bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-500/20">
              更新项目设置失败，请重试。
            </div>
          )}
        </form>

        {/* Danger Zone */}
        <div className="mt-8 card border-red-200 dark:border-red-500/30 p-5">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={18} className="text-red-500" />
            <h2 className="text-sm font-semibold text-red-600 dark:text-red-400">危险操作</h2>
          </div>
          <p className="text-sm text-[--text-secondary] mb-4">
            删除项目是永久性操作，无法撤销。所有部署和设置都将丢失。
          </p>
          {showDeleteConfirm && (
            <div className="mb-4 p-3 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-lg">
              <p className="text-sm text-red-700 dark:text-red-400 font-medium">
                确认操作？此操作无法撤销！
              </p>
            </div>
          )}
          <div className="flex gap-3">
            {showDeleteConfirm && (
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="btn-secondary text-sm"
              >
                取消
              </button>
            )}
            <button
              onClick={handleDelete}
              className="btn-danger text-sm"
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
