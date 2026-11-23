---
icon: lucide/snowflake
---

{{ pdk_heading_counter_reset(page) }}

# Festive overlay

The festive extension adds seasonal overlays to your website. The first two
overlays celebrate Christmas and New Year. Other festive overlays may be added
on request. The overlays stay fixed to the viewport while the page scrolls.

- **Christmas** brings falling snow, gradually melting drifts and Father Christmas
  travelling in his sleigh.
- **New Year** alternates fireworks with animated drone displays, with optional
  sound for the fireworks.

The festive extension is enabled separately from other Prodockit features.
Installing Prodockit leaves it disabled and unconfigured. This reference website
opts in explicitly through its own `zensical.toml`.

## Enable the festive extension

Load the managed `pdk.js` and `pdk.css` assets and refresh them with
`pdk shared-files --apply`. Add these settings to `zensical.toml`.

```toml
[project.extra.festive]
enabled = true
effect = "auto"
season_start = "12-01"
season_end = "12-30"
sleigh = true
fireworks_start = "01-01"
fireworks_hours = 24
```

Only one overlay can be active at a time. Choose a single `effect` value in
one `[project.extra.festive]` configuration table.

`effect = "auto"` selects the New Year overlay on the configured fireworks start
date and the Christmas overlay during the configured snow season. It switches between the overlays
automatically and never displays them together. Use `"snow"` or `"fireworks"` to
select just one overlay. Set `enabled = false`, or remove the festive settings,
to disable the extension independently of other Prodockit features.

Add `&#123;&#123; pdk_festive() &#125;&#125;` to a shared Markdown snippet included on each page,
or to each page where you want the overlay. The normal Prodockit macros setup
provides this helper.

This reference website uses a site-wide alternative in `overrides/main.html`.
Its `extrahead` block adds the festive configuration marker to every page when
`extra.festive.enabled` is true, so no Markdown helper or shared snippet is
needed here. A page needs either the helper or this template marker to display
an overlay in production.

Season dates are inclusive UTC dates and may cross New Year; the default ends
on 30 December. Disabled is the default. Snow is black in the default light
palette and white in the slate palette. A snowflake icon immediately to the
left of the light/dark switch turns festive mode on or off. The pause/play
control and the on/off control remember the visitor's choices when browser
storage is available. Controls appear only while an effect is active, at the
bottom right by default; set `position = "bottom-left"` to move them. Set
`palette = "light"` or `"dark"` to override automatic colour detection.
Each control has a keyboard focus indicator and a 44-pixel minimum target.
Reduced motion starts paused. The decoration allows clicks, scrolling
and text selection through to the page. Browser print and PDF exports omit it.

The sleigh illustration is an optional managed asset. Add this entry to your
existing `.prodockit-shared-files.toml` file and run `pdk shared-files --apply`.

```toml
[[files]]
source = "pdk-sleigh.png"
target = "docs/javascripts/pdk-sleigh.png"
```

Keep the image beside `pdk.js`. The browser loads it when the sleigh is needed.

## Preview with zensical serve

Run `zensical serve` and use the address and port shown in its terminal output.
The URLs below use `8000` as an example; replace it with the port selected by
the server, which may be different. Keep the `/extensions/festive/` path and
query parameters when opening a preview.

```text
http://127.0.0.1:8000/extensions/festive/?pdk-festive-test=1&pdk-festive-time=2026-12-24T10%3A00%3A00Z&pdk-festive-speed=60&pdk-festive-seed=42
```

Preview works only on `localhost`, `127.0.0.1` and IPv6 loopback. It forces the
season active, including on this page without a configuration marker. Production
hosts ignore the preview parameters.

These public effect links work on pages where festive mode is enabled. They
override the seasonal schedule for that page without opening the local preview
panel:

| Effect | Test link |
| --- | --- |
| Snow | [Show snow](?pdk-festive-snow=true) |
| Snow and sleigh | [Show Father Christmas](?pdk-festive-santa=true) |
| Fireworks | [Show fireworks](?pdk-festive-fireworks=true) |
| Drones | [Show drones](?pdk-festive-drone=true) |
| Fireworks and drones | [Show alternating display](?pdk-festive-fireworks-drone=true) |

The combined display alternates after about two minutes, while the drone-only
link starts with drones. [Clear the effect](?) to return to the normal schedule.
Add `&pdk-festive-panel=0` to a local preview URL to hide the diagnostic panel.

Use the UTC date/time field to jump in time, the clock-speed field (0–3600) to
freeze or accelerate the Christmas route, and Step to advance a single frame.
Simulation time controls the route independently of snowfall. Each time Santa
returns for another flight pass in preview mode, the clock jumps to the next
destination. After the last destination, it cycles back to Kiritimati.

Choose **Reset** to restore the initial preview clock, seed and snowfall.
Choose **Changing Location** to start at Kiritimati and advance one destination
per flight pass, skipping consecutive stops with the same display name,
with the clock frozen between passes.

Choose **Current Santa zone** to use the current UTC time of day on 25 December
of the preview year. This lets you inspect the clock-based destination outside
the festive season. It follows the real clock at normal speed and changes
destination at time-zone boundaries, including fractional offsets. Flight passes
do not advance the destination in this preset. Editing the time or speed returns
to the simulated clock. Reset snow
restarts the seeded animation. Presets cover Christmas start, Nepal's fractional
offset, Christmas end, maximum snow, reduced motion and the real theme palette
controls. The output reports UTC time, destination, palette, particle count,
bank height and mean rendering cost. Resize the browser to test mobile layouts.

