import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { api, ApiError, tokens } from '../api'
import { DeletePhoto, ResultCard, Reward, ReviewNote, TaskTypeTag } from '../components/console/game'
import { Button, Callout, Card, Checkbox, Icon, Loading, MessageCard, PageHeader, Screen, Spinner } from '../components/console/ui'
import { cache, type Award, type Task } from '../feed'
import { forgetUpload, isWaiting, prepare, send, useUpload, type Upload } from '../uploads'
import { useConfigVersion } from '../version'

type State = { kind: 'loading' } | { kind: 'missing' } | { kind: 'ready'; task: Task }

function Action({ task, onAward }: { task: Task; onAward: (a: Award) => void }) {
  const { t } = useTranslation()
  const [opened, setOpened] = useState(() => cache.linkOpened(task.id))
  const [ticked, setTicked] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const upload = useUpload(task.id)

  if (task.done && task.review === 'penalty') return <ReviewNote task={task} />
  // The guest deleted the photo before a decision: in place of the state label, as a penalty's note
  if (task.done && task.review === 'withdrawn') return <Callout tone="locked" icon="x">{t('review.withdrawn')}</Callout>
  // A finished quiz opens its result
  if (task.done && task.method === 'quiz') {
    return <Button to={`/app/quiz/${task.id}`} variant="outline" icon="check">{t('quiz.seeResult')}</Button>
  }
  if (task.done) {
    // Sent and paid, the moderator hasn't decided yet: «На проверке» while its stage runs, «Выполнено» after
    return (
      <p className="gc-done gc-label">
        <Icon name={task.state === 'review' ? 'clock' : 'check'} size={20} />
        {t(task.state === 'review' ? 'feed.review' : 'feed.done')}
      </p>
    )
  }
  const submits = task.method === 'photo' || task.method === 'text' || task.method === 'photo_text'
  // All its places are taken; it comes back when places free up or the admin raises the limit. A photo or text
  // already waiting on the phone, or refused, still shows how it went
  if (task.state === 'full') {
    return (
      <>
        {submits && <UploadStatus upload={upload} />}
        {!(submits && isWaiting(upload)) && <Callout tone="locked" icon="lock">{t('feed.full')}</Callout>}
      </>
    )
  }
  if (task.method === 'quiz') {
    if (task.locked) return <Callout tone="locked">{t('quiz.checkInFirst')}</Callout>
    return <Button to={`/app/quiz/${task.id}`}>{t('quiz.start')}</Button>
  }
  if (task.method === 'qr') {
    return <Callout tone="info" icon="qr">{t('task.scanHint')}</Callout>
  }
  if (task.method === 'market') {
    return (
      <Callout tone="info" icon="bag" action={<Button to="/market" icon="bag">{t('task.toMarket')}</Button>}>
        {t('task.marketHint')}
      </Callout>
    )
  }
  if (submits) {
    return (
      <>
        <ReviewNote task={task} />
        <Submit task={task} />
      </>
    )
  }
  if (task.method !== 'link') return <Button disabled icon="lock">{t('task.doSoon')}</Button>

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
      <Button
        href={task.link}
        icon="external"
        onClick={() => {
          cache.markLinkOpened(task.id)
          setOpened(true)
        }}
      >
        {t('task.do')}
      </Button>
      {opened && (
        <>
          <Checkbox checked={ticked} onChange={setTicked}>{t('task.registered')}</Checkbox>
          <Button variant="outline" disabled={!ticked} busy={busy} onClick={confirm}>{t('task.confirm')}</Button>
        </>
      )}
      {error && <Callout tone="danger">{error}</Callout>}
    </div>
  )
}

const TEXT_MAX = 500

function UploadStatus({ upload }: { upload: Upload | null }) {
  const { t } = useTranslation()
  if (upload?.state === 'sending') {
    return <p className="flex min-h-12 items-center justify-center"><Spinner label={t('submit.uploading')} /></p>
  }
  if (upload?.state === 'unclaimed') return <Callout tone="offline">{t('submit.unclaimed')}</Callout>
  if (upload?.state === 'claimed') return <Callout tone="offline">{t('submit.claimed')}</Callout>
  if (upload?.state === 'failed') {
    return <Callout tone="danger">{t(`submit.errors.${upload.reason}`, { defaultValue: t('common.error') })}</Callout>
  }
  return null
}

// Photo, text or both: pick or write, look it over, send once. «Отправить» saves it on the phone first

