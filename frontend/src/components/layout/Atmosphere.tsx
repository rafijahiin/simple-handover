/**
 * Atmosphere — ambient background layer.
 *
 * Was a heavy decorative composition (gradient orbs + Bangladesh topo +
 * conic aurora + grid + grain) tuned for the warm-paper editorial
 * aesthetic. With the UNFPA brand re-tint (off-white surface, orange
 * highlight) those orbs and gradients competed visually with content
 * instead of supporting it, and they violated the kit's "white
 * providing clean, open spaces" principle.
 *
 * Now: just a flat off-white plate with a single very-low-opacity
 * orange dot pattern that disappears below 40% zoom. This gives the
 * page texture without colour noise. Auto-mutes on dark mode via
 * the existing .atm-mesh CSS rule (in index.css).
 */
export function Atmosphere() {
  return (
    <div className="atmosphere" aria-hidden="true">
      <div className="atm-mesh" />
    </div>
  )
}
