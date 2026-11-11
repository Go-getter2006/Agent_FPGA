// 电路图：yosys 把这次提交的代码综合成 RTL 级电路（加法器、比较器、选择器、触发器……），netlistsvg 在浏览器里画出来。
// 联动：鼠标移到电路图里的元件 → 代码里对应的行高亮；鼠标移到代码行 → 电路图里对应的元件高亮。
// 只用于看图理解，不参与判对错（docs/judge.md 第 10 节第 16 条）
import { useQuery } from '@tanstack/react-query'
import { Button } from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'
import { get } from '../api/client'

export interface SchemCell { type: string; lines: number[]; outputs: string[] }
interface SchemData { netlist: unknown; cells: Record<string, SchemCell>; drivers: Record<string, number[]> }

// 元件类型的中文名（没有列出的显示原名）
export const CELL_NAME: Record<string, string> = {
  $add: '加法器', $sub: '减法器', $mul: '乘法器', $eq: '比较器（相等）', $ne: '比较器（不等）', $lt: '比较器（小于）',
  $le: '比较器（≤）', $gt: '比较器（大于）', $ge: '比较器（≥）', $mux: '二选一选择器', $pmux: '多路选择器',
  $dff: '触发器', $adff: '触发器（异步复位）', $sdff: '触发器（同步复位）', $dffe: '触发器（带使能）',
  $dlatch: '锁存器', $and: '与门', $or: '或门', $xor: '异或门', $xnor: '同或门', $not: '非门',
  $logic_not: '逻辑非', $logic_and: '逻辑与', $logic_or: '逻辑或', $reduce_or: '或归约（任一位为 1）',
  $reduce_and: '与归约（全为 1）', $reduce_xor: '异或归约', $shl: '左移', $shr: '右移', $neg: '取负',
}

/** 元件对应的代码行：触发器的 src 覆盖整个 always 块，改用它驱动的信号的赋值行，更准确 */
export function cellLines(cell: SchemCell, drivers: Record<string, number[]>): number[] {
  if (/dff|dlatch/.test(cell.type) && cell.outputs.length) {
    const ls = [...new Set(cell.outputs.flatMap((o) => drivers[o] ?? []))].sort((a, b) => a - b)
    if (ls.length) return ls
  }
  return cell.lines
}

/** 去掉 svg 里可能执行脚本的内容（信号名来自学生代码，Verilog 转义标识符可以含任意字符） */
export function sanitizeSvg(svg: string): string {
  const doc = new DOMParser().parseFromString(svg, 'image/svg+xml')
  doc.querySelectorAll('script, foreignObject, iframe').forEach((n) => n.remove())
  doc.querySelectorAll('*').forEach((el) => {
    for (const a of [...el.attributes]) {
      if (/^on/i.test(a.name) || /^\s*javascript:/i.test(a.value)) el.removeAttribute(a.name)
    }
  })
  return new XMLSerializer().serializeToString(doc.documentElement)
}

