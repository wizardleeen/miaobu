import axios, { AxiosInstance } from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

class ApiService {
  private client: AxiosInstance

  constructor() {
    this.client = axios.create({
      baseURL: `${API_URL}/api/v1`,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    // Add auth token to requests
    this.client.interceptors.request.use((config) => {
      const token = localStorage.getItem('token')
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
      return config
    })

    // Handle auth errors
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          localStorage.removeItem('token')
          localStorage.removeItem('user')
          window.location.href = '/login'
        }
        return Promise.reject(error)
      }
    )
  }

  // Auth endpoints
  async getGitHubLoginUrl() {
    const response = await this.client.get('/auth/github/login')
    return response.data
  }

  async handleGitHubCallback(code: string, state: string) {
    const response = await this.client.get('/auth/github/callback', {
      params: { code, state },
    })
    return response.data
  }

  async getCurrentUser() {
    const response = await this.client.get('/auth/me')
    return response.data
  }

  // Project endpoints
  async getProjects() {
    const response = await this.client.get('/projects')
    return response.data
  }

  async getProject(projectId: number) {
    const response = await this.client.get(`/projects/${projectId}`)
    return response.data
  }

  async getProjectBySlug(slug: string) {
    const response = await this.client.get(`/projects/slug/${slug}`)
    return response.data
  }

  async createProject(data: any) {
    const response = await this.client.post('/projects', data)
    return response.data
  }

  async updateProject(projectId: number, data: any) {
    const response = await this.client.patch(`/projects/${projectId}`, data)
    return response.data
  }

  async deleteProject(projectId: number) {
    await this.client.delete(`/projects/${projectId}`)
  }

  // Deployment endpoints
  async getDeployments(projectId: number) {
    const response = await this.client.get(`/deployments/project/${projectId}`)
    return response.data
  }

  async getDeployment(deploymentId: number) {
    const response = await this.client.get(`/deployments/${deploymentId}`)
    return response.data
  }

  async createDeployment(data: any) {
    const response = await this.client.post('/deployments', data)
    return response.data
  }

  async getDeploymentLogs(deploymentId: number) {
    const response = await this.client.get(`/deployments/${deploymentId}/logs`)
    return response.data
  }

  async triggerDeployment(projectId: number, branch?: string) {
    const response = await this.client.post(`/projects/${projectId}/deploy`, {
      branch,
    })
    return response.data
  }

  async cancelDeployment(deploymentId: number) {
    const response = await this.client.post(`/deployments/${deploymentId}/cancel`)
    return response.data
  }

  // Repository endpoints
  async listRepositories(page: number = 1, perPage: number = 30, search?: string) {
    const response = await this.client.get('/repositories', {
      params: { page, per_page: perPage, search },
    })
    return response.data
  }

  async analyzeRepository(owner: string, repo: string, branch?: string) {
    const response = await this.client.get(`/repositories/${owner}/${repo}/analyze`, {
      params: { branch },
    })
    return response.data
  }

  async importRepository(owner: string, repo: string, branch?: string, customConfig?: any) {
    const response = await this.client.post(`/repositories/${owner}/${repo}/import`, {
      branch,
      custom_config: customConfig,
    })
    return response.data
  }

  // Custom Domain endpoints
  async listDomains(projectId?: number) {
    const response = await this.client.get('/domains', {
      params: projectId ? { project_id: projectId } : {},
    })
    return response.data
  }

  async getDomain(domainId: number) {
    const response = await this.client.get(`/domains/${domainId}`)
    return response.data
  }

  async createDomain(projectId: number, domain: string) {
    const response = await this.client.post('/domains', {
      project_id: projectId,
      domain,
    })
    return response.data
  }

  async verifyDomain(domainId: number) {
    const response = await this.client.post(`/domains/${domainId}/verify`)
    return response.data
  }

  async checkDomainDNS(domainId: number) {
    const response = await this.client.post(`/domains/${domainId}/check-dns`)
    return response.data
  }

  async getDNSInstructions(domainId: number) {
    const response = await this.client.get(`/domains/${domainId}/dns-instructions`)
    return response.data
  }

  async deleteDomain(domainId: number) {
    await this.client.delete(`/domains/${domainId}`)
  }

  // SSL Certificate endpoints
  async issueSSL(domainId: number, useStaging: boolean = false) {
    const response = await this.client.post(`/domains/${domainId}/issue-ssl`, {
      use_staging: useStaging,
    })
    return response.data
  }

  async renewSSL(domainId: number, force: boolean = false) {
    const response = await this.client.post(`/domains/${domainId}/renew-ssl`, {
      force,
    })
    return response.data
  }

  async getSSLStatus(domainId: number) {
    const response = await this.client.get(`/domains/${domainId}/ssl-status`)
    return response.data
  }
}

export const api = new ApiService()
