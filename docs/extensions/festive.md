---
icon: lucide/snowflake
---

{{ pdk_heading_counter_reset(page) }}

# Festive overlay

Add falling snow and a Christmas sleigh to the website. Snow stays fixed to
the viewport while the page scrolls. A shallow bank accumulates at the bottom,
melts in small changing patches and remains bounded at 48 CSS pixels.
Snow between the thawing patches continues to accumulate into drifts.

Installing Prodockit leaves festive mode unconfigured. This reference website
opts in explicitly through its own `zensical.toml`.

## Enable the overlay

Load the managed `pdk.js` and `pdk.css` assets and refresh them with
`pdk shared-files --apply`. Add these settings to `zensical.toml`.

```toml
[project.extra.festive]
enabled = true
effect = "snow"
season_start = "12-01"
season_end = "01-06"
sleigh = true
```

Add `&#123;&#123; pdk_festive() &#125;&#125;` to a shared Markdown snippet included on each page,
or to each page where you want the overlay. The normal Prodockit macros setup
provides this helper. A page without the helper has no decoration in production.

Season dates are inclusive UTC dates and may cross New Year. Disabled is the
default. Snow is black in the default light palette and white in the slate
palette. A snowflake icon immediately to the left of the light/dark switch turns
festive mode on or off and remembers the choice. Visitors can also pause or
hide the effect with the controls at the bottom right. Reduced motion starts paused. The decoration allows clicks, scrolling
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

Run `zensical serve` and open this page with the following query string.

```text
?pdk-festive-test=1&pdk-festive-time=2026-12-24T10%3A00%3A00Z&pdk-festive-speed=60&pdk-festive-seed=42
```

Preview works only on `localhost`, `127.0.0.1` and IPv6 loopback. It forces the
season active, including on this page without a configuration marker. Production
hosts ignore the preview parameters.

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

## Christmas route

Father Christmas starts at Kiritimati, Kiribati, at 10:00 UTC on 24 December.
He visits a representative destination as local Christmas midnight reaches it,
moving westwards. The sleigh disappears at 12:00 UTC on 26 December after Baker
Island's Christmas Day finishes. The visitor's time zone does not alter the route.

The destination table includes half-hour and quarter-hour offsets. The browser's
IANA time-zone database supplies daylight-saving offsets for that year's
Christmas. Tied midnights use the last representative in table order. Labels favour familiar cities, countries and regions, including Fiji, New Zealand,
Nepal, Bangladesh, Newfoundland and Hawaii. American Samoa is labelled explicitly
because Samoa itself is on the other side of the date line. The Chatham Islands handover displays New Zealand while retaining its
quarter-hour offset. Marquesas and South Georgia retain their names to represent
their particular offsets. Baker Island is an uninhabited Pacific island used for the final UTC−12
boundary. Labels use a reserved panel and compact alternatives where needed.
The sleigh carries a mound of parcels behind Father Christmas as it follows
a curved route through the viewport.

## New Year fireworks

Set `effect = "fireworks"` for New Year celebrations, or `effect = "auto"`
for snow in the configured season and fireworks on 1 January. The reference
website uses auto. Installation remains opt-in.

Fireworks appear from **00:00 inclusive until 02:00 exclusive on 1 January**
in the visitor's browser time zone. The display mixes peony bursts, rings,
palms, golden willows and crackling sparks, plus Roman candle banks,
fountains, fan jets and sudden mines erupting from the bottom edge. Mixed mode
chooses randomly between these styles. Aerial fireworks launch in groups of
one to three, bursting together at different positions and in different colours.
Ground sequences use three instances of
the same effect, each with a different colour. Roman candle banks fire repeated
volleys from five tubes, while fountains and fan jets produce sustained sprays.
Changing the selected style clears the previous effects. Each style has a matching synthesised sound. The header uses a firework icon.

Press the speaker icon to enable synthesised launch, boom and crackle sounds.
Sound starts muted and requires a click. Use the volume slider to adjust it.
Pausing, hiding, printing or switching to a hidden tab silences the sound.
Reduced motion starts the display paused.

For a local preview, open the following query on this page. The time is UTC
and `pdk-festive-zone` selects the zone used to evaluate the two-hour window.

```text
?pdk-festive-test=1&pdk-festive-effect=fireworks&pdk-festive-time=2027-01-01T00%3A00%3A00Z&pdk-festive-zone=Europe%2FLondon&pdk-festive-speed=1
```

Choose an individual fireworks style, launch a test burst, change the UTC
clock or speed, and reset the particles in the preview panel. Try zones such
as Pacific/Kiritimati, Asia/Kathmandu and America/New_York around their local
midnight and 02:00 boundaries.

### Drone display

Select **Drone display** for a two-minute choreography of coloured lights.
The lights sample three-dimensional surfaces, shown in perspective with rotating
viewpoints. The deer uses 1,100 surface samples from Quaternius's CC0
[Deer model](https://poly.pizza/m/T6Cs7tmMHJ). The other objects use procedural
volumetric surfaces, including a spherical globe, rounded animal bodies,
three-dimensional wings, cones and petals. The title retains shallow depth for
readability. Birds and butterflies flap their wings, the deer gallops, the dolphin
swims, the heart pulses, and the globe rotates as a sphere. The lights morph
every twelve seconds through Happy New Year, a bird, deer,
dolphin, butterfly, heart, star, globe, tree and flower. Mixed mode can also
choose this sequence, waiting for fireworks to clear before the drones start.
The drone sequence is silent. The New Year time window and visitor controls
apply to both fireworks and drones.
