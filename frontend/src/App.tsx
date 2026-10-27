import { Route, Routes } from 'react-router-dom'
import { AdminGuests } from './pages/AdminGuests'
import { Desk } from './pages/Desk'
import { Welcome } from './pages/Welcome'

// "К заданиям" leads to /app/tasks, which stays an empty page until the task feed piece
export default function App() {
  return (
    <Routes>
      <Route path="/app/welcome" element={<Welcome />} />
      <Route path="/desk" element={<Desk />} />
      <Route path="/admin/guests" element={<AdminGuests />} />
    </Routes>
  )
}
