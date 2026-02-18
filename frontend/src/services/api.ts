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
  async listRepositories(page: number = 1, perPage: number = 30, search?: string, rootDirectory?: string) {
    const response = await this.client.get('/repositories', {
      params: { page, per_page: perPage, search, root_directory: rootDirectory || undefined },
    })
    return response.data
  }

  async analyzeRepository(owner: string, repo: string, branch?: string, rootDirectory?: string) {
    const response = await this.client.get(`/repositories/${owner}/${repo}/analyze`, {
      params: { branch, root_directory: rootDirectory },
    })
    return response.data
  }

  async importRepository(owner: string, repo: string, branch?: string, rootDirectory?: string, customConfig?: any, environmentVariables?: { key: string; value: string; is_secret: boolean }[]) {
    const response = await this.client.post(`/repositories/${owner}/${repo}/import`, {
      branch,
      root_directory: rootDirectory,
      custom_config: customConfig,
      environment_variables: environmentVariables?.length ? environmentVariables : undefined,
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

  // ESA Domain Management endpoints
  async getDomainStatus(domainId: number) {
    const response = await this.client.get(`/domains/${domainId}/status`)
    return response.data
  }

  async getDomainDeployments(domainId: number) {
    const response = await this.client.get(`/domains/${domainId}/deployments`)
    return response.data
  }

  async promoteDeployment(domainId: number, deploymentId: number) {
    const response = await this.client.post(`/domains/${domainId}/promote-deployment`, {
      deployment_id: deploymentId,
    })
    return response.data
  }

  async updateDomainSettings(domainId: number, settings: { auto_update_enabled?: boolean }) {
    const response = await this.client.post(`/domains/${domainId}/settings`, settings)
    return response.data
  }

  async syncEdgeKV(domainId: number) {
    const response = await this.client.post(`/domains/${domainId}/sync-edge-kv`)
    return response.data
  }

  async refreshSSLStatus(domainId: number) {
    const response = await this.client.post(`/domains/${domainId}/refresh-ssl-status`)
    return response.data
  }

  // Environment Variable endpoints
  async listEnvVars(projectId: number) {
    const response = await this.client.get(`/projects/${projectId}/env`)
    return response.data
  }

  async createEnvVar(projectId: number, data: { key: string; value: string; is_secret: boolean }) {
    const response = await this.client.post(`/projects/${projectId}/env`, data)
    return response.data
  }

  async updateEnvVar(projectId: number, varId: number, data: { key?: string; value?: string; is_secret?: boolean }) {
    const response = await this.client.patch(`/projects/${projectId}/env/${varId}`, data)
    return response.data
  }

  async deleteEnvVar(projectId: number, varId: number) {
    await this.client.delete(`/projects/${projectId}/env/${varId}`)
  }

  // Legacy SSL Certificate endpoints (deprecated - ESA handles SSL automatically)
  // Kept for backward compatibility, but these endpoints no longer exist
  async issueSSL(_domainId: number, _useStaging: boolean = false) {
    console.warn('issueSSL is deprecated - ESA handles SSL automatically')
    return { success: false, message: 'SSL is now automatic via ESA' }
  }

  async renewSSL(_domainId: number, _force: boolean = false) {
    console.warn('renewSSL is deprecated - ESA handles SSL automatically')
    return { success: false, message: 'SSL is now automatic via ESA' }
  }

  async getSSLStatus(domainId: number) {
    console.warn('getSSLStatus is deprecated - use getDomainStatus instead')
    // Fallback to domain status for compatibility
    const status = await this.getDomainStatus(domainId)
    return {
      ssl_status: status.ssl_status,
      is_https_enabled: status.esa_status === 'online',
    }
  }
}

export const api = new ApiService()
