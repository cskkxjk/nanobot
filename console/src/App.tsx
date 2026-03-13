import { Routes, Route, Navigate } from "react-router-dom";
import { isLoggedIn } from "./api";
import Login from "./pages/Login";
import Chat from "./pages/Chat";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={isLoggedIn() ? <Navigate to="/chat" replace /> : <Login />} />
      <Route path="/chat" element={isLoggedIn() ? <Chat /> : <Navigate to="/" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
