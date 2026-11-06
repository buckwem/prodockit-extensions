# SuperFences { #superfences }

Reference: [Zensical's supported Python Markdown Extensions](https://zensical.org/docs/compatibility/markdown/python-markdown-extensions/)

## Source

````text
!!! note "Nested fence"
    ```python
    print("nested fence")
    ```
````

## Rendered result

!!! note "Nested fence"
    ```python
    print("nested fence")
    ```

The highlighted fence must remain inside the admonition in both outputs.

## Custom fences { #superfences-custom-fences }

### Configuration source

```toml
[project.markdown_extensions.pymdownx.superfences]
custom_fences = [
  { name = "catalogue", class = "catalogue-fence", format = "pymdownx.superfences.fence_code_format" },
]
```

### Source

````text
```catalogue
phase three custom fence
```
````

### Rendered result

```catalogue
phase three custom fence
```

The custom fence retains its configured class on the website and becomes a
static code block in the PDF.