export default function SchematicView({ attemptId, highlightLines, onHoverLines, onCellClick, linkBlocked }: {
  attemptId: number; highlightLines: number[]; onHoverLines: (lines: number[] | null, label?: string) => void
  onCellClick?: (cell: SchemCell, name: string) => void
  linkBlocked?: boolean          // 探究任务“在代码里点出那一行”还没做完：先不联动高亮代码，免得直接给出答案
}) {
  const q = useQuery({ queryKey: ['schematic', attemptId], staleTime: Infinity, retry: false,
    queryFn: () => get<SchemData>(`/api/student/attempts/${attemptId}/schematic`) })
  const [svg, setSvg] = useState<string | null>(null)
  const [drawErr, setDrawErr] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [hover, setHover] = useState<string | null>(null)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!q.data) return
    let alive = true
    setSvg(null)
    void (async () => {
      try {
        // 按需加载：排版库比较大，只有打开电路图时才下载
        const [mod, skin] = await Promise.all([import('netlistsvg'), import('netlistsvg/lib/default.svg?raw')])
        const render = mod.render ?? (mod as unknown as { default: typeof mod }).default.render
        const out = await render(skin.default, q.data.netlist)
        if (alive) setSvg(sanitizeSvg(out))
      } catch {
        if (alive) setDrawErr('电路图画不出来，可以先看“硬件”页的统计')
      }
    })()
    return () => { alive = false }
  }, [q.data])

  const lineOf = useMemo(() => {
    const m: Record<string, number[]> = {}
    for (const [name, c] of Object.entries(q.data?.cells ?? {})) m[name] = cellLines(c, q.data!.drivers)
    return m
  }, [q.data])

  // 代码行 → 元件高亮
  useEffect(() => {
    const root = box.current
    if (!root || !svg) return
    const hl = new Set(highlightLines)
    root.querySelectorAll<SVGGElement>('[id^="cell_"]').forEach((el) => {
      const name = el.id.slice(5)
      el.classList.toggle('schem-hl', (lineOf[name] ?? []).some((l) => hl.has(l)))
      el.classList.toggle('schem-hover', name === hover)
    })
  }, [svg, highlightLines, lineOf, hover])

  const cellAt = (target: EventTarget | null) => {
    const el = (target as Element | null)?.closest?.('[id^="cell_"]')
    return el ? el.id.slice(5) : null
  }
  const describe = (name: string) => {
    const c = q.data!.cells[name]
    const ls = lineOf[name] ?? []
    return `${CELL_NAME[c.type] ?? c.type}${c.outputs.length ? `（输出 ${c.outputs.join('、')}）` : ''}：第 ${ls.join('、')} 行`
  }

  if (q.isLoading) return <div className="muted" style={{ padding: 16 }}>正在综合电路……</div>
  if (q.error) return <div className="muted" style={{ padding: 16 }} data-testid="schematic-error">{(q.error as Error).message}</div>
  return (
    <div className="schem" data-testid="schematic">
      <div className="schem-bar">
        <span className="muted">yosys 综合出的电路 · 鼠标移到元件上，代码里对应的行会高亮；移到代码行上，这里对应的元件会高亮</span>
        <span className="schem-zoom">
          <Button size="small" onClick={() => setZoom((z) => Math.max(0.4, z - 0.2))}>−</Button>
          <span>{Math.round(zoom * 100)}%</span>
          <Button size="small" onClick={() => setZoom((z) => Math.min(2, z + 0.2))}>+</Button>
        </span>
      </div>
      {/* 固定占一行：出现、消失时不挤动下面的电路图（否则鼠标下的元件会移走，悬停立刻失效） */}
      <div className="schem-info" data-testid="schematic-info">
        {hover && q.data?.cells[hover] ? describe(hover)
          : linkBlocked ? '先完成左边“在代码里点出那一行”的任务，之后电路图和代码会联动高亮'
            : '鼠标移到一个元件上，看看它是什么、对应哪几行代码'}
      </div>
      {drawErr && <div className="muted" style={{ padding: 16 }}>{drawErr}</div>}
      {!svg && !drawErr && <div className="muted" style={{ padding: 16 }}>正在画图……</div>}
      {svg && (
        <div className="schem-canvas" ref={box} style={{ zoom }}
          onMouseOver={(e) => {
            const name = cellAt(e.target)
            if (name === hover) return
            setHover(name)
            onHoverLines(name ? lineOf[name] ?? [] : null, name ? describe(name) : undefined)
          }}
          onMouseLeave={() => { setHover(null); onHoverLines(null) }}
          onClick={(e) => { const name = cellAt(e.target); if (name && q.data) onCellClick?.(q.data.cells[name], name) }}
          dangerouslySetInnerHTML={{ __html: svg }} />
      )}
      <div className="schem-legend muted">
        图里的方块：触发器（带时钟三角的方块）会在时钟上升沿记住数据；选择器、加法器、比较器、与或非门都是组合逻辑。
        方块之间的连线就是代码里的信号。
      </div>
    </div>
  )
}
