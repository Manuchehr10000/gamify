import { ChevronLeft, Coins, Lock, Timer } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, tokens } from '../api'
import { Card, Screen } from '../components/ui'

type QuizState = {
  text: string
  total: number
  answered: number
  question: { number: number; text: string; options: { n: number; text: string }[] } | null
  seconds_left: number | null
  result: { correct: number; total: number; points: number; coins: number } | null
}

type State =
  | { kind: 'loading' }
  | { kind: 'error'; message: string; locked?: boolean }
  | { kind: 'ready'; quiz: QuizState }

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

export function Quiz() {
  const { t } = useTranslation()
  const id = Number(useParams().id)
  const [state, setState] = useState<State>({ kind: 'loading' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  // The countdown runs from the server's seconds left, never from the phone's clock
  const deadline = useRef<number | null>(null)
  const [left, setLeft] = useState<number | null>(null)
  const [timeUp, setTimeUp] = useState(false)

  const show = useCallback((quiz: QuizState) => {
    deadline.current = quiz.seconds_left === null ? null : Date.now() + quiz.seconds_left * 1000
    setLeft(quiz.seconds_left)
    setState({ kind: 'ready', quiz })
  }, [])

  const send = useCallback(async (path: string, json?: unknown) => {
    setBusy(true)
    setError('')
    try {
      show(await api<QuizState>(`/api/quiz/${id}/${path}`, { token: tokens.get('guest'), method: 'POST', json }))
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) setState({ kind: 'error', message: t('quiz.checkInFirst'), locked: true })
      else if (err instanceof ApiError && err.status === 404) setState({ kind: 'error', message: t('quiz.missing') })
      else if (err instanceof ApiError && err.status === 409) setState({ kind: 'error', message: t('quiz.unavailable') })
      else setError(t('common.error'))
    } finally {
      setBusy(false)
    }
  }, [id, show, t])

  // Calls go one at a time: a finish fired by the countdown waits for an answer still on its way
  const queue = useRef<Promise<void>>(Promise.resolve())
  const call = useCallback((path: string, json?: unknown) => {
    queue.current = queue.current.then(() => send(path, json))
    return queue.current
  }, [send])

  useEffect(() => {
    // «Начать» opens the quiz, or brings back where the guest was in it
    void call('start')
  }, [call])

  const running = state.kind === 'ready' && !state.quiz.result
  useEffect(() => {
    if (!running || deadline.current === null) return
    const timer = setInterval(() => {
      const s = Math.max(0, Math.ceil((deadline.current! - Date.now()) / 1000))
      setLeft(s)
      if (s === 0) {
        clearInterval(timer)
        setTimeUp(true)
        void call('finish')
      }
    }, 250)
    return () => clearInterval(timer)
  }, [running, state, call])

  return (
    <Screen>
      <Link to="/app" className="flex items-center gap-1 text-sm font-medium text-slate-600">
        <ChevronLeft className="size-4" aria-hidden />
        {t('feed.toFeed')}
      </Link>
      {state.kind === 'loading' && <p className="text-center text-slate-500">{t('common.loading')}</p>}
      {state.kind === 'error' && (
        <Card className="flex flex-col items-center gap-3 text-center text-lg font-medium">
          {state.locked && <Lock className="size-8 text-amber-600" aria-hidden />}
          {state.message}
        </Card>
      )}
      {state.kind === 'ready' && state.quiz.result && <Result quiz={state.quiz} timeUp={timeUp} />}
      {state.kind === 'ready' && !state.quiz.result && state.quiz.question && (
        <Card className="flex flex-col gap-4">
          <div className="flex items-center justify-between text-sm text-slate-600">
            <span>{t('quiz.progress', { n: state.quiz.answered + 1, total: state.quiz.total })}</span>
            {left !== null && (
              <span className={`flex items-center gap-1 font-semibold tabular-nums ${left <= 10 ? 'text-red-600' : 'text-slate-800'}`}>
                <Timer className="size-4" aria-hidden />
                {t('quiz.secondsLeft', { time: mmss(left) })}
              </span>
            )}
          </div>
          <p className="whitespace-pre-line text-lg font-medium leading-relaxed">{state.quiz.question.text}</p>
          <div className="flex flex-col gap-3">
            {state.quiz.question.options.map((o) => (
              <button
                key={o.n}
                disabled={busy || timeUp}
                className="min-h-12 rounded-xl border border-slate-300 bg-white px-5 py-3 text-left text-base font-medium text-slate-800 transition hover:bg-slate-50 disabled:opacity-50"
                onClick={() => call('answer', { question: state.quiz.question!.number, option: o.n })}
              >
                {o.text}
              </button>
            ))}
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </Card>
      )}
    </Screen>
  )
}

// «3 из 5 · +30 баллов, +30 монет»; which answers were right is never shown
function Result({ quiz, timeUp }: { quiz: QuizState; timeUp: boolean }) {
  const { t } = useTranslation()
  const r = quiz.result!
  return (
    <Card className="flex flex-col items-center gap-4 py-10 text-center">
      {timeUp && <p className="text-base font-medium text-slate-600">{t('quiz.timeUp')}</p>}
      <p className="flex items-center gap-2 text-2xl font-bold text-emerald-700">
        <Coins className="size-6 text-amber-600" aria-hidden />
        {t('quiz.result', {
          correct: r.correct,
          total: r.total,
          points: t('award.points', { count: r.points }),
          coins: t('award.coins', { count: r.coins }),
        })}
      </p>
      <p className="text-base text-slate-600">{quiz.text}</p>
      <Link to="/app" className="mt-2 w-full rounded-xl bg-emerald-600 py-3 font-medium text-white">{t('feed.toFeed')}</Link>
    </Card>
  )
}
