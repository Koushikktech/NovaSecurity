# Narration for the silent checkout walkthrough

The silent video is a chapter walkthrough of saved real results, not a recording of live inference. Suggested narration, at your own pace:

**0–20 seconds — the change.** “This checkout used to work without a coupon. A pricing refactor makes the discount argument required, but checkout still supplies only the subtotal. One small change now prevents this customer from completing the order.”

**20–40 seconds — investigation.** “Proofline follows the change across files. The graph resolves the checkout caller to the changed pricing function. We can inspect the caller directly, rather than relying on a summary.”

**40–60 seconds — evidence.** “Static analysis and the model provide two observations of the same regression. The assessment links the claim to exact source quotations. Source support is useful, but we also want a test.”

**60–80 seconds — repair.** “The model proposes this one-line repair: a checkout without a coupon passes zero discount explicitly. This is the actual generated edit, and it changes only the cited caller.”

**80–100 seconds — verification.** “The same protected test runs against the original, changed and patched snapshots. The original passes. The change fails. The generated repair passes, while the explicit-discount happy path stays green. These checks really ran in isolated Docker containers.”

**100–120 seconds — system.** “Python orchestration combines source snapshots, deterministic checks, caller context, bounded investigation, source assessment and inspectable repair verification. We preserve partial results and expose what was not checked. This demonstration is one controlled end-to-end case, not a claim of universal accuracy.”

Before submission: add your introduction, team details and actual final video URL. Independent human evaluation and measured developer time savings are still unproven; do not claim them in narration.
