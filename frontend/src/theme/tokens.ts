// 设计变量（docs/ui-design.md 第 3 节）。CSS 变量见 global.css，两处保持一致
import type { ThemeConfig } from 'antd'

export const colors = {
  primary: '#3B5BDB',
  primaryBg: '#EEF2FF',
  bg: '#F6F7F9',
  surface: '#FFFFFF',
  border: '#E5E7EB',
  text: '#1F2937',
  text2: '#6B7280',
  success: '#16A34A',
  warning: '#D97706',
  error: '#DC2626',
  errorBg: '#FEE2E2',
  link: '#FDE68A',
  busBorder: '#6366F1',
}

// 四象限与掌握等级（3.2 节）
export const quadrantStyle = {
  mastered: { name: '真掌握', color: '#2563EB', bg: '#DBEAFE', icon: '●' },
  fragile: { name: '会写但没把握', color: '#B45309', bg: '#FEF3C7', icon: '◐' },
  design_gap: { name: '设计偏差', color: '#7C3AED', bg: '#EDE9FE', icon: '◆' },
  concept_gap: { name: '概念未通', color: '#4B5563', bg: '#F3F4F6', icon: '○' },
} as const

export const levelStyle = {
  mastered: { name: '真掌握', icon: '●', className: 'lv-mastered' },
  fragile: { name: '会写但没把握', icon: '◐', className: 'lv-fragile' },
  learning: { name: '学习中', icon: '◌', className: 'lv-learning' },
  not_started: { name: '未开始', icon: '–', className: 'lv-none' },
} as const

export const fontFamily = '"PingFang SC", "Microsoft YaHei", "Noto Sans SC", "WenQuanYi Zen Hei", sans-serif'
export const monoFamily = '"JetBrains Mono", "Fira Code", Consolas, Menlo, monospace'

export const antdTheme: ThemeConfig = {
  token: {
    colorPrimary: colors.primary,
    colorSuccess: colors.success,
    colorWarning: colors.warning,
    colorError: colors.error,
    colorText: colors.text,
    colorTextSecondary: colors.text2,
    colorBorder: colors.border,
    colorBorderSecondary: colors.border,
    colorBgLayout: colors.bg,
    colorBgContainer: colors.surface,
    borderRadius: 6,
    borderRadiusLG: 8,
    borderRadiusSM: 4,
    fontFamily,
    fontFamilyCode: monoFamily,
    fontSize: 14,
    boxShadow: '0 8px 24px rgba(16, 24, 40, .12)',
    boxShadowSecondary: '0 1px 2px rgba(16, 24, 40, .06)',
    motionDurationMid: '0.2s',
    motionDurationSlow: '0.2s',
  },
  components: {
    Card: { paddingLG: 16 },
    Button: { controlHeight: 32 },
  },
}
