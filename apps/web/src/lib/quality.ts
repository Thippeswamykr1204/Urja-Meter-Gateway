import { QUALITY_FLAGS, type QualityFlag } from './generated-api'

export const qualityFlagExplanations: Record<QualityFlag, string> = {
  clean: 'No quality issue was recorded.',
  missing: 'The source did not provide a value.',
  invalid: 'The value could not be parsed safely.',
  duplicate: 'The source returned the same identifier or reading more than once.',
  orphan: 'The hierarchy referenced a parent that was not present.',
  cycle: 'The hierarchy relationship formed a cycle and was retained as a flagged root.',
  unverified: 'The source behavior has not been verified from a captured exchange.',
  out_of_order: 'The source returned readings out of timestamp order.',
  negative_value: 'The source returned a negative reading.',
  unit_converted: 'The value was converted from the observed unit to the configured unit.',
  assumed_timezone: 'The timestamp had no timezone, so the configured timezone was used.',
  unknown_unit: 'The source unit is absent or not documented.',
  schema_drift: 'The response did not match the known response shape.',
  ambiguous_number: 'The numeric separators were ambiguous and were not guessed.',
  ambiguous_date_format: 'The date format was ambiguous and needs explicit configuration.',
  mixed_unit: 'The group contains readings with different units.',
  conflict: 'A newer value replaced an earlier value for the same key.',
  counter_reset: 'A cumulative counter decreased, so the delta was omitted.',
  partial: 'The response does not cover the complete requested range.',
  incompatible_reading: 'The group contains incompatible reading kinds.',
}

export { QUALITY_FLAGS }
