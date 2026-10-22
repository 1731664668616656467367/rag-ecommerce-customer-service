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

export function ChevronDownIcon({ className, strokeWidth = 1.8 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6.5 9.5l5.5 5 5.5-5" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function PanelIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3.5" y="5" width="17" height="14" rx="2.5" stroke="currentColor" strokeWidth={strokeWidth} />
      <path d="M9.5 5v14" stroke="currentColor" strokeWidth={strokeWidth} />
    </svg>
  );
}

export function TruckIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M3 7.5h10v8.2H3z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
      <path d="M13 10.5h3.6l2.4 2.8v2.4H13z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
      <circle cx="6.6" cy="17.8" r="1.6" stroke="currentColor" strokeWidth={strokeWidth} />
      <circle cx="16.4" cy="17.8" r="1.6" stroke="currentColor" strokeWidth={strokeWidth} />
    </svg>
  );
}

export function RefundIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M18.4 9.2A6.6 6.6 0 1 0 19 13" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
      <path d="M18.8 4.9v4.4h-4.4" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12 8.8v6.4M10 10.2h2.8M10 13.8h2.8" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </svg>
  );
}

export function SwapIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4.5 8.5h12M13.5 5.5l3 3-3 3" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
      <path d="M19.5 15.5h-12M10.5 12.5l-3 3 3 3" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function WrenchIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M14.8 5.4a3.9 3.9 0 0 1 4.6 5.1l-2.1-2.1-2.4.7-.7 2.4 2.1 2.1a3.9 3.9 0 0 1-5.1-4.6" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
      <path d="M11.2 11.2l-5.8 5.8a1.8 1.8 0 0 0 2.5 2.5l5.9-5.9" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ReceiptIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6 3.8h12v16.4l-2.4-1.6-2.4 1.6-2.4-1.6-2.4 1.6z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
      <path d="M9 8.4h6M9 12h6M9 15.6h3.5" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </svg>
  );
}

export function HeadsetIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 13v-1.4a7 7 0 0 1 14 0V13" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
      <rect x="3.6" y="12.6" width="3.6" height="5.2" rx="1.6" stroke="currentColor" strokeWidth={strokeWidth} />
      <rect x="16.8" y="12.6" width="3.6" height="5.2" rx="1.6" stroke="currentColor" strokeWidth={strokeWidth} />
      <path d="M18.6 17.8v.6c0 1.1-.9 2-2 2h-2.2" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </svg>
  );
}

export function SparklesIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 4l1.5 4.1L17.6 9.6 13.5 11l-1.5 4.1L10.5 11 6.4 9.6 10.5 8.1z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
      <path d="M17.8 15.4l.7 1.9 1.9.7-1.9.7-.7 1.9-.7-1.9-1.9-.7 1.9-.7z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
    </svg>
  );
}

export function DatabaseIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <ellipse cx="12" cy="6.4" rx="6.8" ry="2.6" stroke="currentColor" strokeWidth={strokeWidth} />
      <path d="M5.2 6.4v5.2c0 1.4 3 2.6 6.8 2.6s6.8-1.2 6.8-2.6V6.4" stroke="currentColor" strokeWidth={strokeWidth} />
      <path d="M5.2 11.6v5.2c0 1.4 3 2.6 6.8 2.6s6.8-1.2 6.8-2.6v-5.2" stroke="currentColor" strokeWidth={strokeWidth} />
    </svg>
  );
}

export function ShieldIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 3.8l6.4 2.4v5.6c0 3.8-2.6 6.9-6.4 8.4-3.8-1.5-6.4-4.6-6.4-8.4V6.2z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
      <path d="M9.2 12.1l2 2 3.6-3.8" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function SearchIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="11" cy="11" r="5.6" stroke="currentColor" strokeWidth={strokeWidth} />
      <path d="M15.2 15.2l4 4" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </svg>
  );
}

export function InfoIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth={strokeWidth} />
      <path d="M12 11.2v5" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
      <circle cx="12" cy="8.2" r="0.9" fill="currentColor" />
    </svg>
  );
}

export function FileIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6.5 3.8h7l4 4v12.4h-11z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
      <path d="M13.2 3.9v4.2h4.1" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
    </svg>
  );
}

export function GridIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3.6" y="3.6" width="7.2" height="7.2" rx="2" stroke="currentColor" strokeWidth={strokeWidth} />
      <rect x="13.2" y="3.6" width="7.2" height="7.2" rx="2" stroke="currentColor" strokeWidth={strokeWidth} />
      <rect x="3.6" y="13.2" width="7.2" height="7.2" rx="2" stroke="currentColor" strokeWidth={strokeWidth} />
      <rect x="13.2" y="13.2" width="7.2" height="7.2" rx="2" stroke="currentColor" strokeWidth={strokeWidth} />
    </svg>
  );
}

export function ArrowUpRightIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M8 16L16 8" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
      <path d="M9.2 8H16v6.8" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function MessageIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4.2 6.6A2.6 2.6 0 0 1 6.8 4h10.4a2.6 2.6 0 0 1 2.6 2.6v6.8a2.6 2.6 0 0 1-2.6 2.6H9l-4.8 3.6z"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function LayersIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 3.8l8 4.2-8 4.2-8-4.2z" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
      <path d="M4 12.4l8 4.2 8-4.2" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
      <path d="M4 16.4l8 4.2 8-4.2" stroke="currentColor" strokeWidth={strokeWidth} strokeLinejoin="round" />
    </svg>
  );
}

export function ClockIcon({ className, strokeWidth = 1.6 }: IconProps) {
  return (
    <svg className={base(className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8.2" stroke="currentColor" strokeWidth={strokeWidth} />
      <path d="M12 7.6V12l3 1.8" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
