# NiceGUI 3.x and Quasar cascade layers

NiceGUI 3.x wraps Quasar's stylesheet in a CSS cascade layer, and Quasar's
utility classes sit in a later layer than author styles. A custom rule with
`!important` therefore still loses to a utility class applied on the same
element, which is the opposite of what pre-3.x behaviour taught.

- Do not fight it with `!important` or higher specificity.
- Style through Quasar's own props and semantic classes (`.props(...)`,
  `.classes('...')`), or put custom rules in a layer declared after Quasar's.
- When a style silently does nothing, check the layer order in the browser
  devtools before touching selectors.

Applies to the NiceGUI apps in this constellation (herdstone, Sync_Plex).
