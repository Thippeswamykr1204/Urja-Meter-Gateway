import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, test } from 'vitest'

const stylesPath = resolve(process.cwd(), 'src/styles.css')

function parseColor(value: string, background?: [number, number, number]): [number, number, number] {
  const hex = value.match(/^#([\da-f]{3}|[\da-f]{6})$/i)
  if (hex) {
    const digits = hex[1].length === 3 ? hex[1].split('').map((digit) => digit + digit).join('') : hex[1]
    return [0, 2, 4].map((offset) => Number.parseInt(digits.slice(offset, offset + 2), 16)) as [number, number, number]
  }
  const rgb = value.match(/^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+))?\s*\)$/i)
  if (!rgb) throw new Error(`Unsupported color: ${value}`)
  const alpha = rgb[4] === undefined ? 1 : Number(rgb[4])
  const foreground = [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])] as [number, number, number]
  if (!background || alpha === 1) return foreground
  return foreground.map((channel, index) => channel * alpha + background[index] * (1 - alpha)) as [number, number, number]
}

function luminance(value: [number, number, number]) {
  const channels = value.map((channel) => channel / 255).map((channel) => channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4)
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722
}

function contrastRatio(foreground: string, background: string) {
  const backgroundRgb = parseColor(background)
  const foregroundRgb = parseColor(foreground, backgroundRgb)
  const light = luminance(foregroundRgb)
  const dark = luminance(backgroundRgb)
  return (Math.max(light, dark) + 0.05) / (Math.min(light, dark) + 0.05)
}

function themeValue(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim()
}

test('styles.css keeps color literals inside the two theme token blocks', () => {
  const css = readFileSync(stylesPath, 'utf8')
  const tokenBlocks = [...css.matchAll(/(?::root|\[data-theme=['"]light['"]\])\s*\{[^}]*\}/g)].map((match) => match[0])
  const nonTokenCss = css.replace(/(?::root|\[data-theme=['"]light['"]\])\s*\{[^}]*\}/g, '')
  const literals = nonTokenCss.match(/#[\da-f]{3,8}\b|rgba?\([^)]*\)/gi) ?? []
  expect(tokenBlocks).toHaveLength(2)
  expect(literals, `unexpected color literals outside theme tokens: ${literals.join(', ')}`).toEqual([])
})

test('light theme token pairs meet WCAG contrast thresholds', () => {
  const style = document.createElement('style')
  style.textContent = readFileSync(stylesPath, 'utf8')
  document.head.append(style)
  document.documentElement.dataset.theme = 'light'

  const textPairs = [
    ['ink', 'panel'],
    ['muted', 'panel'],
    ['nav-muted', 'panel'],
    ['accent', 'panel'],
    ['accent', 'accent-soft'],
    ['warm', 'status-warning-surface'],
    ['red', 'status-offline-surface'],
    ['signal-text', 'signal-surface'],
    ['chart-axis', 'panel'],
    ['chart-tooltip-text', 'chart-tooltip-background'],
    ['on-accent', 'accent'],
  ]
  const borderPairs = [
    ['line', 'panel'],
    ['border-strong', 'panel'],
    ['popup-border', 'surface-popup'],
  ]

  for (const [foreground, background] of textPairs) {
    expect(contrastRatio(themeValue(foreground), themeValue(background)), `${foreground} on ${background}`).toBeGreaterThanOrEqual(4.5)
  }
  for (const [foreground, background] of borderPairs) {
    expect(contrastRatio(themeValue(foreground), themeValue(background)), `${foreground} on ${background}`).toBeGreaterThanOrEqual(3)
  }
})
