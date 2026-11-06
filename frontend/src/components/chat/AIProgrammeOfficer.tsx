/**
 * AI Programme Officer — floating chat widget.
 *
 * A bottom-right chat button that opens a slide-up panel. Sends questions to
 * POST /api/dashboard/chat/ and streams the AI answer back.
 *
 * Available on all authenticated pages via Shell.tsx.
 */
import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'motion/react'
import { Bot, Send, X, ChevronDown, Sparkles } from 'lucide-react'
import { api } from '@/api/client'
import { useAuth } from '@/context/AuthContext'
import { cn } from '@/utils/cn'

// ── Types ──────────────────────────────────────────────────────────────────────

interface Message {
  id: number
  role: 'user' | 'assistant'
  text: string
  loading?: boolean
}

// ── Starter questions ──────────────────────────────────────────────────────────

const STARTERS = [
  'How many activities were recorded this month?',
  'Are there any active alerts I should know about?',
  'Compare PHD and Bandhu performance this month.',
  'How many fistula cases were identified this month?',
  'What is the month-on-month change in submissions?',
]

// ── Helpers ────────────────────────────────────────────────────────────────────

let _id = 0
function nextId() { return ++_id }

// ── Component ──────────────────────────────────────────────────────────────────

export function AIProgrammeOfficer() {
  const { user } = useAuth()
  const reduce    = useReducedMotion()

  const [open,      setOpen]     = useState(false)
  const [messages,  setMessages] = useState<Message[]>([])
  const [input,     setInput]    = useState('')
  const [busy,      setBusy]     = useState(false)

  const listRef  = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Determine partner scope for the API call
  const canSeeAll = ['developer', 'supervisor'].includes(user?.role ?? '')
  const partner   = canSeeAll ? '' : (user?.organisation ?? '')

  // Scroll to bottom whenever messages change
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [messages])

  // Focus input when panel opens
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 150)
    }
  }, [open])

  async function sendMessage(text: string) {
    const question = text.trim()
    if (!question || busy) return

    setInput('')
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: 'user', text: question },
      { id: nextId(), role: 'assistant', text: '', loading: true },
    ])
    setBusy(true)

    try {
      const resp = await api.post('/dashboard/chat/', { question, partner })
      const answer: string = resp.data?.answer ?? 'No response received.'
      setMessages((prev) => {
        const copy = [...prev]
        const last = copy[copy.length - 1]
        if (last?.loading) {
          copy[copy.length - 1] = { ...last, text: answer, loading: false }
        }
        return copy
      })
    } catch {
      setMessages((prev) => {
        const copy = [...prev]
        const last = copy[copy.length - 1]
        if (last?.loading) {
          copy[copy.length - 1] = {
            ...last,
            text: 'Unable to reach the AI Programme Officer. Please try again.',
            loading: false,
          }
        }
        return copy
      })
    } finally {
      setBusy(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  const showStarters = messages.length === 0

  return (
    <>
      {/* ── Floating trigger button ─────────────────────────────────────────── */}
      <motion.button
        aria-label={open ? 'Close AI Programme Officer' : 'Open AI Programme Officer'}
        onClick={() => setOpen((o) => !o)}
        whileHover={reduce ? {} : { scale: 1.05 }}
        whileTap={reduce ? {} : { scale: 0.95 }}
        className={cn(
          'fixed bottom-5 right-5 z-40 flex h-12 w-12 items-center justify-center rounded-full shadow-lg transition-colors',
          open
            ? 'bg-gray-700 dark:bg-gray-600 text-white'
            : 'bg-unfpa-blue text-white hover:bg-unfpa-dark',
        )}
      >
        <AnimatePresence mode="wait">
          {open ? (
            <motion.span
              key="close"
              initial={{ opacity: 0, rotate: -90 }}
              animate={{ opacity: 1, rotate: 0 }}
              exit={{ opacity: 0, rotate: 90 }}
              transition={{ duration: 0.15 }}
            >
              <ChevronDown className="h-5 w-5" />
            </motion.span>
          ) : (
            <motion.span
              key="bot"
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
              transition={{ duration: 0.15 }}
            >
              <Bot className="h-5 w-5" />
            </motion.span>
          )}
        </AnimatePresence>
      </motion.button>

      {/* ── Chat panel ─────────────────────────────────────────────────────── */}
      <AnimatePresence mode="wait">
        {open && (
          <motion.div
            key="chat-panel"
            initial={{ opacity: 0, y: reduce ? 0 : 24, scale: reduce ? 1 : 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: reduce ? 0 : 16, scale: reduce ? 1 : 0.97 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            className={cn(
              'fixed bottom-20 right-5 z-40',
              'flex flex-col',
              'w-[calc(100vw-2.5rem)] sm:w-96',
              'max-h-[calc(100vh-7rem)]',
              'rounded-2xl border border-gray-200 dark:border-gray-700',
              'bg-white dark:bg-gray-900',
              'shadow-2xl shadow-black/10 dark:shadow-black/40',
              'overflow-hidden',
            )}
            role="dialog"
            aria-label="AI Programme Officer"
          >
            {/* Header */}
            <div className="flex items-center gap-3 border-b border-gray-100 dark:border-gray-800 px-4 py-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-unfpa-blue/10 dark:bg-unfpa-blue/20">
                <Bot className="h-4 w-4 text-unfpa-blue" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-gray-900 dark:text-white leading-none">
                  AI Programme Officer
                </p>
                <p className="mt-0.5 text-[10px] text-gray-400 dark:text-gray-500">
                  {partner ? `${partner} · ` : ''}CIPRB/UNFPA RCH
                </p>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Messages */}
            <div
              ref={listRef}
              className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0"
            >
              {showStarters ? (
                /* Starter question chips */
                <div className="space-y-3">
                  <p className="text-xs text-gray-400 dark:text-gray-500 text-center py-2">
                    Ask a question about the programme or choose one below.
                  </p>
                  <div className="flex flex-col gap-2">
                    {STARTERS.map((s) => (
                      <button
                        key={s}
                        onClick={() => sendMessage(s)}
                        className="rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 px-3 py-2 text-left text-xs text-gray-600 dark:text-gray-300 hover:border-unfpa-blue/50 hover:bg-unfpa-blue/5 transition-colors leading-relaxed"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={cn(
                      'flex',
                      msg.role === 'user' ? 'justify-end' : 'justify-start',
                    )}
                  >
                    <div
                      className={cn(
                        'max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-relaxed',
                        msg.role === 'user'
                          ? 'bg-unfpa-blue text-white rounded-br-md'
                          : 'bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 rounded-bl-md',
                      )}
                    >
                      {msg.loading ? (
                        /* Typing indicator */
                        <span className="flex items-center gap-1 py-0.5">
                          {[0, 1, 2].map((i) => (
                            <motion.span
                              key={i}
                              className="block h-1.5 w-1.5 rounded-full bg-gray-400 dark:bg-gray-500"
                              animate={{ opacity: [0.3, 1, 0.3] }}
                              transition={{
                                duration: 1.2,
                                repeat: Infinity,
                                delay: i * 0.2,
                              }}
                            />
                          ))}
                        </span>
                      ) : (
                        msg.text
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* AI disclaimer (only when messages exist) */}
            {messages.length > 0 && (
              <div className="flex items-center justify-center gap-1 px-4 pb-1 pt-0">
                <Sparkles className="h-3 w-3 text-gray-300 dark:text-gray-600" />
                <span className="text-[10px] text-gray-300 dark:text-gray-600">
                  AI-assisted · Groq / LLaMA 3.3 · Review before use
                </span>
              </div>
            )}

            {/* Input */}
            <div className="border-t border-gray-100 dark:border-gray-800 px-3 py-3">
              <div className="flex items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 px-3 py-2 focus-within:border-unfpa-blue transition-colors">
                <input
                  ref={inputRef}
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={busy}
                  maxLength={500}
                  placeholder="Ask about programme performance…"
                  className="flex-1 bg-transparent text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 outline-none disabled:opacity-50"
                />
                <button
                  onClick={() => sendMessage(input)}
                  disabled={!input.trim() || busy}
                  className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-unfpa-blue text-white disabled:opacity-40 hover:bg-unfpa-dark transition-colors"
                  aria-label="Send"
                >
                  <Send className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
