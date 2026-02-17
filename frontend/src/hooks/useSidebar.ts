import { useState, useCallback, useEffect } from 'react'

const STORAGE_KEY = 'sidebar-collapsed'

export function useSidebar() {
  const [isCollapsed, setIsCollapsed] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'true'
    } catch {
      return false
    }
  })
  const [isMobileOpen, setIsMobileOpen] = useState(false)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(isCollapsed))
    } catch {}
  }, [isCollapsed])

  const toggleCollapsed = useCallback(() => setIsCollapsed(prev => !prev), [])
  const toggleMobile = useCallback(() => setIsMobileOpen(prev => !prev), [])
  const openMobile = useCallback(() => setIsMobileOpen(true), [])
  const closeMobile = useCallback(() => setIsMobileOpen(false), [])

  return { isCollapsed, isMobileOpen, toggleCollapsed, toggleMobile, openMobile, closeMobile }
}
