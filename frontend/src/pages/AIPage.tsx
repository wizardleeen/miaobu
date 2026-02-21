import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'
import Layout from '../components/Layout'
import ChatArea from '../components/ai/ChatArea'
import { Plus, MessageSquare, Trash2, Sparkles } from 'lucide-react'

interface Session {
  id: number
  title: string
  project_id: number | null
  created_at: string
  updated_at: string
}

export default function AIPage() {
  const { sessionId: paramSessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(
    paramSessionId ? parseInt(paramSessionId) : null
  )

  // Sync URL param to state
  useEffect(() => {
    if (paramSessionId) {
      setSelectedSessionId(parseInt(paramSessionId))
    }
  }, [paramSessionId])

  const { data: sessionsData } = useQuery({
    queryKey: ['chatSessions'],
    queryFn: () => api.listChatSessions(),
  })

  const sessions: Session[] = sessionsData?.sessions || []

  const createSession = useMutation({
    mutationFn: () => api.createChatSession(),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['chatSessions'] })
      setSelectedSessionId(data.id)
      navigate(`/ai/${data.id}`)
    },
  })

  const deleteSession = useMutation({
    mutationFn: (id: number) => api.deleteChatSession(id),
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({ queryKey: ['chatSessions'] })
      if (selectedSessionId === deletedId) {
        setSelectedSessionId(null)
        navigate('/ai')
      }
    },
  })

  const handleSelectSession = (id: number) => {
    setSelectedSessionId(id)
    navigate(`/ai/${id}`)
  }

  const formatTime = (isoString: string) => {
    const date = new Date(isoString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    if (diffMins < 1) return '刚刚'
    if (diffMins < 60) return `${diffMins} 分钟前`
    const diffHours = Math.floor(diffMins / 60)
    if (diffHours < 24) return `${diffHours} 小时前`
    const diffDays = Math.floor(diffHours / 24)
    if (diffDays < 7) return `${diffDays} 天前`
    return date.toLocaleDateString('zh-CN')
  }

  return (
    <Layout>
      <div className="flex h-[calc(100vh-8rem)] md:h-[calc(100vh-4rem)] -mx-4 sm:-mx-6 lg:-mx-8 -my-8 bg-[--bg-primary]">
        {/* Left panel — session list */}
        <div className="hidden md:flex flex-col w-60 border-r border-[--border-primary] bg-[--bg-elevated] shrink-0">
          <div className="p-3 border-b border-[--border-primary]">
            <button
              onClick={() => createSession.mutate()}
              disabled={createSession.isPending}
              className="flex items-center justify-center gap-2 w-full px-3 py-2 rounded-lg text-sm font-medium bg-accent text-white hover:bg-accent/90 disabled:opacity-50 transition-colors"
            >
              <Plus size={16} />
              新对话
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {sessions.length === 0 && (
              <div className="p-4 text-center text-xs text-[--text-tertiary]">
                暂无对话
              </div>
            )}
            {sessions.map((session) => (
              <div
                key={session.id}
                onClick={() => handleSelectSession(session.id)}
                className={`group flex items-center gap-2 px-3 py-2.5 cursor-pointer border-b border-[--border-primary] transition-colors ${
                  selectedSessionId === session.id
                    ? 'bg-[--accent-bg]'
                    : 'hover:bg-[--bg-tertiary]'
                }`}
              >
                <MessageSquare size={14} className="shrink-0 text-[--text-tertiary]" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-[--text-primary] truncate">
                    {session.title}
                  </p>
                  <p className="text-[10px] text-[--text-tertiary]">
                    {formatTime(session.updated_at)}
                  </p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    deleteSession.mutate(session.id)
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded text-[--text-tertiary] hover:text-red-400 transition-all"
                  title="删除对话"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Right panel — chat area */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Mobile: new chat button on top bar */}
          <div className="md:hidden flex items-center justify-between px-4 py-2 border-b border-[--border-primary] bg-[--bg-elevated]">
            <div className="flex items-center gap-2 text-sm font-medium text-[--text-primary]">
              <Sparkles size={16} className="text-accent" />
              AI 助手
            </div>
            <button
              onClick={() => createSession.mutate()}
              disabled={createSession.isPending}
              className="p-1.5 rounded-lg text-[--text-secondary] hover:text-[--text-primary] hover:bg-[--bg-tertiary]"
            >
              <Plus size={18} />
            </button>
          </div>

          {selectedSessionId ? (
            <ChatArea key={selectedSessionId} sessionId={selectedSessionId} />
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
              <Sparkles size={48} className="text-accent mb-4" />
              <h2 className="text-xl font-semibold text-[--text-primary] mb-2">
                Miaobu AI
              </h2>
              <p className="text-sm text-[--text-secondary] max-w-md mb-6">
                使用 AI 快速创建和修改项目。描述你的想法，AI 会帮你生成代码、创建仓库、并自动部署。
              </p>
              <button
                onClick={() => createSession.mutate()}
                disabled={createSession.isPending}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-accent text-white hover:bg-accent/90 disabled:opacity-50 transition-colors text-sm font-medium"
              >
                <Plus size={16} />
                开始新对话
              </button>
            </div>
          )}
        </div>
      </div>
    </Layout>
  )
}
