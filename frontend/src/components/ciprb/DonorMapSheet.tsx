/**
 * The printed donor map sheet, shown on the dashboard.
 *
 * Dr. Tanjina's 6 October file asked for the maps CIPRB already has in hand
 * (the A4 sheets produced on 27 September for Dr. Sayeed) to appear in
 * SIMPLE. Drawing the same district lists a second time in Leaflet would
 * give two renderings that look different and can drift apart, so the
 * dashboard serves the sheet itself. `scratchpad/make_donor_maps.py` writes
 * both the print PDF and the web PNG in one run, from one district list.
 *
 * Re-render after any change to the donor lists: the PNG is a build
 * artefact, not a drawing to be edited.
 */
export function DonorMapSheet({ src, alt, maxWidth = 560 }: {
  src: string
  alt: string
  /** A4 portrait sheets read well at the default. The A3 landscape sheet
   *  carries two maps and needs more room before its labels close up. */
  maxWidth?: number
}) {
  return (
    <div className="card" style={{ padding: 10 }}>
      {/* Held to a width that keeps the district labels legible without
          letting the sheet dominate the page. */}
      <div style={{ maxWidth, margin: '0 auto' }}>
        <a href={src} target="_blank" rel="noopener noreferrer"
           style={{ display: 'block' }}
           title="Open the full-size sheet">
          <img
            src={src}
            alt={alt}
            loading="lazy"
            style={{
              display: 'block', width: '100%', height: 'auto',
              borderRadius: 6,
              // Without this the white sheet dissolves into a white card.
              outline: '1px solid rgba(0,0,0,0.10)', outlineOffset: -1,
            }}
          />
        </a>
      </div>
    </div>
  )
}
