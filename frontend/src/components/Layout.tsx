import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { useSidebar } from '../hooks/useSidebar'
import Logo from './Logo'
import {
  LayoutDashboard,
  FolderGit2,
  GitBranch,
  PanelLeftClose,
  PanelLeftOpen,
  LogOut,
  Menu,
  X,
} from 'lucide-react'

interface LayoutProps {
  children: React.ReactNode
}

const navItems = [
  { to: '/dashboard', label: '控制台', icon: LayoutDashboard },
  { to: '/projects', label: '项目', icon: FolderGit2 },
  { to: '/projects/import', label: '导入仓库', icon: GitBranch },
]

export default function Layout({ children }: LayoutProps) {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const { isCollapsed, toggleCollapsed, isMobileOpen, openMobile, closeMobile } = useSidebar()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const sidebarWidth = isCollapsed ? 'w-16' : 'w-60'
  const mainMargin = isCollapsed ? 'md:ml-16' : 'md:ml-60'

  const SidebarContent = () => (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="flex items-center h-16 px-4 border-b border-[--border-primary] shrink-0">
        <Link
          to="/dashboard"
          className="flex items-center gap-3 text-[--text-primary] hover:text-accent transition-colors"
          onClick={closeMobile}
        >
          <Logo size={32} />
          {!isCollapsed && <span className="text-lg font-bold tracking-tight">秒部</span>}
        </Link>
      </div>

      {/* Nav Items */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = location.pathname === item.to ||
            (item.to === '/projects' && location.pathname.startsWith('/projects/') && !location.pathname.includes('/import'))
          const Icon = item.icon
          return (
            <Link
              key={item.to}
              to={item.to}
              onClick={closeMobile}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-[--accent-bg] text-accent'
                  : 'text-[--text-secondary] hover:text-[--text-primary] hover:bg-[--bg-tertiary]'
              }`}
              title={isCollapsed ? item.label : undefined}
            >
              <Icon size={20} className="shrink-0" />
              {!isCollapsed && <span>{item.label}</span>}
            </Link>
          )
        })}
      </nav>

      {/* User Section */}
      <div className="border-t border-[--border-primary] p-3 shrink-0">
        {!isCollapsed ? (
          <div className="flex items-center gap-3 px-2 py-2">
            {user?.github_avatar_url ? (
              <img
                src={user.github_avatar_url}
                alt={user.github_username}
                className="w-8 h-8 rounded-full shrink-0"
              />
            ) : (
              <div className="w-8 h-8 rounded-full bg-[--bg-tertiary] shrink-0" />
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-[--text-primary] truncate">
                {user?.github_username}
              </p>
            </div>
            <button
              onClick={handleLogout}
              className="p-1.5 rounded-lg text-[--text-tertiary] hover:text-[--text-primary] hover:bg-[--bg-tertiary] transition-colors"
              title="退出登录"
            >
              <LogOut size={16} />
            </button>
          </div>
        ) : (
          <button
            onClick={handleLogout}
            className="flex items-center justify-center w-full p-2.5 rounded-lg text-[--text-tertiary] hover:text-[--text-primary] hover:bg-[--bg-tertiary] transition-colors"
            title="退出登录"
          >
            <LogOut size={20} />
          </button>
        )}

        {/* Collapse Toggle (desktop only) */}
        <button
          onClick={toggleCollapsed}
          className="hidden md:flex items-center justify-center w-full mt-2 p-2 rounded-lg text-[--text-tertiary] hover:text-[--text-primary] hover:bg-[--bg-tertiary] transition-colors"
          title={isCollapsed ? '展开侧栏' : '收起侧栏'}
        >
          {isCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-[--bg-secondary]">
      {/* Mobile top bar */}
      <div className="md:hidden flex items-center h-14 px-4 bg-[--bg-elevated] border-b border-[--border-primary] sticky top-0 z-40">
        <button
          onClick={openMobile}
          className="p-2 -ml-2 rounded-lg text-[--text-secondary] hover:text-[--text-primary] hover:bg-[--bg-tertiary] transition-colors"
        >
          <Menu size={20} />
        </button>
        <Link to="/dashboard" className="ml-3 text-lg font-bold text-[--text-primary]">
          秒部
        </Link>
      </div>

      {/* Mobile overlay */}
      {isMobileOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/50 z-50 animate-fade-in"
          onClick={closeMobile}
        >
          <div
            className="w-60 h-full bg-[--bg-elevated] border-r border-[--border-primary]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-end p-3">
              <button
                onClick={closeMobile}
                className="p-1.5 rounded-lg text-[--text-tertiary] hover:text-[--text-primary] hover:bg-[--bg-tertiary]"
              >
                <X size={18} />
              </button>
            </div>
            <SidebarContent />
          </div>
        </div>
      )}

      {/* Desktop sidebar */}
      <aside
        className={`hidden md:block fixed left-0 top-0 h-screen ${sidebarWidth} bg-[--bg-elevated] border-r border-[--border-primary] z-30 transition-all duration-200`}
      >
        <SidebarContent />
      </aside>

      {/* Main content */}
      <main className={`${mainMargin} transition-all duration-200`}>
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </div>
      </main>
    </div>
  )
}
