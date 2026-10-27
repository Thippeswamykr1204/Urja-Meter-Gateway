import { QUALITY_FLAGS } from './quality'
import { qualityFlagExplanations } from './quality'
import { expect, test } from 'vitest'

test('every generated backend quality flag has a plain-language explanation', () => {
  expect(QUALITY_FLAGS.every((flag) => qualityFlagExplanations[flag])).toBe(true)
})
