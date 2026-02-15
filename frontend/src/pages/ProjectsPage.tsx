import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../services/api'
import Layout from '../components/Layout'
import CreateProjectModal from '../components/CreateProjectModal'

export default function ProjectsPage() {
  const navigate = useNavigate()
  const [isModalOpen, setIsModalOpen] = useState(false)
  const { data: projects, isLoading, refetch } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.getProjects(),
  })

  return (
    <Layout>
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold mb-2">Projects</h1>
          <p className="text-gray-600">Manage your deployed projects</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setIsModalOpen(true)}
            className="border border-gray-300 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-50 transition"
          >
            Manual Import
          </button>
          <button
            onClick={() => navigate('/projects/import')}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition"
          >
            + Import from GitHub
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-center py-16">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
        </div>
      ) : projects && projects.length > 0 ? (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects.map((project: any) => (
            <Link
              key={project.id}
              to={`/projects/${project.id}`}
              className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition"
            >
              <h3 className="text-xl font-bold mb-2">{project.name}</h3>
              <p className="text-sm text-gray-600 mb-4">{project.github_repo_name}</p>
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <span>🌐</span>
                <span className="truncate">{project.default_domain}</span>
              </div>
              <div className="mt-4 pt-4 border-t text-sm text-gray-500">
                Updated {new Date(project.updated_at).toLocaleDateString()}
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <div className="text-center py-16 bg-white rounded-lg shadow-md">
          <div className="text-6xl mb-4">📦</div>
          <h2 className="text-2xl font-bold mb-2">No projects yet</h2>
          <p className="text-gray-600 mb-6">Import your first project from GitHub to get started</p>
          <button
            onClick={() => navigate('/projects/import')}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition"
          >
            Import from GitHub
          </button>
        </div>
      )}

      <CreateProjectModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSuccess={() => {
          setIsModalOpen(false)
          refetch()
        }}
      />
    </Layout>
  )
}
