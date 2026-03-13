import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  listSessions,
  createSession,
  getSessionMessages,
  fetchAttachmentBlobUrl,
  downloadAttachment,
  uploadFiles,
  transcribeVoice,
  streamChat,
  logout,
  getUserId,
  getToken,
} from "../api";
import styles from "./Chat.module.css";

function VoiceBar({ url }: { url: string }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  return (
    <button
      type="button"
      className={styles.audioBar}
      onClick={() => audioRef.current?.play()}
      title="点击播放"
    >
      <audio ref={audioRef} src={url} preload="metadata" />
      <span style={{ marginRight: 6 }}>🎤</span>
      <span style={{ fontSize: 12, color: "rgba(0,0,0,0.65)" }}>点击播放</span>
    </button>
  );
}

type SessionItem = { key: string; session_id: string; title: string; updated_at?: string };
type StreamMeta = { reasoning: string[]; tool: string[] };
type Message = {
  role: "user" | "assistant";
  content: string;
  streamMeta?: StreamMeta;
  /** 用户语音消息的录音 blob URL，用于重放 */
  voiceUrl?: string | null;
  /** 仅 assistant：当 agent 返回的是音频文件时的播放 URL，此时显示音频条 */
  audioUrl?: string | null;
  /** 用户消息中附带的图片预览 blob URL，用于在气泡内展示 */
  attachmentUrls?: string[];
  /** 仅 assistant：agent 通过 send_file 发来的文件相对路径，用于下载 */
  attachment_paths?: string[];
};

