/** 统一图标集：手写内联 SVG，细线条、无 emoji。
 *  好处：不额外引依赖、颜色随 currentColor、体积可控。 */

type IconProps = {
  className?: string;
  strokeWidth?: number;
};

const base = (className?: string) => `h-[18px] w-[18px] ${className ?? ""}`;

export function ChatIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4.5 5.5h15v10.2h-8.1L7.2 19v-3.3H4.5z"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function BookIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M5 4.8h6.2c.9 0 1.6.7 1.6 1.6v12.8H6.6c-.9 0-1.6-.7-1.6-1.6z"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
      />
      <path
        d="M19 4.8h-4.6c-.9 0-1.6.7-1.6 1.6v12.8h4.6c.9 0 1.6-.7 1.6-1.6z"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function GearIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="3.1" stroke="currentColor" strokeWidth={strokeWidth} />
      <path
        d="M12 3.6v2M12 18.4v2M4.6 12h2M17.4 12h2M6.8 6.8l1.4 1.4M15.8 15.8l1.4 1.4M17.2 6.8l-1.4 1.4M8.2 15.8l-1.4 1.4"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />
    </svg>
  );
}

export function PlusIcon({ className, strokeWidth = 1.7 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 5.5v13M5.5 12h13" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </svg>
  );
}

export function TrashIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 7h14M10 7V5.5h4V7M7.5 7l.8 12h7.4l.8-12" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function SendIcon({ className, strokeWidth = 1.7 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 12h12M12.5 6.5l6 5.5-6 5.5" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function CopyIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="9" y="9" width="10" height="10" rx="2" stroke="currentColor" strokeWidth={strokeWidth} />
      <path d="M6.5 15H6a1.5 1.5 0 0 1-1.5-1.5V6A1.5 1.5 0 0 1 6 4.5h7.5A1.5 1.5 0 0 1 15 6v.5" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </svg>
  );
}

export function CheckIcon({ className, strokeWidth = 1.8 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5.5 12.5l4 4 9-9" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ThumbUpIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M7 10.5l3.2-5.2c.3-.5.9-.8 1.5-.7.7.1 1.2.7 1.2 1.4v3.2h3.6c1 0 1.8.9 1.6 1.9l-.8 4.4c-.1.7-.7 1.2-1.4 1.2H7z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
      <path d="M7 10.5H4.6v6.7H7" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
    </svg>
  );
}

export function ThumbDownIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M17 13.5l-3.2 5.2c-.3.5-.9.8-1.5.7-.7-.1-1.2-.7-1.2-1.4v-3.2H7.5c-1 0-1.8-.9-1.6-1.9l.8-4.4c.1-.7.7-1.2 1.4-1.2H17z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
      <path d="M17 13.5h2.4V6.8H17" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
    </svg>
  );
}

export function UploadIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 15.5V5.8M8.4 9.2L12 5.6l3.6 3.6" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5 15.5v2.3c0 .9.7 1.6 1.6 1.6h10.8c.9 0 1.6-.7 1.6-1.6v-2.3" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </svg>
  );
}

export function MenuIcon({ className, strokeWidth = 1.7 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4.5 7h15M4.5 12h15M4.5 17h15" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </svg>
  );
}

export function CloseIcon({ className, strokeWidth = 1.7 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </svg>
  );
}

export function AlertIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth={strokeWidth} />
      <path d="M12 7.8v5.1" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
      <circle cx="12" cy="16.1" r="0.9" fill="currentColor" />
    </svg>
  );
}

export function RefreshIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M18.5 12a6.5 6.5 0 1 1-1.9-4.6" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
      <path d="M18.6 4.8v3.4h-3.4" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
