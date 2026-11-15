# Marswalk logo concepts

## Selected identity

Philippe selected **the walking astronaut over Mars** on 2026-11-15. Use `marswalk-mark.svg` as the primary symbol, `marswalk-logo.svg` on light surfaces, and `marswalk-logo-inverse.svg` in the dark blue application header. The helmet remains an unselected alternative, not the default favicon or secondary identity. For small icons, simplify the selected walking mark if needed rather than switching symbols without a new decision.

Original SVG drawings built for the frontend direction selected by Philippe: dark orange and deep blue, an astronaut, and Mars. The mark simplifies the astronaut to helmet, visor, backpack and walking silhouette over a planetary disc. A second concept combines a helmet and an orange terrain horizon.

## Assets

- `marswalk-mark.svg`: walking astronaut / Mars disc, transparent canvas.
- `marswalk-logo.svg`: primary horizontal lockup for light surfaces.
- `marswalk-logo-inverse.svg`: light wordmark for navy surfaces.
- `marswalk-helmet.svg`: alternative helmet symbol.
- `marswalk-mark-mono.svg`, `marswalk-helmet-mono.svg`: single-color versions using `currentColor` and transparent negative-space masks.
- `identity-preview.png`: rendered comparison sheet with light/dark applications and small-size previews.
- `marswalk-mark.png`, `marswalk-helmet.png`: 512 px transparent PNG previews.

All SVGs contain vector geometry, not embedded raster images. The wordmark is live text with the font stack `Bahnschrift, Segoe UI, Arial, sans-serif`; outline or bundle the chosen font before locking final typography across platforms. The symbols themselves have no font dependency.

## Palette

- Mars orange: `#B64E26`
- Deep blue: `#152B40`
- Light ink / suit: `#F5F3EF`

Prefer the walking symbol at 40 px or larger. Check its legibility before using it at favicon sizes; a simplified walking-mark version can be prepared if needed. Use the inverse lockup in the navy application header.

## References

- [NASA spacesuits](https://www.nasa.gov/humans-in-space/astronauts/spacesuits/): helmet, visor and life-support silhouette reference.
- [NASA Hubble portrait of Mars](https://science.nasa.gov/image-detail/hs-2016-15-a-full_tif_for_promo/): planetary disc and rust-color reference.

The artwork is newly drawn geometry; it does not embed those photographs or reproduce a NASA insignia. The terrain line is stylized, not a geographic outline of a specific Martian feature.

## Editing

The SVGs are directly editable vector sources and need no build tool. The frontend asset-sync script copies only the three selected logo SVGs into its ignored public asset directory.
