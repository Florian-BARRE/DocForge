# General Code Rules — Applied to All Projects

## Language

- All code, comments, docstrings, variable names, and commit messages must be written in **English**.

---

## Object-Oriented Design

Always structure code around classes and objects. Avoid standalone procedural scripts.

- Every logical concept (a service, a processor, a client, a handler) must be its own class.
- Classes must follow the **Single Responsibility Principle**: one class = one clear responsibility.
- Prefer composition over inheritance. Use inheritance only when a true "is-a" relationship exists.
- Never write God classes that do everything. If a class grows beyond ~150 lines, question whether it should be split.

---

## File & Module Structure

**Never write monolithic files.** Code must be split into distinct files that reflect logical boundaries.

- One class per file as a general rule. Exceptions allowed only for small, tightly related dataclasses or enums.
- Group files by domain/responsibility, not by type. Prefer:
  ```
  user/
    user_service.py
    user_repository.py
    user_model.py
  ```
  Over:
  ```
  services/user_service.py
  models/user_model.py   ← acceptable for larger projects, but domain grouping is preferred
  ```
- Each file must have a single, obvious purpose that is clear from its name alone.
- If a file exceeds ~200 lines, treat it as a signal to refactor and split.

---

## Functions & Methods

- Write **small, cohesive functions** with a single responsibility.
- A function should do one thing and do it well. If you need "and" to describe what it does, split it.
- Keep functions under ~30 lines. Extract helpers freely to preserve clarity.
- **Inside every function or method**, segment logic into **clear, numbered steps**:
  ```python
  def process_document(self, raw_text: str) -> ParsedDocument:
      # 1. Clean and normalize raw input
      cleaned = self._clean_text(raw_text)

      # 2. Extract structured fields from cleaned text
      fields = self._extract_fields(cleaned)

      # 3. Build and return the parsed document object
      return ParsedDocument(**fields)
  ```

---

## Docstrings

Provide **Google-style English docstrings** for all classes, methods, and functions — no exceptions.

```python
class DocumentProcessor:
    """
    Handles the full processing pipeline for a single document.

    Responsible for cleaning, parsing, and structuring raw document
    content into a normalized format suitable for downstream consumption.
    """

def extract_metadata(self, content: str) -> dict:
    """
    Extract metadata fields from raw document content.

    Args:
        content (str): Raw text content of the document.

    Returns:
        dict: A dictionary containing extracted metadata fields
              (e.g., title, author, date).

    Raises:
        ValueError: If content is empty or cannot be parsed.
    """
```

---

## Comments

- Add comments to explain **intent, assumptions, and non-obvious decisions** — not to restate what the code does.
- Refine or clarify existing comments to improve readability, but always preserve the original meaning.
- Bad comment: `# Increment counter` → the code already says that.
- Good comment: `# Start at 1 because index 0 is reserved for the header row`

---

## General Best Practices

- Use **type hints** everywhere: function arguments, return types, and class attributes.
- Prefer **explicit over implicit**: clear names, no magic numbers, no unexplained constants.
- No hardcoded secrets, URLs, paths, or environment-specific values — always use environment variables or config files.
- Delete dead code. Do not comment out unused code and leave it in place — use version control for history.
