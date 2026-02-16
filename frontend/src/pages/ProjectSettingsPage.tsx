import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'
import Layout from '../components/Layout'
import DomainsManagement from '../components/DomainsManagement'

export default function ProjectSettingsPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [formData, setFormData] = useState({
    name: '',
    build_command: '',
    install_command: '',
    output_directory: '',
    node_version: '18',
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
        build_command: project.build_command,
        install_command: project.install_command,
        output_directory: project.output_directory,
        node_version: project.node_version,
      })
    }
  }, [project])

  const updateMutation = useMutation({
    mutationFn: (data: any) => api.updateProject(Number(projectId), data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId] })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      alert('Project settings updated successfully!')
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
          <h2 className="text-2xl font-bold mb-2">Project not found</h2>
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
            ← Back to project
          </button>
          <h1 className="text-3xl font-bold mb-2">Project Settings</h1>
          <p className="text-gray-600">{project.github_repo_name}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* General Settings */}
          <div className="bg-white p-6 rounded-lg shadow-md">
            <h2 className="text-xl font-bold mb-4">General</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Project Name</label>
                <input
                  type="text"
                  required
                  className="w-full border rounded-lg px-3 py-2"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">Project Slug</label>
                <input
                  type="text"
                  disabled
                  className="w-full border rounded-lg px-3 py-2 bg-gray-50 text-gray-600"
                  value={project.slug}
                />
                <p className="text-xs text-gray-500 mt-1">
                  Slug cannot be changed after creation
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">Default Domain</label>
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
                    Visit
                  </a>
                </div>
              </div>
            </div>
          </div>

          {/* Build Settings */}
          <div className="bg-white p-6 rounded-lg shadow-md">
            <h2 className="text-xl font-bold mb-4">Build Configuration</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Build Command</label>
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
                <label className="block text-sm font-medium mb-1">Install Command</label>
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
                  <label className="block text-sm font-medium mb-1">Output Directory</label>
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
                  <label className="block text-sm font-medium mb-1">Node Version</label>
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
            </div>
          </div>

          {/* Git Settings */}
          <div className="bg-white p-6 rounded-lg shadow-md">
            <h2 className="text-xl font-bold mb-4">Git Repository</h2>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium mb-1">Repository</label>
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
                    View on GitHub
                  </a>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">Default Branch</label>
                <input
                  type="text"
                  disabled
                  className="w-full border rounded-lg px-3 py-2 bg-gray-50 text-gray-600"
                  value={project.default_branch}
                />
              </div>
            </div>
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
              {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
            </button>
          </div>

          {updateMutation.isError && (
            <div className="bg-red-50 text-red-800 p-3 rounded-lg text-sm">
              Failed to update project settings. Please try again.
            </div>
          )}
        </form>

        {/* Danger Zone */}
        <div className="mt-8 bg-red-50 border border-red-200 p-6 rounded-lg">
          <h2 className="text-xl font-bold text-red-800 mb-2">Danger Zone</h2>
          <p className="text-sm text-red-700 mb-4">
            Deleting a project is permanent and cannot be undone. All deployments and settings will
            be lost.
          </p>
          {showDeleteConfirm && (
            <div className="mb-4 p-3 bg-red-100 border border-red-300 rounded-lg">
              <p className="text-sm text-red-800 font-semibold">
                Are you sure? This action cannot be undone!
              </p>
            </div>
          )}
          <div className="flex gap-3">
            {showDeleteConfirm && (
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
            )}
            <button
              onClick={handleDelete}
              className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending
                ? 'Deleting...'
                : showDeleteConfirm
                ? 'Confirm Delete'
                : 'Delete Project'}
            </button>
          </div>
        </div>
      </div>
    </Layout>
  )
}
