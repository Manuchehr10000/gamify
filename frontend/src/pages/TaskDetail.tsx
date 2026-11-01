import { Camera, Check, ChevronLeft, ExternalLink, LoaderCircle, Lock, QrCode, ShoppingBag, WifiOff } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, tokens } from '../api'
import { AwardView } from '../components/AwardView'
import { ReviewNote } from '../components/ReviewNote'
import { TaskIcon } from '../components/TaskIcon'
import { Button, Card, Screen } from '../components/ui'
import { cache, type Award, type Task } from '../feed'
import { forgetUpload, sendPhoto, sendText, shrink, useUpload, type Upload } from '../uploads'
import { PartnerBadge, Reward } from './Feed'

type State = { kind: 'loading' } | { kind: 'missing' } | { kind: 'ready'; task: Task }

function Action({ task, onAward }: { task: Task; onAward: (a: Award) => void }) {
  const { t } = useTranslation()
  const [opened, setOpened] = useState(() => cache.linkOpened(task.id))
  const [ticked, setTicked] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  if (task.done && task.review === 'penalty') return <ReviewNote task={task} />
  // A finished quiz opens its result
  if (task.done && task.method === 'quiz') {
    return (
      <Link to={`/app/quiz/${task.id}`} className="flex items-center justify-center gap-1 py-3 font-medium text-emerald-700">
        <Check className="size-5" aria-hidden />
        {t('quiz.seeResult')}
      </Link>
    )
  }
  if (task.done) {
    return (
      <p className="flex items-center justify-center gap-1 py-3 font-medium text-emerald-700">
        <Check className="size-5" aria-hidden />
        {t('feed.done')}
      </p>
    )
  }
  if (task.method === 'quiz') {
    if (task.locked) {
      return (
        <p className="flex items-center gap-2 rounded-xl bg-amber-50 px-4 py-3 text-amber-800">
          <Lock className="size-5 shrink-0" aria-hidden />
          {t('quiz.checkInFirst')}
        </p>
      )
    }
    return (
      <Link to={`/app/quiz/${task.id}`} className="inline-flex h-12 items-center justify-center rounded-xl bg-emerald-600 px-5 font-medium text-white">
        {t('quiz.start')}
      </Link>
    )
  }
  if (task.method === 'qr') {
    return (
      <p className="flex items-center gap-2 rounded-xl bg-emerald-50 px-4 py-3 text-emerald-800">
        <QrCode className="size-5 shrink-0" aria-hidden />
        {t('task.scanHint')}
      </p>
    )
  }
  if (task.method === 'market') {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-slate-700">{t('task.marketHint')}</p>
        <Link to="/market" className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 font-medium text-white">
          <ShoppingBag className="size-4" aria-hidden />
          {t('task.toMarket')}
        </Link>
      </div>
    )
  }
  if (task.method === 'photo' || task.method === 'text' || task.method === 'photo_text') {
    return (
      <>
        <ReviewNote task={task} />
        <Submit task={task} />
      </>
    )
  }
  if (task.method !== 'link') return <Button disabled>{t('task.doSoon')}</Button>

  async function confirm() {
    setBusy(true)
    setError('')
    try {
      onAward(await api<Award>(`/api/tasks/${task.id}/complete`, { token: tokens.get('guest'), method: 'POST' }))
    } catch {
      setError(t('common.error'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <a
        href={task.link}
        target="_blank"
        rel="noopener noreferrer"
        onClick={() => {
          cache.markLinkOpened(task.id)
          setOpened(true)
        }}
        className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 font-medium text-white"
      >
        {t('task.do')}
        <ExternalLink className="size-4" aria-hidden />
      </a>
      {opened && (
        <>
          <label className="flex items-center gap-3 text-base">
            <input type="checkbox" className="size-5 accent-emerald-600" checked={ticked} onChange={(e) => setTicked(e.target.checked)} />
            {t('task.registered')}
          </label>
          <Button variant="outline" disabled={!ticked || busy} onClick={confirm}>{t('task.confirm')}</Button>
        </>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  )
}

const TEXT_MAX = 500

function UploadStatus({ upload }: { upload: Upload | null }) {
  const { t } = useTranslation()
  if (upload?.state === 'sending') {
    return (
      <p className="flex items-center justify-center gap-2 py-3 font-medium text-slate-700">
        <LoaderCircle className="size-5 animate-spin" aria-hidden />
        {t('submit.sending')}
      </p>
    )
  }
  if (upload?.state === 'offline') {
    return (
      <p className="flex items-center gap-2 rounded-xl bg-amber-50 px-4 py-3 text-amber-800">
        <WifiOff className="size-5 shrink-0" aria-hidden />
        {t('submit.offline')}
      </p>
    )
  }
  if (upload?.state === 'failed') {
    return <p className="text-sm text-red-600">{t(`submit.errors.${upload.reason}`, { defaultValue: t('common.error') })}</p>
  }
  return null
}

// Photo, text or both: pick or write, look it over, send once
function Submit({ task }: { task: Task }) {
  const { t } = useTranslation()
  const upload = useUpload(task.id)
  const picker = useRef<HTMLInputElement>(null)
  const [photo, setPhoto] = useState<Blob | null>(null)
  const [preview, setPreview] = useState('')
  const [text, setText] = useState('')
  const [preparing, setPreparing] = useState(false)
  const [pickError, setPickError] = useState(false)
  const wantsPhoto = task.method !== 'text'
  const wantsText = task.method !== 'photo'

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview)
  }, [preview])

  async function pick(file: File | undefined) {
    if (!file) return
    setPreparing(true)
    setPickError(false)
    try {
      const small = await shrink(file)
      setPhoto(small)
      setPreview(URL.createObjectURL(small))
    } catch {
      setPickError(true)
    } finally {
      setPreparing(false)
    }
  }

  const busy = upload?.state === 'sending' || upload?.state === 'offline'
  const ready = (!wantsPhoto || photo) && (!wantsText || text.trim())

  function send() {
    if (!ready) return
    if (wantsPhoto) sendPhoto(task.id, photo!, wantsText ? text.trim() : undefined)
    else sendText(task.id, text.trim())
  }

  return (
    <div className="flex flex-col gap-4">
      {wantsPhoto && (
        <input
          ref={picker}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            void pick(e.target.files?.[0])
            // Choosing the same file again after «Переснять» still fires a change
            e.target.value = ''
          }}
        />
      )}
      {preview && <img src={preview} alt={t('submit.previewAlt')} className="max-h-96 w-full rounded-xl object-contain bg-slate-100" />}
      {wantsText && (
        <label className="flex flex-col gap-1">
          <textarea
            value={text}
            maxLength={TEXT_MAX}
            rows={5}
            disabled={busy}
            placeholder={t('submit.textPlaceholder')}
            onChange={(e) => setText(e.target.value)}
            className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-base outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/20"
          />
          <span className="self-end text-xs text-slate-500">{t('submit.count', { count: text.length, max: TEXT_MAX })}</span>
        </label>
      )}
      {pickError && <p className="text-sm text-red-600">{t('submit.badPhoto')}</p>}
      <UploadStatus upload={upload} />
      {!busy && (
        wantsPhoto && !photo ? (
          <Button disabled={preparing} onClick={() => picker.current?.click()} className="gap-2">
            {preparing ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : <Camera className="size-4" aria-hidden />}
            {t('task.do')}
          </Button>
        ) : (
          <>
            <Button disabled={!ready || preparing} onClick={send}>{t('submit.send')}</Button>
            {wantsPhoto && (
              <Button variant="outline" disabled={preparing} onClick={() => picker.current?.click()}>{t('submit.retake')}</Button>
            )}
          </>
        )
      )}
    </div>
  )
}

