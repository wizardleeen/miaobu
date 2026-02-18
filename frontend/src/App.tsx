import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './stores/authStore'
import { useTheme } from './hooks/useTheme'
import { ToastProvider } from './components/Toast'
import LandingPage from './pages/LandingPage'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import ProjectsPage from './pages/ProjectsPage'
import ProjectDetailPage from './pages/ProjectDetailPage'
import ProjectSettingsPage from './pages/ProjectSettingsPage'
import ImportRepositoryPage from './pages/ImportRepositoryPage'
import CallbackPage from './pages/CallbackPage'

function App() {
  useTheme()
  const { isAuthenticated } = useAuthStore()

  return (
    <ToastProvider>
    <Router>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/callback" element={<CallbackPage />} />

        {/* Protected routes */}
        <Route
          path="/dashboard"
          element={isAuthenticated ? <DashboardPage /> : <Navigate to="/login" />}
        />
        <Route
          path="/projects"
          element={isAuthenticated ? <ProjectsPage /> : <Navigate to="/login" />}
        />
        <Route
          path="/projects/import"
          element={isAuthenticated ? <ImportRepositoryPage /> : <Navigate to="/login" />}
        />
        <Route
          path="/projects/:projectId"
          element={isAuthenticated ? <ProjectDetailPage /> : <Navigate to="/login" />}
        />
        <Route
          path="/projects/:projectId/settings"
          element={isAuthenticated ? <ProjectSettingsPage /> : <Navigate to="/login" />}
        />
      </Routes>
    </Router>
    </ToastProvider>
  )
}

export default App
