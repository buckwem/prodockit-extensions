# Maths and captions

Reference: [Zensical's supported Python Markdown Extensions](https://zensical.org/docs/compatibility/markdown/python-markdown-extensions/)

## Arithmatex { #arithmatex }

### Source

```text
Inline mathematics: $p^2 + q^2$.

$$
\sum_{i=1}^{3} i = 6
$$
```

### Rendered result

Inline mathematics: $p^2 + q^2$.

$$
\sum_{i=1}^{3} i = 6
$$

The website uses MathJax to typeset the generic Arithmatex wrappers. The PDF
must replace the TeX source with static vector mathematics.

## Blocks Caption { #blocks-caption }

### Source

```text
![Website output flows to PDF output](../assets/core-sample.svg)
/// caption
Phase 3 caption attached to an image
///
```

### Rendered result

![Website output flows to PDF output](../assets/core-sample.svg)
/// caption
Phase 3 caption attached to an image
///

The image and caption must remain one semantic figure in the website and stay
visibly associated in the PDF.
