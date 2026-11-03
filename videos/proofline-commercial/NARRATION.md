# Proofline — narration for the 100-second hackathon film

Read the paragraphs aloud; the bold headings are timing cues. Speak conversationally, with short pauses on the three test outcomes. Music is already included in the main export.

**0–10 · A tiny change**

Someone removes a default value from a pricing function. Just two characters. Looks harmless. But it changes what the rest of the project needs to send.

**10–22 · A real consequence**

Now a customer without a coupon can’t finish checkout. The checkout code never changed. That’s the problem: a bug’s cause and consequence can live in different files.

**22–30 · Meet Proofline**

This is Proofline. It combines code analysis with AI investigation to follow a change beyond the diff.

**30–44 · Trace the caller**

First, we pin the source snapshot. Pricing now requires two arguments. Our caller analysis finds checkout still sending one. This graph connects the changed function to the code that uses it.

**44–54 · Inspect the evidence**

The warning includes exact source quotations and a separate assessment pass. You can check the reasoning. But that still doesn’t prove a fix works.

**54–66 · Inspect the repair**

The model proposes this small edit: pass zero discount when there’s no coupon. You inspect the patch. The tests stay outside the model’s control.

**66–80 · Run the same test**

We run the same protected checkout test against three versions. Original: passes. Changed: fails. Repaired: passes. The normal discount case still works. These are actual isolated test runs.

**80–90 · Show the working app**

Here’s that recorded result in the app: the evidence, generated patch and test results. This is one controlled example, with everything open to inspection.

**90–100 · Close**

Review a repository, pull request, commit or local folder. Proofline: understand the change, see what it breaks, and check the repair.

---

Recording notes:

- Rehearse against the export once. Start each paragraph near its cue; allow the result labels to land before saying the next one.
- This is an edited animated demonstration of a real recorded run. Do not describe it as an uninterrupted live review.
- Language depth differs. The Python case demonstrates the caller analysis and protected repair verification shown here; `docs/language-support.md` contains the support matrix.
- Use `proofline-hackathon-music.mp4` to retain the included music, or `proofline-hackathon-clean.mp4` to mix your own audio.
- Include the music attribution from `UPLOAD-DESCRIPTION.md` when uploading the music version.
