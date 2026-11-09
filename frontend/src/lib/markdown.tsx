// 极简 Markdown 渲染：标题、段落、有序 / 无序列表、引用、表格、代码块（Verilog 高亮）、行内代码与粗体
// 题目说明、提示、助教回复、入门课都用它；不支持 HTML，内容一律当文本处理（不会执行脚本）
import { useState, type ReactNode } from 'react'

function inline(text: string, keyBase: string): ReactNode[] {
  const out: ReactNode[] = []
  const re = /(`[^`]+`|\*\*[^*]+\*\*)/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const tok = m[0]
    out.push(tok.startsWith('`')
      ? <code key={`${keyBase}-${i++}`} className="md-code">{tok.slice(1, -1)}</code>
      : <b key={`${keyBase}-${i++}`}>{tok.slice(2, -2)}</b>)
    last = m.index + tok.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

const KEYWORDS = new Set(('module endmodule input output inout wire reg integer parameter localparam assign always ' +
  'initial begin end if else case casez casex endcase default posedge negedge or and not for while forever ' +
  'function endfunction task endtask generate endgenerate genvar signed').split(' '))
const TOKEN = /(\/\/.*$)|("(?:[^"\\]|\\.)*")|(\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+|\b\d+\b)|(_{3,})|(\$?[A-Za-z_][\w$]*)/g

/** Verilog 语法高亮：关键字、注释、数字、字符串、系统任务；____ 是要学生自己填的空 */
export function highlightVerilog(code: string): ReactNode[] {
  return code.split('\n').flatMap((line, li) => {
    const parts: ReactNode[] = []
    let last = 0
    let m: RegExpExecArray | null
    TOKEN.lastIndex = 0
    let n = 0
    while ((m = TOKEN.exec(line))) {
      if (m.index > last) parts.push(line.slice(last, m.index))
      const [tok, comment, str, num, blank, word] = m
      const key = `${li}-${n++}`
      if (comment) parts.push(<span key={key} className="hl-c">{tok}</span>)
      else if (str) parts.push(<span key={key} className="hl-s">{tok}</span>)
      else if (num) parts.push(<span key={key} className="hl-n">{tok}</span>)
      else if (blank) parts.push(<span key={key} className="hl-blank" title="这里要你自己填">{tok}</span>)
      else if (word && word.startsWith('$')) parts.push(<span key={key} className="hl-f">{tok}</span>)
      else if (word && KEYWORDS.has(word)) parts.push(<span key={key} className="hl-k">{tok}</span>)
      else parts.push(tok)
      last = m.index + tok.length
    }
    if (last < line.length) parts.push(line.slice(last))
    return li === 0 ? parts : ['\n', ...parts]
  })
}

export function CodeBlock({ code, lang = 'verilog', title }: { code: string; lang?: string; title?: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    void navigator.clipboard?.writeText(code).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) })
  }
  return (
    <div className="code-block" data-testid="code-block">
      <div className="cb-h"><span>{title ?? (lang || 'code')}</span>
        <button type="button" onClick={copy}>{copied ? '已复制' : '复制'}</button></div>
      <pre><code>{lang === 'verilog' || lang === 'v' || lang === '' ? highlightVerilog(code) : code}</code></pre>
    </div>
  )
}

const LIST = /^\s*([-*]|\d+[.)])\s+/

export default function Markdown({ text, skipTitle = false }: { text: string; skipTitle?: boolean }) {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let i = 0
  let k = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) { i++; continue }
    const fence = line.match(/^\s*```\s*([\w-]*)/)
    if (fence) {
      const body: string[] = []
      i++
      while (i < lines.length && !/^\s*```/.test(lines[i])) { body.push(lines[i]); i++ }
      i++                                   // 跳过结束的 ```（流式输出时可能还没到）
      blocks.push(<CodeBlock key={k++} code={body.join('\n')} lang={(fence[1] || 'verilog').toLowerCase()} />)
      continue
    }
    const h = line.match(/^(#{1,4})\s+(.*)$/)
    if (h) {
      if (!(skipTitle && h[1].length === 1)) {
        const Tag = (h[1].length === 1 ? 'h3' : 'h4') as 'h3' | 'h4'
        blocks.push(<Tag key={k++} className="md-h">{inline(h[2], `h${k}`)}</Tag>)
      }
      i++
      continue
    }
    if (line.trim().startsWith('|')) {
      const rows: string[][] = []
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        const cells = lines[i].trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
        if (!cells.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(cells)
        i++
      }
      const [head, ...body] = rows
      blocks.push(
        <div key={k++} className="md-table-wrap"><table className="md-table"><thead><tr>{head.map((c, j) => <th key={j}>{inline(c, `th${k}${j}`)}</th>)}</tr></thead>
          <tbody>{body.map((r, ri) => <tr key={ri}>{r.map((c, j) => <td key={j}>{inline(c, `td${k}${ri}${j}`)}</td>)}</tr>)}</tbody></table></div>,
      )
      continue
    }
    if (line.trim().startsWith('>')) {
      const quote: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('>')) { quote.push(lines[i].trim().replace(/^>\s?/, '')); i++ }
      blocks.push(<blockquote key={k++} className="md-quote">{inline(quote.join('\n'), `q${k}`)}</blockquote>)
      continue
    }
    if (LIST.test(line)) {
      const ordered = /^\s*\d/.test(line)
      const items: string[] = []
      while (i < lines.length && LIST.test(lines[i])) { items.push(lines[i].replace(LIST, '')); i++ }
      const lis = items.map((t, j) => <li key={j}>{inline(t, `li${k}${j}`)}</li>)
      blocks.push(ordered ? <ol key={k++} className="md-ol">{lis}</ol> : <ul key={k++} className="md-ul">{lis}</ul>)
      continue
    }
    const para: string[] = []
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|\||\s*```|\s*>)/.test(lines[i]) && !LIST.test(lines[i])) {
      para.push(lines[i]); i++
    }
    blocks.push(<p key={k++} className="md-p">{inline(para.join('\n'), `p${k}`)}</p>)
  }
  return <div className="md">{blocks}</div>
}
