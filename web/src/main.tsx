import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter, Route, Routes } from 'react-router-dom'
import './index.css'
import { Layout } from './components/Layout'
import Overview from './pages/Overview'
import Welcome from './pages/Welcome'
import { DatasetProvider } from './lib/dataset'

// Welcome and Overview ship in the main bundle for first paint; the rest load on demand.
const SupplierPage = lazy(() => import('./pages/SupplierPage'))
const Attribution = lazy(() => import('./pages/Attribution'))
const Briefs = lazy(() => import('./pages/Briefs'))
const Method = lazy(() => import('./pages/Method'))
const Upload = lazy(() => import('./pages/Upload'))

// Hash routing: the build is a folder of static files that works on any
// host, including a plain file server, with no rewrite rules.
const root = document.getElementById('root')
if (!root) throw new Error('index.html is missing the #root element')

createRoot(root).render(
  <StrictMode>
    <DatasetProvider>
    <HashRouter>
      <Suspense fallback={<div className="p-10 text-sm text-ink-3">Loading…</div>}>
        <Routes>
          <Route index element={<Welcome />} />
          <Route element={<Layout />}>
            <Route path="overview" element={<Overview />} />
            <Route path="supplier/:id" element={<SupplierPage />} />
            <Route path="attribution" element={<Attribution />} />
            <Route path="briefs" element={<Briefs />} />
            <Route path="method" element={<Method />} />
            <Route path="upload" element={<Upload />} />
            <Route path="*" element={<Overview />} />
          </Route>
        </Routes>
      </Suspense>
    </HashRouter>
    </DatasetProvider>
  </StrictMode>,
)
