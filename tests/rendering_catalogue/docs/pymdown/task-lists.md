# Task lists { #task-lists }

Reference: [Zensical's supported Python Markdown Extensions](https://zensical.org/docs/compatibility/markdown/python-markdown-extensions/)

## Configuration source

```toml
[project.markdown_extensions.pymdownx.tasklist]
custom_checkbox = true
clickable_checkbox = true
```

## Custom checkbox { #tasklist-checkbox }

The website replaces native checkbox styling with the supported custom
indicator.

## Clickable checkbox { #tasklist-clickable-checkbox }

The website checkboxes are interactive for review, although their state is
not persisted.

## Source

```text
- [x] Phase 3 implemented
- [ ] Visual review pending
```

## Rendered result

- [x] Phase 3 implemented
- [ ] Visual review pending

The PDF must show the checked and unchecked states as static list markers.
