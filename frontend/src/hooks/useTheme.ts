import { useEffect } from 'react'

export function useTheme() {
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

    const applyTheme = (isDark: boolean) => {
      document.documentElement.classList.toggle('dark', isDark)
    }

    applyTheme(mediaQuery.matches)

    const handler = (e: MediaQueryListEvent) => applyTheme(e.matches)
    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [])
}
