import { Route, Routes } from 'react-router-dom'
import { AdminGuests } from './pages/AdminGuests'
import { AdminTasks } from './pages/AdminTasks'
import { Desk } from './pages/Desk'
import { Feed } from './pages/Feed'
import { TaskDetail } from './pages/TaskDetail'
import { Welcome } from './pages/Welcome'

export default function App() {
  return (
    <Routes>
      <Route path="/app" element={<Feed />} />
      <Route path="/app/tasks/:id" element={<TaskDetail />} />
      <Route path="/app/welcome" element={<Welcome />} />
      <Route path="/desk" element={<Desk />} />
      <Route path="/admin/guests" element={<AdminGuests />} />
      <Route path="/admin/tasks" element={<AdminTasks />} />
    </Routes>
  )
}
