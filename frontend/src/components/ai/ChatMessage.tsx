import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ChevronDown, ChevronRight, Check, Loader2, Wrench } from 'lucide-react'

interface ToolCall {
  id: string
  name: string
  input: Record<string, any>
  result?: Record<string, any>
  status?: 'running' | 'done'
}

interface ChatMessageProps {
  role: 'user' | 'assistant'
  content: string
  toolCalls?: ToolCall[]
}

const TOOL_LABELS: Record<string, string> = {
  list_user_projects: '列出项目',
  get_project_details: '获取项目详情',
  list_repo_files: '列出仓库文件',
  read_file: '读取文件',
  create_repository: '创建仓库',
  commit_files: '提交文件',
  create_miaobu_project: '创建秒部项目',
  trigger_deployment: '触发部署',
}

function ToolCallCard({ tool }: { tool: ToolCall }) {
  const [expanded, setExpanded] = useState(false)
  const label = TOOL_LABELS[tool.name] || tool.name
  const isDone = tool.status === 'done'

  return (
    <div className="my-2 border border-[--border-primary] rounded-lg overflow-hidden bg-[--bg-secondary]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-3 py-2 text-left text-xs font-medium text-[--text-secondary] hover:bg-[--bg-tertiary] transition-colors"
      >
        {isDone ? (
          <Check size={14} className="text-green-500 shrink-0" />
        ) : (
          <Loader2 size={14} className="animate-spin text-accent shrink-0" />
        )}
        <Wrench size={14} className="shrink-0 text-[--text-tertiary]" />
        <span className="flex-1 truncate">{label}</span>
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {expanded && (
        <div className="px-3 pb-2 space-y-2">
          <div>
            <span className="text-[10px] uppercase tracking-wider text-[--text-tertiary]">Input</span>
            <pre className="mt-0.5 text-xs text-[--text-secondary] bg-[--bg-tertiary] rounded p-2 overflow-x-auto">
              {JSON.stringify(tool.input, null, 2)}
            </pre>
          </div>
          {tool.result && (
            <div>
              <span className="text-[10px] uppercase tracking-wider text-[--text-tertiary]">Result</span>
              <pre className="mt-0.5 text-xs text-[--text-secondary] bg-[--bg-tertiary] rounded p-2 overflow-x-auto max-h-48 overflow-y-auto">
                {JSON.stringify(tool.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function ChatMessage({ role, content, toolCalls }: ChatMessageProps) {
  if (role === 'user') {
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-[80%] bg-accent text-white px-4 py-2.5 rounded-2xl rounded-br-md text-sm whitespace-pre-wrap">
          {content}
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start mb-4">
      <div className="max-w-[80%]">
        {toolCalls && toolCalls.length > 0 && (
          <div className="mb-2">
            {toolCalls.map((tool) => (
              <ToolCallCard key={tool.id} tool={tool} />
            ))}
          </div>
        )}
        {content && (
          <div className="bg-[--bg-tertiary] px-4 py-2.5 rounded-2xl rounded-bl-md text-sm text-[--text-primary] prose prose-sm max-w-none prose-invert prose-pre:bg-[--bg-secondary] prose-pre:text-[--text-primary] prose-code:text-accent prose-a:text-accent">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}
