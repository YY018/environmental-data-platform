# Design plan v4 (work copy: dashboard\design_v4\)

The live report (`dashboard\MyReport.pbip`) is not changed. The redesign is built in
`dashboard\design_v4\MyReport.pbip`, a copy of the project, so it can be opened and checked
in Power BI Desktop separately.

## What the tools support
- Page background image (gradient PNG) and white visual cards with borders: supported.
- Left-hand navigation: built from four `actionButton` visuals with `PageNavigation` links.
  Power BI has no built-in sidebar, so it is a shape plus buttons. Supported.
- Button icons: only generic built-in icons (help, information, bookmarks, reset, back and
  similar). There are no weather, air or earthquake icons. Custom icon images are possible but
  need extra PNG files. Not included in this version.
- Card value size and label size: supported (`labels.fontSize`, `categoryLabels.fontSize`).
- Slicer title, header and item text size: supported (`title`, `header.show`, `items.textSize`).
- Dynamic subtitles and titles from DAX measures: supported (already in use).
- Chart titles, axis and legend text: supported.

## Limitations
- Shadows and gradient fills on visuals are not used, to keep the look minimal.
- Date slicer default range (2020 to 2030) is stored in the slicer filter. Changing it to the
  real data range needs a filter change, so it is deferred to the next phase.
- Series colours follow the theme. A custom palette needs a theme file, which is deferred.

## Layout (1280 x 720)
- Left sidebar: x 0, width 208. Deep purple panel with the product name and four navigation
  buttons (Weather, Air Quality, Earthquakes, Pipeline Health). The active page is highlighted
  in muted pink.
- Content area: x 232 to 1264 (width 1032).
- Header: page title (22px, bold, white) at y 20; dynamic date range subtitle at y 60.
- Slicers: y 104, height 80. City on the left, date range on the right.
- KPI row: y 196, height 96. Equal-width cards.
- Body: y 308, height 396. Two equal columns; the Earthquakes right column is split in two.

## Styling
- Page background: gradient image (unchanged from the current gradient).
- Visual cards: white, 1px `#E5E7EB` border, 10px radius.
- KPI cards: no title (the measure name is shown as the label). Value 28pt in `#3F2D6E`,
  label 11pt in `#6B7280`. This removes duplicate titles.
- Chart and table titles: 13pt Segoe UI Semibold, `#24364B`.
- Slicers: one heading only (the slicer title). Slicer header hidden, so "City" is not repeated.
  Title 13pt Segoe UI Semibold. Items 12pt regular, `#374151`.
- Header title and subtitle: white and light grey, readable on the gradient.

## Four-page consistency
The same sidebar, header, slicer, KPI and chart styles are generated for all four pages.

## Verification
1. Validate the design_v4 report with `powerbi-report-author validate`.
2. Open `dashboard\design_v4\MyReport.pbip` in Power BI Desktop.
3. Capture each page and review the screenshots.
4. Only after approval, replace the live report files with the design_v4 files.
