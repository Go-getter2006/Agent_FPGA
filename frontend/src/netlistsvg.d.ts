// netlistsvg 没有自带类型：只用到 render(skin, netlist) → Promise<svg 字符串>
declare module 'netlistsvg' {
  export function render(skin: string, netlist: unknown): Promise<string>
}