Keep the query string in the address bar when navigating between pages. The
controller persists across instant navigation while the configuration is the
same. Live reload restarts the deterministic seed and requested preview time.

## Christmas overlay

Snow forms a shallow bank at the bottom of the viewport. It melts in small
changing patches and remains bounded at 48 CSS pixels. Snow between the thawing
patches continues to accumulate into drifts.

### Christmas route

Father Christmas starts at Kiritimati, Kiribati, at 10:00 UTC on 24 December.
He visits a representative destination as local Christmas midnight reaches it,
moving westwards. The sleigh follows a 25-hour flight window and disappears at
11:00 UTC on 25 December. The visitor's time zone does not alter the route.

The destination table includes half-hour and quarter-hour offsets. The browser's
IANA time-zone database supplies daylight-saving offsets for that year's
Christmas. Tied midnights use the last representative in table order. Labels favour familiar cities, countries and regions, including Fiji, New Zealand,
Nepal, Bangladesh, Newfoundland and Hawaii. The Chatham Islands handover
displays New Zealand while retaining its quarter-hour offset. Marquesas and
South Georgia retain their names to represent their particular offsets. Labels
use a reserved panel and compact alternatives where needed.
The sleigh carries a mound of parcels behind Father Christmas as it follows
a curved route through the viewport.

## New Year fireworks

Set `effect = "fireworks"` for New Year celebrations, or `effect = "auto"`
for snow in the configured season and fireworks on the configured date. The reference
website uses auto. Installation remains opt-in.

To enable only the New Year overlay, add this configuration to `zensical.toml`.
Load the managed assets and include the configuration helper as described in
[Enable the festive extension](#enable-the-festive-extension).

```toml
[project.extra.festive]
enabled = true
effect = "fireworks"
drone = true
fireworks_start = "01-01"
fireworks_hours = 24
```

The New Year overlay uses the configured local start date and duration, so it
does not need snow season dates or sleigh settings. Change `effect` to `"auto"` in the full
configuration above to cover both celebrations automatically, with only one
overlay active at a time. The configuration blocks are alternatives; do not add
a second `[project.extra.festive]` table.

By default, fireworks appear throughout **1 January** in the visitor's browser
time zone. Set `fireworks_start` to another `MM-DD` date and
`fireworks_hours` to a whole number from 1 to 24 to shorten or move the display.
The display mixes peony bursts, rings,
palms, golden willows and crackling sparks, plus Roman candle banks,
fountains, fan jets and sudden mines erupting from the bottom edge. The fireworks phase chooses randomly between these styles. Aerial fireworks launch in groups of
one to three, bursting together at different positions and in different colours.
Ground sequences use three instances of
the same effect, each with a different colour. Roman candle banks fire repeated
volleys from five tubes, while fountains and fan jets produce sustained sprays.
Each style has a matching synthesised sound. The header uses a firework icon. Festive icons appear only during the active
season or New Year window.

Press the speaker icon to enable synthesised launch, boom and crackle sounds.
Selected aerial launches whistle upwards, and every aerial burst has a report,
with deeper booms and rumbling tails for larger shells after a short
propagation delay. Sound starts muted and requires a click. Use the volume slider to adjust it.
Set `sound = false` to remove the speaker and volume controls.
Pausing, hiding, printing or switching to a hidden tab silences the sound.
Reduced motion starts the display paused.

For a local preview, open the following URL, replacing `8000` with the port
shown by `zensical serve`. The time is UTC
and `pdk-festive-zone` selects the zone used to evaluate the scheduled window.

```text
http://127.0.0.1:8000/extensions/festive/?pdk-festive-test=1&pdk-festive-effect=fireworks&pdk-festive-time=2027-01-01T00%3A00%3A00Z&pdk-festive-zone=Europe%2FLondon&pdk-festive-speed=1
```

The show rotates automatically without a style selector. In the preview panel,
launch a test burst, step a frame, change the UTC clock or speed, or reset the show. Try zones such
as Pacific/Kiritimati, Asia/Kathmandu and America/New_York around their local
midnight and the configured end-hour boundaries.

### Drone display

Drone displays are enabled by default. Omitting `drone` is equivalent to
`drone = true`. Set `drone = false` in `[project.extra.festive]` to disable
them and show fireworks throughout the active New Year window. This setting
also applies when `effect = "auto"` selects the New Year overlay.
The public drone-only test uses a silent display.

Each drone phase provides a two-minute choreography of coloured lights.
The lights sample three-dimensional surfaces, shown in perspective with rotating
viewpoints. The deer uses 1,100 surface samples from Quaternius's CC0
[Deer model](https://poly.pizza/m/T6Cs7tmMHJ). The other objects use procedural
volumetric surfaces, including a spherical globe, rounded animal bodies,
three-dimensional wings, cones and petals. The title retains shallow depth for
readability. Birds and butterflies flap their wings, the deer trots with alternating diagonal leg pairs, the dolphin
swims, the heart pulses, and the globe rotates as a sphere. The lights morph
every twelve seconds through Happy New Year, a bird, deer,
dolphin, butterfly, heart, star, globe, tree and flower. The show alternates automatically between two minutes of fireworks and the
two-minute drone sequence, allowing the previous fireworks to clear first.
The drone sequence is silent. The New Year time window and visitor controls
apply to both fireworks and drones.
