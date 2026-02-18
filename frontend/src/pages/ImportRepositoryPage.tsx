import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../services/api'
import Layout from '../components/Layout'
import { Search, ArrowLeft, AlertTriangle, Check, X } from 'lucide-react'

interface Repository {
  id: number
  name: string
  full_name: string
  html_url: string
  description: string | null
  language: string | null
  default_branch: string
  private: boolean
  updated_at: string
  is_imported: boolean
}

export default function ImportRepositoryPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [selectedRepo, setSelectedRepo] = useState<Repository | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<any>(null)
  const [customConfig, setCustomConfig] = useState<any>(null)
  const [rootDirectory, setRootDirectory] = useState('')

  const { data: reposData, isLoading } = useQuery({
    queryKey: ['repositories', search],
    queryFn: () => api.listRepositories(1, 30, search || undefined),
  })

  const importMutation = useMutation({
    mutationFn: ({ owner, repo, branch, rootDir, config }: any) =>
      api.importRepository(owner, repo, branch, rootDir, config),
    onSuccess: (data) => {
      navigate(`/projects/${data.project.id}`)
    },
  })

  const handleSelectRepo = async (repo: Repository) => {

    setSelectedRepo(repo)
    setAnalyzing(true)
    setAnalysis(null)
    setCustomConfig(null)

    try {
      const [owner, repoName] = repo.full_name.split('/')
      const result = await api.analyzeRepository(owner, repoName, repo.default_branch, rootDirectory)
      setAnalysis(result)

      setCustomConfig({
        name: result.repository.name,
        project_type: result.project_type || 'static',
        root_directory: result.root_directory || rootDirectory || '',
        build_command: result.build_config.build_command || 'npm run build',
        install_command: result.build_config.install_command || 'npm install',
        output_directory: result.build_config.output_directory || 'dist',
        node_version: result.build_config.node_version || '18',
        is_spa: result.build_config.is_spa ?? true,
        python_version: result.build_config.python_version || '3.11',
        start_command: result.build_config.start_command || '',
        python_framework: result.build_config.python_framework || '',
      })
    } catch (error) {
      console.error('Failed to analyze repository:', error)
      alert('分析仓库失败，请重试。')
      setSelectedRepo(null)
    } finally {
      setAnalyzing(false)
    }
  }

  const handleImport = () => {
    if (!selectedRepo || !analysis) return

    const [owner, repo] = selectedRepo.full_name.split('/')
    importMutation.mutate({
      owner,
      repo,
      branch: selectedRepo.default_branch,
      rootDir: customConfig?.root_directory || '',
      config: customConfig,
    })
  }

  const handleBack = () => {
    setSelectedRepo(null)
    setAnalysis(null)
    setCustomConfig(null)
  }

  return (
    <Layout>
      <div className="max-w-5xl mx-auto">
        {!selectedRepo ? (
          <>
            <div className="mb-8">
              <h1 className="text-2xl font-bold text-[--text-primary] mb-1">导入仓库</h1>
              <p className="text-sm text-[--text-secondary]">选择一个 GitHub 仓库进行导入和部署</p>
            </div>

            <div className="mb-6 space-y-3">
              <div className="relative">
                <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-[--text-tertiary]" />
                <input
                  type="text"
                  placeholder="搜索仓库..."
                  className="input pl-10"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[--text-secondary] mb-1">
                  根目录（用于 Monorepo）
                </label>
                <input
                  type="text"
                  placeholder="例如: frontend（单项目仓库留空）"
                  className="input font-mono text-sm"
                  value={rootDirectory}
                  onChange={(e) => setRootDirectory(e.target.value)}
                />
                <p className="text-xs text-[--text-tertiary] mt-1">
                  为 Monorepo 项目指定包含 package.json 的子目录
                </p>
              </div>
            </div>

            {isLoading ? (
              <div className="text-center py-16">
                <div className="animate-spin rounded-full h-10 w-10 border-2 border-accent border-t-transparent mx-auto"></div>
              </div>
            ) : reposData?.repositories && reposData.repositories.length > 0 ? (
              <div className="space-y-3">
                {reposData.repositories.map((repo: Repository) => (
                  <div
                    key={repo.id}
                    className="card p-5 transition-colors cursor-pointer hover:border-accent/50"
                    onClick={() => handleSelectRepo(repo)}
                  >
                    <div className="flex justify-between items-start">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="text-base font-semibold text-[--text-primary]">{repo.name}</h3>
                          {repo.private && (
                            <span className="badge-warning">私有</span>
                          )}
                          {repo.is_imported && (
                            <span className="badge-success">已导入</span>
                          )}
                        </div>
                        <p className="text-sm text-[--text-secondary] mb-1.5">{repo.full_name}</p>
                        {repo.description && (
                          <p className="text-sm text-[--text-primary] mb-2">{repo.description}</p>
                        )}
                        <div className="flex items-center gap-4 text-xs text-[--text-tertiary]">
                          {repo.language && (
                            <span className="flex items-center gap-1.5">
                              <span className="w-2.5 h-2.5 rounded-full bg-accent"></span>
                              {repo.language}
                            </span>
                          )}
                          <span>分支: {repo.default_branch}</span>
                          <span>更新于 {new Date(repo.updated_at).toLocaleDateString()}</span>
                        </div>
                      </div>
                      <button className="btn-primary text-sm">选择</button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="card text-center py-16">
                <p className="text-[--text-secondary]">未找到仓库</p>
              </div>
            )}
          </>
        ) : (
          <>
            <div className="mb-8">
              <button
                onClick={handleBack}
                className="flex items-center gap-1.5 text-sm text-accent hover:text-[--accent-hover] mb-4 font-medium"
              >
                <ArrowLeft size={16} />
                返回仓库列表
              </button>
              <h1 className="text-2xl font-bold text-[--text-primary] mb-1">配置导入</h1>
              <p className="text-sm text-[--text-secondary]">{selectedRepo.full_name}</p>
            </div>

            {analyzing ? (
              <div className="card text-center py-16">
                <div className="animate-spin rounded-full h-10 w-10 border-2 border-accent border-t-transparent mx-auto mb-4"></div>
                <p className="text-[--text-secondary]">正在分析仓库...</p>
              </div>
            ) : analysis && customConfig ? (
              <div className="space-y-4">
                {/* Detection Summary */}
                <div className="card p-5">
                  <h2 className="text-sm font-semibold text-[--text-primary] mb-4">自动检测结果</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <label className="text-xs text-[--text-tertiary]">项目类型</label>
                      <p className="font-medium text-sm text-[--text-primary] mt-0.5">
                        {analysis.project_type === 'python' ? (
                          <span className="inline-flex items-center gap-1.5">
                            <span className="w-2.5 h-2.5 rounded-full bg-blue-500 inline-block"></span>
                            Python 后端
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5">
                            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block"></span>
                            静态/前端
                          </span>
                        )}
                      </p>
                    </div>
                    <div>
                      <label className="text-xs text-[--text-tertiary]">检测到的框架</label>
                      <p className="font-medium text-sm text-[--text-primary] capitalize mt-0.5">
                        {analysis.build_config.framework}
                        {analysis.build_config.confidence && (
                          <span className={`ml-2 ${
                            analysis.build_config.confidence === 'high'
                              ? 'badge-success'
                              : analysis.build_config.confidence === 'medium'
                              ? 'badge-warning'
                              : 'badge-error'
                          }`}>
                            {analysis.build_config.confidence === 'high' ? '高' : analysis.build_config.confidence === 'medium' ? '中' : '低'}置信度
                          </span>
                        )}
                      </p>
                    </div>
                    {analysis.project_type !== 'python' && (
                      <div>
                        <label className="text-xs text-[--text-tertiary]">包管理器</label>
                        <p className="font-medium text-sm text-[--text-primary] mt-0.5">{analysis.build_config.package_manager}</p>
                      </div>
                    )}
                  </div>
                  {analysis.build_config.note && (
                    <div className="mt-4 p-3 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-lg flex items-start gap-2">
                      <AlertTriangle size={16} className="text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                      <p className="text-sm text-amber-800 dark:text-amber-300">{analysis.build_config.note}</p>
                    </div>
                  )}
                </div>

                {/* Configuration Form */}
                <div className="card p-5">
                  <h2 className="text-sm font-semibold text-[--text-primary] mb-1">
                    {customConfig.project_type === 'python' ? 'Python 部署配置' : '构建配置'}
                  </h2>
                  <p className="text-xs text-[--text-secondary] mb-4">
                    检查并自定义自动检测的设置
                  </p>

                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-[--text-secondary] mb-1">项目名称</label>
                      <input
                        type="text"
                        className="input"
                        value={customConfig.name}
                        onChange={(e) =>
                          setCustomConfig({ ...customConfig, name: e.target.value })
                        }
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-[--text-secondary] mb-1">项目类型</label>
                      <select
                        className="input"
                        value={customConfig.project_type}
                        onChange={(e) =>
                          setCustomConfig({ ...customConfig, project_type: e.target.value })
                        }
                      >
                        <option value="static">静态/前端 (Node.js)</option>
                        <option value="python">Python 后端</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-[--text-secondary] mb-1">
                        根目录（Monorepo 支持）
                      </label>
                      <input
                        type="text"
                        className="input font-mono text-sm"
                        placeholder="例如: frontend（单项目仓库留空）"
                        value={customConfig.root_directory || ''}
                        onChange={(e) =>
                          setCustomConfig({ ...customConfig, root_directory: e.target.value })
                        }
                      />
                      <p className="text-xs text-[--text-tertiary] mt-1">
                        包含项目文件的子目录
                      </p>
                    </div>

                    {customConfig.project_type === 'python' ? (
                      <>
                        <div>
                          <label className="block text-sm font-medium text-[--text-secondary] mb-1">启动命令</label>
                          <input
                            type="text"
                            className="input font-mono text-sm"
                            placeholder="uvicorn main:app --host 0.0.0.0 --port 9000"
                            value={customConfig.start_command || ''}
                            onChange={(e) =>
                              setCustomConfig({ ...customConfig, start_command: e.target.value })
                            }
                          />
                          <p className="text-xs text-[--text-tertiary] mt-1">
                            应用必须监听端口 9000
                          </p>
                        </div>

                        <div>
                          <label className="block text-sm font-medium text-[--text-secondary] mb-1">Python 版本</label>
                          <select
                            className="input"
                            value={customConfig.python_version || '3.11'}
                            onChange={(e) =>
                              setCustomConfig({ ...customConfig, python_version: e.target.value })
                            }
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
                          <label className="block text-sm font-medium text-[--text-secondary] mb-1">构建命令</label>
                          <input
                            type="text"
                            className="input font-mono text-sm"
                            value={customConfig.build_command}
                            onChange={(e) =>
                              setCustomConfig({ ...customConfig, build_command: e.target.value })
                            }
                          />
                        </div>

                        <div>
                          <label className="block text-sm font-medium text-[--text-secondary] mb-1">安装命令</label>
                          <input
                            type="text"
                            className="input font-mono text-sm"
                            value={customConfig.install_command}
                            onChange={(e) =>
                              setCustomConfig({ ...customConfig, install_command: e.target.value })
                            }
                          />
                        </div>

                        <div className="grid md:grid-cols-2 gap-4">
                          <div>
                            <label className="block text-sm font-medium text-[--text-secondary] mb-1">输出目录</label>
                            <input
                              type="text"
                              className="input font-mono text-sm"
                              value={customConfig.output_directory}
                              onChange={(e) =>
                                setCustomConfig({ ...customConfig, output_directory: e.target.value })
                              }
                            />
                          </div>

                          <div>
                            <label className="block text-sm font-medium text-[--text-secondary] mb-1">Node 版本</label>
                            <select
                              className="input"
                              value={customConfig.node_version}
                              onChange={(e) =>
                                setCustomConfig({ ...customConfig, node_version: e.target.value })
                              }
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
                              checked={customConfig.is_spa}
                              onChange={(e) =>
                                setCustomConfig({ ...customConfig, is_spa: e.target.checked })
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

                {/* Repository Structure Info */}
                {analysis.repo_structure && (
                  <div className="card p-5">
                    <h2 className="text-sm font-semibold text-[--text-primary] mb-4">仓库详情</h2>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      {[
                        { label: 'TypeScript', value: analysis.repo_structure.has_typescript },
                        { label: '测试', value: analysis.repo_structure.has_tests },
                        { label: 'Docker', value: analysis.repo_structure.has_docker },
                      ].map((item) => (
                        <div key={item.label} className="flex items-center gap-2">
                          <span className="text-[--text-tertiary]">{item.label}:</span>
                          {item.value ? (
                            <Check size={14} className="text-emerald-500" />
                          ) : (
                            <X size={14} className="text-[--text-tertiary]" />
                          )}
                        </div>
                      ))}
                      <div>
                        <span className="text-[--text-tertiary]">锁文件:</span>
                        <span className="ml-2 font-medium text-[--text-primary]">
                          {analysis.repo_structure.lock_file || '无'}
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Import Button */}
                <div className="flex justify-end gap-3">
                  <button
                    onClick={handleBack}
                    className="btn-secondary"
                    disabled={importMutation.isPending}
                  >
                    取消
                  </button>
                  <button
                    onClick={handleImport}
                    className="btn-primary"
                    disabled={importMutation.isPending}
                  >
                    {importMutation.isPending ? '正在导入...' : '导入仓库'}
                  </button>
                </div>

                {importMutation.isError && (
                  <div className="p-3 rounded-lg text-sm bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-500/20">
                    导入仓库失败，请重试。
                  </div>
                )}
              </div>
            ) : null}
          </>
        )}
      </div>
    </Layout>
  )
}
