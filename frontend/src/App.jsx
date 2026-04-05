import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Charts from './pages/Charts'
import Signals from './pages/Signals'
import Backtest from './pages/Backtest'
import Portfolio from './pages/Portfolio'
import News from './pages/News'
import TokenUsage from './pages/TokenUsage'
import Settings from './pages/Settings'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="charts" element={<Charts />} />
          <Route path="signals" element={<Signals />} />
          <Route path="backtest" element={<Backtest />} />
          <Route path="portfolio" element={<Portfolio />} />
          <Route path="news" element={<News />} />
          <Route path="tokens" element={<TokenUsage />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
