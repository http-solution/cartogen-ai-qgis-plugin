# Map profiles

A profile is a small JSON file that holds the choices your team repeats on every map. Name it in a request ("make a situation map with the profile `weekly-sitrep`") or in `create_print_layout(profile="weekly-sitrep")`.

Cartogen AI ships **no organisation's template, logo or brand colours**. You write the profile; an example with placeholder values is in [docs/examples/map_profile_example.json](examples/map_profile_example.json).

## Where to put it
`<your project folder>/cartogen_profiles/<name>.json` (looked up first), or `<QGIS profile folder>/cartogen_ai/profiles/<name>.json`. The file name is the profile name: letters, digits, spaces, `-` and `_` only.

## Fields (all optional)
| Field | Values | Effect |
|---|---|---|
| `profile_version` | `1` | Format version. |
| `name`, `description` | text | For people; not used by the tools. |
| `page_size` | `A4`, `A3`, `A2`, `A1` | Page size of new layouts (the layout is built for A4 and scaled). |
| `orientation` | `landscape`, `portrait` | Page orientation. |
| `export_preset` | `draft` (96 dpi), `web` (150), `print` (300) | Resolution of exports of layouts made with the profile. |
| `file_name_pattern` | text with `{title}`, `{date}`, `{layout}` | Name of an exported file when you give a folder instead of a file name. |
| `logo_path` | a PNG or JPG file, relative to the profile's own folder (or a full local path) | Your logo in the masthead; the title is narrowed to make room. A web address, a network path, `..` or an SVG is refused. A missing file gives a warning and a layout without a logo. |
| `logo_position` | `left`, `right` | Which end of the masthead holds the logo (default `left`). |
| `masthead_colour` | `#rrggbb` | Masthead background (beats the Settings colour). |
| `masthead_text_colour` | `#rrggbb` | Title colour; if it is hard to read on the background (contrast under 3:1) the automatic dark or light text is used and a warning says so. |
| `font_family` | a font name | Typeface of every text on the layout. If the font is not installed on the computer a warning is given and the default is used. |
| `footer_lines` | 1 to 3 single-line texts of at most 120 characters | Extra footer lines (for example a contact line), placed before the disclaimer. |
| `sign_off` | object: `prepared_by`, `reviewed_by`, `review_date` (YYYY-MM-DD), `status` (`Draft`, `Reviewed`, `Approved`) | One footer line. With no `reviewed_by` it always reads "Status: Draft - not reviewed". `Reviewed` or `Approved` needs both `reviewed_by` and `review_date`, or the file is refused. The plugin records what you write; it does not check that a review happened. |
| `require_sign_off` | `true`, `false` | A publication export is refused (unless the user gives a reason and confirms) while the sign-off is not a named, dated `Reviewed` or `Approved`. |
| `cod_boundaries` | `true` | Marks the map as using Common Operational Dataset boundaries. Needs `cod_credit`. |
| `cod_credit` | one line, at most 100 characters | Your organisation's own credit wording; Cartogen AI supplies none. It leads the footer's Credits line. An export of the layout also lists any drawn layer that has duplicate admin P-code values (warning only; the field is found by its common names such as `admin2_pcode`). |
| `required_elements` | list of `MAP_MAIN`, `TITLE`, `LEGEND`, `SCALEBAR`, `NORTH_ARROW`, `MAP_INFO`, `FOOTER`, `BODY_TEXT`, `INSET_MAP` | The elements a layout must have; a missing one is reported on export and blocks a publication export unless you give a reason. |

An argument you give in the request beats the profile; the profile beats the defaults. A field the plugin does not know (for example a field from a later version of the plugin) is **refused by name**, never ignored, so a file written for a later version cannot look as if it worked. The profile is remembered on the layout, so a later `export_layout` uses its file name pattern, export preset and required elements.

## Changing a profile after a layout was made
A layout remembers the profile's name. At export the file is read again, so a requirement you add later (for example `require_sign_off`, or a longer `required_elements` list) applies to layouts you already made. What the map itself says is fixed when the layout is built: a review you add to `sign_off` later does not change a footer that already reads "Draft - not reviewed", so rebuild the layout to print it. If the profile file has been deleted or no longer validates, the copy kept on the layout is used and the export result says so (`profile_note`).
