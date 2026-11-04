# Proofline — Beyond the happy path

120 seconds. Read naturally; headings are timing cues, not spoken text. Leave short pauses when a result changes. The film already contains subtle music, with space for your voice.

**0–12 · The promise**

Imagine you’ve just vibe-coded an expense app. The screen looks good. Search works. Saving seems fine. But a working interface doesn’t tell you whether the behavior underneath is safe.

**12–25 · The consequence**

In this example, Alice changes a search input and gets Bob’s private expense back. The normal search test passed. What failed was the boundary between one user’s data and another’s.

**25–33 · Introduce Proofline**

That’s where Proofline comes in: code analysis, AI investigation, and execution evidence, brought together in one review workflow.

**33–47 · Build the graph**

We organize the source into symbols and relationships. Here, the request reaches a route, then a service, then the expense repository. The graph view makes those boundaries visible, instead of leaving you to jump between files.

**47–64 · Investigate the risky path**

Follow the search input to the database query. It’s mixed into SQL instead of bound as data. Then follow the result back to Alice. Solid links show imports; dashed links need source assessment. The graph organizes the investigation. The test proves this particular leak.

**64–77 · Show another class of bug**

It also reviews correctness. This async loop starts the saves, but doesn’t wait for them. The caller can report “saved” while writes are still pending. A nice-looking success message can hide unfinished work.

**77–91 · Inspect actual repairs**

The model generated two repairs: bind the search values as parameters, and await all the save promises. These are small, reviewable edits. But we still need to check their behavior.

**91–106 · Show execution evidence**

We run the same protected contracts against three versions. The original passes. The changed version leaks data and returns too early. With the generated repairs, both contracts pass again. Normal search still works, too.

**106–113 · Show provenance**

The saved artifacts contain the review, source evidence, model-generated patches and actual test output. This is one controlled example you can inspect.

**113–120 · Close**

Build at AI speed. Review with understanding. Proofline.

---

This is an authored AI-assisted-development scenario, not a claim that a particular AI generated the original bugs. The app cards and graph are animated explanations, not captures of a live app session. The review and model patches are real recorded outputs. The graph distinguishes imports and source-assessed dynamic relationships; it is not complete interprocedural taint analysis. Execution uses local Python/SQLite and Node subprocesses, not Docker. Include the music credit from `UPLOAD-DESCRIPTION.md` when uploading.
