"use client";

import { relativeDay } from "@/lib/format";
import type { SessionItem } from "@/lib/types";
import { CloseIcon, PlusIcon, TrashIcon } from "@/components/icons";

interface Props {
  sessions: SessionItem[];
  activeId: string | null;
  loading: boolean;
  mobileOpen: boolean;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  onCloseMobile: () => void;
}

export default function SessionSidebar({
  sessions,
  activeId,
  loading,
  mobileOpen,
  onSelect,
  onCreate,
  onDelete,
  onCloseMobile,
}: Props) {
  return (
    <>
      {/* 移动端遮罩 */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-ink/20 lg:hidden"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[268px] flex-col border-r border-hairline bg-mist/50 transition-transform duration-200 lg:static lg:z-0 lg:translate-x-0 ${
          /* 关闭时多推 5%，否则 1px 边框会在屏幕左侧留一条细线 */
          mobileOpen ? "translate-x-0" : "-translate-x-[105%] pointer-events-none lg:pointer-events-auto"
        }`}
        aria-label="会话列表"
      >
        <div className="flex items-center gap-2 px-4 pb-2 pt-14 lg:pt-4">
          <button type="button" onClick={onCreate} className="btn-primary flex-1">
            <PlusIcon className="h-4 w-4" />
            新建对话
          </button>
          <button
            type="button"
            onClick={onCloseMobile}
            className="btn-quiet px-2 lg:hidden"
            aria-label="关闭会话列表"
          >
            <CloseIcon />
          </button>
        </div>

        <div className="px-4 pb-1 pt-3">
          <p className="label">历史会话</p>
        </div>

        <nav className="scroll-thin flex-1 overflow-y-auto px-2 pb-4">
          {loading && <p className="px-3 py-2 text-[13px] text-muted">加载中…</p>}

          {!loading && sessions.length === 0 && (
            <p className="px-3 py-2 text-[13px] leading-relaxed text-muted">
              还没有会话。发送第一条问题后会自动创建。
            </p>
          )}

          <ul className="space-y-0.5">
            {sessions.map((s) => {
              const active = s.id === activeId;
              return (
                <li key={s.id} className="group relative">
                  <button
                    type="button"
                    onClick={() => onSelect(s.id)}
                    aria-current={active ? "true" : undefined}
                    className={`w-full rounded-xl px-3 py-2 text-left transition-colors ${
                      active ? "bg-white shadow-sm" : "hover:bg-white/70"
                    }`}
                  >
                    <span className="block truncate pr-6 text-[13.5px] text-ink">{s.title}</span>
                    <span className="mt-0.5 block text-[11.5px] text-muted">
                      {relativeDay(s.updated_at)}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(s.id);
                    }}
                    aria-label={`删除会话 ${s.title}`}
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-muted opacity-0 transition-opacity hover:bg-mist hover:text-ink focus:opacity-100 group-hover:opacity-100"
                  >
                    <TrashIcon className="h-4 w-4" />
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="border-t border-hairline px-4 py-3">
          <p className="text-[11px] leading-relaxed text-muted">
            会话与消息保存在本地 SQLite，重启后仍可查看。
          </p>
        </div>
      </aside>
    </>
  );
}
