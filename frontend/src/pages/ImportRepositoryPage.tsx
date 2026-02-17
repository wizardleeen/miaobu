import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../services/api'
import Layout from '../components/Layout'

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
    if (repo.is_imported) return

    setSelectedRepo(repo)
    setAnalyzing(true)
    setAnalysis(null)
    setCustomConfig(null)

    try {
      const [owner, repoName] = repo.full_name.split('/')
      const result = await api.analyzeRepository(owner, repoName, repo.default_branch, rootDirectory)
      setAnalysis(result)

      // Initialize custom config with detected values
      setCustomConfig({
        name: result.repository.name,
        project_type: result.project_type || 'static',
        root_directory: result.root_directory || rootDirectory || '',
        // Static fields
        build_command: result.build_config.build_command || 'npm run build',
        install_command: result.build_config.install_command || 'npm install',
        output_directory: result.build_config.output_directory || 'dist',
        node_version: result.build_config.node_version || '18',
        // Python fields
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
      <div className="max-w-6xl mx-auto">
        {!selectedRepo ? (
          <>
            <div className="mb-8">
              <h1 className="text-3xl font-bold mb-2">导入仓库</h1>
              <p className="text-gray-600">选择一个 GitHub 仓库进行导入和部署</p>
            </div>

            <div className="mb-6 space-y-3">
              <input
                type="text"
                placeholder="搜索仓库..."
                className="w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-700">
                  根目录（用于 Monorepo）
                </label>
                <input
                  type="text"
                  placeholder="例如: frontend（单项目仓库留空）"
                  className="w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
                  value={rootDirectory}
                  onChange={(e) => setRootDirectory(e.target.value)}
                />
                <p className="text-xs text-gray-500 mt-1">
                  为 Monorepo 项目指定包含 package.json 的子目录
                </p>
              </div>
            </div>

            {isLoading ? (
              <div className="text-center py-16">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
              </div>
            ) : reposData?.repositories && reposData.repositories.length > 0 ? (
              <div className="grid gap-4">
                {reposData.repositories.map((repo: Repository) => (
                  <div
                    key={repo.id}
                    className={`bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition ${
                      repo.is_imported ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
                    }`}
                    onClick={() => handleSelectRepo(repo)}
                  >
                    <div className="flex justify-between items-start">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <h3 className="text-xl font-bold">{repo.name}</h3>
                          {repo.private && (
                            <span className="px-2 py-1 bg-yellow-100 text-yellow-800 text-xs rounded">
                              私有
                            </span>
                          )}
                          {repo.is_imported && (
                            <span className="px-2 py-1 bg-green-100 text-green-800 text-xs rounded">
                              已导入
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-gray-600 mb-2">{repo.full_name}</p>
                        {repo.description && (
                          <p className="text-gray-700 mb-3">{repo.description}</p>
                        )}
                        <div className="flex items-center gap-4 text-sm text-gray-500">
                          {repo.language && (
                            <span className="flex items-center gap-1">
                              <span className="w-3 h-3 rounded-full bg-blue-500"></span>
                              {repo.language}
                            </span>
                          )}
                          <span>分支: {repo.default_branch}</span>
                          <span>更新于 {new Date(repo.updated_at).toLocaleDateString()}</span>
                        </div>
                      </div>
                      {!repo.is_imported && (
                        <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                          选择
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-16 bg-white rounded-lg shadow-md">
                <p className="text-gray-600">未找到仓库</p>
              </div>
            )}
          </>
        ) : (
          <>
            <div className="mb-8">
              <button
                onClick={handleBack}
                className="text-blue-600 hover:underline mb-4"
              >
                ← 返回仓库列表
              </button>
              <h1 className="text-3xl font-bold mb-2">配置导入</h1>
              <p className="text-gray-600">{selectedRepo.full_name}</p>
            </div>

            {analyzing ? (
              <div className="text-center py-16 bg-white rounded-lg shadow-md">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                <p className="text-gray-600">正在分析仓库...</p>
              </div>
            ) : analysis && customConfig ? (
              <div className="space-y-6">
                {/* Detection Summary */}
                <div className="bg-white p-6 rounded-lg shadow-md">
                  <h2 className="text-xl font-bold mb-4">自动检测结果</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <label className="text-sm text-gray-600">项目类型</label>
                      <p className="font-semibold">
                        {analysis.project_type === 'python' ? (
                          <span className="inline-flex items-center gap-1.5">
                            <span className="w-3 h-3 rounded-full bg-blue-500 inline-block"></span>
                            Python 后端
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5">
                            <span className="w-3 h-3 rounded-full bg-green-500 inline-block"></span>
                            静态/前端
                          </span>
                        )}
                      </p>
                    </div>
                    <div>
                      <label className="text-sm text-gray-600">检测到的框架</label>
                      <p className="font-semibold capitalize">
                        {analysis.build_config.framework}
                        {analysis.build_config.confidence && (
                          <span className={`ml-2 text-xs px-2 py-1 rounded ${
                            analysis.build_config.confidence === 'high'
                              ? 'bg-green-100 text-green-800'
                              : analysis.build_config.confidence === 'medium'
                              ? 'bg-yellow-100 text-yellow-800'
                              : 'bg-red-100 text-red-800'
                          }`}>
                            {analysis.build_config.confidence === 'high' ? '高' : analysis.build_config.confidence === 'medium' ? '中' : '低'}置信度
                          </span>
                        )}
                      </p>
                    </div>
                    {analysis.project_type !== 'python' && (
                      <div>
                        <label className="text-sm text-gray-600">包管理器</label>
                        <p className="font-semibold">{analysis.build_config.package_manager}</p>
                      </div>
                    )}
                  </div>
                  {analysis.build_config.note && (
                    <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                      <p className="text-sm text-yellow-800">⚠️ {analysis.build_config.note}</p>
                    </div>
                  )}
                </div>

                {/* Configuration Form */}
                <div className="bg-white p-6 rounded-lg shadow-md">
                  <h2 className="text-xl font-bold mb-4">
                    {customConfig.project_type === 'python' ? 'Python 部署配置' : '构建配置'}
                  </h2>
                  <p className="text-sm text-gray-600 mb-4">
                    检查并自定义自动检测的设置
                  </p>

                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium mb-1">项目名称</label>
                      <input
                        type="text"
                        className="w-full border rounded-lg px-3 py-2"
                        value={customConfig.name}
                        onChange={(e) =>
                          setCustomConfig({ ...customConfig, name: e.target.value })
                        }
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium mb-1">项目类型</label>
                      <select
                        className="w-full border rounded-lg px-3 py-2"
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
                      <label className="block text-sm font-medium mb-1">
                        根目录（Monorepo 支持）
                      </label>
                      <input
                        type="text"
                        className="w-full border rounded-lg px-3 py-2 font-mono text-sm"
                        placeholder="例如: frontend（单项目仓库留空）"
                        value={customConfig.root_directory || ''}
                        onChange={(e) =>
                          setCustomConfig({ ...customConfig, root_directory: e.target.value })
                        }
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        包含项目文件的子目录
                      </p>
                    </div>

                    {customConfig.project_type === 'python' ? (
                      <>
                        <div>
                          <label className="block text-sm font-medium mb-1">启动命令</label>
                          <input
                            type="text"
                            className="w-full border rounded-lg px-3 py-2 font-mono text-sm"
                            placeholder="uvicorn main:app --host 0.0.0.0 --port 9000"
                            value={customConfig.start_command || ''}
                            onChange={(e) =>
                              setCustomConfig({ ...customConfig, start_command: e.target.value })
                            }
                          />
                          <p className="text-xs text-gray-500 mt-1">
                            应用必须监听端口 9000
                          </p>
                        </div>

                        <div>
                          <label className="block text-sm font-medium mb-1">Python 版本</label>
                          <select
                            className="w-full border rounded-lg px-3 py-2"
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
                          <label className="block text-sm font-medium mb-1">构建命令</label>
                          <input
                            type="text"
                            className="w-full border rounded-lg px-3 py-2 font-mono text-sm"
                            value={customConfig.build_command}
                            onChange={(e) =>
                              setCustomConfig({ ...customConfig, build_command: e.target.value })
                            }
                          />
                        </div>

                        <div>
                          <label className="block text-sm font-medium mb-1">安装命令</label>
                          <input
                            type="text"
                            className="w-full border rounded-lg px-3 py-2 font-mono text-sm"
                            value={customConfig.install_command}
                            onChange={(e) =>
                              setCustomConfig({ ...customConfig, install_command: e.target.value })
                            }
                          />
                        </div>

                        <div className="grid md:grid-cols-2 gap-4">
                          <div>
                            <label className="block text-sm font-medium mb-1">输出目录</label>
                            <input
                              type="text"
                              className="w-full border rounded-lg px-3 py-2 font-mono text-sm"
                              value={customConfig.output_directory}
                              onChange={(e) =>
                                setCustomConfig({ ...customConfig, output_directory: e.target.value })
                              }
                            />
                          </div>

                          <div>
                            <label className="block text-sm font-medium mb-1">Node 版本</label>
                            <select
                              className="w-full border rounded-lg px-3 py-2"
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
                      </>
                    )}
                  </div>
                </div>

                {/* Repository Structure Info */}
                {analysis.repo_structure && (
                  <div className="bg-white p-6 rounded-lg shadow-md">
                    <h2 className="text-xl font-bold mb-4">仓库详情</h2>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      <div>
                        <span className="text-gray-600">TypeScript:</span>
                        <span className="ml-2 font-semibold">
                          {analysis.repo_structure.has_typescript ? '✓ 是' : '✗ 否'}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-600">测试:</span>
                        <span className="ml-2 font-semibold">
                          {analysis.repo_structure.has_tests ? '✓ 是' : '✗ 否'}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-600">Docker:</span>
                        <span className="ml-2 font-semibold">
                          {analysis.repo_structure.has_docker ? '✓ 是' : '✗ 否'}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-600">锁文件:</span>
                        <span className="ml-2 font-semibold">
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
                    className="px-6 py-3 border rounded-lg hover:bg-gray-50"
                    disabled={importMutation.isPending}
                  >
                    取消
                  </button>
                  <button
                    onClick={handleImport}
                    className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                    disabled={importMutation.isPending}
                  >
                    {importMutation.isPending ? '正在导入...' : '导入仓库'}
                  </button>
                </div>

                {importMutation.isError && (
                  <div className="bg-red-50 text-red-800 p-3 rounded-lg text-sm">
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
