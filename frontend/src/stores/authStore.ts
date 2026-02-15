import { create } from 'zustand'

interface User {
  id: number
  github_username: string
  github_email?: string
  github_avatar_url?: string
  created_at: string
  updated_at: string
}

interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  setAuth: (token: string, user: User) => void
  logout: () => void
  initializeAuth: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  isAuthenticated: false,

  setAuth: (token: string, user: User) => {
    localStorage.setItem('token', token)
    localStorage.setItem('user', JSON.stringify(user))
    set({ token, user, isAuthenticated: true })
  },

  logout: () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    set({ token: null, user: null, isAuthenticated: false })
  },

  initializeAuth: () => {
    const token = localStorage.getItem('token')
    const userStr = localStorage.getItem('user')
    if (token && userStr) {
      try {
        const user = JSON.parse(userStr)
        set({ token, user, isAuthenticated: true })
      } catch (error) {
        console.error('Failed to parse stored user:', error)
        localStorage.removeItem('token')
        localStorage.removeItem('user')
      }
    }
  },
}))

// Initialize auth on app load
useAuthStore.getState().initializeAuth()
