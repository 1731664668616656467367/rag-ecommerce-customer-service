"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookIcon, ChatIcon, GearIcon } from "./icons";

const NAV = [
  { href: "/chat", label: "对话", Icon: ChatIcon },
  { href: "/knowledge", label: "知识库", Icon: BookIcon },
  { href: "/settings", label: "系统状态", Icon: GearIcon },
];

export default function NavBar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-hairline bg-canvas/95">
      <div className="mx-auto flex h-14 max-w-content items-center justify-between px-5 sm:px-8">
        <Link href="/chat" className="flex items-baseline gap-2">
          <span className="text-[17px] font-semibold tracking-tight">智能客服</span>
          <span className="hidden text-xs text-muted sm:inline">知识库驱动</span>
        </Link>

        <nav className="flex items-center gap-1" aria-label="主导航">
          {NAV.map(({ href, label, Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] transition-colors ${
                  active
                    ? "bg-mist text-ink"
                    : "text-muted hover:bg-mist hover:text-ink"
                }`}
              >
                <Icon className="h-4 w-4" />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
