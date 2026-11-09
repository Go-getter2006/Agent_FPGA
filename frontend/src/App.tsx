// 路由：/login、/student/*、/teacher/*；登录后按角色跳转，角色不对的路由一律重定向
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useEffect } from 'react'
import { ApiError } from './api/client'
import { useMe } from './api/hooks'
import { ErrorState, Loading } from './components/Common'
import StudentLayout from './components/StudentLayout'
import { reporter } from './lib/events'
import Login, { homeFor } from './pages/Login'
import Consent from './pages/student/Consent'
import Home from './pages/student/Home'
import Problems from './pages/student/Problems'
import Report from './pages/student/Report'
import Review from './pages/student/Review'
import Workbench from './pages/student/Workbench'
import TeacherHome from './pages/teacher/TeacherHome'

function Guard({ role, children, consentPage = false }: { role: 'student' | 'teacher'; children: ReactNode; consentPage?: boolean }) {
  const me = useMe()
  const location = useLocation()
  useEffect(() => {
    if (me.data?.user.role === 'student') reporter.start()
    return () => reporter.stop()
  }, [me.data?.user.role])
  if (me.isLoading) return <Loading />
  if (me.error) {
    if (me.error instanceof ApiError && me.error.status === 401) return <Navigate to="/login" replace state={{ from: location.pathname }} />
    return <ErrorState error={me.error} onRetry={() => me.refetch()} />
  }
  const data = me.data!
  const isStudent = data.user.role === 'student'
  if ((role === 'student') !== isStudent) return <Navigate to={homeFor(data)} replace />
  if (isStudent && data.consent?.required && !consentPage) return <Navigate to="/student/consent" replace />
  if (isStudent && consentPage && !data.consent?.required) return <Navigate to="/student" replace />
  return <>{children}</>
}

function Root() {
  const me = useMe()
  if (me.isLoading) return <Loading />
  if (!me.data) return <Navigate to="/login" replace />
  return <Navigate to={homeFor(me.data)} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Root />} />
      <Route path="/login" element={<Login />} />
      <Route path="/student/consent" element={<Guard role="student" consentPage><Consent /></Guard>} />
      <Route path="/student/problems/:pid" element={<Guard role="student"><Workbench /></Guard>} />
      <Route path="/student" element={<Guard role="student"><StudentLayout /></Guard>}>
        <Route index element={<Home />} />
        <Route path="problems" element={<Problems />} />
        <Route path="report" element={<Report />} />
        <Route path="review" element={<Review />} />
      </Route>
      <Route path="/teacher/*" element={<Guard role="teacher"><TeacherHome /></Guard>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
