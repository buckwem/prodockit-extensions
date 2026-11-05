# PyMdown nesting { #nested-pymdown }

These risk-based specimens place the Phase 3 extensions inside representative
containers. They supplement the standalone pages without attempting every
possible combination.

## Maths and formatting in an admonition { #nested-math-and-formatting }

!!! info "Nested maths and formatting"
    Inline mathematics $a^2 + b^2$, ^^inserted^^, ==marked==,
    ~~deleted~~, CO~2~ and (c) -->.

## Caption in a blockquote { #nested-caption }

> ![Nested caption asset](../assets/core-sample.svg)
> /// caption
> Nested Phase 3 caption
> ///

## Details in a list { #nested-details }

1. A list item before the disclosure.
2. ???+ note "Nested details"
       The details body is inside an ordered list.

## Emoji and keys in an admonition { #nested-emoji-and-keys }

!!! tip "Nested controls"
    :material-test-tube: :catalogue-phase: and ++ctrl+shift+p++.

## Highlighted code in a tab { #nested-highlight }

=== "Nested Python"

    ```python
    nested_value = "phase three"
    ```

=== "Nested inline code"

    Inline `#!python print("nested")` remains highlighted.

## Included snippet in a blockquote { #nested-snippet }

<blockquote markdown>

--8<-- "snippets/phase-three.md"

</blockquote>

## Custom fence in an admonition { #nested-superfence }

!!! note "Nested custom fence"
    ```catalogue
    nested custom fence
    ```

## Tabs in an admonition { #nested-tabs }

!!! example "Nested tab set"
    === "First nested tab"

        First nested tab body.

    === "Second nested tab"

        Second nested tab body.

## Task list in a blockquote { #nested-task-list }

> - [x] Nested task complete
> - [ ] Nested task pending
