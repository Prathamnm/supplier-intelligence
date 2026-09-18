// Detail data, split out so it loads only with the pages that show it,
// not with the overview.
import returnsJson from '../data/returns.json'
import detailsJson from '../data/supplier_details.json'
import type { ReturnRow, SupplierDetails } from './types'

export const returns = returnsJson as unknown as ReturnRow[]
export const details = detailsJson as unknown as SupplierDetails
