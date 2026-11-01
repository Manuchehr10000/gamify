import { Route, Routes } from 'react-router-dom'
import { AdminGuests } from './pages/AdminGuests'
import { AdminTasks } from './pages/AdminTasks'
import { AdminTasksQr } from './pages/AdminTasksQr'
import { Desk } from './pages/Desk'
import { Feed } from './pages/Feed'
import { Hall } from './pages/Hall'
import { Market } from './pages/Market'
import { Moderate } from './pages/Moderate'
import { Quiz } from './pages/Quiz'
import { Rating } from './pages/Rating'
import { Scan } from './pages/Scan'
import { Stand } from './pages/Stand'
import { TaskDetail } from './pages/TaskDetail'
import { Welcome } from './pages/Welcome'

export default function App() {
  return (
    <Routes>
      <Route path="/app" element={<Feed />} />
      <Route path="/app/rating" element={<Rating />} />
      <Route path="/app/tasks/:id" element={<TaskDetail />} />
      <Route path="/app/quiz/:id" element={<Quiz />} />
      <Route path="/app/welcome" element={<Welcome />} />
      <Route path="/desk" element={<Desk />} />
      <Route path="/admin/guests" element={<AdminGuests />} />
      <Route path="/admin/tasks" element={<AdminTasks />} />
      <Route path="/admin/tasks/qr" element={<AdminTasksQr />} />
      <Route path="/q/:code" element={<Scan />} />
      <Route path="/market" element={<Market />} />
      <Route path="/stand/:code" element={<Stand />} />
      <Route path="/moderate" element={<Moderate />} />
      <Route path="/hall" element={<Hall />} />
    </Routes>
  )
}
