import { useEffect, useMemo, useState } from 'react'

const tokenNames = [
  'ink',
  'muted',
  'line',
  'panel',
  'panel-light',
  'accent',
  'accent-soft',
  'warm',
  'red',
  'blue',
  'on-accent',
  'chart-axis',
  'chart-axis-line',
  'chart-grid',
  'chart-area',
  'chart-tooltip-background',
  'chart-tooltip-border',
  'chart-tooltip-text',
  'chart-shadow',
  'chart-slider-background',
  'chart-slider-border',
  'chart-slider-filler',
  'chart-slider-data',
  'chart-slider-selected',
  'chart-slider-handle',
  'chart-slider-handle-border',
  'chart-slider-emphasis',
  'map-background',
  'map-raster-opacity',
  'map-cluster-opacity',
  'map-marker-border',
] as const

export type ThemeColors = Record<(typeof tokenNames)[number], string>

export function readThemeColors(theme?: string): ThemeColors {
  void theme
  const styles = getComputedStyle(document.documentElement)
  return Object.fromEntries(tokenNames.map((name) => [name, styles.getPropertyValue(`--${name}`).trim()])) as ThemeColors
}

export function useThemeColors() {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme ?? 'dark')

  useEffect(() => {
    const root = document.documentElement
    const observer = new MutationObserver(() => setTheme(root.dataset.theme ?? 'dark'))
    observer.observe(root, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])

  return useMemo(() => readThemeColors(theme), [theme])
}
