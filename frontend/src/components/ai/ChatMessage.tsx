import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ChevronDown, ChevronRight, Check, Loader2, Wrench, Globe } from 'lucide-react'

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
  update_project: '更新项目设置',
  list_project_deployments: '查看部署记录',
  get_deployment_logs: '查看构建日志',
  wait_for_deployment: '等待部署完成',
  list_env_vars: '查看环境变量',
  set_env_var: '设置环境变量',
  delete_env_var: '删除环境变量',
  get_manul_guide: '加载 Manul 指南',
  fetch_project_url: '访问项目 URL',
  glob_repo_files: '搜索文件',
  grep_repo_files: '搜索代码',
  git_log: '提交历史',
  git_diff: '比较差异',
}

function getToolSubtitle(tool: ToolCall): string | null {
  const input = tool.input || {}
  switch (tool.name) {
    case 'commit_files':
      return input.commit_message || null
    case 'create_repository':
      return input.name || null
    case 'create_miaobu_project':
      return input.project_type ? `${input.repo} (${input.project_type})` : input.repo || null
    case 'read_file':
      return input.path || null
    case 'update_project':
      return input.project_type ? `类型 → ${input.project_type}` : null
    case 'get_deployment_logs':
    case 'wait_for_deployment':
      return input.deployment_id ? `#${input.deployment_id}` : null
    case 'list_env_vars':
      return input.project_id ? `项目 #${input.project_id}` : null
    case 'set_env_var':
    case 'delete_env_var':
      return input.key || null
    case 'fetch_project_url':
      return `${input.method || 'GET'} ${input.path}` || null
    case 'glob_repo_files':
      return input.pattern || null
    case 'grep_repo_files':
      return input.query || null
    case 'git_log':
      return input.path || input.branch || null
    case 'git_diff':
      return input.base && input.head ? `${input.base}...${input.head}` : null
    default:
      return null
  }
}

function statusColor(code: number): string {
  if (code >= 200 && code < 300) return 'text-green-400'
  if (code >= 300 && code < 400) return 'text-yellow-400'
  return 'text-red-400'
}

function FetchResultDisplay({ result }: { result: Record<string, any> }) {
  if (result.error) {
    return (
      <div className="text-xs text-red-400 bg-[--bg-tertiary] rounded p-2">
        {result.error}
      </div>
    )
  }

  const code = result.status_code as number
  const headers = result.headers as Record<string, string> | undefined
  const contentType = headers?.['content-type'] || ''

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 text-xs">
        <span className={`font-mono font-bold ${statusColor(code)}`}>{code}</span>
        <span className="text-[--text-tertiary] truncate">{result.url}</span>
      </div>
      {headers && Object.keys(headers).length > 0 && (
        <div className="text-[10px] text-[--text-tertiary] font-mono bg-[--bg-tertiary] rounded px-2 py-1">
          {Object.entries(headers).map(([k, v]) => (
            <div key={k}><span className="text-[--text-secondary]">{k}:</span> {v}</div>
          ))}
        </div>
      )}
      {result.body && (
        <pre className="text-xs text-[--text-secondary] bg-[--bg-tertiary] rounded p-2 overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap break-all">
          {contentType.includes('json') ? (() => { try { return JSON.stringify(JSON.parse(result.body), null, 2) } catch { return result.body } })() : result.body}
        </pre>
      )}
    </div>
  )
}

function ToolCallCard({ tool }: { tool: ToolCall }) {
  const [expanded, setExpanded] = useState(false)
  const label = TOOL_LABELS[tool.name] || tool.name
  const subtitle = getToolSubtitle(tool)
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
        {tool.name === 'fetch_project_url'
          ? <Globe size={14} className="shrink-0 text-[--text-tertiary]" />
          : <Wrench size={14} className="shrink-0 text-[--text-tertiary]" />
        }
        <span className="flex-1 truncate">
          {label}
          {subtitle && <span className="text-[--text-tertiary] font-normal"> · {subtitle}</span>}
          {tool.name === 'fetch_project_url' && isDone && tool.result && !tool.result.error && (
            <span className={`font-mono font-normal ml-1 ${statusColor(tool.result.status_code)}`}>{tool.result.status_code}</span>
          )}
        </span>
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
              {tool.name === 'fetch_project_url' ? (
                <div className="mt-0.5">
                  <FetchResultDisplay result={tool.result} />
                </div>
              ) : (
                <pre className="mt-0.5 text-xs text-[--text-secondary] bg-[--bg-tertiary] rounded p-2 overflow-x-auto max-h-48 overflow-y-auto">
                  {JSON.stringify(tool.result, null, 2)}
                </pre>
              )}
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
        <div className="max-w-[80%] bg-accent text-white px-4 py-2.5 rounded-2xl rounded-br-md text-sm whitespace-pre-wrap break-words overflow-hidden">
          {content}
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start mb-4">
      <div className="max-w-[80%] min-w-0 [overflow-wrap:anywhere]">
        {toolCalls && toolCalls.length > 0 && (
          <div className="mb-2">
            {toolCalls.map((tool) => (
              <ToolCallCard key={tool.id} tool={tool} />
            ))}
          </div>
        )}
        {content && (
          <div className="chat-markdown bg-[--bg-tertiary] px-4 py-2.5 rounded-2xl rounded-bl-md text-sm text-[--text-primary]">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}
