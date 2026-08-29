"""Provider integration seams for configuration, model calls and safe evidence."""

# Keep this package intentionally lazy: provider modules are imported by their
# consumers so importing the package never creates network clients or cycles.
