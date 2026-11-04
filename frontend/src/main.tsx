import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.tsx'
import { skinReady } from './components/console/skin'
import './i18n'
import './index.css'
import { takeLoginFromAddress } from './push'
import { resumeUploads } from './uploads'

// The Home Screen app's first opening: the login came in the address
takeLoginFromAddress()

// The first paint is already in the event's skin
skinReady().then(() => createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
))

// Lets /app open from the phone's copy when the network drops, and sends waiting photos with the app closed (Android)
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {})
}
// Photos and texts saved on the phone before the app was last closed go on sending
resumeUploads()
