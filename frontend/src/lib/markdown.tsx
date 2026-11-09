// 极简 Markdown 渲染：只支持题目说明里用到的标题、段落、列表、表格、行内代码与粗体
import type { ReactNode } from 'react'

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

export default function Markdown({ text, skipTitle = false }: { text: string; skipTitle?: boolean }) {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let i = 0
  let k = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) { i++; continue }
    const h = line.match(/^(#{1,3})\s+(.*)$/)
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
        <table key={k++} className="md-table"><thead><tr>{head.map((c, j) => <th key={j}>{inline(c, `th${k}${j}`)}</th>)}</tr></thead>
          <tbody>{body.map((r, ri) => <tr key={ri}>{r.map((c, j) => <td key={j}>{inline(c, `td${k}${ri}${j}`)}</td>)}</tr>)}</tbody></table>,
      )
      continue
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*]\s+/, '')); i++ }
      blocks.push(<ul key={k++} className="md-ul">{items.map((t, j) => <li key={j}>{inline(t, `li${k}${j}`)}</li>)}</ul>)
      continue
    }
    const para: string[] = []
    while (i < lines.length && lines[i].trim() && !/^(#|\||\s*[-*]\s)/.test(lines[i])) { para.push(lines[i]); i++ }
    blocks.push(<p key={k++} className="md-p">{inline(para.join(''), `p${k}`)}</p>)
  }
  return <div className="md">{blocks}</div>
}
