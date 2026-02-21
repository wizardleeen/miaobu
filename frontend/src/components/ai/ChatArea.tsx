import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../services/api'
import ChatMessage from './ChatMessage'
import ChatInput from './ChatInput'

interface ToolCall {
  id: string
  name: string
  input: Record<string, any>
  result?: Record<string, any>
  status?: 'running' | 'done'
}

interface Message {
  id?: number
  role: 'user' | 'assistant'
  content: string
  toolCalls?: ToolCall[]
}

interface ChatAreaProps {
  sessionId: number
}

function parseStoredMessage(msg: any): Message {
  const m: Message = {
    id: msg.id,
    role: msg.role,
    content: msg.content || '',
  }
  if (msg.tool_calls) {
    try {
      const calls = JSON.parse(msg.tool_calls)
      const results = msg.tool_results ? JSON.parse(msg.tool_results) : []
      const resultMap = new Map(results.map((r: any) => [r.tool_use_id, r.result]))
      m.toolCalls = calls.map((tc: any) => ({
        id: tc.id,
        name: tc.name,
        input: tc.input,
        result: resultMap.get(tc.id),
        status: 'done' as const,
      }))
    } catch {
      // ignore parse errors
    }
  }
  return m
}

export default function ChatArea({ sessionId }: ChatAreaProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<(() => void) | null>(null)
  const queryClient = useQueryClient()

  const { data: sessionData } = useQuery({
    queryKey: ['chatSession', sessionId],
    queryFn: () => api.getChatSession(sessionId),
  })

  // Load messages from session data
  useEffect(() => {
    if (sessionData?.messages) {
      setMessages(sessionData.messages.map(parseStoredMessage))
    }
  }, [sessionData])

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(
    async (text: string) => {
      if (isStreaming) return

      // Optimistic add user message
      const userMsg: Message = { role: 'user', content: text }
      setMessages((prev) => [...prev, userMsg])
      setIsStreaming(true)

      // Prepare a streaming assistant message
      let assistantMsg: Message = { role: 'assistant', content: '', toolCalls: [] }
      setMessages((prev) => [...prev, assistantMsg])

      try {
        const { stream, abort } = api.sendChatMessage(sessionId, text)
        abortRef.current = abort

        if (!stream) {
          setIsStreaming(false)
          return
        }

        const reader = stream.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })

          // Process SSE events in the buffer
          const lines = buffer.split('\n')
          buffer = lines.pop() || '' // keep incomplete line

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const jsonStr = line.slice(6)
            if (!jsonStr) continue

            try {
              const event = JSON.parse(jsonStr)

              switch (event.type) {
                case 'text_delta':
                  assistantMsg = {
                    ...assistantMsg,
                    content: assistantMsg.content + event.data.text,
                  }
                  setMessages((prev) => [...prev.slice(0, -1), assistantMsg])
                  break

                case 'tool_call_start': {
                  const tc: ToolCall = {
                    id: event.data.id,
                    name: event.data.name,
                    input: event.data.input,
                    status: 'running',
                  }
                  assistantMsg = {
                    ...assistantMsg,
                    toolCalls: [...(assistantMsg.toolCalls || []), tc],
                  }
                  setMessages((prev) => [...prev.slice(0, -1), assistantMsg])
                  break
                }

                case 'tool_call_result': {
                  const updatedCalls = (assistantMsg.toolCalls || []).map((tc) =>
                    tc.id === event.data.id
                      ? { ...tc, result: event.data.result, status: 'done' as const }
                      : tc
                  )
                  assistantMsg = { ...assistantMsg, toolCalls: updatedCalls }
                  setMessages((prev) => [...prev.slice(0, -1), assistantMsg])
                  break
                }

                case 'message_done':
                  // Invalidate session list to update title
                  queryClient.invalidateQueries({ queryKey: ['chatSessions'] })
                  queryClient.invalidateQueries({ queryKey: ['chatSession', sessionId] })
                  break

                case 'error':
                  assistantMsg = {
                    ...assistantMsg,
                    content: assistantMsg.content + `\n\n**Error:** ${event.data.message}`,
                  }
                  setMessages((prev) => [...prev.slice(0, -1), assistantMsg])
                  break
              }
            } catch {
              // ignore malformed events
            }
          }
        }
      } catch (err: any) {
        if (err.name !== 'AbortError') {
          assistantMsg = {
            ...assistantMsg,
            content: assistantMsg.content + `\n\n**Error:** ${err.message}`,
          }
          setMessages((prev) => [...prev.slice(0, -1), assistantMsg])
        }
      } finally {
        setIsStreaming(false)
        abortRef.current = null
      }
    },
    [sessionId, isStreaming, queryClient]
  )

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full min-h-[300px] text-center">
              <div className="text-4xl mb-4">&#x2728;</div>
              <h3 className="text-lg font-medium text-[--text-primary] mb-2">
                Miaobu AI
              </h3>
              <p className="text-sm text-[--text-secondary] max-w-md">
                描述你想构建的项目，AI 会帮你创建仓库、写代码、部署上线。
              </p>
            </div>
          )}
          {messages.map((msg, i) => (
            <ChatMessage
              key={i}
              role={msg.role}
              content={msg.content}
              toolCalls={msg.toolCalls}
            />
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <ChatInput onSend={handleSend} disabled={isStreaming} />
    </div>
  )
}
