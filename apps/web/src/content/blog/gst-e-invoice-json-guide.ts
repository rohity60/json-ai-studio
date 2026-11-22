import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'gst-e-invoice-json-guide',
    title: 'GST e-Invoice JSON Explained: Format, Sample File and Common IRP Errors',
    description:
      'A field-by-field guide to the Indian GST e-invoice JSON (IRP schema 1.1): TranDtls, DocDtls, seller and buyer, ItemList, ValDtls and EwbDtls for e-way bills. Includes a sample file, the tax math, and fixes for common rejection reasons.',
    updatedAt: '2026-11-22',
    author: 'JSON AI Studio',
    tags: ['gst', 'e-invoice', 'e-invoice json', 'irn', 'e-way bill', 'india', 'json file kaise banaye'],
    readingTime: '9 min',
    aiSummary:
      'An Indian GST e-invoice is a JSON document in the IRP schema (version 1.1) uploaded to the Invoice Registration Portal to get an IRN and signed QR code. Main sections: Version, TranDtls (tax scheme, supply type, reverse charge), DocDtls (type INV/CRN/DBN, number, dd/mm/yyyy date), SellerDtls and BuyerDtls (GSTIN, legal name, address, numeric pin, two-digit state code; buyer Pos = place of supply), ItemList (HSN/SAC, quantity, unit price, assessable amount, GST rate, tax amounts, item total), ValDtls (invoice totals) and optional EwbDtls to generate the e-way bill at the same time. Inter-state uses IGST, intra-state CGST+SGST. Totals must match the items. Test in the NIC sandbox; never commit real GSTINs or credentials.',
    relatedTemplates: ['gst-e-invoice', 'json-schema', 'sample-json-data'],
    relatedBlogs: ['json-schema-guide', 'sample-json-data-guide'],
    faq: [
      {
        q: 'What is an e-invoice JSON file?',
        a: 'It is the invoice data in the government\'s standard JSON format. Your ERP, billing software or the offline tool creates it; the IRP validates it and returns an IRN (Invoice Reference Number), an acknowledgement number and a signed QR code.',
      },
      {
        q: 'JSON file kaise banaye for e-invoice?',
        a: 'Do not write it by hand for production. Use your billing or ERP software, a GSP, or the free offline Excel/bulk generation tool from the e-invoice portal, which exports the JSON. For testing, start from the sample on this page and change the values.',
      },
      {
        q: 'How do I generate an e-way bill from an e-invoice?',
        a: 'Add an EwbDtls block (transporter id, mode, distance, vehicle or transport document details) to the e-invoice JSON. The IRP then generates the e-way bill together with the IRN. You can also generate it later from the IRN.',
      },
      {
        q: 'What is the date format in e-invoice JSON?',
        a: 'dd/mm/yyyy as a string, for example "21/11/2026". ISO dates like "2026-11-21" are rejected.',
      },
      {
        q: 'Is the GSTIN in the sample real?',
        a: 'No. The GSTINs in the sample are placeholders that will not pass checksum validation. Use the test GSTINs provided by the sandbox when testing against NIC.',
      },
    ],
  },
  body: `Under India's GST e-invoicing rules, businesses above the turnover threshold report each B2B invoice to the **Invoice Registration Portal (IRP)** as JSON. The IRP validates it and returns an **IRN** and a **signed QR code** that must appear on the invoice.

This guide walks through the JSON field by field. The full sample is in the [GST e-Invoice template](/templates/gst-e-invoice).

> The schema is versioned by GSTN/NIC. This guide follows version **1.1**. Always check the current schema and validation rules on the official e-invoice portal before going live.

## The overall structure

\`\`\`json
{
  "Version": "1.1",
  "TranDtls":   { },
  "DocDtls":    { },
  "SellerDtls": { },
  "BuyerDtls":  { },
  "ItemList":   [ ],
  "ValDtls":    { },
  "EwbDtls":    { }
}
\`\`\`

Optional sections not shown: \`DispDtls\` (dispatch from), \`ShipDtls\` (ship to), \`PayDtls\`, \`RefDtls\`, \`AddlDocDtls\` and \`ExpDtls\` (exports).

## TranDtls: transaction details

\`\`\`json
"TranDtls": { "TaxSch": "GST", "SupTyp": "B2B", "RegRev": "N", "IgstOnIntra": "N" }
\`\`\`

| Field | Meaning |
|---|---|
| \`TaxSch\` | Always \`"GST"\` |
| \`SupTyp\` | \`B2B\`, \`SEZWP\` / \`SEZWOP\` (SEZ with / without payment), \`EXPWP\` / \`EXPWOP\` (export), \`DEXP\` (deemed export) |
| \`RegRev\` | \`"Y"\` if reverse charge applies |
| \`IgstOnIntra\` | \`"Y"\` if IGST applies even though seller and buyer are in the same state |

## DocDtls: document details

\`\`\`json
"DocDtls": { "Typ": "INV", "No": "ACME/2026/0142", "Dt": "21/11/2026" }
\`\`\`

- \`Typ\`: \`INV\` (invoice), \`CRN\` (credit note) or \`DBN\` (debit note).
- \`No\`: up to 16 characters; letters, digits, \`/\` and \`-\`; cannot start with \`0\`, \`/\` or \`-\`. Must be unique for the seller in the financial year.
- \`Dt\`: **dd/mm/yyyy** as a string.

## SellerDtls and BuyerDtls

\`\`\`json
"SellerDtls": {
  "Gstin": "29AABCA1234A1Z5", "LglNm": "Acme Technologies Private Limited",
  "Addr1": "12 MG Road", "Loc": "Bengaluru", "Pin": 560001, "Stcd": "29"
},
"BuyerDtls": {
  "Gstin": "27AABCB5678B1Z3", "LglNm": "Bluebird Retail LLP", "Pos": "27",
  "Addr1": "4th Floor, Nariman Point", "Loc": "Mumbai", "Pin": 400021, "Stcd": "27"
}
\`\`\`

- \`Pin\` is a **number**; \`Stcd\` and \`Pos\` are two-digit **strings** (state codes: 27 Maharashtra, 29 Karnataka, 07 Delhi, 33 Tamil Nadu, and so on).
- \`Pos\` is the **place of supply**. It decides IGST vs CGST+SGST.
- For exports, the buyer \`Gstin\` is \`"URP"\` (unregistered person) and \`Pos\` is \`"96"\` (other country).

## ItemList: line items

\`\`\`json
{
  "SlNo": "1", "PrdDesc": "Laptop 14-inch", "IsServc": "N", "HsnCd": "847130",
  "Qty": 10, "Unit": "NOS", "UnitPrice": 1000,
  "TotAmt": 10000, "Discount": 0, "AssAmt": 10000,
  "GstRt": 18, "IgstAmt": 1800, "CgstAmt": 0, "SgstAmt": 0,
  "CesRt": 0, "CesAmt": 0, "TotItemVal": 11800
}
\`\`\`

The math the IRP checks:

\`\`\`text
TotAmt     = Qty × UnitPrice
AssAmt     = TotAmt − Discount
IgstAmt    = AssAmt × GstRt / 100            (inter-state)
CgstAmt    = SgstAmt = AssAmt × GstRt / 200  (intra-state)
TotItemVal = AssAmt + IgstAmt + CgstAmt + SgstAmt + CesAmt + ... + OthChrg
\`\`\`

- \`IsServc\`: \`"Y"\` for services, which use a SAC code starting with \`99\` in \`HsnCd\`.
- \`Unit\`: a UQC code such as \`NOS\`, \`KGS\`, \`MTR\`, \`BOX\` or \`OTH\`.
- \`GstRt\` must be a valid GST slab.

## ValDtls: invoice totals

\`\`\`json
"ValDtls": {
  "AssVal": 15000, "CgstVal": 0, "SgstVal": 0, "IgstVal": 2700,
  "CesVal": 0, "StCesVal": 0, "Discount": 0, "OthChrg": 0,
  "RndOffAmt": 0, "TotInvVal": 17700
}
\`\`\`

Each total must equal the sum of the matching item fields (the IRP allows a small rounding tolerance). \`TotInvVal\` = \`AssVal\` + taxes + cess + \`OthChrg\` − \`Discount\` + \`RndOffAmt\`.

## EwbDtls: e-way bill with the IRN

To get an e-way bill at the same time as the IRN, add:

\`\`\`json
"EwbDtls": {
  "TransId": "29AABCT9999T1Z2", "TransName": "Speedy Logistics",
  "TransMode": "1", "Distance": 980,
  "TransDocNo": "LR-55812", "TransDocDt": "21/11/2026",
  "VehNo": "KA01AB1234", "VehType": "R"
}
\`\`\`

- \`TransMode\`: \`"1"\` road, \`"2"\` rail, \`"3"\` air, \`"4"\` ship.
- \`VehType\`: \`"R"\` regular, \`"O"\` over-dimensional cargo.
- \`Distance\` in km. For road you need either the vehicle number or the transporter id.

**Bulk e-way bills** that are not tied to an e-invoice use a different JSON layout, produced by the e-way bill portal's bulk generation tool. Generate that file with the official tool rather than by hand.

## Common rejection reasons and fixes

| Error | Fix |
|---|---|
| Invalid GSTIN / checksum | Use a real, active GSTIN (or the sandbox test GSTINs). Placeholders fail. |
| Date format | Use \`"dd/mm/yyyy"\`, not ISO dates. |
| Duplicate IRN | The same seller GSTIN + document type + number + financial year was already registered. Use a new number or fetch the existing IRN. |
| Tax type mismatch | Seller \`Stcd\` ≠ buyer \`Pos\` needs IGST; equal needs CGST + SGST (unless \`IgstOnIntra\` is \`"Y"\`). |
| Totals do not match | Recompute \`ValDtls\` from \`ItemList\`; round consistently to 2 decimals. |
| Invalid HSN | Use a valid HSN/SAC with enough digits for your turnover. |
| Pin code / state mismatch | The pin must belong to the state in \`Stcd\`. |
| Wrong types | \`Pin\` and amounts are numbers; \`Stcd\`, \`Pos\`, \`SlNo\` are strings. |

## Other GST JSON files

- **GSTR-1**: the return JSON is generated by the GST offline tool or your software and uploaded on the GST portal. Its layout is different from the e-invoice schema.
- **ITR**: income-tax return JSON is produced by the income-tax department's utilities. Use the official utility; do not edit the exported JSON by hand, since the portal validates it strictly.

## Security

- Keep IRP API credentials, client secrets and session tokens on the server. Never call the IRP from browser code.
- Do not commit real GSTINs, customer data or credentials to test fixtures.

## Check and edit it with AI

Open the [GST e-Invoice template](/templates/gst-e-invoice) in the studio and ask "convert this to an intra-state invoice", "add a third item at 12% GST" or "check that the totals match the items". Each change appears as a diff for you to review.
`,
};
