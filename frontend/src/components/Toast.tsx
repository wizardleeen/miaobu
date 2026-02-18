import { createContext, useContext, useState, useCallback, useRef } from 'react'
import { CheckCircle2, AlertTriangle, Info, X } from 'lucide-react'

type ToastType = 'success' | 'error' | 'warning' | 'info'

interface Toast {
  id: number
  message: string
  type: ToastType
  leaving: boolean
}

interface ToastContextValue {
  toast: (message: string, type?: ToastType) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const idRef = useRef(0)

  const dismiss = useCallback((id: number) => {
    setToasts(prev => prev.map(t => t.id === id ? { ...t, leaving: true } : t))
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 200)
  }, [])

  const toast = useCallback((message: string, type: ToastType = 'info') => {
    const id = ++idRef.current
    setToasts(prev => [...prev, { id, message, type, leaving: false }])
    const duration = type === 'error' || type === 'warning' ? 6000 : 4000
    setTimeout(() => dismiss(id), duration)
  }, [dismiss])

  const styles: Record<ToastType, { bg: string; text: string; icon: React.ReactNode }> = {
    success: {
      bg: 'bg-emerald-50 dark:bg-emerald-950 border-emerald-200 dark:border-emerald-800',
      text: 'text-emerald-800 dark:text-emerald-200',
      icon: <CheckCircle2 size={16} className="text-emerald-500 dark:text-emerald-400 flex-shrink-0" />,
    },
    error: {
      bg: 'bg-red-50 dark:bg-red-950 border-red-200 dark:border-red-800',
      text: 'text-red-800 dark:text-red-200',
      icon: <AlertTriangle size={16} className="text-red-500 dark:text-red-400 flex-shrink-0" />,
    },
    warning: {
      bg: 'bg-amber-50 dark:bg-amber-950 border-amber-200 dark:border-amber-800',
      text: 'text-amber-800 dark:text-amber-200',
      icon: <AlertTriangle size={16} className="text-amber-500 dark:text-amber-400 flex-shrink-0" />,
    },
    info: {
      bg: 'bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800',
      text: 'text-blue-800 dark:text-blue-200',
      icon: <Info size={16} className="text-blue-500 dark:text-blue-400 flex-shrink-0" />,
    },
  }

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      {toasts.length > 0 && (
        <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 max-w-sm">
          {toasts.map((t) => {
            const s = styles[t.type]
            return (
              <div
                key={t.id}
                className={`${s.bg} ${t.leaving ? 'animate-toast-out' : 'animate-toast-in'} border rounded-lg p-3 shadow-lg flex items-start gap-2.5`}
              >
                {s.icon}
                <span className={`${s.text} text-sm leading-snug flex-1`}>{t.message}</span>
                <button
                  type="button"
                  onClick={() => dismiss(t.id)}
                  className={`${s.text} opacity-50 hover:opacity-100 flex-shrink-0 mt-0.5`}
                >
                  <X size={14} />
                </button>
              </div>
            )
          })}
        </div>
      )}
    </ToastContext.Provider>
  )
}
