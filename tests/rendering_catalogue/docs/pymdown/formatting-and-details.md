# Formatting and details

Reference: [Zensical's supported Python Markdown Extensions](https://zensical.org/docs/compatibility/markdown/python-markdown-extensions/)

Authoring reference: [Zensical formatting](https://zensical.org/docs/authoring/formatting/)

## Caret { #caret }

### Source

```text
^^Inserted text^^ and H^2^O.
```

### Rendered result

^^Inserted text^^ and H^2^O.

The inserted and superscript forms must remain distinguishable in both
outputs.

## Mark { #mark }

### Source

```text
The ==review marker== remains visible.
```

### Rendered result

The ==review marker== remains visible.

## Tilde { #tilde }

### Source

```text
~~Deleted text~~ and CO~2~.
```

### Rendered result

~~Deleted text~~ and CO~2~.

The website and PDF must preserve deleted and subscript text semantically and
visually.

## Details { #details }

### Source

```text
???+ note "Expanded review details"
    This body can be collapsed on the website.
```

### Rendered result

???+ note "Expanded review details"
    This body can be collapsed on the website.

The website provides an interactive disclosure control. The static PDF must
show its title and expanded body.
