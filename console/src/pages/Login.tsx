import { useState } from "react";
import { login, setToken } from "../api";

export default function Login() {
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const r = await login(userId.trim(), password);
      setToken(r.token, r.user_id);
      window.location.assign("/chat");
      return;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 380, margin: "100px auto", padding: 32, background: "#fff", borderRadius: 12, border: "1px solid #f0f0f0", boxShadow: "0 2px 8px rgba(0,0,0,0.08)" }}>
      <h1 style={{ marginBottom: 28, fontSize: 24, fontWeight: 600, color: "rgba(0,0,0,0.88)" }}>Nanobot 控制台</h1>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: 18 }}>
          <label style={{ display: "block", marginBottom: 8, color: "rgba(0,0,0,0.65)", fontSize: 14 }}>用户名</label>
          <input
            type="text"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            required
            autoComplete="username"
            style={{ width: "100%", padding: "12px 14px", fontSize: 16, background: "#fff", border: "1px solid #d9d9d9", color: "rgba(0,0,0,0.88)", borderRadius: 8 }}
          />
        </div>
        <div style={{ marginBottom: 24 }}>
          <label style={{ display: "block", marginBottom: 8, color: "rgba(0,0,0,0.65)", fontSize: 14 }}>密码</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            style={{ width: "100%", padding: "12px 14px", fontSize: 16, background: "#fff", border: "1px solid #d9d9d9", color: "rgba(0,0,0,0.88)", borderRadius: 8 }}
          />
        </div>
        {error && <p style={{ color: "#ff4d4f", marginBottom: 12, fontSize: 14 }}>{error}</p>}
        <button
          type="submit"
          disabled={loading}
          style={{ width: "100%", padding: 14, fontSize: 16, background: loading ? "#d9d9d9" : "#1677ff", border: "none", color: "#fff", borderRadius: 8, cursor: loading ? "not-allowed" : "pointer", fontWeight: 500 }}
        >
          {loading ? "登录中…" : "登录"}
        </button>
      </form>
    </div>
  );
}
