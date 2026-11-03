import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { api, ApiError, tokens } from '../api'
import { Button, Callout, Icon, Loading, MessageCard, PageHeader, Screen } from '../components/console/ui'
import { CountdownTimer, QuizQuestion } from '../components/console/rewards'

type QuizState = {
  text: string
  total: number
  answered: number
  question: { number: number; text: string; options: { n: number; text: string }[] } | null
  seconds_left: number | null
  // speed: a blitz's bonus in points; null for a quiz that isn't a blitz
  result: { correct: number; total: number; points: number; coins: number; speed: number | null } | null
}

type State =
  | { kind: 'loading' }
  | { kind: 'error'; message: string; locked?: boolean }
  | { kind: 'ready'; quiz: QuizState }

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
  // The answer just sent stays pressed until the next question comes back
  const [selected, setSelected] = useState<number | null>(null)

  const show = useCallback((quiz: QuizState) => {
    setSelected(null)
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
      else if (err instanceof ApiError && err.status === 409) {
        setState({ kind: 'error', message: t(err.detail === 'limit' ? 'quiz.limit' : 'quiz.unavailable') })
      }
      else setError(t('common.error'))
    } finally {
      setBusy(false)
      setSelected(null)
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
      <PageHeader title={t('types.quiz')} back={{ to: '/app', label: t('feed.toFeed') }} />
      {state.kind === 'loading' && <Loading />}
      {state.kind === 'error' && (
        <MessageCard
          icon={state.locked ? 'lock' : 'alert'}
          title={state.message}
          action={<Button variant="outline" to="/app">{t('feed.toFeed')}</Button>}
        />
      )}
      {state.kind === 'ready' && state.quiz.result && <Result quiz={state.quiz} timeUp={timeUp} />}
      {state.kind === 'ready' && !state.quiz.result && state.quiz.question && (
        <>
          {left !== null && <CountdownTimer seconds={left} />}
          <QuizQuestion
            number={state.quiz.answered + 1}
            total={state.quiz.total}
            text={state.quiz.question.text}
            options={state.quiz.question.options}
            selected={selected}
            disabled={busy || timeUp}
            onSelect={(n) => {
              setSelected(n)
              void call('answer', { question: state.quiz.question!.number, option: n })
            }}
          />
          {error && <Callout tone="danger">{error}</Callout>}
        </>
      )}
    </Screen>
  )
}

// «3 из 5 · +30 баллов, +30 монет» (and «· +55 за скорость» on a blitz) over the quiz text, under «Время вышло» when
// the clock ran out; which answers were right is never shown
function Result({ quiz, timeUp }: { quiz: QuizState; timeUp: boolean }) {
  const { t } = useTranslation()
  const r = quiz.result!
  return (
    <div className="gc-result-card gc-result-card--win" role="status">
      <span className="gc-result-card__icon gc-crt"><Icon name={timeUp ? 'clock' : 'trophy'} size={48} /></span>
      {timeUp && <p className="gc-result-card__title gc-display-m">{t('quiz.timeUp')}</p>}
      <p className="gc-result-card__score gc-score-m gc-num gc-crt gc-glow">
        {t('quiz.result', {
          correct: r.correct,
          total: r.total,
          points: t('award.points', { count: r.points }),
          coins: t('award.coins', { count: r.coins }),
        })}
        {r.speed !== null && t('quiz.speed', { n: r.speed })}
      </p>
      <p className="gc-result-card__text gc-body">{quiz.text}</p>
      <div className="gc-result-card__action">
        <Button to="/app">{t('feed.toFeed')}</Button>
      </div>
    </div>
  )
}
