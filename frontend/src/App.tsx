import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './components/AuthProvider';
import ProtectedRoute from './components/ProtectedRoute';
import MainLayout from './components/MainLayout';
import LandingPage from './components/LandingPage';
import DashboardPage from './components/DashboardPage';
import UploadForm from './components/UploadForm';
import AIDetectionPage from './components/AIDetectionPage';
import AdminPage from './components/AdminPage';
import BatchResultsPage from './components/BatchResultsPage';
import './index.css';

function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/" element={<MainLayout />}>
            <Route index element={<LandingPage />} />
            <Route path="dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
            <Route path="upload" element={<ProtectedRoute><UploadForm /></ProtectedRoute>} />
            <Route path="ai-check" element={<ProtectedRoute><AIDetectionPage /></ProtectedRoute>} />
            <Route path="admin" element={<ProtectedRoute requiredRole="admin"><AdminPage /></ProtectedRoute>} />
            <Route path="batch/:batchId" element={<ProtectedRoute><BatchResultsPage /></ProtectedRoute>} />
          </Route>
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;