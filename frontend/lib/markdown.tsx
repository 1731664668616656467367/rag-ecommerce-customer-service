import type { ReactNode } from "react";

/** 极简 Markdown 渲染器（无第三方依赖）。
 *
 *  为什么不用 react-markdown？
 *  1. 这里只需要标题/列表/粗体/行内代码/代码块/链接这几种，引入 40KB 依赖不划算；
 *  2. 自己实现可以保证**绝不使用 dangerouslySetInnerHTML**——
 *     回答内容来自知识库文档，文档可能被替换，任何 HTML 注入都是风险。
 *     这里全部走 React 元素，文本天然转义。
 *
 *  为什么不直接显示原文？
 *  后端返回的摘录里带 `#`、`**`、`- ` 这些标记，直接铺在气泡里会像乱码。
 */

const INLINE = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\[[^\]\n]+\]\(https?:\/\/[^\s)]+\)|\*[^*\n]+\*)/g;

function renderInline(text: string, prefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let i = 0;

  for (const match of text.matchAll(INLINE)) {
    const index = match.index ?? 0;
    if (index > last) nodes.push(text.slice(last, index));
    const token = match[0];
    const key = `${prefix}-${i++}`;

    if (token.startsWith("**")) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      nodes.push(<code key={key}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith("[")) {
      const link = /^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/.exec(token);
      if (link) {
        nodes.push(
          <a key={key} href={link[2]} target="_blank" rel="noreferrer noopener">
            {link[1]}
          </a>
        );
      } else {
        nodes.push(token);
      }
    } else {
      nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    }
    last = index + token.length;
  }

  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

type Block =
  | { type: "heading"; level: 1 | 2 | 3; text: string }
  | { type: "paragraph"; lines: string[] }
  | { type: "ul"; items: string[] }
  | { type: "ol"; items: string[] }
  | { type: "code"; code: string }
  | { type: "quote"; lines: string[] }
  | { type: "hr" };

function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) {
      i += 1;
      continue;
    }

    // 代码块
    if (line.trim().startsWith("```")) {
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        body.push(lines[i]);
        i += 1;
      }
      i += 1; // 跳过结束围栏
      blocks.push({ type: "code", code: body.join("\n") });
      continue;
    }

    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({
        type: "heading",
        level: Math.min(heading[1].length, 3) as 1 | 2 | 3,
        text: heading[2].trim(),
      });
      i += 1;
      continue;
    }

    if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) {
      blocks.push({ type: "hr" });
      i += 1;
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      const quote: string[] = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        quote.push(lines[i].replace(/^\s*>\s?/, ""));
        i += 1;
      }
      blocks.push({ type: "quote", lines: quote });
      continue;
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*+]\s+/, ""));
        i += 1;
      }
      blocks.push({ type: "ul", items });
      continue;
    }

    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+[.)]\s+/, ""));
        i += 1;
      }
      blocks.push({ type: "ol", items });
      continue;
    }

    // 普通段落：连续非空行合为一段，保留行内换行
    const paragraph: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,3})\s+/.test(lines[i]) &&
      !/^\s*([-*+]|\d+[.)])\s+/.test(lines[i]) &&
      !lines[i].trim().startsWith("```") &&
      !/^\s*>\s?/.test(lines[i])
    ) {
      paragraph.push(lines[i].trim());
      i += 1;
    }
    blocks.push({ type: "paragraph", lines: paragraph });
  }

  return blocks;
}

export function Markdown({ text }: { text: string }) {
  const blocks = parseBlocks(text || "");

  return (
    <div className="prose-chat">
      {blocks.map((block, index) => {
        const key = `b${index}`;
        switch (block.type) {
          case "heading": {
            const Tag = (`h${block.level}` as unknown) as "h1";
            return <Tag key={key}>{renderInline(block.text, key)}</Tag>;
          }
          case "hr":
            return <hr key={key} />;
          case "code":
            return (
              <pre key={key}>
                <code>{block.code}</code>
              </pre>
            );
          case "quote":
            // 引用块逐行保留换行：知识库摘录是按文档小节断行的，
            // 合并成一行会把"发货时间 / 配送时效"揉成一团，读起来费劲。
            // 原文里的 "- " 列表项在这里还原成圆点，否则用户会看到一堆裸露的短横线。
            return (
              <blockquote key={key}>
                {block.lines.map((line, i) => {
                  const bullet = /^[-*+][ \t]+/.exec(line);
                  const lineKey = `${key}-${i}`;
                  return bullet ? (
                    <span key={lineKey} className="quote-item">
                      {renderInline(line.slice(bullet[0].length), lineKey)}
                    </span>
                  ) : (
                    <span key={lineKey} className="quote-line">
                      {renderInline(line, lineKey)}
                    </span>
                  );
                })}
              </blockquote>
            );
          case "ul":
            return (
              <ul key={key}>
                {block.items.map((item, i) => (
                  <li key={`${key}-${i}`}>{renderInline(item, `${key}-${i}`)}</li>
                ))}
              </ul>
            );
          case "ol":
            return (
              <ol key={key}>
                {block.items.map((item, i) => (
                  <li key={`${key}-${i}`}>{renderInline(item, `${key}-${i}`)}</li>
                ))}
              </ol>
            );
          default:
            return (
              <p key={key}>
                {block.lines.map((line, i) => (
                  <span key={`${key}-${i}`}>
                    {i > 0 && <br />}
                    {renderInline(line, `${key}-${i}`)}
                  </span>
                ))}
              </p>
            );
        }
      })}
    </div>
  );
}

export default Markdown;