function Submit({ task }: { task: Task }) {
  const { t } = useTranslation()
  const upload = useUpload(task.id)
  const picker = useRef<HTMLInputElement>(null)
  const [photo, setPhoto] = useState<{ photo: Blob; thumb: Blob } | null>(null)
  const [preview, setPreview] = useState('')
  const [text, setText] = useState('')
  const [preparing, setPreparing] = useState(false)
  const [pickError, setPickError] = useState(false)
  const [full, setFull] = useState(false)
  // Saving on the phone takes a moment: a second tap meanwhile must not save the send twice
  const [saving, setSaving] = useState(false)
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
      const files = await prepare(file)
      setPhoto(files)
      setPreview(URL.createObjectURL(files.photo))
    } catch {
      setPickError(true)
    } finally {
      setPreparing(false)
    }
  }

  const busy = isWaiting(upload)
  const ready = (!wantsPhoto || photo) && (!wantsText || text.trim())

  async function submit() {
    if (!ready || saving) return
    setSaving(true)
    try {
      // Up to the admin's number of sends wait on one phone; beyond that nothing is saved
      setFull(!(await send(task.id, wantsText ? text.trim() : '', wantsPhoto ? photo! : undefined)))
    } finally {
      setSaving(false)
    }
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
      {/* The frame appears once a photo is picked: «Загрузка…» while it is prepared, then the photo */}
      {(preparing || preview) && (
        <div className="gc-photo-frame gc-crt" aria-busy={preparing || undefined}>
          {preparing
            ? <Spinner size={32} label={t('common.loading')} />
            : <img src={preview} alt={t('submit.previewAlt')} className="gc-photo-frame__img" />}
        </div>
      )}
      {wantsText && (
        <label className="gc-text-area">
          <textarea
            value={text}
            maxLength={TEXT_MAX}
            rows={5}
            disabled={busy}
            placeholder={t('submit.textPlaceholder')}
            aria-label={t('submit.textPlaceholder')}
            onChange={(e) => setText(e.target.value)}
            className="gc-text-area__field gc-body"
          />
          <span className="gc-text-area__count gc-caption gc-num">{t('submit.count', { count: text.length, max: TEXT_MAX })}</span>
        </label>
      )}
      {pickError && <Callout tone="danger" icon="camera">{t('submit.badPhoto')}</Callout>}
      {full && !busy && <Callout tone="warning">{t('submit.queueFull')}</Callout>}
      <UploadStatus upload={upload} />
      {!busy && (
        wantsPhoto && !photo ? (
          <Button busy={preparing} icon="camera" onClick={() => picker.current?.click()}>{t('task.do')}</Button>
        ) : (
          <>
            <Button disabled={!ready || preparing || saving} onClick={() => void submit()}>{t('submit.send')}</Button>
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

  const load = useCallback(() => {
    api<Task>(`/api/tasks/${id}`, { token: tokens.get('guest') })
      .then((task) => setState({ kind: 'ready', task }))
      .catch((err) => {
        if (err instanceof ApiError) setState({ kind: 'missing' })
        // Offline: keep the feed's copy if there is one
        else setState((s) => (s.kind === 'loading' ? { kind: 'missing' } : s))
      })
  }, [id])

  useEffect(load, [load])
  // An admin's change to the task (points, switched off) shows within 10 seconds
  useConfigVersion(load)

  if (shown) return <Screen><ResultCard award={shown} /></Screen>
  if (state.kind === 'loading') return <Screen><Loading /></Screen>
  if (state.kind === 'missing') {
    return (
      <Screen>
        <MessageCard icon="alert" title={t('task.missing')} action={<Button to="/app" icon="chevron-left">{t('feed.toFeed')}</Button>} />
      </Screen>
    )
  }

  const { task } = state
  return (
    <Screen>
      <PageHeader title={t(`types.${task.type}`)} back={{ to: '/app', label: t('feed.toFeed') }} />
      <Card>
        <TaskTypeTag task={task} showType={false} />
        <p className="gc-body-l m-0 whitespace-pre-line [overflow-wrap:anywhere]">{task.text}</p>
        <Reward task={task} size="m" />
        <Action task={task} onAward={setAward} />
        {task.photo_id != null && (
          <DeletePhoto key={task.photo_id} photoId={task.photo_id} undecided={!!task.photo_undecided} onDeleted={load} />
        )}
      </Card>
    </Screen>
  )
}
