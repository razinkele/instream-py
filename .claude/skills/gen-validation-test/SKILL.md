---
name: gen-validation-test
description: Scaffold a new validation test comparing Python inSTREAM output against NetLogo 7.4 reference data. Use when adding a new validation test case or activating a skipped test.
disable-model-invocation: true
---

# Generate Validation Test

Scaffold a new validation test that compares Python output against NetLogo 7.4 reference data.

**Usage**: `/gen-validation-test <procedure-name>`

The `<procedure-name>` should match the NetLogo test procedure name (e.g., `test-cell-depths`, `test-growth-report`).

## Steps

### 1. Identify the NetLogo procedure

Ask or determine:
- **NetLogo test procedure name** (from the argument)
- **What it tests** (cell variables, depths, velocities, growth, survival, etc.)
- **Expected reference CSV filename** (convention: kebab-case, e.g., `cell-depth-test-out.csv`)

### 2. Check for existing reference data

Look in `tests/fixtures/reference/` for the expected CSV file. List available files:

```bash
ls tests/fixtures/reference/
```

If the reference CSV does not exist yet, inform the user they need to generate it using the `/netlogo-oracle` skill first, then re-run this skill.

### 3. Read the reference CSV structure

Read the first few lines of the reference CSV to understand columns and data types:

```bash
head -5 "tests/fixtures/reference/<filename>.csv"
```

### 4. Scaffold the test class

Add a new test class to `tests/test_validation.py` following this pattern:

```python
class Test<PascalCaseName>:
    """Port of NetLogo <procedure-name>."""

    def test_<snake_case_name>(self):
        import numpy as np
        import pandas as pd

        ref_path = require_reference("<reference-file>.csv")
        ref = pd.read_csv(ref_path)

        # --- Run Python equivalent ---
        # TODO: Initialize model and run the equivalent computation
        # from instream.model import InSTREAMModel
        # model = InSTREAMModel.from_config("tests/fixtures/example_a")
        # result = model.<relevant_method>()

        # --- Compare outputs ---
        # For each column in reference data, assert close match:
        # np.testing.assert_allclose(
        #     python_values,
        #     ref["<column>"].values,
        #     rtol=1e-4,
        #     err_msg="<Column> mismatch",
        # )

        # Remove this line once implemented:
        pytest.skip("Not yet implemented — reference data ready, needs Python equivalent")
```

### 5. Conventions

- Place the new class in `tests/test_validation.py` (do NOT create a separate file)
- Use `require_reference()` helper to skip gracefully when reference data is missing
- Use `np.testing.assert_allclose` with `rtol=1e-4` for floating-point comparisons (loosen to `rtol=1e-2` if NetLogo uses different precision)
- Use `assert ==` for integer and string comparisons
- Reference the NetLogo procedure name in the docstring
- Name the test method `test_<descriptive_snake_case>`
- Import heavy modules inside the test function (not at module level)

### 6. Report

After scaffolding, report:
- Test class name and method name added
- Reference CSV used (or note that it needs to be generated)
- Whether the test is fully implemented or has a `pytest.skip` placeholder
- Suggest next steps (implement Python equivalent, or generate reference data)
