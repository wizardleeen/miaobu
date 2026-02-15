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

  const { data: reposData, isLoading, refetch } = useQuery({
    queryKey: ['repositories', search],
    queryFn: () => api.listRepositories(1, 30, search || undefined),
  })

  const importMutation = useMutation({
    mutationFn: ({ owner, repo, branch, config }: any) =>
      api.importRepository(owner, repo, branch, config),
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
      const result = await api.analyzeRepository(owner, repoName, repo.default_branch)
      setAnalysis(result)

      // Initialize custom config with detected values
      setCustomConfig({
        name: result.repository.name,
        build_command: result.build_config.build_command,
        install_command: result.build_config.install_command,
        output_directory: result.build_config.output_directory,
        node_version: result.build_config.node_version,
      })
    } catch (error) {
      console.error('Failed to analyze repository:', error)
      alert('Failed to analyze repository. Please try again.')
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
              <h1 className="text-3xl font-bold mb-2">Import Repository</h1>
              <p className="text-gray-600">Select a GitHub repository to import and deploy</p>
            </div>

            <div className="mb-6">
              <input
                type="text"
                placeholder="Search repositories..."
                className="w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
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
                              Private
                            </span>
                          )}
                          {repo.is_imported && (
                            <span className="px-2 py-1 bg-green-100 text-green-800 text-xs rounded">
                              Already Imported
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
                          <span>Branch: {repo.default_branch}</span>
                          <span>Updated {new Date(repo.updated_at).toLocaleDateString()}</span>
                        </div>
                      </div>
                      {!repo.is_imported && (
                        <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                          Select
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-16 bg-white rounded-lg shadow-md">
                <p className="text-gray-600">No repositories found</p>
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
                ← Back to repositories
              </button>
              <h1 className="text-3xl font-bold mb-2">Configure Import</h1>
              <p className="text-gray-600">{selectedRepo.full_name}</p>
            </div>

            {analyzing ? (
              <div className="text-center py-16 bg-white rounded-lg shadow-md">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                <p className="text-gray-600">Analyzing repository...</p>
              </div>
            ) : analysis && customConfig ? (
              <div className="space-y-6">
                {/* Detection Summary */}
                <div className="bg-white p-6 rounded-lg shadow-md">
                  <h2 className="text-xl font-bold mb-4">Auto-Detection Results</h2>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <label className="text-sm text-gray-600">Detected Framework</label>
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
                            {analysis.build_config.confidence} confidence
                          </span>
                        )}
                      </p>
                    </div>
                    <div>
                      <label className="text-sm text-gray-600">Package Manager</label>
                      <p className="font-semibold">{analysis.build_config.package_manager}</p>
                    </div>
                  </div>
                  {analysis.build_config.note && (
                    <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                      <p className="text-sm text-yellow-800">⚠️ {analysis.build_config.note}</p>
                    </div>
                  )}
                </div>

                {/* Configuration Form */}
                <div className="bg-white p-6 rounded-lg shadow-md">
                  <h2 className="text-xl font-bold mb-4">Build Configuration</h2>
                  <p className="text-sm text-gray-600 mb-4">
                    Review and customize the auto-detected settings
                  </p>

                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium mb-1">Project Name</label>
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
                      <label className="block text-sm font-medium mb-1">Build Command</label>
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
                      <label className="block text-sm font-medium mb-1">Install Command</label>
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
                        <label className="block text-sm font-medium mb-1">Output Directory</label>
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
                        <label className="block text-sm font-medium mb-1">Node Version</label>
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
                  </div>
                </div>

                {/* Repository Structure Info */}
                {analysis.repo_structure && (
                  <div className="bg-white p-6 rounded-lg shadow-md">
                    <h2 className="text-xl font-bold mb-4">Repository Details</h2>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      <div>
                        <span className="text-gray-600">TypeScript:</span>
                        <span className="ml-2 font-semibold">
                          {analysis.repo_structure.has_typescript ? '✓ Yes' : '✗ No'}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-600">Tests:</span>
                        <span className="ml-2 font-semibold">
                          {analysis.repo_structure.has_tests ? '✓ Yes' : '✗ No'}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-600">Docker:</span>
                        <span className="ml-2 font-semibold">
                          {analysis.repo_structure.has_docker ? '✓ Yes' : '✗ No'}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-600">Lock File:</span>
                        <span className="ml-2 font-semibold">
                          {analysis.repo_structure.lock_file || 'None'}
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
                    Cancel
                  </button>
                  <button
                    onClick={handleImport}
                    className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                    disabled={importMutation.isPending}
                  >
                    {importMutation.isPending ? 'Importing...' : 'Import Repository'}
                  </button>
                </div>

                {importMutation.isError && (
                  <div className="bg-red-50 text-red-800 p-3 rounded-lg text-sm">
                    Failed to import repository. Please try again.
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
