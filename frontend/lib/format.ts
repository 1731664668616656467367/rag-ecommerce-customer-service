export function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  if (sameDay) return hm;
  return `${d.getMonth() + 1}月${d.getDate()}日 ${hm}`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function relativeDay(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const today = new Date();
  const diff = Math.floor(
    (new Date(today.toDateString()).getTime() - new Date(d.toDateString()).getTime()) / 86400000
  );
  if (diff <= 0) return "今天";
  if (diff === 1) return "昨天";
  if (diff < 7) return `${diff} 天前`;
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

/** 降级原因 -> 给用户看的人话 */
export const DEGRADED_TEXT: Record<string, string> = {
  llm_not_configured: "后端未配置大模型密钥，当前仅展示知识库原文",
  llm_timeout: "大模型响应超时，当前仅展示知识库原文",
  llm_unavailable: "大模型服务暂时不可用，当前仅展示知识库原文",
  llm_quota_exceeded: "大模型账户余额不足，当前仅展示知识库原文",
  llm_auth_error: "大模型鉴权失败，请联系管理员",
};
