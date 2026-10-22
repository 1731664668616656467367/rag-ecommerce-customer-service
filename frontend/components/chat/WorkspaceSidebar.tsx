"use client";

import Link from "next/link";
import { relativeDay } from "@/lib/format";
import type { SessionItem } from "@/lib/types";
import {
  ChevronDownIcon,
  CloseIcon,
  PanelIcon,
  PlusIcon,
  ShieldIcon,
  TrashIcon,
} from "@/components/icons";

/** 工作台左侧栏：新建会话 + 会话历史 + 当前运行模式。
 *
 *  为什么这里不再放"聊天 / 知识库 / 设置"这组导航？
 *  全站顶栏已经有同一组胶囊导航，且每个页面都在。侧栏再放一遍，
 *  等于在相隔 40px 的地方给用户两份一模一样的入口——既占高度，
 *  也让人分不清"哪个才是当前所在的位置"。侧栏只承担它独有的事：
 *  在当前会话与历史会话之间切换。
 *
 *  折叠：桌面端隐藏（68px 只留图标列），状态存 localStorage。
 *  移动端走抽屉，遮罩点击关闭。
 */
interface Props {
  sessions: SessionItem[];
  activeId: string | null;
  loading: boolean;
  mobileOpen: boolean;
  collapsed: boolean;
  modeLabel: string;
  modeUsable: boolean;
  modelHint: string;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  onToggleCollapse: () => void;
  onCloseMobile: () => void;
}

export default function WorkspaceSidebar({
  sessions,
  activeId,
  loading,
  mobileOpen,
  collapsed,
  modeLabel,
  modeUsable,
  modelHint,
  onSelect,
  onCreate,
  onDelete,
  onToggleCollapse,
  onCloseMobile,
}: Props) {
  return (
    <>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-ink/20 animate-fade backdrop-blur-[2px] lg:hidden"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <aside
        aria-label="工作台导航"
        className={`fixed inset-y-0 left-0 z-40 flex flex-col border-r border-hairline bg-[#FAF8F2] transition-[width,transform] duration-200 ease-out-soft
          lg:static lg:z-0 lg:translate-x-0
          ${mobileOpen ? "translate-x-0" : "-translate-x-[105%] pointer-events-none lg:pointer-events-auto"}
          ${collapsed ? "w-[264px] lg:w-[68px]" : "w-[264px]"}`}
      >
        {/* 顶部只放收/展按钮：品牌已在全站顶栏，重复一次只会挤占会话列表高度 */}
        <div className={`flex h-11 items-center justify-end gap-1 px-2.5 ${collapsed ? "lg:justify-center lg:px-0" : ""}`}>
          <button
            type="button"
            onClick={onToggleCollapse}
            className={`btn-quiet btn-icon hidden lg:inline-flex ${collapsed ? "lg:hidden" : ""}`}
            aria-label="收起侧栏"
            title="收起侧栏"
          >
            <PanelIcon className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onCloseMobile}
            className="btn-quiet btn-icon lg:hidden"
            aria-label="关闭导航"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        </div>

        {/* 新建 */}
        <div className={`px-3 pt-3 ${collapsed ? "lg:px-0 lg:flex lg:justify-center" : ""}`}>
          <button
            type="button"
            onClick={onCreate}
            data-testid="new-session"
            className={`btn-primary w-full ${collapsed ? "lg:w-8 lg:px-0" : ""}`}
            aria-label="新建对话"
          >
            <PlusIcon className="h-4 w-4" />
            <span className={collapsed ? "lg:hidden" : ""}>新建对话</span>
          </button>
        </div>

        {/* 折叠态的展开按钮 */}
        {collapsed && (
          <button
            type="button"
            onClick={onToggleCollapse}
            className="btn-quiet btn-icon mx-auto mt-2 hidden lg:inline-flex"
            aria-label="展开侧栏"
            title="展开侧栏"
          >
            <PanelIcon className="h-4 w-4" />
          </button>
        )}

        {/* 会话列表 */}
        <div className={`mt-2 flex min-h-0 flex-1 flex-col ${collapsed ? "lg:hidden" : ""}`}>
          <p className="px-4 pb-1.5 text-[11px] font-medium uppercase tracking-[0.06em] text-muted">
            最近会话
          </p>
          <nav className="scroll-thin min-h-0 flex-1 overflow-y-auto px-2 pb-3" aria-label="最近会话">
            {loading && <p className="px-2.5 py-2 text-[12.5px] text-muted">加载中…</p>}

            {!loading && sessions.length === 0 && (
              <p className="px-2.5 py-2 text-[12.5px] leading-relaxed text-muted">
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
                      onClick={() => {
                        onSelect(s.id);
                        onCloseMobile();
                      }}
                      aria-current={active ? "true" : undefined}
                      className={`w-full rounded-control px-2.5 py-1.5 pr-8 text-left transition-colors ${
                        active
                          ? "bg-cream-soft ring-1 ring-[#EADFAF]"
                          : "hover:bg-white/70"
                      }`}
                    >
                      <span
                        className={`block truncate text-[13px] ${active ? "font-medium text-ink" : "text-ink"}`}
                      >
                        {s.title}
                      </span>
                      <span className="mt-0.5 block text-[11px] text-muted">
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
                      className="absolute right-1 top-1/2 -translate-y-1/2 rounded-[7px] p-1.5 text-muted opacity-0 transition-opacity hover:bg-hairline hover:text-ink focus:opacity-100 group-hover:opacity-100"
                    >
                      <TrashIcon className="h-3.5 w-3.5" />
                    </button>
                  </li>
                );
              })}
            </ul>
          </nav>
        </div>

        {/* 运行模式 */}
        <div className={`border-t border-hairline p-2.5 ${collapsed ? "lg:px-1.5" : ""}`}>
          <Link
            href="/settings"
            onClick={onCloseMobile}
            className={`block rounded-control border border-[#EADFAF] bg-cream-soft px-2.5 py-2 transition-colors hover:bg-cream ${
              collapsed ? "lg:flex lg:justify-center lg:border-0 lg:bg-transparent lg:p-1.5" : ""
            }`}
            title={`${modeLabel} · ${modelHint}`}
          >
            <span className={`flex items-center gap-1.5 ${collapsed ? "lg:hidden" : ""}`}>
              <span
                className={`h-1.5 w-1.5 rounded-full ${modeUsable ? "bg-success" : "bg-warning"}`}
                aria-hidden="true"
              />
              <span className="truncate text-[12px] font-medium text-ink">{modeLabel}</span>
              <ChevronDownIcon className="ml-auto h-3 w-3 -rotate-90 text-muted" />
            </span>
            <span className={`mt-0.5 block truncate text-[11px] text-muted ${collapsed ? "lg:hidden" : ""}`}>
              {modelHint}
            </span>
            {collapsed && <ShieldIcon className="h-4 w-4 text-muted" />}
          </Link>
        </div>
      </aside>
    </>
  );
}
