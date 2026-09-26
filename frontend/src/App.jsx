import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import Sidebar from './components/Sidebar'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import NewScreeningPage from './pages/NewScreeningPage'
import ScreeningDetailPage from './pages/ScreeningDetailPage'
import HistoryPage from './pages/HistoryPage'
import { Spinner } from './components/UIComponents'

function ProtectedLayout() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-sentinel-bg">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto bg-sentinel-bg">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/new-screening" element={<NewScreeningPage />} />
          <Route path="/screening/:id" element={<ScreeningDetailPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

function AppRoutes() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-sentinel-bg">
        <Spinner size="lg" />
      </div>
    )
  }

  return (
    <Routes>
      <Route
        path="/login"
        element={user ? <Navigate to="/" replace /> : <LoginPage />}
      />
      <Route path="/*" element={<ProtectedLayout />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