export default function Chat() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [attachedPaths, setAttachedPaths] = useState<string[]>([]);
  /** 与 attachedPaths 一一对应，用于生成图片预览 URL 并在发送后展示在消息中 */
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingMeta, setStreamingMeta] = useState<{ reasoning: string[]; tool: string[] }>({ reasoning: [], tool: [] });
  const [pushNotification, setPushNotification] = useState<{ session_id: string; content: string } | null>(null);
  const [notificationPermission, setNotificationPermission] = useState<NotificationPermission>(
    () => ("Notification" in window ? Notification.permission : "denied")
  );
  const [dragOver, setDragOver] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  /** 当前输入区录音预览：可点击重放，发送后清空 */
  const [voicePreviewUrl, setVoicePreviewUrl] = useState<string | null>(null);
  const [inputFocused, setInputFocused] = useState(false);
  const abortRef = useRef<(() => void) | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const messagesRef = useRef<Message[]>([]);
  const streamingMetaRef = useRef<StreamMeta>({ reasoning: [], tool: [] });
  useEffect(() => {
    streamingMetaRef.current = streamingMeta;
  }, [streamingMeta]);

  // SSE for push notifications (e.g. cron reminders)
  useEffect(() => {
    const token = getToken();
    if (!token) return;
    const url = `/api/events?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as { session_id?: string; content?: string };
        const session_id = data.session_id ?? "";
        const content = data.content ?? "";
        setPushNotification({ session_id, content });
        if (session_id && currentSessionId === session_id) {
          setMessages((prev) => [...prev, { role: "assistant", content }]);
        }
        // 浏览器桌面弹窗提醒
        if (content && "Notification" in window) {
          const show = () => {
            const body = content.length > 200 ? content.slice(0, 197) + "…" : content;
            const n = new Notification("Nanobot 提醒", { body, icon: "/favicon.ico" });
            n.onclick = () => {
              n.close();
              window.focus();
            };
          };
          if (Notification.permission === "granted") {
            show();
          } else if (Notification.permission === "default") {
            Notification.requestPermission().then((p) => {
              setNotificationPermission(p);
              if (p === "granted") show();
            });
          }
        }
      } catch {
        // ignore parse errors
      }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [currentSessionId]);

  const loadSessions = useCallback(async () => {
    try {
      const list = await listSessions();
      setSessions(list);
      /* 不自动选中已有会话，进入时默认显示新会话 */
    } catch {
      setSessions([]);
    }
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // Load history when switching session; revoke blob URLs from previous messages
  useEffect(() => {
    if (!currentSessionId) {
      messagesRef.current.forEach((m) => {
        if (m.voiceUrl) URL.revokeObjectURL(m.voiceUrl);
        m.attachmentUrls?.forEach((u) => URL.revokeObjectURL(u));
      });
      setMessages([]);
      return;
    }
    let cancelled = false;
    const prev = messagesRef.current;
    prev.forEach((m) => {
      if (m.voiceUrl) URL.revokeObjectURL(m.voiceUrl);
      m.attachmentUrls?.forEach((u) => URL.revokeObjectURL(u));
    });
    getSessionMessages(currentSessionId)
      .then(async (data) => {
        if (cancelled || !data.messages) return;
        const withUrls = await Promise.all(
          data.messages.map(async (m) => {
            const msg: Message = {
              role: m.role as "user" | "assistant",
              content: m.content || "",
            };
            if (m.attachment_paths?.length) {
              try {
                msg.attachmentUrls = await Promise.all(
                  m.attachment_paths.map((p) => fetchAttachmentBlobUrl(p))
                );
              } catch {
                msg.attachmentUrls = [];
              }
            }
            return msg;
          })
        );
        if (!cancelled) setMessages(withUrls);
      })
      .catch(() => {
        if (!cancelled) setMessages([]);
      });
    setStreamingContent("");
    setStreamingMeta({ reasoning: [], tool: [] });
    return () => {
      cancelled = true;
    };
  }, [currentSessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent, streamingMeta]);

  async function handleNewSession() {
    try {
      const r = await createSession();
      const uid = getUserId();
      const newItem: SessionItem = {
        key: uid ? `dashboard:${uid}:${r.session_id}` : r.session_id,
        session_id: r.session_id,
        title: "New chat",
        updated_at: new Date().toISOString(),
      };
      setSessions((prev) => [newItem, ...prev]);
      setCurrentSessionId(r.session_id);
      setMessages([]);
      setStreamingContent("");
      setStreamingMeta({ reasoning: [], tool: [] });
      setSidebarOpen(false);
    } catch (e) {
      console.error(e);
    }
  }

  function handleLogout() {
    logout();
    navigate("/", { replace: true });
  }

  function handleAttach() {
    fileInputRef.current?.click();
  }

  async function onFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files?.length) return;
    const list = Array.from(files);
    try {
      const r = await uploadFiles(list);
      const paths = r.paths.slice(0, list.length);
      setAttachedPaths((p) => [...p, ...paths]);
      setAttachedFiles((p) => [...p, ...list]);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Upload failed");
    }
    e.target.value = "";
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!dragOver) setDragOver(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (e.currentTarget === e.target || !e.currentTarget.contains(e.relatedTarget as Node)) setDragOver(false);
  }

  async function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    const files = e.dataTransfer?.files;
    if (!files?.length) return;
    const list = Array.from(files);
    try {
      const r = await uploadFiles(list);
      const paths = r.paths.slice(0, list.length);
      setAttachedPaths((p) => [...p, ...paths]);
      setAttachedFiles((p) => [...p, ...list]);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Upload failed");
    }
  }

  function removeAttachment(index: number) {
    setAttachedPaths((p) => p.filter((_, i) => i !== index));
    setAttachedFiles((f) => f.filter((_, i) => i !== index));
  }

  async function handleVoiceInput() {
    if (isRecording) {
      const rec = mediaRecorderRef.current;
      if (rec && rec.state === "recording") rec.stop();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      alert("您的浏览器不支持麦克风录音");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      mediaRecorderRef.current = rec;
      const chunks: Blob[] = [];
      rec.ondataavailable = (e) => {
        if (e.data.size) chunks.push(e.data);
      };
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        mediaRecorderRef.current = null;
        setIsRecording(false);
        if (chunks.length === 0) return;
        const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
        const url = URL.createObjectURL(blob);
        try {
          const file = new File([blob], "voice.webm", { type: blob.type });
          const r = await transcribeVoice(file);
          const text = (r.text || "").trim();
          if (text) {
            doSend(text, url, []);
          } else {
            setVoicePreviewUrl(url);
            setInput("");
          }
        } catch (err) {
          setVoicePreviewUrl(url);
          setInput("");
          alert(err instanceof Error ? err.message : "Transcribe failed");
        }
      };
      rec.start();
      setIsRecording(true);
    } catch (err) {
      alert(err instanceof Error ? err.message : "无法访问麦克风");
    }
  }

  function clearVoicePreview() {
    if (voicePreviewUrl) {
      URL.revokeObjectURL(voicePreviewUrl);
      setVoicePreviewUrl(null);
    }
  }

  messagesRef.current = messages;

  async function doSend(text: string, voiceUrl?: string | null, paths?: string[], files?: File[]) {
    const trimmed = text.trim();
    const pathsToUse = paths ?? attachedPaths;
    if (!trimmed && !pathsToUse.length) return;
    if (loading) return;
    const imageUrls =
      files?.filter((f) => f.type.startsWith("image/")).map((f) => URL.createObjectURL(f)) ?? [];
    let sessionId = currentSessionId;
    if (!sessionId) {
      try {
        const r = await createSession();
        sessionId = r.session_id;
        const uid = getUserId();
        const newItem: SessionItem = {
          key: uid ? `dashboard:${uid}:${r.session_id}` : r.session_id,
          session_id: r.session_id,
          title: "New chat",
          updated_at: new Date().toISOString(),
        };
        setSessions((prev) => [newItem, ...prev]);
        setCurrentSessionId(r.session_id);
      } catch (e) {
        console.error(e);
        return;
      }
    }
    setInput("");
    setAttachedPaths([]);
    setAttachedFiles([]);
    const userMsg: Message = {
      role: "user",
      content: trimmed,
      voiceUrl: voiceUrl || undefined,
      ...(imageUrls.length > 0 ? { attachmentUrls: imageUrls } : {}),
    };
    setMessages((m) => [...m, userMsg]);
    setLoading(true);
    setStreamingContent("");
    setStreamingMeta({ reasoning: [], tool: [] });

    abortRef.current = streamChat(
      trimmed,
      sessionId,
      pathsToUse,
      (event, data) => {
        if (event === "message") {
          const payload = typeof data === "string" ? { text: data } : (data as { text?: string; audio_url?: string; attachment_paths?: string[] });
          const content = payload?.text ?? "";
          const audioUrl = payload?.audio_url ?? undefined;
          const attachment_paths = payload?.attachment_paths ?? undefined;
          const meta: StreamMeta = { reasoning: [...streamingMetaRef.current.reasoning], tool: [...streamingMetaRef.current.tool] };
          setMessages((m) => [...m, { role: "assistant", content, streamMeta: meta, audioUrl, attachment_paths }]);
          setStreamingContent("");
          setStreamingMeta({ reasoning: [], tool: [] });
          setLoading(false);
          loadSessions();
          return;
        }
        if (event === "error") {
          setMessages((m) => [...m, { role: "assistant", content: "Error: " + String(data) }]);
          setLoading(false);
          return;
        }
        if (event === "reasoning") {
          setStreamingMeta((meta) => ({ ...meta, reasoning: [...meta.reasoning, String(data)] }));
          return;
        }
        if (event === "tool_summary") {
          const o = data as { tool_name?: string; status?: string; output?: string };
          const line = [o.tool_name, o.status, o.output].filter(Boolean).join(" — ");
          setStreamingMeta((meta) => ({ ...meta, tool: [...meta.tool, line] }));
          return;
        }
        if (event === "text_delta" || event === "reasoning_delta") {
          setStreamingContent((c) => c + (typeof data === "string" ? data : ""));
        }
        if (event === "tool_hint" || event === "progress") {
          setStreamingMeta((meta) => ({ ...meta, tool: [...meta.tool, String(data)] }));
        }
      }
    );
  }

  function sendMessage() {
    const text = input.trim();
    if (!text && !attachedFiles.length) return;
    doSend(text, voicePreviewUrl, attachedPaths, attachedFiles.length ? attachedFiles : undefined);
    if (voicePreviewUrl) setVoicePreviewUrl(null);
  }

  return (
    <div className={styles.container}>
      {sidebarOpen && (
        <button
          type="button"
          onClick={() => setSidebarOpen(false)}
          className={styles.sidebarBackdrop}
          aria-label="关闭侧栏"
        />
      )}
      <aside
        className={`${styles.sidebar} ${sidebarOpen ? styles.sidebarOverlay : styles.sidebarCollapsed}`}
      >
        <div className={styles.sidebarHeader}>
          <span className={styles.sidebarTitle}>Nanobot</span>
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            className={styles.sidebarClose}
            aria-label="收起侧栏"
          >
            ◀
          </button>
        </div>
        <button
          type="button"
          onClick={handleNewSession}
          className={styles.sidebarNewChat}
        >
          新建对话
        </button>
        <ul className={styles.sidebarList}>
          {sessions.map((s) => (
            <li key={s.key}>
              <button
                type="button"
                onClick={() => {
                  setCurrentSessionId(s.session_id);
                  setSidebarOpen(false);
                }}
                className={`${styles.sessionItem} ${currentSessionId === s.session_id ? styles.sessionItemActive : ""}`}
              >
                {s.title || "New chat"}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className={styles.main}>
        <header className={styles.mainHeader}>
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className={styles.headerMenuBtn}
            aria-label="展开会话列表"
          >
            ☰
          </button>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: "auto" }}>
            {"Notification" in window && notificationPermission !== "granted" && (
              <button
                type="button"
                onClick={() => {
                  Notification.requestPermission().then((p) => setNotificationPermission(p));
                }}
                style={{ padding: "8px 12px", background: "#e6f4ff", border: "1px solid #91caff", color: "rgba(0,0,0,0.88)", borderRadius: 8, cursor: "pointer", fontSize: 13 }}
              >
                开启桌面提醒
              </button>
            )}
            <button type="button" onClick={handleLogout} style={{ padding: "8px 14px", background: "#f5f5f5", border: "1px solid #d9d9d9", color: "rgba(0,0,0,0.88)", borderRadius: 8, cursor: "pointer", fontSize: 14 }}>退出</button>
          </div>
        </header>

        {pushNotification && (
          <div style={{ padding: "12px 24px", background: "#e6f4ff", borderBottom: "1px solid #91caff", display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ flex: 1, fontSize: 14, color: "rgba(0,0,0,0.88)" }}>🔔 {pushNotification.content}</span>
            <button type="button" onClick={() => setPushNotification(null)} style={{ padding: "4px 8px", background: "transparent", border: "none", color: "rgba(0,0,0,0.45)", cursor: "pointer", fontSize: 14 }}>关闭</button>
          </div>
        )}

        <div
          className={`${styles.dropZone} ${dragOver ? styles.dropZoneActive : ""}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
        <div className={styles.messagesArea}>
          {messages.length === 0 && !loading && (
            <div className={styles.welcomePlaceholder}>
              <div className={styles.welcomePlaceholderTitle}>Nanobot</div>
              <div className={styles.welcomePlaceholderHint}>
                轻量个人 AI 助手 · 支持文字、语音、附件与多轮对话
              </div>
            </div>
          )}
          {messages.map((msg, i) => (
            <div
              key={i}
              style={{
                marginBottom: 16,
                textAlign: msg.role === "user" ? "right" : "left",
                maxWidth: "85%",
                marginLeft: msg.role === "user" ? "auto" : 0,
                marginRight: msg.role === "user" ? 0 : "auto",
              }}
            >
              {msg.role === "assistant" && msg.streamMeta && (msg.streamMeta.reasoning.length > 0 || msg.streamMeta.tool.length > 0) && (
                <div style={{ marginBottom: 8 }}>
                  {msg.streamMeta.reasoning.length > 0 && (
                    <details style={{ marginBottom: 6, background: "#f5f5f5", padding: "8px 12px", borderRadius: 8, border: "1px solid #f0f0f0" }}>
                      <summary style={{ cursor: "pointer", color: "rgba(0,0,0,0.65)", fontSize: 13 }}>思维链</summary>
                      <pre style={{ margin: "8px 0 0", fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-word", color: "rgba(0,0,0,0.88)" }}>{msg.streamMeta.reasoning.join("")}</pre>
                    </details>
                  )}
                  {msg.streamMeta.tool.length > 0 && (
                    <details style={{ marginBottom: 6, background: "#f5f5f5", padding: "8px 12px", borderRadius: 8, border: "1px solid #f0f0f0" }}>
                      <summary style={{ cursor: "pointer", color: "rgba(0,0,0,0.65)", fontSize: 13 }}>工具 / 进度</summary>
                      <pre style={{ margin: "8px 0 0", fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-word", color: "rgba(0,0,0,0.88)" }}>{msg.streamMeta.tool.join("\n")}</pre>
                    </details>
                  )}
                </div>
              )}
              {(msg.content || msg.attachmentUrls?.length || msg.attachment_paths?.length || (msg.role === "user" && msg.voiceUrl)) && (
              <div
                className={`${styles.msgContent} ${msg.role === "assistant" ? styles.msgContentAssistant : styles.msgContentUser}`}
              >
                {msg.role === "assistant" ? (
                  <>
                    <ReactMarkdown remarkPlugins={[remarkGfm]} className={styles.markdownBody}>
                      {msg.content}
                    </ReactMarkdown>
                    {msg.attachment_paths && msg.attachment_paths.length > 0 && (
                      <div className={styles.msgDownloads}>
                        {msg.attachment_paths.map((path, j) => {
                          const name = path.replace(/^.*[/\\]/, "") || "file";
                          return (
                            <button
                              key={j}
                              type="button"
                              className={styles.msgDownloadBtn}
                              onClick={() => downloadAttachment(path, name).catch((e) => alert(e?.message || "下载失败"))}
                            >
                              📥 {name}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    {msg.attachmentUrls && msg.attachmentUrls.length > 0 && (
                      <div className={styles.msgImages}>
                        {msg.attachmentUrls.map((url, j) => (
                          <img key={j} src={url} alt="" className={styles.msgImage} />
                        ))}
                      </div>
                    )}
                    {msg.content && (
                      <span style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{msg.content}</span>
                    )}
                  </>
                )}
              </div>
              )}
              {msg.role === "assistant" && msg.audioUrl && (
                <VoiceBar url={msg.audioUrl} />
              )}
              {msg.role === "user" && msg.voiceUrl && (
                <VoiceBar url={msg.voiceUrl} />
              )}
            </div>
          ))}
          {loading && (
            <div style={{ marginBottom: 16, textAlign: "left" }}>
              {streamingMeta.reasoning.length > 0 && (
                <details open style={{ marginBottom: 8, background: "#f5f5f5", padding: "10px 14px", borderRadius: 10, border: "1px solid #f0f0f0" }}>
                  <summary style={{ cursor: "pointer", color: "rgba(0,0,0,0.65)", fontSize: 13 }}>思维链</summary>
                  <pre style={{ margin: "8px 0 0", fontSize: 12, whiteSpace: "pre-wrap", color: "rgba(0,0,0,0.88)" }}>{streamingMeta.reasoning.join("")}</pre>
                </details>
              )}
              {streamingMeta.tool.length > 0 && (
                <details open style={{ marginBottom: 8, background: "#f5f5f5", padding: "10px 14px", borderRadius: 10, border: "1px solid #f0f0f0" }}>
                  <summary style={{ cursor: "pointer", color: "rgba(0,0,0,0.65)", fontSize: 13 }}>工具 / 进度</summary>
                  <pre style={{ margin: "8px 0 0", fontSize: 12, whiteSpace: "pre-wrap", color: "rgba(0,0,0,0.88)" }}>{streamingMeta.tool.join("\n")}</pre>
                </details>
              )}
              {streamingContent && (
                <div className={`${styles.msgContent} ${styles.msgContentAssistant}`}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]} className={styles.markdownBody}>
                    {streamingContent}
                  </ReactMarkdown>
                </div>
              )}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className={styles.inputArea}>
          {attachedFiles.length > 0 && (
            <div className={styles.attachedRow}>
              <span className={styles.attachedHint}>已附加 {attachedFiles.length} 个文件</span>
              <div className={styles.attachedChips}>
                {attachedFiles.map((file, i) => (
                  <span key={i} className={styles.attachedChip}>
                    <span className={styles.attachedChipName} title={file.name}>
                      {file.name.length > 12 ? file.name.slice(0, 10) + "…" : file.name}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeAttachment(i)}
                      className={styles.attachedChipRemove}
                      aria-label="移除该附件"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            </div>
          )}
          {voicePreviewUrl && (
            <div className={styles.voicePreviewRow}>
              <VoiceBar url={voicePreviewUrl} />
              <button type="button" onClick={clearVoicePreview} className={styles.btnClear}>清除</button>
            </div>
          )}
          <div className={`${styles.inputBar} ${inputFocused ? styles.inputBarFocused : ""}`}>
            <input type="file" ref={fileInputRef} onChange={onFileSelect} multiple style={{ display: "none" }} />
            {!inputFocused && (
              <>
                <button
                  type="button"
                  onClick={handleVoiceInput}
                  className={styles.inputBarIcon}
                  title={isRecording ? "停止录音" : "语音"}
                  aria-label="语音"
                >
                  {isRecording ? "⏹" : "🎤"}
                </button>
                <textarea
                  className={styles.inputField}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), sendMessage())}
                  onFocus={() => setInputFocused(true)}
                  placeholder="发消息..."
                  rows={2}
                />
                <button
                  type="button"
                  onClick={handleAttach}
                  className={styles.inputBarIcon}
                  title="附件"
                  aria-label="附件"
                >
                  📎
                </button>
              </>
            )}
            {inputFocused && (
              <textarea
                className={`${styles.inputField} ${styles.inputFieldFocused}`}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), sendMessage())}
                onBlur={() => setInputFocused(false)}
                autoFocus
                placeholder="发消息…"
                rows={3}
              />
            )}
            {loading ? (
              <button
                type="button"
                onClick={() => abortRef.current?.()}
                onMouseDown={(e) => inputFocused && e.preventDefault()}
                className={styles.btnSendStop}
              >
                停止
              </button>
            ) : (
              <button
                type="button"
                onClick={sendMessage}
                onMouseDown={(e) => inputFocused && e.preventDefault()}
                disabled={loading}
                className={styles.btnSend}
              >
                发送
              </button>
            )}
          </div>
          {inputFocused && (
            <div className={styles.inputBottomRow}>
              <button
                type="button"
                onClick={handleVoiceInput}
                onMouseDown={(e) => e.preventDefault()}
                className={styles.bottomIcon}
                title={isRecording ? "停止录音" : "语音"}
                aria-label="语音"
              >
                {isRecording ? "⏹" : "🎤"}
              </button>
              <button
                type="button"
                onClick={handleAttach}
                onMouseDown={(e) => e.preventDefault()}
                className={styles.bottomIcon}
                title="附件"
                aria-label="附件"
              >
                📎
              </button>
            </div>
          )}
        </div>
        </div>
      </main>
    </div>
  );
}