export function TaskDetail() {
  const { t } = useTranslation()
  const id = Number(useParams().id)
  // Open at once from the feed's copy; the server's answer replaces it
  const [state, setState] = useState<State>(() => {
    const saved = cache.task(id)
    return saved ? { kind: 'ready', task: saved } : { kind: 'loading' }
  })
  const [award, setAward] = useState<Award | null>(null)
  const upload = useUpload(id)
  const shown = award ?? (upload?.state === 'sent' ? upload.award : null)

  // The result was seen here; next time the task itself says «Выполнено»
  useEffect(() => () => forgetUpload(id), [id])

  useEffect(() => {
    api<Task>(`/api/tasks/${id}`, { token: tokens.get('guest') })
      .then((task) => setState({ kind: 'ready', task }))
      .catch((err) => {
        if (err instanceof ApiError) setState({ kind: 'missing' })
        // Offline: keep the feed's copy if there is one
        else setState((s) => (s.kind === 'loading' ? { kind: 'missing' } : s))
      })
  }, [id])

  if (shown) return <Screen><AwardView award={shown} /></Screen>

  return (
    <Screen>
      <Link to="/app" className="flex items-center gap-1 text-sm font-medium text-slate-600">
        <ChevronLeft className="size-4" aria-hidden />
        {t('feed.toFeed')}
      </Link>
      {state.kind === 'loading' && <p className="text-center text-slate-500">{t('common.loading')}</p>}
      {state.kind === 'missing' && <Card className="text-center text-lg font-medium">{t('task.missing')}</Card>}
      {state.kind === 'ready' && (
        <Card className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
            <TaskIcon type={state.task.type} className="size-5 text-emerald-700" />
            <span>{t(`types.${state.task.type}`)}</span>
            {state.task.partner_name && <PartnerBadge name={state.task.partner_name} />}
          </div>
          <p className="whitespace-pre-line text-lg leading-relaxed">{state.task.text}</p>
          <Reward task={state.task} />
          <Action task={state.task} onAward={setAward} />
        </Card>
      )}
    </Screen>
  )
}
