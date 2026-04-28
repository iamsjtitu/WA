import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, Outlet, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Register from "./pages/Register";
import DashboardLayout from "./pages/DashboardLayout";
import Overview from "./pages/Overview";
import Sessions from "./pages/Sessions";
import SessionDetail from "./pages/SessionDetail";
import ServiceCreate from "./pages/ServiceCreate";
import SendMessage from "./pages/SendMessage";
import BulkSend from "./pages/BulkSend";
import MessageLogs from "./pages/MessageLogs";
import ApiDocs from "./pages/ApiDocs";
import Customers from "./pages/Customers";
import AdminPlans from "./pages/AdminPlans";
import Billing from "./pages/Billing";
import Settings from "./pages/Settings";
import { Toaster } from "sonner";

function Protected() {
  const { user } = useAuth();
  const location = useLocation();
  if (user === null)
    return (
      <div className="min-h-screen flex items-center justify-center text-sm font-mono text-neutral-500">
        Loading…
      </div>
    );
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  return <Outlet />;
}

function GuestOnly({ children }) {
  const { user } = useAuth();
  if (user === null) return null;
  if (user) return <Navigate to="/app" replace />;
  return children;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster position="top-right" richColors closeButton />
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route
            path="/login"
            element={
              <GuestOnly>
                <Login />
              </GuestOnly>
            }
          />
          <Route
            path="/register"
            element={
              <GuestOnly>
                <Register />
              </GuestOnly>
            }
          />
          <Route element={<Protected />}>
            <Route path="/app" element={<DashboardLayout />}>
              <Route index element={<Overview />} />
              <Route path="sessions" element={<Sessions />} />
              <Route path="sessions/new" element={<ServiceCreate />} />
              <Route path="sessions/:id" element={<SessionDetail />} />
              <Route path="send" element={<SendMessage />} />
              <Route path="bulk" element={<BulkSend />} />
              <Route path="logs" element={<MessageLogs />} />
              <Route path="docs" element={<ApiDocs />} />
              <Route path="customers" element={<Customers />} />
              <Route path="plans" element={<AdminPlans />} />
              <Route path="billing" element={<Billing />} />
              <Route path="settings" element={<Settings />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
