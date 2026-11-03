# Language capability matrix

Proofline analyzes source without executing project configuration or installing reviewed dependencies.

| Capability | Python | JavaScript / JSX | TypeScript / TSX |
|---|---|---|---|
| Changed files and source review | Yes | Yes | Yes |
| Gemini contextual review | With configured API/model | With configured API/model | With configured API/model |
| Syntax / deterministic rules | Ruff, Bandit, E/F/B rules | Trusted TypeScript parser; async forEach, loose equality | Parser/rules plus selected project semantic diagnostics |
| Changed required-argument compatibility | Explicit top-level `from module import name` calls | Explicit relative named imports to exported function declarations | Same, with optional/default parameters recognized |
| Context retrieval | Python AST resolved call graph + bounded lexical dependency hints | Compiler-resolved snapshot-local calls + bounded dependency hints | Same |
| Test-gap questions | Heuristic, not measured code coverage | Heuristic | Heuristic |
| Behavioral verification | Approved operator-owned Python oracles with Docker | Approved Node contract oracle with Docker | Trusted transpilation and Node contract oracle with Docker |

TypeScript uses a virtual project compiler host and selected argument/return/assignment/nullability diagnostics. Relative imports, re-exports and root tsconfig path aliases are supported within the snapshot. External dependency declarations, tsconfig extends/plugins, full framework compilation, arbitrary dynamic dispatch and general taint analysis are not supported. JavaScript semantic checkJs is disabled. Syntax parsing alone is not type checking. Compatibility detectors intentionally skip spread calls, dynamic imports and uncertain bindings. Review limitations and stage failures remain visible.

Install frontend dependencies (`npm ci`) as well as Python dependencies: the backend parser adapter uses the pinned project's TypeScript compiler library through Node. It never imports the target repository's JavaScript or ESLint configuration. Missing Node/compiler produces explicit failed coverage.

Parser results persist in implementation/content/compiler-version-addressed caches. The compiler host reads reviewed source from the immutable inventory and standard libraries only from the trusted TypeScript installation; it does not execute project configuration.
