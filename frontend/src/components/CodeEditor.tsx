// Monaco 编辑器（docs/ui-design.md 第 5 节 CodeEditor）：行号、联动整行高亮、驱动行左侧 3px 主色竖条、编译错误波浪线
import Editor, { loader, type OnMount } from '@monaco-editor/react'
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api'
import 'monaco-editor/esm/vs/basic-languages/systemverilog/systemverilog.contribution'
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import { useEffect, useRef } from 'react'
import './CodeEditor.css'

;(self as unknown as { MonacoEnvironment: unknown }).MonacoEnvironment = { getWorker: () => new EditorWorker() }
loader.config({ monaco })   // 用本地打包的 Monaco，不从 CDN 加载

export interface CodeEditorProps {
  value: string
  onChange?: (v: string) => void
  readOnly?: boolean
  driverLines?: number[]
  linkLines?: number[]
  pickedLine?: number | null
  errors?: { line: number; message: string }[]
  onLineClick?: (line: number) => void
  onLineHover?: (line: number | null) => void
  height?: string | number
  testId?: string
}

export default function CodeEditor({ value, onChange, readOnly, driverLines = [], linkLines = [], pickedLine = null,
  errors = [], onLineClick, onLineHover, height = '100%', testId = 'code-editor' }: CodeEditorProps) {
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null)
  const decorations = useRef<monaco.editor.IEditorDecorationsCollection | null>(null)
  const clickRef = useRef(onLineClick)
  const hoverRef = useRef(onLineHover)
  clickRef.current = onLineClick
  hoverRef.current = onLineHover

  const onMount: OnMount = (editor) => {
    editorRef.current = editor
    decorations.current = editor.createDecorationsCollection([])
    editor.onMouseDown((e) => {
      const line = e.target.position?.lineNumber
      if (line && clickRef.current) clickRef.current(line)
    })
    let last: number | null = null
    editor.onMouseMove((e) => {
      const line = e.target.position?.lineNumber ?? null
      if (line !== last) { last = line; hoverRef.current?.(line) }
    })
    editor.onMouseLeave(() => { last = null; hoverRef.current?.(null) })
    applyDecorations()
  }

  function applyDecorations() {
    const editor = editorRef.current
    if (!editor || !decorations.current) return
    const items: monaco.editor.IModelDeltaDecoration[] = []
    const drv = new Set(driverLines)
    for (const line of new Set([...driverLines, ...linkLines])) {
      items.push({ range: new monaco.Range(line, 1, line, 1), options: {
        isWholeLine: true, className: 'ln-link', linesDecorationsClassName: drv.has(line) ? 'ln-drv-bar' : undefined } })
    }
    if (pickedLine) {
      items.push({ range: new monaco.Range(pickedLine, 1, pickedLine, 1), options: {
        isWholeLine: true, className: 'ln-pick', lineNumberClassName: 'ln-pick-no' } })
    }
    decorations.current.set(items)
    const model = editor.getModel()
    if (model) {
      monaco.editor.setModelMarkers(model, 'judge', errors.filter((e) => e.line >= 1).map((e) => ({
        startLineNumber: e.line, endLineNumber: e.line, startColumn: 1,
        endColumn: model.getLineMaxColumn(Math.min(e.line, model.getLineCount())),
        message: e.message, severity: monaco.MarkerSeverity.Error,
      })))
    }
    const first = [...drv].sort((a, b) => a - b)[0]
    if (first) editor.revealLineInCenterIfOutsideViewport(first)
  }

  useEffect(applyDecorations, [driverLines.join(','), linkLines.join(','), pickedLine, // eslint-disable-line react-hooks/exhaustive-deps
    errors.map((e) => `${e.line}:${e.message}`).join('|'), value])

  return (
    <div data-testid={testId} style={{ height, minHeight: 0 }} className={readOnly ? 'editor-ro' : undefined}>
      <Editor
        value={value}
        language="systemverilog"
        onChange={(v) => onChange?.(v ?? '')}
        onMount={onMount}
        options={{
          readOnly, minimap: { enabled: false }, fontSize: 13, lineHeight: 20, fontFamily: 'var(--mono)',
          scrollBeyondLastLine: false, automaticLayout: true, tabSize: 4, renderLineHighlight: 'none',
          glyphMargin: false, lineDecorationsWidth: 6, folding: false, wordWrap: 'off',
          autoClosingBrackets: 'never', autoClosingQuotes: 'never',
          domReadOnly: readOnly,
        }}
        loading={<div style={{ padding: 12, color: 'var(--c-text-2)' }}>编辑器加载中…</div>}
      />
    </div>
  )
}
